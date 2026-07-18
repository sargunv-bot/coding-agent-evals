#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml


VARIANTS = {
    "linux-arm64-egl": "ubuntu-24.04-arm",
    "linux-arm64-vulkan": "ubuntu-24.04-arm",
    "linux-x64-egl": "ubuntu-latest",
    "linux-x64-vulkan": "ubuntu-latest",
    "macos-arm64-metal": "macos-latest",
    "macos-arm64-vulkan": "macos-latest",
    "macos-arm64-egl": "macos-latest",
    "ios-arm64-metal": "macos-latest",
    "ios-simulator-arm64-metal": "macos-latest",
    "windows-x64-vulkan": "windows-2022",
    "windows-x64-wgl": "windows-2022",
}


def expected_commands(variant: str) -> set[str]:
    ios = variant.startswith("ios-")
    macos_egl = variant == "macos-arm64-egl"
    commands = {"mise run configure", "mise run build" if ios else "mise run test"}
    if not ios and not macos_egl:
        commands |= {
            "mise run //bindings/java-ffm:build",
            "mise run //bindings/java-jni:build",
            "mise run //bindings/dotnet:test",
            "mise run //bindings/rust:ci",
            "mise run //examples/rust-map:ci",
            "mise run //examples/zig-map:build",
        }
    if not ios:
        commands |= {
            "mise run //bindings/zig:ci",
            "mise run //examples/zig-readback:run",
        }
    if variant in {"linux-x64-egl", "linux-x64-vulkan", "macos-arm64-metal", "macos-arm64-vulkan"}:
        commands.add("mise run //bindings/kotlin-native:build")
    if variant in {"macos-arm64-metal", "macos-arm64-vulkan"}:
        commands.add("mise run //bindings/swift:test")
    if "vulkan" in variant:
        commands.add("mise run //examples/lwjgl-map:build")
    if variant == "macos-arm64-metal":
        commands.add("mise run //examples/swift-map:build")
    return commands


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_generator(root: pathlib.Path) -> pathlib.Path:
    preferred = root / ".mise/tasks/ci/generate-workflow"
    if preferred.is_file():
        return preferred
    candidates = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("test_"):
            continue
        relative = path.relative_to(root)
        if path.suffix not in {"", ".py", ".sh"} or ".git" in relative.parts:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        if ".github" in text and "ci.yml" in text and "manifest" in lowered:
            candidates.append(path)
    if len(candidates) != 1:
        raise AssertionError(f"expected one discoverable workflow generator, got {candidates}")
    return candidates[0]


def generator_commands(generator: pathlib.Path) -> tuple[list[str], list[str]]:
    text = generator.read_text()
    base = [sys.executable, str(generator)]
    if 'add_parser("generate"' in text and 'add_parser("check"' in text:
        return base + ["generate"], base + ["check"]
    if "--check" in text:
        return base, base + ["--check"]
    if "--validate" in text:
        return base, base + ["--validate"]
    raise AssertionError("generator has no discoverable non-mutating drift-check mode")


def run(command: list[str], *, cwd: pathlib.Path, expect_success: bool) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
    )
    if (result.returncode == 0) != expect_success:
        raise AssertionError(
            f"generator {command[2:]} returned {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def enabled(step: dict[str, object], matrix: dict[str, object]) -> bool:
    condition = step.get("if")
    if condition is None:
        return True
    if not isinstance(condition, str):
        raise AssertionError(f"unsupported step condition: {condition!r}")
    prefix = "${{ matrix."
    if condition.startswith(prefix) and condition.endswith(" }}"):
        key = condition[len(prefix) : -3].strip()
        value = matrix.get(key)
        assert isinstance(value, bool), (key, value)
        return value
    membership = re.fullmatch(
        r"\$\{\{\s*contains\(matrix\.([A-Za-z_][A-Za-z0-9_]*),\s*(['\"])([^'\"]+)\2\)\s*}}",
        condition,
    )
    if membership:
        key, _, item = membership.groups()
        value = matrix.get(key)
        assert isinstance(value, list) and all(isinstance(entry, str) for entry in value), (
            key,
            value,
        )
        return item in value
    raise AssertionError(f"generated variant step retains procedural condition: {condition}")


def workflow_policy(document: dict[str, object]) -> dict[str, tuple[str, set[str]]]:
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    if "variants" in jobs:
        job = jobs["variants"]
        assert isinstance(job, dict)
        strategy = job["strategy"]
        assert isinstance(strategy, dict)
        matrix = strategy["matrix"]
        assert isinstance(matrix, dict)
        rows = matrix["include"]
        assert isinstance(rows, list)
        policy = {}
        for row in rows:
            assert isinstance(row, dict)
            variant = row["mise_env"]
            runner = row["runner"]
            assert isinstance(variant, str) and isinstance(runner, str)
            commands = {
                command
                for step in job["steps"]
                if isinstance(step, dict) and enabled(step, row)
                if isinstance(command := step.get("run"), str)
            }
            policy[variant] = (runner, commands)
        return policy

    if all(f"variant-{variant}" in jobs for variant in VARIANTS):
        policy = {}
        for variant in VARIANTS:
            job = jobs[f"variant-{variant}"]
            assert isinstance(job, dict)
            runner = job["runs-on"]
            assert isinstance(runner, str)
            commands = {
                command
                for step in job["steps"]
                if isinstance(step, dict)
                if isinstance(command := step.get("run"), str)
            }
            policy[variant] = (runner, commands)
        return policy

    # A generator may organize equivalent policy by feature rather than by
    # target. Aggregate every matrix row back into its target's command set.
    aggregate: dict[str, tuple[str, set[str]]] = {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        strategy = job.get("strategy")
        if not isinstance(strategy, dict):
            continue
        matrix = strategy.get("matrix")
        if not isinstance(matrix, dict):
            continue
        rows = matrix.get("include")
        if not isinstance(rows, list):
            continue
        commands = {
            command
            for step in job.get("steps", [])
            if isinstance(step, dict)
            if isinstance(command := step.get("run"), str)
        }
        for row in rows:
            assert isinstance(row, dict)
            variant = row.get("mise_env")
            runner = row.get("runner")
            assert isinstance(variant, str) and isinstance(runner, str)
            if variant in aggregate:
                previous_runner, previous_commands = aggregate[variant]
                assert previous_runner == runner, (variant, previous_runner, runner)
                previous_commands.update(commands)
            else:
                aggregate[variant] = (runner, set(commands))
    return aggregate


def validate_workflow(root: pathlib.Path) -> None:
    document = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    assert document["name"] == "CI"
    assert document["permissions"] == {"contents": "read"}
    assert "concurrency" in document
    jobs = document["jobs"]
    required = jobs["required"]
    assert required["if"] == "${{ always() }}"
    assert set(required["needs"]) == set(jobs) - {"required"}
    assert required["name"] == "ci-required"
    for job in jobs.values():
        for step in job.get("steps", []):
            action = step.get("uses")
            if action and action.startswith("actions/"):
                version = action.rsplit("@", 1)[-1]
                assert len(version) == 40 and all(char in "0123456789abcdef" for char in version), action

    policy = workflow_policy(document)
    assert set(policy) == set(VARIANTS), policy.keys()
    for variant, runner in VARIANTS.items():
        actual_runner, commands = policy[variant]
        assert actual_runner == runner, (variant, actual_runner, runner)
        assert commands == expected_commands(variant), (
            variant,
            sorted(commands - expected_commands(variant)),
            sorted(expected_commands(variant) - commands),
        )


def main() -> None:
    source = pathlib.Path("/app")
    with tempfile.TemporaryDirectory() as directory:
        fixture = pathlib.Path(directory) / "repo"
        shutil.copytree(source, fixture, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        generator = find_generator(fixture)
        generate, check = generator_commands(generator)
        workflow = fixture / ".github/workflows/ci.yml"

        before = digest(workflow)
        run(check, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "check modified the checked-in workflow"
        run(generate, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "checked-in workflow is not canonical"
        run(generate, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "generation is nondeterministic"
        validate_workflow(fixture)

        text = workflow.read_text()
        assert "mise run test" in text
        workflow.write_text(text.replace("mise run test", "mise run test-drift", 1))
        drifted = digest(workflow)
        run(check, cwd=fixture, expect_success=False)
        assert digest(workflow) == drifted, "failed check mutated the workflow"
        run(generate, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "generation did not repair workflow drift"
        validate_workflow(fixture)


if __name__ == "__main__":
    main()