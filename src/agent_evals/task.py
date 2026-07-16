from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{40}$")


class TaskValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Resources:
    cpus: int
    memory_mb: int
    storage_mb: int


@dataclass(frozen=True)
class ScenarioSpec:
    root: Path
    scenario_id: str
    track: str
    gold_patch: Path
    answer: str
    full_info_addendum: str

    @classmethod
    def load(cls, root: Path, task_root: Path) -> ScenarioSpec:
        data = tomllib.loads((root / "scenario.toml").read_text())
        gold = (root / data["gold_patch"]).resolve()
        if task_root.resolve() not in gold.parents:
            raise TaskValidationError(f"scenario gold patch escapes task root: {gold}")
        return cls(
            root=root.resolve(),
            scenario_id=str(data["scenario_id"]),
            track=str(data["track"]),
            gold_patch=gold,
            answer=str(data["interaction"]["answer"]),
            full_info_addendum=str(data["full_info"]["addendum"]),
        )

    @property
    def tests(self) -> Path:
        return self.root / "tests"


@dataclass(frozen=True)
class TaskSpec:
    root: Path
    task_id: str
    name: str
    repository_url: str
    base_commit: str
    gold_commit: str
    track: str
    upstream_license: str
    agent_timeout: int
    verifier_timeout: int
    resources: Resources

    @property
    def containerfile(self) -> Path:
        return self.root / "environment" / "Containerfile"

    @property
    def instruction(self) -> Path:
        return self.root / "instruction.md"

    @property
    def tests(self) -> Path:
        return self.root / "tests"

    @property
    def gold_patch(self) -> Path:
        return self.root / "solution" / "solution.patch"

    def scenarios(self) -> list[ScenarioSpec]:
        root = self.root / "scenarios"
        return [
            ScenarioSpec.load(path.parent, self.root)
            for path in sorted(root.glob("*/scenario.toml"))
        ]

    def scenario(self, scenario_id: str) -> ScenarioSpec:
        matches = [scenario for scenario in self.scenarios() if scenario.scenario_id == scenario_id]
        if len(matches) != 1:
            raise TaskValidationError(
                f"unknown or duplicate scenario {scenario_id!r} for {self.task_id}"
            )
        return matches[0]

    @classmethod
    def load(cls, path: Path) -> TaskSpec:
        manifest = path if path.name == "task.toml" else path / "task.toml"
        try:
            data: dict[str, Any] = tomllib.loads(manifest.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise TaskValidationError(f"cannot load {manifest}: {exc}") from exc
        try:
            meta = data["metadata"]
            env = data["environment"]
            return cls(
                root=manifest.parent.resolve(),
                task_id=meta["task_id"],
                name=data["task"]["name"],
                repository_url=meta["repository_url"],
                base_commit=meta["base_commit_hash"],
                gold_commit=meta["gold_commit_hash"],
                track=meta["track"],
                upstream_license=meta["upstream_license"],
                agent_timeout=int(data["agent"]["timeout_sec"]),
                verifier_timeout=int(data["verifier"]["timeout_sec"]),
                resources=Resources(
                    cpus=int(env["cpus"]),
                    memory_mb=int(env["memory_mb"]),
                    storage_mb=int(env["storage_mb"]),
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TaskValidationError(f"invalid manifest {manifest}: {exc}") from exc

    def validate(self, *, require_solution: bool = True) -> list[str]:
        errors: list[str] = []
        if self.root.name != self.task_id:
            errors.append(f"directory {self.root.name!r} must equal task_id {self.task_id!r}")
        if not _SHA.fullmatch(self.base_commit):
            errors.append("base_commit_hash must be a lowercase 40-character SHA")
        if not _SHA.fullmatch(self.gold_commit):
            errors.append("gold_commit_hash must be a lowercase 40-character SHA")
        if self.base_commit == self.gold_commit:
            errors.append("base and gold commits must differ")
        for required in (self.containerfile, self.instruction, self.tests / "test.sh"):
            if not required.is_file():
                errors.append(f"missing {required.relative_to(self.root)}")
        if require_solution and not self.gold_patch.is_file():
            errors.append("missing evaluator-only solution/solution.patch")
        seen_scenarios: set[str] = set()
        for scenario in self.scenarios():
            if scenario.scenario_id in seen_scenarios:
                errors.append(f"duplicate scenario {scenario.scenario_id}")
            seen_scenarios.add(scenario.scenario_id)
            if not scenario.gold_patch.is_file():
                errors.append(f"scenario {scenario.scenario_id} is missing its gold patch")
        if self.agent_timeout <= 0 or self.verifier_timeout <= 0:
            errors.append("timeouts must be positive")
        if min(self.resources.cpus, self.resources.memory_mb, self.resources.storage_mb) <= 0:
            errors.append("resource limits must be positive")
        return errors


def discover_tasks(root: Path) -> list[TaskSpec]:
    return [TaskSpec.load(path) for path in sorted(root.glob("*/task.toml"))]
