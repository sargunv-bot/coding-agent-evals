from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

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


def test_discovers_json_manifest_generator_and_validate_mode(tmp_path: Path) -> None:
    generator = tmp_path / ".github" / "tools" / "generate-ci-workflow.py"
    generator.parent.mkdir(parents=True)
    generator.write_text(
        "# Generate .github/workflows/ci.yml from the JSON manifest.\n"
        "parser.add_argument('--validate')\n"
    )

    assert VERIFIER.find_generator(tmp_path) == generator
    generate, check = VERIFIER.generator_commands(generator)
    assert generate[-1] == str(generator)
    assert check[-1] == "--validate"


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