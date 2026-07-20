from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .providers import ProviderRoute, resolve_model
from .task import TaskSpec, discover_tasks

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ExperimentValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PricingSpec:
    basis: str
    currency: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    reasoning_per_million: float


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    pricing: PricingSpec | None = None
    cells: tuple[str, ...] | None = None


@dataclass(frozen=True)
class CellSpec:
    task_id: str
    scenario: str | None


@dataclass(frozen=True)
class ExpandedCell:
    cell_id: str
    provider: str
    model: str
    task_id: str
    scenario: str | None
    repeat: int


@dataclass(frozen=True)
class ExperimentSpec:
    path: Path
    experiment_id: str
    description: str
    stage: str
    repeats: int
    concurrency: int
    infrastructure_retries: int
    proctor_model: str
    models: tuple[ModelSpec, ...]
    cells: tuple[CellSpec, ...]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    @classmethod
    def load(
        cls,
        path: Path,
        repo_root: Path,
        providers: dict[str, dict[str, Any]],
    ) -> ExperimentSpec:
        path = path.resolve()
        try:
            data = tomllib.loads(path.read_text())
            meta = data["experiment"]
            models = tuple(_model_spec(item) for item in data["models"])
            cells = tuple(
                CellSpec(
                    task_id=str(item["task"]),
                    scenario=str(item["scenario"]) if item.get("scenario") else None,
                )
                for item in data["cells"]
            )
            spec = cls(
                path=path,
                experiment_id=str(meta["id"]),
                description=str(meta.get("description", "")),
                stage=str(meta["stage"]),
                repeats=int(meta.get("repeats", 1)),
                concurrency=int(meta.get("concurrency", 1)),
                infrastructure_retries=int(meta.get("infrastructure_retries", 1)),
                proctor_model=str(meta["proctor_model"]),
                models=models,
                cells=cells,
            )
        except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
            raise ExperimentValidationError(f"invalid experiment manifest {path}: {exc}") from exc
        spec.validate(repo_root, providers)
        return spec

    def validate(self, repo_root: Path, providers: dict[str, dict[str, Any]]) -> None:
        errors: list[str] = []
        if not _ID.fullmatch(self.experiment_id):
            errors.append(
                "experiment.id must use lowercase letters, digits, dots, dashes, or underscores"
            )
        if not self.stage:
            errors.append("experiment.stage is required")
        if self.repeats < 1:
            errors.append("experiment.repeats must be at least 1")
        if self.concurrency != 1:
            errors.append("only concurrency=1 is supported for sequential execution")
        if self.infrastructure_retries not in {0, 1}:
            errors.append("infrastructure_retries must be 0 or 1")
        if not self.proctor_model.strip():
            errors.append("experiment.proctor_model is required")
        if not self.models:
            errors.append("at least one [[models]] entry is required")
        if not self.cells:
            errors.append("at least one [[cells]] entry is required")

        model_keys = [(item.provider, item.model) for item in self.models]
        if len(set(model_keys)) != len(model_keys):
            errors.append("duplicate provider/model entries are not allowed")
        for model in self.models:
            try:
                resolve_model(model.provider, model.model, providers)
            except (LookupError, RuntimeError, ValueError) as exc:
                errors.append(str(exc))
            if model.pricing is not None:
                if not model.pricing.basis.strip() or not model.pricing.currency.strip():
                    errors.append(
                        "pricing basis and currency are required for "
                        f"{model.provider}/{model.model}"
                    )
                rates = (
                    model.pricing.input_per_million,
                    model.pricing.cached_input_per_million,
                    model.pricing.output_per_million,
                    model.pricing.reasoning_per_million,
                )
                if any(rate < 0 for rate in rates):
                    errors.append(
                        f"pricing rates must be nonnegative for {model.provider}/{model.model}"
                    )

        tasks: dict[str, TaskSpec] = {
            task.task_id: task for task in discover_tasks(repo_root / "tasks")
        }
        cell_keys = [(item.task_id, item.scenario) for item in self.cells]
        if len(set(cell_keys)) != len(cell_keys):
            errors.append("duplicate task/scenario cells are not allowed")
        declared_cell_ids = {_cell_id(item) for item in self.cells}
        for model in self.models:
            if model.cells is not None:
                if not model.cells:
                    errors.append(f"model {model.provider}/{model.model} selects no cells")
                unknown = set(model.cells) - declared_cell_ids
                if unknown:
                    errors.append(
                        f"model {model.provider}/{model.model} selects unknown cells: "
                        + ", ".join(sorted(unknown))
                    )
        for cell in self.cells:
            task = tasks.get(cell.task_id)
            if task is None:
                errors.append(f"unknown task {cell.task_id!r}")
                continue
            scenarios = task.scenarios()
            if scenarios and cell.scenario is None:
                errors.append(f"task {cell.task_id!r} requires an explicit scenario")
            if cell.scenario is not None:
                try:
                    task.scenario(cell.scenario)
                except ValueError as exc:
                    errors.append(str(exc))

        if errors:
            raise ExperimentValidationError("; ".join(errors))

    def routes(self, providers: dict[str, dict[str, Any]]) -> dict[tuple[str, str], ProviderRoute]:
        return {
            (model.provider, model.model): resolve_model(model.provider, model.model, providers)
            for model in self.models
        }

    def pricing(self, provider: str, model: str) -> PricingSpec | None:
        return next(
            item.pricing
            for item in self.models
            if item.provider == provider and item.model == model
        )

    def expand(self) -> tuple[ExpandedCell, ...]:
        expanded: list[ExpandedCell] = []
        for model in self.models:
            for cell in self.cells:
                if model.cells is not None and _cell_id(cell) not in model.cells:
                    continue
                for repeat in range(1, self.repeats + 1):
                    parts = [
                        model.provider,
                        model.model,
                        cell.task_id,
                        cell.scenario or "default",
                        f"r{repeat:02d}",
                    ]
                    cell_id = "__".join(_slug(part) for part in parts)
                    expanded.append(
                        ExpandedCell(
                            cell_id=cell_id,
                            provider=model.provider,
                            model=model.model,
                            task_id=cell.task_id,
                            scenario=cell.scenario,
                            repeat=repeat,
                        )
                    )
        return tuple(expanded)


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()


def _cell_id(cell: CellSpec) -> str:
    return f"{cell.task_id}/{cell.scenario or 'default'}"


def _model_spec(item: dict[str, Any]) -> ModelSpec:
    value = item.get("pricing")
    pricing = None
    if value is not None:
        if not isinstance(value, dict):
            raise TypeError("model pricing must be an inline table")
        pricing = PricingSpec(
            basis=str(value["basis"]),
            currency=str(value.get("currency", "USD")),
            input_per_million=float(value["input_per_million"]),
            cached_input_per_million=float(value["cached_input_per_million"]),
            output_per_million=float(value["output_per_million"]),
            reasoning_per_million=float(value["reasoning_per_million"]),
        )
    cells_value = item.get("cells")
    if cells_value is not None and not isinstance(cells_value, list):
        raise TypeError("model cells must be an array")
    cells = tuple(str(value) for value in cells_value) if cells_value is not None else None
    if cells is not None and len(cells) != len(set(cells)):
        raise ValueError("model cells must not contain duplicates")
    return ModelSpec(
        provider=str(item["provider"]),
        model=str(item["model"]),
        pricing=pricing,
        cells=cells,
    )
