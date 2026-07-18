from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .agent import OPENCODE_VERSION, AgentRunner
from .engine import PodmanEngine
from .experiment import ExpandedCell, ExperimentSpec
from .providers import ProviderRoute
from .task import TaskSpec, discover_tasks


class MatrixError(RuntimeError):
    pass


class MatrixRunner:
    def __init__(
        self,
        repo_root: Path,
        engine: PodmanEngine,
        experiment: ExperimentSpec,
        routes: dict[tuple[str, str], ProviderRoute],
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.engine = engine
        self.experiment = experiment
        self.routes = routes
        self.root = self.repo_root / ".runs" / "experiments" / experiment.experiment_id
        self.results = self.root / "results"
        self.lock_path = self.root / "lock.json"
        self.tasks: dict[str, TaskSpec] = {
            task.task_id: task for task in discover_tasks(self.repo_root / "tasks")
        }

    def plan(self) -> dict:
        return {
            "experiment_id": self.experiment.experiment_id,
            "stage": self.experiment.stage,
            "manifest": str(self.experiment.path),
            "manifest_sha256": self.experiment.digest,
            "concurrency": self.experiment.concurrency,
            "infrastructure_retries": self.experiment.infrastructure_retries,
            "proctor_model": self.experiment.proctor_model,
            "routes": [self._redacted_route(route) for route in self.routes.values()],
            "model_configs": self._model_configs(),
            "cells": [asdict(cell) for cell in self.experiment.expand()],
        }

    def prepare_lock(self, task_ids: set[str] | None = None) -> dict:
        commit = self._signed_clean_commit()
        if self.lock_path.exists():
            lock = json.loads(self.lock_path.read_text())
            self._validate_lock(lock, commit)
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            self.results.mkdir(parents=True, exist_ok=True)
            lock = {
                "schema_version": 1,
                "experiment_id": self.experiment.experiment_id,
                "stage": self.experiment.stage,
                "created_at": datetime.now(UTC).isoformat(),
                "benchmark_commit": commit,
                "manifest_path": str(self.experiment.path.relative_to(self.repo_root)),
                "manifest_sha256": self.experiment.digest,
                "opencode_version": OPENCODE_VERSION,
                "proctor_model": self.experiment.proctor_model,
                "routes": [self._redacted_route(route) for route in self.routes.values()],
                "model_configs": self._model_configs(),
                "images": {},
                "cells": [asdict(cell) for cell in self.experiment.expand()],
            }

        required_task_ids = task_ids or {cell.task_id for cell in self.experiment.expand()}
        agent = AgentRunner(self.repo_root, self.engine)
        images = lock["images"]
        for task_id in sorted(required_task_ids - images.keys()):
            task = self.tasks[task_id]
            task_image_id = self.engine.build(task)
            agent_image = agent.build_agent_image(task)
            agent_image_id = self.engine.runner.run(
                ["podman", "image", "inspect", agent_image, "--format", "{{.Id}}"]
            ).stdout.strip()
            images[task_id] = {
                "task_image": self.engine.image_name(task),
                "task_image_id": task_image_id,
                "agent_image": agent_image,
                "agent_image_id": agent_image_id,
            }
        self.lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
        return lock

    def run(self, cell_id: str | None = None) -> dict:
        if os.environ.get("CAE_ALLOW_CANDIDATE_RUN") != "1":
            raise MatrixError(
                "matrix candidate runs are gated; set CAE_ALLOW_CANDIDATE_RUN=1 explicitly"
            )
        cells = self.experiment.expand()
        selected = list(cells)
        if cell_id is not None:
            selected = [cell for cell in cells if cell.cell_id == cell_id]
            if not selected:
                raise MatrixError(f"unknown matrix cell {cell_id!r}")
        lock = self.prepare_lock(task_ids={cell.task_id for cell in selected})
        self.results.mkdir(parents=True, exist_ok=True)
        positions = {cell.cell_id: index for index, cell in enumerate(cells, start=1)}
        for cell in selected:
            index = positions[cell.cell_id]
            path = self.results / f"{cell.cell_id}.json"
            existing = json.loads(path.read_text()) if path.exists() else None
            if existing and existing.get("state") in {"completed", "infrastructure_error"}:
                print(f"[MATRIX_SKIP] {index}/{len(lock['cells'])} cell={cell.cell_id}", flush=True)
                continue
            self._run_cell(cell, path, index, len(lock["cells"]))
        return self.status()

    def status(self) -> dict:
        cells = self.experiment.expand()
        records: dict[str, dict] = {}
        if self.results.exists():
            for path in self.results.glob("*.json"):
                records[path.stem] = json.loads(path.read_text())
        counts = {"pending": 0, "completed": 0, "infrastructure_error": 0}
        for cell in cells:
            state = records.get(cell.cell_id, {}).get("state", "pending")
            counts[state if state in counts else "pending"] += 1
        return {
            "experiment_id": self.experiment.experiment_id,
            "total": len(cells),
            **counts,
            "lock": str(self.lock_path) if self.lock_path.exists() else None,
        }

    def _run_cell(self, cell: ExpandedCell, path: Path, index: int, total: int) -> None:
        attempts: list[dict] = []
        maximum = 1 + self.experiment.infrastructure_retries
        for attempt in range(1, maximum + 1):
            print(
                f"[MATRIX_CELL] {index}/{total} cell={cell.cell_id} attempt={attempt}/{maximum}",
                flush=True,
            )
            try:
                result = AgentRunner(self.repo_root, self.engine).run(
                    self.tasks[cell.task_id],
                    self.routes[(cell.provider, cell.model)],
                    scenario=cell.scenario,
                    instruction_mode=cell.mode,
                    initial_clarification=cell.initial_clarification,
                )
                result_data = asdict(result)
                verification = result_data.get("verification")
                completion_status = result_data.get("agent_completion_status")
                infrastructure = (
                    bool(
                        isinstance(verification, dict)
                        and verification.get("outcome") == "infrastructure_error"
                    )
                    or completion_status != "completed"
                )
                attempts.append(
                    {
                        "attempt": attempt,
                        "kind": "infrastructure_error" if infrastructure else "completed",
                        "result": result_data,
                    }
                )
            except Exception as exc:
                infrastructure = True
                attempts.append(
                    {
                        "attempt": attempt,
                        "kind": "infrastructure_error",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
            state = "infrastructure_error" if infrastructure else "completed"
            record = {
                "schema_version": 1,
                "experiment_id": self.experiment.experiment_id,
                "cell": asdict(cell),
                "state": state,
                "attempts": attempts,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
            if not infrastructure:
                return
        print(f"[MATRIX_INFRASTRUCTURE_ERROR] cell={cell.cell_id}", flush=True)

    def _signed_clean_commit(self) -> str:
        status = self._git("status", "--porcelain")
        if status:
            raise MatrixError(
                "benchmark working tree must be clean before creating or using a lock"
            )
        commit = self._git("rev-parse", "HEAD")
        verification = subprocess.run(
            ["git", "verify-commit", commit],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
        )
        if verification.returncode:
            raise MatrixError(f"benchmark commit {commit} does not have a valid signature")
        return commit

    def _validate_lock(self, lock: dict, commit: str) -> None:
        if lock.get("manifest_sha256") != self.experiment.digest:
            raise MatrixError("experiment manifest changed after lock creation")
        if lock.get("benchmark_commit") != commit:
            raise MatrixError("benchmark commit changed after lock creation")
        expected_routes = [self._redacted_route(route) for route in self.routes.values()]
        if lock.get("routes") != expected_routes:
            raise MatrixError("provider routes changed after lock creation")
        if lock.get("model_configs") != self._model_configs():
            raise MatrixError("generated model configuration changed after lock creation")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo_root, text=True, capture_output=True, check=False
        )
        if result.returncode:
            raise MatrixError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout.strip()

    @staticmethod
    def _redacted_route(route: ProviderRoute) -> dict[str, str]:
        endpoint = urlsplit(route.base_url)
        return {
            "provider": route.provider,
            "model": route.model,
            "endpoint_host": endpoint.hostname or "",
            "api_key_env": route.api_key_env,
        }

    def _model_configs(self) -> list[dict]:
        configs: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for cell in self.experiment.expand():
            key = (cell.provider, cell.model, cell.mode)
            if key in seen:
                continue
            seen.add(key)
            route = self.routes[(cell.provider, cell.model)]
            configs.append(
                {
                    "provider": cell.provider,
                    "model": cell.model,
                    "mode": cell.mode,
                    "sha256": AgentRunner.opencode_config_sha256(route, cell.mode),
                    "config": AgentRunner.opencode_config(route, cell.mode),
                }
            )
        return configs
