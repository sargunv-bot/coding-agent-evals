#!/opt/venv/bin/python
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import tomllib

import yaml


def run(generator: pathlib.Path, *args: str, cwd: pathlib.Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(generator), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
    )
    if (result.returncode == 0) != (expect == 0):
        raise AssertionError(
            f"generator {' '.join(args)} returned {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_generator(root: pathlib.Path) -> pathlib.Path:
    preferred = root / ".mise/tasks/ci/generate-workflow"
    if preferred.is_file():
        return preferred
    candidates = [
        path
        for base in (root / ".mise/tasks", root / "scripts", root / "ci")
        if base.is_dir()
        for path in base.rglob("*")
        if path.is_file() and "workflow" in path.name.lower()
    ]
    if len(candidates) != 1:
        raise AssertionError(f"expected one discoverable workflow generator, got {candidates}")
    return candidates[0]


def validate_workflow(root: pathlib.Path) -> None:
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    assert workflow["name"] == "CI"
    assert workflow["permissions"] == {"contents": "read"}
    assert "concurrency" in workflow
    jobs = workflow["jobs"]
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
    variants = tomllib.loads((root / "ci/variants.toml").read_text())["variants"]
    assert {f"variant-{name}" for name in variants} <= set(jobs)


def main() -> None:
    source = pathlib.Path("/app")
    generator = find_generator(source)
    workflow = source / ".github/workflows/ci.yml"
    before = digest(workflow)
    run(generator, "--check", cwd=source)
    assert digest(workflow) == before, "--check modified the checked-in workflow"
    run(generator, cwd=source)
    assert digest(workflow) == before, "checked-in workflow is not canonical"
    run(generator, cwd=source)
    assert digest(workflow) == before, "generation is nondeterministic"
    validate_workflow(source)

    with tempfile.TemporaryDirectory() as directory:
        fixture = pathlib.Path(directory) / "repo"
        shutil.copytree(source, fixture, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        fixture_generator = fixture / generator.relative_to(source)
        fixture_workflow = fixture / ".github/workflows/ci.yml"
        original = digest(fixture_workflow)
        extra = fixture / "ci/subprojects/hidden-probe.toml"
        extra.write_text(
            '[requires]\nos = ["linux"]\narch = ["x64"]\nbackend = ["vulkan"]\n\n'
            '[ci]\nbuild = "//hidden/probe:build"\n'
        )
        run(fixture_generator, "--check", cwd=fixture, expect=1)
        assert digest(fixture_workflow) == original, "failed --check mutated workflow"
        run(fixture_generator, cwd=fixture)
        changed = fixture_workflow.read_text()
        assert "mise run //hidden/probe:build" in changed
        parsed = yaml.safe_load(changed)
        containing = [
            job_id
            for job_id, job in parsed["jobs"].items()
            if any(step.get("run") == "mise run //hidden/probe:build" for step in job.get("steps", []))
        ]
        assert containing == ["variant-linux-x64-vulkan"], containing
        stable = digest(fixture_workflow)
        run(fixture_generator, cwd=fixture)
        assert digest(fixture_workflow) == stable

        extra.write_text(extra.read_text() + 'unknown_field = "rejected"\n')
        failure = run(fixture_generator, cwd=fixture, expect=1)
        assert "unknown_field" in failure.stderr or "unknown_field" in failure.stdout


if __name__ == "__main__":
    main()
