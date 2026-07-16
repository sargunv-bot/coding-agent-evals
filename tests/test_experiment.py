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

    def test_full_info_requires_actual_initial_information(self) -> None:
        with self.assertRaisesRegex(ExperimentValidationError, "requires a scenario or"):
            self._load(
                """
[experiment]
id = "empty-full-info"
stage = "diagnostic"
proctor_model = "proctor"

[[models]]
provider = "chosen"
model = "model-a"

[[cells]]
task = "ce-01-antidote-output"
mode = "full_info"
"""
            )

    def test_loads_frozen_pricing_and_initial_clarification(self) -> None:
        spec = self._load(
            """
[experiment]
id = "priced-full-info"
stage = "diagnostic"
proctor_model = "proctor"

[[models]]
provider = "chosen"
model = "model-a"

[models.pricing]
basis = "published-list"
currency = "USD"
input_per_million = 1
cached_input_per_million = 0.1
output_per_million = 2
reasoning_per_million = 2

[[cells]]
task = "ce-01-antidote-output"
mode = "full_info"
initial_clarification = "Apply the behavior to clone and update paths."
"""
        )
        self.assertEqual("published-list", spec.models[0].pricing.basis)
        self.assertEqual(
            "Apply the behavior to clone and update paths.",
            spec.expand()[0].initial_clarification,
        )


if __name__ == "__main__":
    unittest.main()
