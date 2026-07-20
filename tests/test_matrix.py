from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_evals.agent import AgentRunResult, AgentUsage
from agent_evals.engine import PodmanEngine
from agent_evals.experiment import CellSpec, ExperimentSpec, ModelSpec
from agent_evals.matrix import MatrixError, MatrixRunner
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
            cells=(CellSpec("ce-01-antidote-output", None),),
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
        self.assertEqual(1, len(plan["model_configs"]))
        self.assertEqual(64, len(plan["model_configs"][0]["sha256"]))
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
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            duration_seconds=1.0,
            agent_exit_code=1,
            agent_completion_status="completed",
            agent_exit_discrepancy=True,
            model_config_sha256="abc",
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

    @patch.dict("os.environ", {"CAE_ALLOW_CANDIDATE_RUN": "1"}, clear=False)
    def test_incomplete_agent_turn_is_retried_and_quarantined_as_infrastructure(self) -> None:
        cell = self.experiment.expand()[0]
        result = AgentRunResult(
            run_id="run-incomplete",
            task_id=cell.task_id,
            scenario=None,
            provider=cell.provider,
            model=cell.model,
            endpoint_host="chosen.invalid",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            duration_seconds=1.0,
            agent_exit_code=0,
            agent_completion_status="incomplete",
            agent_exit_discrepancy=True,
            model_config_sha256="abc",
            patch_path="patch",
            trajectory_path="trajectory",
            usage=AgentUsage(input_tokens=10, output_tokens=2),
            verification={"outcome": "passed", "reward": {"reward": 1}},
        )
        lock = {"cells": self.runner.plan()["cells"]}
        with (
            patch.object(self.runner, "prepare_lock", return_value=lock),
            patch("agent_evals.matrix.AgentRunner.run", return_value=result) as run,
        ):
            status = self.runner.run()
        self.assertEqual(2, run.call_count)
        self.assertEqual(1, status["infrastructure_error"])
        record = next(self.runner.results.glob("*.json")).read_text()
        self.assertIn('"state": "infrastructure_error"', record)
        self.assertEqual(2, record.count('"kind": "infrastructure_error"'))

    @patch.dict("os.environ", {"CAE_ALLOW_CANDIDATE_RUN": "1"}, clear=False)
    def test_exact_cell_selection_runs_only_selected_task(self) -> None:
        experiment = replace(
            self.experiment,
            cells=(
                CellSpec("ce-01-antidote-output", None),
                CellSpec("ce-02-horologia-overdue", None),
            ),
        )
        runner = MatrixRunner(self.repo_root, self.runner.engine, experiment, self.runner.routes)
        runner.root = self.runner.root
        runner.results = self.runner.results
        runner.lock_path = self.runner.lock_path
        selected = experiment.expand()[1]
        result = AgentRunResult(
            run_id="run-selected",
            task_id=selected.task_id,
            scenario=None,
            provider=selected.provider,
            model=selected.model,
            endpoint_host="chosen.invalid",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            duration_seconds=1.0,
            agent_exit_code=0,
            agent_completion_status="completed",
            agent_exit_discrepancy=False,
            model_config_sha256="abc",
            patch_path="patch",
            trajectory_path="trajectory",
            usage=AgentUsage(input_tokens=10, output_tokens=2),
            verification={"outcome": "passed", "reward": {"reward": 1}},
        )
        lock = {"cells": runner.plan()["cells"]}
        with (
            patch.object(runner, "prepare_lock", return_value=lock) as prepare,
            patch("agent_evals.matrix.AgentRunner.run", return_value=result) as run,
        ):
            status = runner.run(cell_id=selected.cell_id)
        prepare.assert_called_once_with(task_ids={selected.task_id})
        run.assert_called_once()
        self.assertEqual(1, status["completed"])
        self.assertEqual(1, status["pending"])
        self.assertEqual(
            [f"{selected.cell_id}.json"],
            [path.name for path in runner.results.iterdir()],
        )

    @patch.dict("os.environ", {"CAE_ALLOW_CANDIDATE_RUN": "1"}, clear=False)
    def test_unknown_cell_is_rejected_before_lock_or_build(self) -> None:
        with (
            patch.object(self.runner, "prepare_lock") as prepare,
            self.assertRaisesRegex(MatrixError, "unknown matrix cell"),
        ):
            self.runner.run(cell_id="does-not-exist")
        prepare.assert_not_called()

    def test_partial_lock_builds_only_requested_tasks_and_appends_later(self) -> None:
        experiment = replace(
            self.experiment,
            path=self.repo_root / "experiments/real-models-v1-stage-b.toml",
            cells=(
                CellSpec("ce-01-antidote-output", None),
                CellSpec("ce-02-horologia-overdue", None),
            ),
        )
        runner = MatrixRunner(self.repo_root, self.runner.engine, experiment, self.runner.routes)
        runner.root = self.runner.root
        runner.results = self.runner.results
        runner.lock_path = self.runner.lock_path
        with (
            patch.object(runner, "_signed_clean_commit", return_value="a" * 40),
            patch.object(runner.engine, "build", return_value="task-image-id") as build,
            patch(
                "agent_evals.matrix.AgentRunner.build_agent_image",
                return_value="localhost/agent:dev",
            ) as build_agent,
            patch.object(
                runner.engine.runner,
                "run",
                return_value=SimpleNamespace(stdout="agent-image-id\n"),
            ),
        ):
            first = runner.prepare_lock(task_ids={"ce-02-horologia-overdue"})
            second = runner.prepare_lock(task_ids={"ce-01-antidote-output"})
        self.assertEqual({"ce-02-horologia-overdue"}, set(first["images"]))
        self.assertEqual(
            {"ce-01-antidote-output", "ce-02-horologia-overdue"},
            set(second["images"]),
        )
        self.assertEqual(2, build.call_count)
        self.assertEqual(2, build_agent.call_count)


if __name__ == "__main__":
    unittest.main()
