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

[[cells]]
task = "ce-07-mobility-result"
scenario = "all-errors-as-result"
"""
        )
        expanded = spec.expand()
        self.assertEqual(4, len(expanded))
        self.assertTrue(all(cell.provider == "chosen" for cell in expanded))
        self.assertEqual({1, 2}, {cell.repeat for cell in expanded})
        self.assertEqual(4, len({cell.cell_id for cell in expanded}))

    def test_model_cell_allowlist_limits_cartesian_expansion(self) -> None:
        spec = self._load(
            """
[experiment]
id = "selected-cells"
stage = "breadth"
proctor_model = "proctor"

[[models]]
provider = "chosen"
model = "model-a"
cells = ["ce-01-antidote-output/default"]

[[cells]]
task = "ce-01-antidote-output"

[[cells]]
task = "ce-02-horologia-overdue"
"""
        )
        self.assertEqual(
            ["chosen__model-a__ce-01-antidote-output__default__r01"],
            [cell.cell_id for cell in spec.expand()],
        )

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

    def test_loads_frozen_pricing(self) -> None:
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
"""
        )
        self.assertEqual("published-list", spec.models[0].pricing.basis)


if __name__ == "__main__":
    unittest.main()
