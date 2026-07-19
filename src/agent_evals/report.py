from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from .experiment import ExperimentSpec


class ReportError(RuntimeError):
    pass


def write_experiment_report(repo_root: Path, experiment: ExperimentSpec, output: Path) -> dict:
    results_root = (
        repo_root.resolve() / ".runs" / "experiments" / experiment.experiment_id / "results"
    )
    if not results_root.is_dir():
        raise ReportError(f"no results found for experiment {experiment.experiment_id!r}")
    rows: list[dict] = []
    for path in sorted(results_root.glob("*.json")):
        record = json.loads(path.read_text())
        cell = record["cell"]
        state = record.get("state")
        attempts = record.get("attempts", [])
        latest = attempts[-1] if attempts else {}
        result = latest.get("result") if isinstance(latest, dict) else None
        result = result if isinstance(result, dict) else {}
        usage = result.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        verification = result.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        run_id = result.get("run_id")
        question_count = 0
        answer_count = 0
        if isinstance(run_id, str):
            proctor = repo_root / ".runs" / run_id / "proctor"
            question_count = len(list((proctor / "questions").glob("*.json")))
            answer_count = len(list((proctor / "answers").glob("*.json")))
        pricing = experiment.pricing(cell["provider"], cell["model"])
        estimated_cost = None
        if pricing is not None:
            estimated_cost = float(
                (
                    Decimal(str(usage.get("input_tokens", 0)))
                    * Decimal(str(pricing.input_per_million))
                    + Decimal(str(usage.get("cached_input_tokens", 0)))
                    * Decimal(str(pricing.cached_input_per_million))
                    + Decimal(str(usage.get("output_tokens", 0)))
                    * Decimal(str(pricing.output_per_million))
                    + Decimal(str(usage.get("reasoning_tokens", 0)))
                    * Decimal(str(pricing.reasoning_per_million))
                )
                / Decimal(1_000_000)
            )
        rows.append(
            {
                "cell_id": cell["cell_id"],
                "provider": cell["provider"],
                "model": cell["model"],
                "task_id": cell["task_id"],
                "scenario": cell.get("scenario") or "",
                "mode": cell["mode"],
                "repeat": cell["repeat"],
                "state": state,
                "run_id": run_id or "",
                "agent_exit_code": result.get("agent_exit_code"),
                "agent_completion_status": result.get("agent_completion_status", "unknown"),
                "agent_exit_discrepancy": result.get("agent_exit_discrepancy", False),
                "model_config_sha256": result.get("model_config_sha256", ""),
                "verification_outcome": verification.get("outcome", ""),
                "deterministic_pass": (
                    verification.get("outcome") == "passed"
                    if state == "completed"
                    else None
                ),
                "duration_seconds": result.get("duration_seconds"),
                "input_tokens": usage.get("input_tokens", 0),
                "cached_input_tokens": usage.get("cached_input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "reasoning_tokens": usage.get("reasoning_tokens", 0),
                "provider_reported_cost": usage.get("provider_reported_cost"),
                "estimated_cost": round(estimated_cost, 12) if estimated_cost is not None else None,
                "pricing_basis": pricing.basis if pricing else "",
                "pricing_currency": pricing.currency if pricing else "",
                "questions": question_count,
                "answers": answer_count,
                "attempts": len(attempts),
            }
        )
    totals = {
        "cells": len(rows),
        "completed": sum(row["state"] == "completed" for row in rows),
        "infrastructure_errors": sum(row["state"] == "infrastructure_error" for row in rows),
        "deterministic_passes": sum(bool(row["deterministic_pass"]) for row in rows),
        "input_tokens": sum(int(row["input_tokens"] or 0) for row in rows),
        "cached_input_tokens": sum(int(row["cached_input_tokens"] or 0) for row in rows),
        "output_tokens": sum(int(row["output_tokens"] or 0) for row in rows),
        "reasoning_tokens": sum(int(row["reasoning_tokens"] or 0) for row in rows),
        "provider_reported_cost": round(
            sum(float(row["provider_reported_cost"] or 0) for row in rows), 12
        ),
        "estimated_cost": (
            round(sum(float(row["estimated_cost"] or 0) for row in rows), 12)
            if rows and all(row["estimated_cost"] is not None for row in rows)
            else None
        ),
        "questions": sum(int(row["questions"]) for row in rows),
    }
    payload = {
        "schema_version": 1,
        "experiment_id": experiment.experiment_id,
        "manifest_sha256": experiment.digest,
        "totals": totals,
        "rows": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with (output / "results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]) if rows else ["cell_id"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    (output / "summary.md").write_text(_markdown(payload))
    return payload


def _markdown(payload: dict) -> str:
    totals = payload["totals"]
    lines = [
        f"# Experiment {payload['experiment_id']}",
        "",
        "## Totals",
        "",
        "| Cells | Passes | Infra errors | Input | Cached input | Output | Questions |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {totals['cells']} | {totals['deterministic_passes']} | "
            f"{totals['infrastructure_errors']} | {totals['input_tokens']} | "
            f"{totals['cached_input_tokens']} | {totals['output_tokens']} | "
            f"{totals['questions']} |"
        ),
        "",
        (
            "Provider-reported cost is retained when supplied, but token counts are the "
            "primary usage record."
        ),
        "",
        "## Cells",
        "",
        "| Provider | Model | Task | Scenario | Mode | Pass | Input | Cached | Output | Run |",
        "|---|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in payload["rows"]:
        pass_label = "—"
        if row["state"] == "completed":
            pass_label = "yes" if row["deterministic_pass"] else "no"
        lines.append(
            f"| {row['provider']} | {row['model']} | {row['task_id']} | "
            f"{row['scenario'] or '—'} | {row['mode']} | "
            f"{pass_label} | {row['input_tokens']} | "
            f"{row['cached_input_tokens']} | {row['output_tokens']} | {row['run_id']} |"
        )
    return "\n".join(lines) + "\n"
