from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_evals.experiment import ExperimentSpec, ExperimentValidationError


class ExperimentSpecTest(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def providers(self) -> dict:
        return {
            "chosen": {
                "base_url": "https://chosen.invalid/v1",
                "api_key_env": "CHOSEN_KEY",
                "models": ["model-a", "model-b"],
            },
            "other": {
                "base_url": "https://other.invalid/v1",
                "api_key_env": "OTHER_KEY",
                "models": ["model-a"],
            },
        }

    def _load(self, content: str) -> ExperimentSpec:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "experiment.toml"
        path.write_text(content)
        return ExperimentSpec.load(path, self.repo_root, self.providers)

    def test_expands_explicit_provider_task_and_repeat_cells(self) -> None:
        spec = self._load(
            """
[experiment]
id = "stage-a"
stage = "smoke"
repeats = 2
concurrency = 1
infrastructure_retries = 1
proctor_model = "sota-proctor"

[[models]]
provider = "chosen"
model = "model-a"

[[cells]]
task = "ce-01-antidote-output"
mode = "ask_user"

[[cells]]
task = "ce-07-mobility-result"
scenario = "all-errors-as-result"
mode = "ask_user"
"""
        )
        expanded = spec.expand()
        self.assertEqual(4, len(expanded))
        self.assertTrue(all(cell.provider == "chosen" for cell in expanded))
        self.assertEqual({1, 2}, {cell.repeat for cell in expanded})
        self.assertEqual(4, len({cell.cell_id for cell in expanded}))

    def test_rejects_model_not_declared_by_selected_provider(self) -> None:
        with self.assertRaisesRegex(ExperimentValidationError, "not configured for provider"):
            self._load(
                """
[experiment]
id = "bad-route"
stage = "smoke"
proctor_model = "proctor"

[[models]]
provider = "other"
model = "model-b"

[[cells]]
task = "ce-01-antidote-output"
"""
            )

    def test_requires_scenario_for_scenario_task(self) -> None:
        with self.assertRaisesRegex(ExperimentValidationError, "requires an explicit scenario"):
            self._load(
                """
[experiment]
id = "missing-scenario"
stage = "smoke"
proctor_model = "proctor"

[[models]]
provider = "chosen"
model = "model-a"

[[cells]]
task = "ce-07-mobility-result"
"""
            )


if __name__ == "__main__":
    unittest.main()
