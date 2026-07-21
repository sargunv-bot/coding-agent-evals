#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
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

GENERATE_COMMAND = ["mise", "run", "ci:generate-workflow"]
CHECK_COMMAND = [*GENERATE_COMMAND, "--", "--check"]


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


def run(command: list[str], *, cwd: pathlib.Path, expect_success: bool) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        env=os.environ
        | {
            "PYTHONDONTWRITEBYTECODE": "1",
            "MISE_AUTO_INSTALL": "0",
            "MISE_TRUSTED_CONFIG_PATHS": str(cwd),
        },
    )
    if (result.returncode == 0) != expect_success:
        raise AssertionError(
            f"generator {command[2:]} returned {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def candidate_manifest_paths(source: pathlib.Path) -> list[pathlib.Path]:
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", "HEAD"],
        cwd=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    ignored = {"mise.toml", "mise.lock", "pyproject.toml", "uv.lock"}
    return [
        pathlib.Path(line)
        for line in sorted(set(changed + untracked))
        if pathlib.Path(line).suffix in {".toml", ".json", ".yaml", ".yml"}
        and pathlib.Path(line).as_posix() not in ignored
        and not pathlib.Path(line).as_posix().startswith(".github/workflows/")
        and not pathlib.Path(line).as_posix().startswith(".github/actions/")
    ]


def malformed_bytes(path: pathlib.Path, original: bytes) -> bytes:
    if path.suffix == ".toml":
        return original + b"\n[[[\n"
    if path.suffix == ".json":
        return original + b"{\n"
    return original + b"\n: invalid\n"


def assert_required_inputs_reject_malformed(source: pathlib.Path, fixture: pathlib.Path, canonical: str) -> None:
    workflow = fixture / ".github/workflows/ci.yml"
    dependencies: list[pathlib.Path] = []
    for relative in candidate_manifest_paths(source):
        path = fixture / relative
        if not path.is_file():
            continue
        original = path.read_bytes()
        path.unlink()
        result = subprocess.run(GENERATE_COMMAND, cwd=fixture, text=True, capture_output=True)
        changed = workflow.is_file() and workflow.read_text() != canonical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
        run(GENERATE_COMMAND, cwd=fixture, expect_success=True)
        if result.returncode != 0 or changed:
            dependencies.append(relative)

    assert dependencies, "no candidate manifest was behaviorally connected to workflow generation"
    for relative in dependencies:
        path = fixture / relative
        original = path.read_bytes()
        path.write_bytes(malformed_bytes(path, original))
        run(GENERATE_COMMAND, cwd=fixture, expect_success=False)
        path.write_bytes(original)
        run(GENERATE_COMMAND, cwd=fixture, expect_success=True)
        assert workflow.read_text() == canonical


def evaluate_expression(expression: str, context: dict[str, object]) -> bool:
    result = subprocess.run(
        ["node", "/opt/gha-expressions/evaluate_expression.mjs"],
        input=json.dumps({"expression": expression, "context": context}),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"invalid GitHub Actions expression {expression!r}: {result.stderr.strip()}")
    response = json.loads(result.stdout)
    assert isinstance(response.get("enabled"), bool), response
    return response["enabled"]


def enabled(step: dict[str, object], matrix: dict[str, object]) -> bool:
    condition = step.get("if")
    if condition is None:
        return True
    if not isinstance(condition, str):
        raise AssertionError(f"unsupported step condition: {condition!r}")
    return evaluate_expression(condition, {"matrix": matrix})


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
        workflow = fixture / ".github/workflows/ci.yml"

        before = digest(workflow)
        run(CHECK_COMMAND, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "check modified the checked-in workflow"
        run(GENERATE_COMMAND, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "checked-in workflow is not canonical"
        run(GENERATE_COMMAND, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "generation is nondeterministic"
        validate_workflow(fixture)
        assert_required_inputs_reject_malformed(source, fixture, workflow.read_text())

        text = workflow.read_text()
        assert "mise run test" in text
        workflow.write_text(text.replace("mise run test", "mise run test-drift", 1))
        drifted = digest(workflow)
        run(CHECK_COMMAND, cwd=fixture, expect_success=False)
        assert digest(workflow) == drifted, "failed check mutated the workflow"
        run(GENERATE_COMMAND, cwd=fixture, expect_success=True)
        assert digest(workflow) == before, "generation did not repair workflow drift"
        validate_workflow(fixture)


if __name__ == "__main__":
    main()