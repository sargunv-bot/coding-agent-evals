from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

VERIFIER_PATH = (
    Path(__file__).parents[1]
    / "tasks"
    / "ce-06-maplibre-ffi-ci"
    / "tests"
    / "verify_workflow.py"
)
SPEC = importlib.util.spec_from_file_location("ce06_verify_workflow", VERIFIER_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
sys.modules.setdefault("yaml", ModuleType("yaml"))
SPEC.loader.exec_module(VERIFIER)


def test_uses_declared_contributor_commands() -> None:
    assert VERIFIER.GENERATE_COMMAND == ["mise", "run", "ci:generate-workflow"]
    assert VERIFIER.CHECK_COMMAND == [
        "mise",
        "run",
        "ci:generate-workflow",
        "--",
        "--check",
    ]


def test_discovers_candidate_policy_manifests_without_assuming_paths() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@invalid"], cwd=root, check=True)
        (root / "mise.toml").write_text("[tasks]\n")
        (root / "README.md").write_text("base\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)

        (root / "mise.toml").write_text("[tasks]\nci = 'generate'\n")
        manifest = root / "policy" / "targets.json"
        manifest.parent.mkdir()
        manifest.write_text('{"targets": []}\n')

        assert VERIFIER.candidate_manifest_paths(root) == [Path("policy/targets.json")]


def test_aggregates_feature_matrices_into_target_policy() -> None:
    document = {
        "jobs": {
            "build": {
                "strategy": {
                    "matrix": {
                        "include": [
                            {"mise_env": "linux-x64-vulkan", "runner": "ubuntu-latest"}
                        ]
                    }
                },
                "steps": [{"run": "mise run configure"}, {"run": "mise run test"}],
            },
            "rust": {
                "strategy": {
                    "matrix": {
                        "include": [
                            {"mise_env": "linux-x64-vulkan", "runner": "ubuntu-latest"}
                        ]
                    }
                },
                "steps": [{"run": "mise run //bindings/rust:ci"}],
            },
        }
    }

    assert VERIFIER.workflow_policy(document) == {
        "linux-x64-vulkan": (
            "ubuntu-latest",
            {"mise run configure", "mise run test", "mise run //bindings/rust:ci"},
        )
    }


def test_enabled_delegates_expression_and_matrix_context() -> None:
    expression = (
        "${{ contains(fromJSON('[\"linux-x64-vulkan\"]'), matrix.mise_env) }}"
    )
    row = {"mise_env": "linux-x64-vulkan"}
    with patch.object(VERIFIER, "evaluate_expression", return_value=True) as evaluate:
        assert VERIFIER.enabled({"if": expression}, row)
    evaluate.assert_called_once_with(expression, {"matrix": row})


def test_unconditional_step_is_enabled_without_expression_evaluation() -> None:
    with patch.object(VERIFIER, "evaluate_expression") as evaluate:
        assert VERIFIER.enabled({}, {"mise_env": "linux-x64-vulkan"})
    evaluate.assert_not_called()


def test_expression_evaluator_uses_official_helper_protocol() -> None:
    completed = subprocess.CompletedProcess(
        args=["node"], returncode=0, stdout='{"enabled":true}\n', stderr=""
    )
    with patch.object(VERIFIER.subprocess, "run", return_value=completed) as run:
        assert VERIFIER.evaluate_expression("${{ matrix.enabled }}", {"matrix": {"enabled": True}})

    assert run.call_args.args[0] == ["node", "/opt/gha-expressions/evaluate_expression.mjs"]
    request = json.loads(run.call_args.kwargs["input"])
    assert request == {
        "expression": "${{ matrix.enabled }}",
        "context": {"matrix": {"enabled": True}},
    }


def test_expression_evaluator_rejects_parser_errors() -> None:
    completed = subprocess.CompletedProcess(
        args=["node"], returncode=1, stdout="", stderr="Unexpected symbol"
    )
    with patch.object(VERIFIER.subprocess, "run", return_value=completed):
        try:
            VERIFIER.evaluate_expression("${{ invalid( }}", {"matrix": {}})
        except AssertionError as error:
            assert "Unexpected symbol" in str(error)
        else:
            raise AssertionError("invalid expression was accepted")
