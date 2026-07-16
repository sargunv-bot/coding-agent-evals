from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_evals.agent import AgentRunResult, AgentUsage
from agent_evals.engine import PodmanEngine
from agent_evals.experiment import CellSpec, ExperimentSpec, ModelSpec
from agent_evals.matrix import MatrixRunner
from agent_evals.providers import ProviderRoute


class MatrixRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        manifest = Path(self.temp.name) / "stage-a.toml"
        manifest.write_text("fixture")
        self.experiment = ExperimentSpec(
            path=manifest,
            experiment_id="unit-stage-a",
            description="test",
            stage="smoke",
            repeats=1,
            concurrency=1,
            infrastructure_retries=1,
            proctor_model="proctor",
            models=(ModelSpec("chosen", "model-a"),),
            cells=(CellSpec("ce-01-antidote-output", None, "ask_user"),),
        )
        route = ProviderRoute("chosen", "model-a", "https://chosen.invalid/v1", "KEY")
        self.runner = MatrixRunner(
            self.repo_root,
            PodmanEngine(self.repo_root),
            self.experiment,
            {("chosen", "model-a"): route},
        )
        self.runner.root = Path(self.temp.name) / "runs"
        self.runner.results = self.runner.root / "results"
        self.runner.lock_path = self.runner.root / "lock.json"

    def test_plan_contains_only_explicit_route_and_stable_cell(self) -> None:
        plan = self.runner.plan()
        self.assertEqual(1, len(plan["routes"]))
        self.assertEqual("chosen", plan["routes"][0]["provider"])
        self.assertNotIn("base_url", plan["routes"][0])
        self.assertEqual(1, len(plan["cells"]))
        self.assertIn("chosen__model-a", plan["cells"][0]["cell_id"])

    @patch.dict("os.environ", {"CAE_ALLOW_CANDIDATE_RUN": "1"}, clear=False)
    def test_completed_cell_is_not_retried_or_rerun(self) -> None:
        cell = self.experiment.expand()[0]
        result = AgentRunResult(
            run_id="run-1",
            task_id=cell.task_id,
            scenario=None,
            provider=cell.provider,
            model=cell.model,
            endpoint_host="chosen.invalid",
            instruction_mode=cell.mode,
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            duration_seconds=1.0,
            agent_exit_code=1,
            patch_path="patch",
            trajectory_path="trajectory",
            usage=AgentUsage(input_tokens=10, output_tokens=2),
            verification={"outcome": "failed", "reward": {"reward": 0}},
        )
        lock = {"cells": [plan_cell for plan_cell in self.runner.plan()["cells"]]}
        with (
            patch.object(self.runner, "prepare_lock", return_value=lock),
            patch("agent_evals.matrix.AgentRunner.run", return_value=result) as run,
        ):
            first = self.runner.run()
            second = self.runner.run()
        self.assertEqual(1, run.call_count)
        self.assertEqual(1, first["completed"])
        self.assertEqual(first, second)
        record = next(self.runner.results.glob("*.json")).read_text()
        self.assertIn('"state": "completed"', record)
        self.assertIn('"input_tokens": 10', record)


if __name__ == "__main__":
    unittest.main()
