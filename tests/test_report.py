from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.experiment import CellSpec, ExperimentSpec, ModelSpec, PricingSpec
from agent_evals.report import write_experiment_report


class ExperimentReportTest(unittest.TestCase):
    def test_reports_completed_results_without_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "experiment.toml"
            manifest.write_text("manifest")
            experiment = ExperimentSpec(
                path=manifest,
                experiment_id="report-test",
                description="",
                stage="smoke",
                repeats=1,
                concurrency=1,
                infrastructure_retries=1,
                proctor_model="proctor",
                models=(
                    ModelSpec(
                        "chosen",
                        "model",
                        PricingSpec(
                            basis="operator-test-rates",
                            currency="USD",
                            input_per_million=1.0,
                            cached_input_per_million=0.5,
                            output_per_million=2.0,
                            reasoning_per_million=3.0,
                        ),
                    ),
                ),
                cells=(CellSpec("task", None),),
            )
            cell = experiment.expand()[0]
            results = root / ".runs" / "experiments" / experiment.experiment_id / "results"
            results.mkdir(parents=True)
            record = {
                "cell": cell.__dict__,
                "state": "completed",
                "attempts": [
                    {
                        "attempt": 1,
                        "kind": "completed",
                        "result": {
                            "run_id": "run-1",
                            "agent_exit_code": 0,
                            "duration_seconds": 12.5,
                            "usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 60,
                                "output_tokens": 20,
                                "reasoning_tokens": 3,
                                "provider_reported_cost": 0.01,
                            },
                            "verification": {"outcome": "passed"},
                        },
                    }
                ],
            }
            (results / f"{cell.cell_id}.json").write_text(json.dumps(record))
            infrastructure_record = {
                "cell": {**cell.__dict__, "cell_id": "infrastructure-cell"},
                "state": "infrastructure_error",
                "attempts": [
                    {
                        "attempt": 1,
                        "kind": "infrastructure_error",
                        "error_type": "RuntimeError",
                        "error": "provider unavailable",
                    }
                ],
            }
            (results / "infrastructure-cell.json").write_text(json.dumps(infrastructure_record))
            output = root / "report"
            payload = write_experiment_report(root, experiment, output)
            self.assertEqual(100, payload["totals"]["input_tokens"])
            self.assertEqual(60, payload["totals"]["cached_input_tokens"])
            self.assertEqual(20, payload["totals"]["output_tokens"])
            self.assertEqual(1, payload["totals"]["deterministic_passes"])
            self.assertEqual(1, payload["totals"]["cells"])
            self.assertNotIn("infrastructure_errors", payload["totals"])
            self.assertNotIn("infrastructure-cell", {row["cell_id"] for row in payload["rows"]})
            self.assertEqual(0.000179, payload["totals"]["estimated_cost"])
            self.assertEqual("operator-test-rates", payload["rows"][0]["pricing_basis"])
            self.assertNotIn(b"\r\n", (output / "results.csv").read_bytes())
            report = (output / "results.json").read_text()
            self.assertNotIn(directory, report)
            self.assertTrue((output / "results.csv").is_file())
            self.assertTrue((output / "summary.md").is_file())
            self.assertIn(
                "| chosen | model | task | — | yes |",
                (output / "summary.md").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
