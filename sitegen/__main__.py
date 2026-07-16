from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import quote, urlsplit

SCHEMA_VERSION = 1
EXPECTED_ARTIFACTS = (
    "artifacts.json",
    "instruction.txt",
    "matrix-record.json",
    "model.patch",
    "proctor-review.json",
    "transcript.jsonl",
    "verifier/stdout.txt",
    "verifier/stderr.txt",
)
SCORE_FIELDS = (
    ("scope_discipline", "Scope discipline"),
    ("code_clarity", "Code clarity"),
    ("test_quality", "Test quality"),
    ("repository_fit", "Repository fit"),
    ("security_and_safety", "Security and safety"),
)


def _read_json(path: Path, warnings: list[str]) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        warnings.append(f"Could not read {path.name}: {error}")
        return None


def _read_text(path: Path, warnings: list[str]) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        warnings.append(f"Could not read {path.name}: {error}")
        return None


def _safe_component(value: Any, fallback: str) -> str:
    text = str(value or fallback)
    return quote(text, safe="-._~")


def _base_path(value: str) -> str:
    value = value.strip()
    if not value or value == "/":
        return ""
    return "/" + value.strip("/")


def _url(base: str, *parts: str) -> str:
    encoded = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return f"{base}/{encoded}" if encoded else f"{base}/"


def _page_url(base: str, *parts: str) -> str:
    return _url(base, *parts).rstrip("/") + "/"


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _html_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _latest_result(matrix: dict[str, Any]) -> dict[str, Any]:
    attempts = matrix.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return {}
    latest = attempts[-1]
    if not isinstance(latest, dict) or not isinstance(latest.get("result"), dict):
        return {}
    return latest["result"]


def _manifest_entries(value: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append("Artifact manifest is not a list")
        return []
    entries: list[dict[str, Any]] = []
    for number, item in enumerate(value, 1):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            warnings.append(f"Artifact manifest entry {number} is malformed")
            continue
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            warnings.append(f"Artifact path is unsafe: {item['path']}")
            continue
        entries.append(item)
    return sorted(entries, key=lambda item: item["path"])


def _copy_artifacts(
    run_root: Path,
    output_root: Path,
    base: str,
    experiment_slug: str,
    cell_slug: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    manifest = _manifest_entries(_read_json(run_root / "artifacts.json", warnings), warnings)
    paths = {item["path"] for item in manifest}
    paths.update(name for name in EXPECTED_ARTIFACTS if (run_root / name).is_file())
    expected = {item["path"]: item for item in manifest}
    published: list[dict[str, Any]] = []
    for relative_text in sorted(paths):
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            warnings.append(f"Artifact path is unsafe: {relative_text}")
            continue
        source = run_root.joinpath(*relative.parts)
        if not source.is_file() or source.is_symlink():
            warnings.append(f"Artifact is missing: {relative_text}")
            continue
        data = source.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        target = output_root / "artifacts" / experiment_slug / cell_slug / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        expected_item = expected.get(relative_text, {})
        expected_hash = expected_item.get("sha256")
        hash_matches = expected_hash == actual_hash if isinstance(expected_hash, str) else None
        if hash_matches is False:
            warnings.append(f"Artifact hash mismatch: {relative_text}")
        published.append(
            {
                "path": relative_text,
                "bytes": len(data),
                "expected_bytes": expected_item.get("bytes"),
                "sha256": actual_hash,
                "expected_sha256": expected_hash,
                "hash_matches": hash_matches,
                "url": _url(base, "artifacts", experiment_slug, cell_slug, *relative.parts),
            }
        )
    return published


def _artifact_by_path(artifacts: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    return next((item for item in artifacts if item["path"] == path), None)


def _cell_data(
    experiment_id: str,
    row: dict[str, Any],
    run_root: Path | None,
    output_root: Path,
    base: str,
    experiment_slug: str,
    experiment_proctor_model: str | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    matrix_value = _read_json(run_root / "matrix-record.json", warnings) if run_root else None
    matrix = matrix_value if isinstance(matrix_value, dict) else {}
    if matrix_value is not None and not isinstance(matrix_value, dict):
        warnings.append("Matrix record is not an object")
    review_value = _read_json(run_root / "proctor-review.json", warnings) if run_root else None
    review = review_value if isinstance(review_value, dict) else None
    if review_value is not None and not isinstance(review_value, dict):
        warnings.append("Proctor review is not an object")
    matrix_cell = cast(
        dict[str, Any], matrix.get("cell") if isinstance(matrix.get("cell"), dict) else {}
    )
    result = _latest_result(matrix)
    verification = cast(
        dict[str, Any],
        result.get("verification") if isinstance(result.get("verification"), dict) else {},
    )
    usage = cast(
        dict[str, Any], result.get("usage") if isinstance(result.get("usage"), dict) else {}
    )
    merged = {**matrix_cell, **result, **row}
    cell_id = str(merged.get("cell_id") or (run_root.name if run_root else "unknown-cell"))
    cell_slug = _safe_component(cell_id, "unknown-cell")
    artifacts = (
        _copy_artifacts(run_root, output_root, base, experiment_slug, cell_slug, warnings)
        if run_root
        else []
    )
    outcome = merged.get("verification_outcome") or verification.get("outcome")
    deterministic_pass = merged.get("deterministic_pass")
    if not isinstance(deterministic_pass, bool):
        deterministic_pass = outcome == "passed" if outcome else None
    state = merged.get("state") or matrix.get("state") or "partial"
    subjective = None
    if review:
        rationales = review.get("rating_rationales")
        subjective = {
            "separate_from_deterministic": True,
            "can_override_deterministic": False,
            "proctor": review.get("proctor"),
            "proctor_model": review.get("proctor_model") or experiment_proctor_model,
            "blinded_to_model_identity": review.get("blinded_to_model_identity"),
            "mergeable": review.get("mergeable"),
            "scores": {field: review.get(field) for field, _ in SCORE_FIELDS},
            "rationales": rationales if isinstance(rationales, dict) else {},
            "blockers": review.get("blockers") if isinstance(review.get("blockers"), list) else [],
            "strengths": review.get("strengths") if isinstance(review.get("strengths"), list) else [],
            "summary": review.get("summary"),
            "overall_reasoning": review.get("overall_reasoning"),
        }
        if review.get("can_override_deterministic") not in (None, False):
            warnings.append("Review incorrectly claims it can override deterministic verification")
    detail = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "cell_id": cell_id,
        "state": state,
        "attribution": {
            "provider": merged.get("provider"),
            "model": merged.get("model"),
            "proctor_model": (subjective or {}).get("proctor_model") or experiment_proctor_model,
        },
        "task": {
            "task_id": merged.get("task_id"),
            "scenario": merged.get("scenario"),
            "mode": merged.get("mode"),
            "repeat": merged.get("repeat"),
        },
        "run": {
            "run_id": merged.get("run_id"),
            "attempts": merged.get("attempts"),
            "agent_exit_code": merged.get("agent_exit_code"),
            "agent_completion_status": merged.get("agent_completion_status"),
            "duration_seconds": merged.get("duration_seconds"),
        },
        "usage": {
            key: merged.get(key, usage.get(key))
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "provider_reported_cost",
                "estimated_cost",
                "pricing_currency",
                "pricing_basis",
            )
        },
        "deterministic": {
            "authoritative": True,
            "pass": deterministic_pass,
            "outcome": outcome,
            "verification": verification or None,
        },
        "subjective": subjective,
        "candidate_patch": _artifact_by_path(artifacts, "model.patch"),
        "transcript": _artifact_by_path(artifacts, "transcript.jsonl"),
        "verifier_output": [item for item in artifacts if item["path"].startswith("verifier/")],
        "artifacts": artifacts,
        "warnings": warnings,
        "page_url": _page_url(base, "experiments", experiment_slug, "cells", cell_slug),
        "data_url": _url(base, "data", "experiments", experiment_slug, "cells", f"{cell_slug}.json"),
    }
    return detail


def _experiment_config(data_root: Path, experiment_id: str, warnings: list[str]) -> dict[str, Any]:
    path = data_root / "experiments" / f"{experiment_id}.toml"
    if not path.is_file():
        return {}
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        warnings.append(f"Could not read experiment TOML: {error}")
        return {}
    return value if isinstance(value, dict) else {}


def _discover_experiments(data_root: Path) -> list[Path]:
    reports = data_root / "reports" / "experiments"
    if not reports.is_dir():
        return []
    return sorted((path for path in reports.iterdir() if path.is_dir()), key=lambda path: path.name)


def _collect_experiment(data_root: Path, report_root: Path, output_root: Path, base: str) -> dict[str, Any]:
    warnings: list[str] = []
    results_value = _read_json(report_root / "results.json", warnings)
    results = results_value if isinstance(results_value, dict) else {}
    if results_value is not None and not isinstance(results_value, dict):
        warnings.append("results.json is not an object")
    experiment_id = str(results.get("experiment_id") or report_root.name)
    experiment_slug = _safe_component(experiment_id, report_root.name)
    config = _experiment_config(data_root, experiment_id, warnings)
    config_meta = cast(
        dict[str, Any],
        config.get("experiment") if isinstance(config.get("experiment"), dict) else {},
    )
    evidence_root = report_root / "evidence"
    index_value = _read_json(evidence_root / "index.json", warnings)
    evidence_index = index_value if isinstance(index_value, dict) else {}
    if index_value is not None and not isinstance(index_value, dict):
        warnings.append("Evidence index is not an object")
    rows: dict[str, dict[str, Any]] = {}
    result_rows = results.get("rows")
    if isinstance(result_rows, list):
        for number, row in enumerate(result_rows, 1):
            if not isinstance(row, dict) or not row.get("cell_id"):
                warnings.append(f"Skipped malformed results row {number}")
                continue
            rows[str(row["cell_id"])] = row
    elif result_rows is not None:
        warnings.append("results.json rows is not a list")
    index_runs = evidence_index.get("runs")
    if isinstance(index_runs, list):
        for number, item in enumerate(index_runs, 1):
            if not isinstance(item, dict) or not item.get("cell_id"):
                warnings.append(f"Skipped malformed evidence-index row {number}")
                continue
            cell_id = str(item["cell_id"])
            rows.setdefault(cell_id, {"cell_id": cell_id, "state": "partial"})

    runs_root = evidence_root / "runs"
    run_roots: dict[str, Path] = {}
    if runs_root.is_dir():
        for path in sorted(runs_root.iterdir(), key=lambda item: item.name):
            if path.is_dir() and not path.is_symlink():
                rows.setdefault(path.name, {"cell_id": path.name, "state": "partial"})
                run_roots[path.name] = path
    proctor_model = config_meta.get("proctor_model")
    cells = [
        _cell_data(
            experiment_id,
            rows[cell_id],
            run_roots.get(cell_id),
            output_root,
            base,
            experiment_slug,
            str(proctor_model) if proctor_model else None,
        )
        for cell_id in sorted(rows)
    ]
    expected_cells = None
    models = config.get("models")
    planned_cells = config.get("cells")
    repeats = config_meta.get("repeats", 1)
    if isinstance(models, list) and isinstance(planned_cells, list) and isinstance(repeats, int):
        expected_cells = len(models) * len(planned_cells) * repeats
    completed = sum(cell["state"] == "completed" for cell in cells)
    passes = sum(cell["deterministic"]["pass"] is True for cell in cells)
    infra_errors = sum(cell["state"] == "infrastructure_error" for cell in cells)
    subjective_summary = _read_text(report_root / "subjective-summary.md", warnings)
    report_summary = _read_text(report_root / "summary.md", warnings)
    experiment = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "slug": experiment_slug,
        "description": config_meta.get("description"),
        "stage": config_meta.get("stage"),
        "manifest_sha256": results.get("manifest_sha256"),
        "proctor_model": proctor_model,
        "summary": {
            "discovered_cells": len(cells),
            "expected_cells": expected_cells,
            "completed_cells": completed,
            "deterministic_passes": passes,
            "infrastructure_errors": infra_errors,
            "is_partial": expected_cells is not None and completed < expected_cells,
            "reported_totals": results.get("totals") if isinstance(results.get("totals"), dict) else None,
        },
        "subjective_summary_markdown": subjective_summary,
        "report_summary_markdown": report_summary,
        "cells": cells,
        "warnings": warnings,
        "page_url": _page_url(base, "experiments", experiment_slug),
        "data_url": _url(base, "data", "experiments", f"{experiment_slug}.json"),
    }
    return experiment


def _value(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return '<span class="unavailable">Unavailable</span>'
    return f"{html.escape(str(value))}{html.escape(suffix)}"


def _human_number(value: Any) -> str:
    """Compact a count for scanning while retaining the exact source value."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _value(value)
    absolute = abs(value)
    if absolute >= 1_000_000:
        shown = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    elif absolute >= 1_000:
        shown = f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    else:
        shown = f"{value:,}"
    exact = f"{value:,}"
    return f'<span class="human-value" title="Exact value: {exact}" aria-label="{exact}">{shown}</span>'


def _human_duration(value: Any) -> str:
    """Humanize seconds while preserving the exact duration for assistive/detail use."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _value(value)
    seconds = float(value)
    if seconds < 60:
        shown = f"{seconds:.1f} s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remainder = int(round(seconds % 60))
        shown = f"{minutes}m {remainder:02d}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        shown = f"{hours}h {minutes:02d}m"
    exact = f"{value} seconds"
    return f'<span class="human-value" title="Exact runtime: {html.escape(exact)}" aria-label="{html.escape(exact)}">{shown}</span>'


def _status_label(cell: dict[str, Any]) -> tuple[str, str]:
    passed = cell["deterministic"]["pass"]
    if passed is True:
        return "Passed", "pass"
    if passed is False:
        return "Failed", "fail"
    return str(cell.get("state") or "Partial").replace("_", " ").title(), "partial"


def _layout(title: str, body: str, base: str, breadcrumbs: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{html.escape(title)} · Coding Agent Evals</title>
  <link rel="stylesheet" href="{_url(base, 'assets', 'site.css')}">
  <script src="{_url(base, 'assets', 'site.js')}" defer></script>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header"><div class="header-inner"><a class="site-title" href="{_url(base)}"><span class="site-mark" aria-hidden="true">cae</span><span>Coding Agent Evals <small>results browser</small></span></a><button class="theme-toggle" type="button" data-theme-toggle aria-label="Toggle color theme" title="Toggle color theme" hidden>◐</button></div></header>
  <div class="breadcrumb-wrap">{breadcrumbs}</div>
  <main id="main" class="page-shell">{body}</main>
  <footer class="site-footer"><p>Deterministic verification is authoritative. Subjective review is separate and non-overriding.</p></footer>
</body>
</html>
"""


def _warnings(values: list[str]) -> str:
    if not values:
        return ""
    items = "".join(f"<li>{html.escape(item)}</li>" for item in values)
    return f'<aside class="notice notice-warning" aria-labelledby="warnings-title"><h2 id="warnings-title">Data warnings</h2><ul>{items}</ul></aside>'


def _experiment_index(experiments: list[dict[str, Any]], base: str) -> str:
    cards = []
    for experiment in experiments:
        summary = experiment["summary"]
        progress = f"{summary['completed_cells']} completed"
        if summary["expected_cells"] is not None:
            progress += f" of {summary['expected_cells']} planned"
        cards.append(
            f"""<article class="experiment-card">
<h2><a href="{experiment['page_url']}">{html.escape(experiment['experiment_id'])}</a></h2>
<p>{_value(experiment.get('description'))}</p>
<dl class="metrics index-metrics"><div><dt>Progress</dt><dd>{html.escape(progress)}</dd></div><div><dt>Deterministic passes</dt><dd>{summary['deterministic_passes']}</dd></div><div class="metric-span"><dt>Stage</dt><dd>{_value(experiment.get('stage'))}</dd></div></dl>
</article>"""
        )
    content = "".join(cards) or '<p class="empty-state">No committed experiment reports are available yet.</p>'
    body = f"""<header class="page-heading"><p class="eyebrow">Public evidence browser</p><h1>Evaluation experiments</h1><p>Browse committed deterministic results, usage, qualitative reviews, patches, transcripts, verifier output, and artifact hashes.</p></header><section class="experiment-grid" aria-label="Experiments">{content}</section>"""
    return _layout("Experiments", body, base)


def _cell_row(cell: dict[str, Any]) -> str:
    label, status_class = _status_label(cell)
    attribution = cell["attribution"]
    task = cell["task"]
    usage = cell["usage"]
    subjective = cell.get("subjective")
    score_values = list((subjective or {}).get("scores", {}).values())
    numeric_scores = [score for score in score_values if isinstance(score, (int, float))]
    average = sum(numeric_scores) / len(numeric_scores) if numeric_scores else None
    search = " ".join(str(value or "") for value in (attribution.get("provider"), attribution.get("model"), task.get("task_id"), task.get("scenario"), label))
    return f"""<tr data-cell-row data-search="{html.escape(search.lower(), quote=True)}" data-provider="{html.escape(str(attribution.get('provider') or ''), quote=True)}" data-result="{status_class}">
<td data-label="Provider / model"><a href="{cell['page_url']}">{html.escape(str(attribution.get('provider') or 'Unknown'))} / {html.escape(str(attribution.get('model') or 'Unknown'))}</a></td>
<td data-label="Task">{_value(task.get('task_id'))}<small>{_value(task.get('scenario')) if task.get('scenario') else ''}</small></td>
<td data-label="Deterministic"><span class="status status-{status_class}">{html.escape(label)}</span></td>
<td data-label="Tokens"><span title="Exact input / output: {html.escape(str(usage.get('input_tokens')))} / {html.escape(str(usage.get('output_tokens')))}">{_human_number(usage.get('input_tokens'))} <span aria-hidden="true">/</span> {_human_number(usage.get('output_tokens'))}</span></td>
<td data-label="Runtime">{_human_duration(cell['run'].get('duration_seconds'))}</td>
<td data-label="Subjective avg.">{_value(f'{average:.1f}' if average is not None else None)}</td>
</tr>"""


def _experiment_page(experiment: dict[str, Any], base: str) -> str:
    summary = experiment["summary"]
    partial = ""
    if summary["is_partial"]:
        partial = '<aside class="notice" role="status"><strong>Experiment in progress.</strong> This page includes only data committed so far.</aside>'
    provider_options = sorted({str(cell["attribution"].get("provider")) for cell in experiment["cells"] if cell["attribution"].get("provider")})
    options = "".join(f'<option value="{html.escape(value, quote=True)}">{html.escape(value)}</option>' for value in provider_options)
    rows = "".join(_cell_row(cell) for cell in experiment["cells"])
    if not rows:
        rows = '<tr><td colspan="6" class="empty-state">No cells have been committed yet.</td></tr>'
    subjective = ""
    if experiment.get("subjective_summary_markdown"):
        subjective = f'<details class="raw-summary"><summary>Published subjective summary (Markdown)</summary><pre>{html.escape(experiment["subjective_summary_markdown"])}</pre></details>'
    planned = summary["expected_cells"]
    progress = f"{summary['completed_cells']} completed" + (f" of {planned} planned" if planned is not None else "")
    body = f"""<header class="page-heading"><p class="eyebrow">{_value(experiment.get('stage'))} · explore results</p><h1>{html.escape(experiment['experiment_id'])}</h1><p>{_value(experiment.get('description'))}</p></header>
{partial}{_warnings(experiment['warnings'])}
<section aria-labelledby="summary-title"><div class="section-heading"><h2 id="summary-title">Experiment summary</h2><p class="progress-label"><strong>{html.escape(progress)}</strong></p></div><dl class="metrics summary-metrics"><div><dt>Completed / planned</dt><dd>{summary['completed_cells']}<span aria-hidden="true"> / </span>{_value(planned)}</dd></div><div><dt>Discovered evidence</dt><dd>{summary['discovered_cells']}</dd></div><div><dt>Deterministic passes</dt><dd>{summary['deterministic_passes']}</dd></div><div><dt>Infrastructure errors</dt><dd>{summary['infrastructure_errors']}</dd></div><div class="metric-wide"><dt>Subjective reviewer</dt><dd>{_value(experiment.get('proctor_model'))}<small>Separate, non-overriding judgment</small></dd></div></dl></section>
<section aria-labelledby="cells-title" data-cell-browser><div class="section-heading"><h2 id="cells-title">Cells</h2><p aria-live="polite" data-filter-count>{len(experiment['cells'])} cells</p></div>
<form class="filters" data-cell-filters><label>Search <input type="search" name="query" placeholder="Model, task, scenario…"></label><label>Provider <select name="provider"><option value="">All providers</option>{options}</select></label><label>Result <select name="result"><option value="">All results</option><option value="pass">Passed</option><option value="fail">Failed</option><option value="partial">Partial</option></select></label><button type="reset">Clear</button></form>
<div class="table-wrap cell-table"><table><caption>Committed experiment cells. Tokens are compact input / output counts; exact values are available on hover and to assistive technology.</caption><thead><tr><th scope="col">Provider / model</th><th scope="col">Task</th><th scope="col">Deterministic result</th><th scope="col">Tokens</th><th scope="col">Runtime</th><th scope="col">Subjective avg.</th></tr></thead><tbody>{rows}</tbody></table></div></section>
{subjective}<p class="data-link"><a href="{experiment['data_url']}">Download experiment JSON</a></p>"""
    breadcrumbs = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="{_url(base)}">Experiments</a></li><li aria-current="page">{html.escape(experiment["experiment_id"])}</li></ol></nav>'
    return _layout(experiment["experiment_id"], body, base, breadcrumbs)


def _raw_panel(title: str, artifact: dict[str, Any] | None, run_root: Path | None, panel_id: str) -> str:
    if not artifact:
        return f'<section id="{panel_id}" class="artifact-panel evidence-panel"><h2>{html.escape(title)}</h2><p class="unavailable">Unavailable</p></section>'
    preview = ""
    if run_root:
        source = run_root.joinpath(*PurePosixPath(artifact["path"]).parts)
        try:
            text = source.read_text(encoding="utf-8")
            truncated = len(text) > 100_000
            text = text[:100_000]
            note = '<p class="preview-note">Preview truncated at 100,000 characters; download the complete artifact.</p>' if truncated else ""
            open_attribute = "" if panel_id == "transcript" else " open"
            preview = f'<details{open_attribute}><summary>Inline preview</summary><div class="preview-scroll" tabindex="0"><pre>{html.escape(text)}</pre></div>{note}</details>'
        except (OSError, UnicodeError):
            pass
    return f'<section id="{panel_id}" class="artifact-panel evidence-panel"><div class="artifact-heading"><h2>{html.escape(title)}</h2><a class="raw-link" href="{artifact["url"]}" download>Download raw</a></div><p class="artifact-meta">{_human_number(artifact["bytes"])} bytes · SHA-256 <code title="{html.escape(artifact["sha256"])}">{html.escape(artifact["sha256"][:16])}…</code></p>{preview}</section>'


def _cell_page(cell: dict[str, Any], experiment: dict[str, Any], run_root: Path | None, base: str) -> str:
    label, status_class = _status_label(cell)
    attribution = cell["attribution"]
    task = cell["task"]
    run = cell["run"]
    usage = cell["usage"]
    subjective = cell.get("subjective")
    score_html = '<p class="unavailable">No subjective review has been committed.</p>'
    if subjective:
        score_items = []
        for field, display in SCORE_FIELDS:
            rationale = subjective.get("rationales", {}).get(field)
            score_items.append(f'<div><dt>{html.escape(display)}</dt><dd><strong>{_value(subjective["scores"].get(field), "/5")}</strong>{f"<p>{html.escape(str(rationale))}</p>" if rationale else ""}</dd></div>')
        blockers = "".join(f"<li>{html.escape(str(item))}</li>" for item in subjective.get("blockers", [])) or "<li>None reported</li>"
        strengths = "".join(f"<li>{html.escape(str(item))}</li>" for item in subjective.get("strengths", [])) or "<li>None reported</li>"
        score_html = f"""<p class="trust-note"><strong>Separate review:</strong> these judgments cannot override deterministic verification.</p><dl class="score-grid">{''.join(score_items)}</dl><h3>Summary</h3><p>{_value(subjective.get('summary'))}</p><h3>Overall reasoning</h3><p>{_value(subjective.get('overall_reasoning'))}</p><div class="review-lists"><div><h3>Blockers</h3><ul>{blockers}</ul></div><div><h3>Strengths</h3><ul>{strengths}</ul></div></div>"""
    verifier_panels = "".join(_raw_panel(f"Verifier {item['path'].split('/')[-1]}", item, run_root, f"verifier-{number}") for number, item in enumerate(cell["verifier_output"], 1))
    if not verifier_panels:
        verifier_panels = _raw_panel("Verifier output", None, run_root, "verifier-1")
    artifact_rows = "".join(
        f'<tr><td><a href="{item["url"]}">{html.escape(item["path"])}</a></td><td>{_human_number(item["bytes"])}</td><td><code title="{html.escape(item["sha256"])}">{html.escape(item["sha256"][:16])}…</code></td><td>{"Yes" if item["hash_matches"] is True else "No" if item["hash_matches"] is False else "Not declared"}</td></tr>'
        for item in cell["artifacts"]
    ) or '<tr><td colspan="4" class="unavailable">No artifact manifest is available.</td></tr>'
    provider = str(attribution.get("provider") or "Unknown provider")
    model = str(attribution.get("model") or "Unknown model")
    task_id = str(task.get("task_id") or "Unknown task")
    body = f"""<header class="page-heading cell-heading"><p class="eyebrow">Inspect · run evidence</p><h1>{html.escape(provider)} / {html.escape(model)}</h1><p class="task-lede">{html.escape(task_id)}{f" · {html.escape(str(task.get('scenario')))}" if task.get('scenario') else ""}</p><p class="cell-id"><span>Cell ID</span> <code>{html.escape(cell['cell_id'])}</code></p></header>
{_warnings(cell['warnings'])}
<nav class="evidence-nav" aria-label="Cell evidence"><a href="#deterministic">Verdict</a><a href="#usage">Usage</a><a href="#subjective">Subjective</a><a href="#patch">Patch</a><a href="#transcript">Transcript</a><a href="#verifier-1">Verifier</a><a href="#artifacts">Hashes</a></nav>
<section id="deterministic" aria-labelledby="result-title"><h2 id="result-title">Deterministic result <span class="status status-{status_class}">{html.escape(label)}</span></h2><p class="trust-note authoritative"><strong>Authoritative:</strong> deterministic verifier output determines behavioral success. Subjective review does not change this result.</p><dl class="metrics"><div><dt>Outcome</dt><dd>{_value(cell['deterministic'].get('outcome'))}</dd></div><div><dt>Task</dt><dd>{_value(task.get('task_id'))}</dd></div><div><dt>Scenario</dt><dd>{_value(task.get('scenario'))}</dd></div><div><dt>Mode</dt><dd>{_value(task.get('mode'))}</dd></div><div><dt>Run</dt><dd>{_value(run.get('run_id'))}</dd></div><div><dt>Runtime</dt><dd>{_human_duration(run.get('duration_seconds'))}</dd></div></dl></section>
<section id="usage" aria-labelledby="usage-title"><h2 id="usage-title">Usage</h2><dl class="metrics"><div><dt>Input tokens</dt><dd>{_human_number(usage.get('input_tokens'))}</dd></div><div><dt>Cached input</dt><dd>{_human_number(usage.get('cached_input_tokens'))}</dd></div><div><dt>Output tokens</dt><dd>{_human_number(usage.get('output_tokens'))}</dd></div><div><dt>Reasoning tokens</dt><dd>{_human_number(usage.get('reasoning_tokens'))}</dd></div><div><dt>Reported cost</dt><dd>{_value(usage.get('provider_reported_cost'))}</dd></div></dl></section>
<section id="subjective" aria-labelledby="review-title"><h2 id="review-title">Subjective proctor review <span class="section-qualifier">separate · non-overriding</span></h2><p>Reviewer model: {_value(attribution.get('proctor_model'))}</p>{score_html}</section>
{_raw_panel('Candidate patch', cell.get('candidate_patch'), run_root, 'patch')}
{_raw_panel('Canonical transcript (JSONL)', cell.get('transcript'), run_root, 'transcript')}
{verifier_panels}
<section id="artifacts" aria-labelledby="artifacts-title"><h2 id="artifacts-title">Artifact hashes</h2><div class="table-wrap"><table><caption>Published artifact byte sizes and SHA-256 digests.</caption><thead><tr><th scope="col">Artifact</th><th scope="col">Bytes</th><th scope="col">SHA-256</th><th scope="col">Matches manifest</th></tr></thead><tbody>{artifact_rows}</tbody></table></div></section>
<p class="data-link"><a href="{cell['data_url']}">Download cell detail JSON</a></p>"""
    breadcrumbs = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li><a href="{_url(base)}">Experiments</a></li><li><a href="{experiment["page_url"]}">{html.escape(experiment["experiment_id"])}</a></li><li aria-current="page">{html.escape(cell["cell_id"])}</li></ol></nav>'
    return _layout(cell["cell_id"], body, base, breadcrumbs)


CSS = """/* Warm editorial/technical system: linen, ink, graphite, hairline rules. */
:root {
  --page-max: 76rem; --ink: #1b1b19; --ink-2: #403e38; --muted: #6f695c;
  --faint: #958d7c; --linen: #f3f0e6; --paper: #fffdf7; --paper-2: #f8f4e9;
  --rule: #d9d1bf; --rule-strong: #bdb3a0; --accent: #2558a1; --accent-soft: #e5ecf7;
  --pass: #28633d; --pass-soft: #e4eee3; --fail: #9b3528; --fail-soft: #f2e2dc;
  --partial: #805812; --partial-soft: #f1e7cf; --code: #ece7d9;
  color-scheme: light; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 16px; line-height: 1.5; font-feature-settings: "tnum" 1;
}
html[data-theme="dark"] {
  --ink: #e8e3d7; --ink-2: #c8c1b2; --muted: #9d9587; --faint: #777064;
  --linen: #121317; --paper: #1a1d23; --paper-2: #20242b; --rule: #30343c;
  --rule-strong: #484d57; --accent: #8bace8; --accent-soft: #23314a;
  --pass: #88ca98; --pass-soft: #1d2c21; --fail: #e18370; --fail-soft: #301e1a;
  --partial: #d3aa59; --partial-soft: #302716; --code: #15181e; color-scheme: dark;
}
@media (prefers-color-scheme: dark) {
  html:not([data-theme="light"]) {
    --ink: #e8e3d7; --ink-2: #c8c1b2; --muted: #9d9587; --faint: #777064;
    --linen: #121317; --paper: #1a1d23; --paper-2: #20242b; --rule: #30343c;
    --rule-strong: #484d57; --accent: #8bace8; --accent-soft: #23314a;
    --pass: #88ca98; --pass-soft: #1d2c21; --fail: #e18370; --fail-soft: #301e1a;
    --partial: #d3aa59; --partial-soft: #302716; --code: #15181e; color-scheme: dark;
  }
}
* { box-sizing: border-box; }
html { scroll-padding-top: 4.4rem; }
body { margin: 0; color: var(--ink); background: var(--linen); }
a { color: var(--accent); text-underline-offset: .18em; text-decoration-thickness: .08em; }
a:hover { text-decoration-thickness: .14em; }
button, input, select { color: inherit; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, [tabindex]:focus-visible { outline: .18rem solid var(--accent); outline-offset: .16rem; }
.skip-link { position: fixed; left: .6rem; top: -5rem; z-index: 100; padding: .55rem .8rem; color: var(--ink); background: var(--paper); border: 1px solid var(--rule-strong); }
.skip-link:focus { top: .6rem; }
.site-header { position: sticky; top: 0; z-index: 40; background: var(--paper-2); border-bottom: 1px solid var(--rule); }
.header-inner, .site-footer, .page-shell, .breadcrumbs { width: min(100% - 2rem, var(--page-max)); margin-inline: auto; }
.header-inner { min-height: 3rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.site-title { display: flex; align-items: center; gap: .55rem; color: var(--ink); font-weight: 720; text-decoration: none; letter-spacing: -.015em; }
.site-title small { color: var(--muted); font-size: .73rem; font-weight: 500; margin-left: .25rem; }
.site-mark { display: grid; place-items: center; width: 1.45rem; height: 1.45rem; border: 1.5px solid var(--ink); border-radius: .16rem; font: 700 .63rem ui-monospace, monospace; background: var(--paper); }
.theme-toggle { width: 2.3rem; height: 2.3rem; border: 1px solid var(--rule); background: var(--paper); border-radius: .2rem; font: inherit; cursor: pointer; }
.theme-toggle:hover { border-color: var(--rule-strong); }
.breadcrumb-wrap { border-bottom: 1px solid var(--rule); background: var(--paper-2); }
.breadcrumbs { padding-block: .55rem; color: var(--muted); font-size: .76rem; }
.breadcrumbs ol { display: flex; flex-wrap: wrap; gap: .35rem; list-style: none; margin: 0; padding: 0; min-width: 0; }
.breadcrumbs li { min-width: 0; overflow-wrap: anywhere; }
.breadcrumbs li + li::before { content: "/"; color: var(--faint); margin-right: .35rem; }
.page-shell { padding-block: 1.35rem 4rem; }
.page-heading { padding-block: .2rem 1.15rem; margin-bottom: 1.2rem; border-bottom: 1px solid var(--rule); }
.page-heading h1 { margin: .25rem 0 .35rem; max-width: 28ch; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.75rem, 4vw, 2.65rem); line-height: 1.08; letter-spacing: -.025em; text-wrap: balance; }
.page-heading > p:last-child { max-width: 72ch; color: var(--ink-2); margin-bottom: 0; }
.eyebrow { margin: 0; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); font-size: .68rem; font-weight: 750; }
.cell-heading h1 { font-family: ui-sans-serif, system-ui, sans-serif; font-size: clamp(1.55rem, 3.5vw, 2.25rem); }
.task-lede { font-weight: 650; }
.cell-id { display: flex; gap: .55rem; align-items: baseline; margin-top: .7rem; font-size: .72rem; color: var(--muted); }
.cell-id span { text-transform: uppercase; letter-spacing: .08em; font-weight: 700; }
.cell-id code { overflow-wrap: anywhere; }
h2 { margin: 1.85rem 0 .7rem; font-family: Georgia, "Times New Roman", serif; font-size: 1.42rem; letter-spacing: -.012em; }
h3 { margin-top: 1.3rem; font-size: 1rem; }
section { scroll-margin-top: 4.4rem; }
.experiment-grid { display: grid; gap: 0; border-top: 1px solid var(--rule); }
.experiment-card { display: grid; grid-template-columns: minmax(14rem, 1fr) 2fr minmax(18rem, 1.2fr); align-items: start; gap: 1.2rem; padding: 1.2rem .2rem; border-bottom: 1px solid var(--rule); }
.experiment-card h2 { margin: 0; font: 700 1rem ui-monospace, monospace; }
.experiment-card p { margin: 0; color: var(--ink-2); }
.notice { border: 1px solid var(--rule); padding: .85rem 1rem; margin-block: 1rem; background: var(--paper); }
.notice strong { color: var(--partial); }
.notice-warning { background: var(--partial-soft); }
.metrics, .score-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr)); gap: 1px; margin: 0; padding: 1px; background: var(--rule); border: 1px solid var(--rule); }
.metrics div, .score-grid div { min-width: 0; padding: .8rem .9rem; background: var(--paper); }
.summary-metrics { grid-template-columns: repeat(4, minmax(8rem, 1fr)) minmax(13rem, 1.35fr); }
.index-metrics { grid-template-columns: 1.3fr 1fr; }
.index-metrics .metric-span { grid-column: 1 / -1; }
.metric-wide dd small, .metrics dd small { display: block; margin-top: .18rem; color: var(--muted); font: 500 .68rem ui-sans-serif, system-ui, sans-serif; }
.score-grid dd p { font: 450 .83rem/1.4 ui-sans-serif, system-ui, sans-serif; }
dt { color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .075em; font-weight: 720; }
dd { margin: .28rem 0 0; font: 650 .94rem ui-monospace, "SFMono-Regular", Consolas, monospace; overflow-wrap: anywhere; }
.section-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; margin-top: 1.4rem; }
.section-heading h2 { margin-bottom: .3rem; }
.progress-label { color: var(--muted); font-size: .76rem; }
.filters { display: flex; flex-wrap: wrap; gap: .6rem; align-items: end; padding: .65rem .7rem; margin-block: .4rem .8rem; border: 1px solid var(--rule); background: var(--paper-2); }
.filters label { display: grid; gap: .18rem; color: var(--muted); font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; }
.filters label:first-child { flex: 1 1 16rem; }
.filters input, .filters select, .filters button { min-height: 2.35rem; padding: .4rem .55rem; border: 1px solid var(--rule-strong); border-radius: .15rem; background: var(--paper); font: 500 .85rem ui-sans-serif, system-ui, sans-serif; text-transform: none; letter-spacing: 0; }
.filters input { width: 100%; }
.filters button { cursor: pointer; }
.table-wrap { overflow-x: auto; border: 1px solid var(--rule); background: var(--paper); }
table { width: 100%; border-collapse: collapse; font-size: .83rem; }
caption { text-align: left; padding: .55rem .65rem; color: var(--muted); font-size: .73rem; }
th, td { text-align: left; vertical-align: top; padding: .58rem .65rem; border-bottom: 1px solid var(--rule); }
th { color: var(--muted); background: var(--paper-2); font-size: .68rem; text-transform: uppercase; letter-spacing: .055em; }
tbody tr:hover td { background: var(--accent-soft); }
td small { display: block; color: var(--muted); font-size: .7rem; }
.human-value { white-space: nowrap; font-variant-numeric: tabular-nums; }
.status { display: inline-block; border: 1px solid currentColor; border-radius: 99rem; padding: .08rem .5rem; font-size: .72rem; font-weight: 700; white-space: nowrap; }
.status-pass { color: var(--pass); background: var(--pass-soft); }
.status-fail { color: var(--fail); background: var(--fail-soft); }
.status-partial { color: var(--partial); background: var(--partial-soft); }
.unavailable { color: var(--muted); font-style: italic; }
.trust-note { padding: .7rem .8rem; border: 1px solid var(--rule); background: var(--paper); }
.trust-note.authoritative { border-color: color-mix(in srgb, var(--accent) 45%, var(--rule)); background: var(--accent-soft); }
.section-qualifier { display: inline-block; margin-left: .4rem; color: var(--muted); font: 700 .63rem ui-sans-serif, system-ui, sans-serif; text-transform: uppercase; letter-spacing: .08em; }
.review-lists { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr)); gap: 1.5rem; }
.evidence-nav { position: sticky; top: 3rem; z-index: 30; display: flex; gap: .18rem; overflow-x: auto; margin: 0 0 1.4rem; padding: .35rem; border: 1px solid var(--rule); background: var(--paper-2); scrollbar-width: thin; }
.evidence-nav a { flex: 0 0 auto; padding: .38rem .58rem; color: var(--ink-2); font-size: .73rem; font-weight: 650; text-decoration: none; }
.evidence-nav a:hover { color: var(--accent); background: var(--paper); }
.artifact-panel { margin-block: 1rem; border: 1px solid var(--rule); background: var(--paper); scroll-margin-top: 7.5rem; }
.artifact-heading { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding: .7rem .85rem; border-bottom: 1px solid var(--rule); background: var(--paper-2); }
.artifact-heading h2, .artifact-panel > h2 { margin: 0; font: 700 .88rem ui-sans-serif, system-ui, sans-serif; }
.raw-link { flex: 0 0 auto; font-size: .75rem; }
.artifact-meta { margin: 0; padding: .55rem .85rem; color: var(--muted); font-size: .72rem; border-bottom: 1px solid var(--rule); }
details summary { padding: .55rem .85rem; color: var(--ink-2); font-weight: 650; font-size: .78rem; cursor: pointer; }
.preview-scroll { max-height: 32rem; overflow: auto; border-top: 1px solid var(--rule); background: var(--code); scrollbar-width: thin; }
pre { margin: 0; padding: .85rem 1rem; min-width: max-content; font: .75rem/1.55 ui-monospace, "SFMono-Regular", Consolas, monospace; white-space: pre; tab-size: 2; color: var(--ink-2); }
.preview-note { margin: 0; padding: .6rem .85rem; color: var(--partial); font-size: .73rem; border-top: 1px solid var(--rule); }
code { font-family: ui-monospace, "SFMono-Regular", Consolas, monospace; overflow-wrap: anywhere; }
.raw-summary pre { min-width: 0; white-space: pre-wrap; }
.site-footer { margin-top: 3rem; padding-block: 1.2rem; border-top: 1px solid var(--rule); color: var(--muted); font-size: .75rem; }
.data-link { margin-block: 2rem; }
[hidden] { display: none !important; }
@media (max-width: 760px) {
  .header-inner, .site-footer, .page-shell, .breadcrumbs { width: min(100% - 1.4rem, var(--page-max)); }
  .site-header { position: static; }
  .header-inner { min-height: 3.2rem; }
  .site-title small { display: none; }
  .site-title { font-size: .9rem; }
  .theme-toggle { flex: 0 0 auto; }
  .page-shell { padding-top: 1rem; }
  .page-heading h1 { overflow-wrap: anywhere; }
  .experiment-card { grid-template-columns: 1fr; gap: .6rem; }
  .summary-metrics { grid-template-columns: 1fr 1fr; }
  .metric-wide { grid-column: 1 / -1; }
  .section-heading { align-items: end; }
  .filters { display: grid; grid-template-columns: 1fr 1fr auto; }
  .filters label:first-child { grid-column: 1 / -1; }
  .evidence-nav { top: 0; margin-inline: -.2rem; }
  .cell-table { border: 0; overflow: visible; background: transparent; }
  .cell-table table, .cell-table tbody, .cell-table tr, .cell-table td { display: block; width: 100%; }
  .cell-table thead, .cell-table caption { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .cell-table tr { margin-bottom: .65rem; padding: .72rem .78rem; border: 1px solid var(--rule); background: var(--paper); }
  .cell-table td { display: grid; grid-template-columns: minmax(7.4rem, 40%) 1fr; gap: .65rem; padding: .25rem 0; border: 0; overflow-wrap: anywhere; }
  .cell-table td::before { content: attr(data-label); color: var(--muted); font-size: .64rem; font-weight: 720; letter-spacing: .06em; text-transform: uppercase; }
  .cell-table td:first-child { padding-bottom: .48rem; margin-bottom: .25rem; border-bottom: 1px solid var(--rule); font-weight: 700; }
  .artifact-heading { align-items: flex-start; }
  .preview-scroll { max-height: 25rem; }
  pre { font-size: .7rem; }
}
@media (max-width: 420px) {
  .summary-metrics { grid-template-columns: 1fr 1fr; }
  .filters { grid-template-columns: 1fr 1fr; }
  .filters button { grid-column: 1 / -1; }
  .section-qualifier { display: block; margin: .25rem 0 0; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; } }
"""

JS = """(() => {
  const toggle = document.querySelector('[data-theme-toggle]');
  if (toggle) {
    toggle.hidden = false;
    let saved = null;
    try { saved = localStorage.getItem('cae-theme'); } catch (_) { /* storage is optional */ }
    if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
    toggle.addEventListener('click', () => {
      const current = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('cae-theme', next); } catch (_) { /* theme still works for this page */ }
    });
  }
})();

document.querySelectorAll('[data-cell-browser]').forEach((browser) => {
  const form = browser.querySelector('[data-cell-filters]');
  const rows = [...browser.querySelectorAll('[data-cell-row]')];
  const count = browser.querySelector('[data-filter-count]');
  if (!form) return;
  const apply = () => {
    const data = new FormData(form);
    const query = String(data.get('query') || '').trim().toLowerCase();
    const provider = String(data.get('provider') || '');
    const result = String(data.get('result') || '');
    let visible = 0;
    rows.forEach((row) => {
      const show = (!query || row.dataset.search.includes(query)) && (!provider || row.dataset.provider === provider) && (!result || row.dataset.result === result);
      row.hidden = !show;
      if (show) visible += 1;
    });
    if (count) count.textContent = `Showing ${visible} of ${rows.length} committed cells`;
  };
  form.addEventListener('input', apply);
  form.addEventListener('reset', () => setTimeout(apply));
  apply();
});
"""


def build_site(data_root: Path, output: Path, base_path: str = "") -> dict[str, Any]:
    data_root = data_root.resolve()
    output = output.resolve()
    base = _base_path(base_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        experiments = [
            _collect_experiment(data_root, report_root, temporary, base)
            for report_root in _discover_experiments(data_root)
        ]
        for experiment in experiments:
            slug = experiment["slug"]
            _json_write(temporary / "data" / "experiments" / f"{slug}.json", experiment)
            _html_write(temporary / "experiments" / slug / "index.html", _experiment_page(experiment, base))
            run_roots = {path.name: path for path in (data_root / "reports" / "experiments" / experiment["experiment_id"] / "evidence" / "runs").iterdir()} if (data_root / "reports" / "experiments" / experiment["experiment_id"] / "evidence" / "runs").is_dir() else {}
            for cell in experiment["cells"]:
                cell_slug = _safe_component(cell["cell_id"], "unknown-cell")
                _json_write(temporary / "data" / "experiments" / slug / "cells" / f"{cell_slug}.json", cell)
                _html_write(temporary / "experiments" / slug / "cells" / cell_slug / "index.html", _cell_page(cell, experiment, run_roots.get(cell["cell_id"]), base))
        site_data = {
            "schema_version": SCHEMA_VERSION,
            "base_path": base,
            "experiments": [
                {key: experiment[key] for key in ("experiment_id", "description", "stage", "summary", "page_url", "data_url", "warnings")}
                for experiment in experiments
            ],
        }
        _json_write(temporary / "data" / "site.json", site_data)
        _html_write(temporary / "index.html", _experiment_index(experiments, base))
        _html_write(temporary / "assets" / "site.css", CSS)
        _html_write(temporary / "assets" / "site.js", JS)
        _html_write(temporary / ".nojekyll", "")
        if output.exists():
            shutil.rmtree(output)
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return site_data


def validate_site(site: Path) -> list[str]:
    site = site.resolve()
    errors: list[str] = []
    site_data = _read_json(site / "data" / "site.json", errors)
    if not isinstance(site_data, dict):
        errors.append("data/site.json is missing or invalid")
        return errors
    base = site_data.get("base_path")
    if not isinstance(base, str):
        errors.append("data/site.json has no string base_path")
        base = ""
    for required in ("index.html", "assets/site.css", "assets/site.js", ".nojekyll"):
        if not (site / required).is_file():
            errors.append(f"Missing required output: {required}")
    for json_path in sorted(site.rglob("*.json")):
        try:
            json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"Invalid generated JSON {json_path.relative_to(site)}: {error}")
    for html_path in sorted(site.rglob("*.html")):
        text = html_path.read_text(encoding="utf-8")
        if '<main id="main"' not in text or "Skip to content" not in text:
            errors.append(f"Missing accessibility landmarks: {html_path.relative_to(site)}")
        for marker in ('href="', 'src="'):
            for fragment in text.split(marker)[1:]:
                target = fragment.split('"', 1)[0]
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or target.startswith("#"):
                    continue
                if not parsed.path.startswith(f"{base}/") and parsed.path != f"{base}/":
                    errors.append(f"URL outside base path in {html_path.relative_to(site)}: {target}")
                    continue
                relative = parsed.path[len(base) :].lstrip("/")
                candidate = site / relative
                if parsed.path.endswith("/"):
                    candidate = candidate / "index.html"
                if not candidate.is_file():
                    errors.append(f"Broken local URL in {html_path.relative_to(site)}: {target}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="Build the static site")
    build_parser.add_argument("--data-root", type=Path, default=Path("."))
    build_parser.add_argument("--output", type=Path, default=Path("_site"))
    build_parser.add_argument("--base-path", default="")
    validate_parser = subparsers.add_parser("validate", help="Validate a generated site")
    validate_parser.add_argument("--site", type=Path, default=Path("_site"))
    args = parser.parse_args(argv)
    if args.command == "build":
        result = build_site(args.data_root, args.output, args.base_path)
        cells = sum(item["summary"]["discovered_cells"] for item in result["experiments"])
        print(f"Built {args.output}: {len(result['experiments'])} experiments, {cells} cells")
        return 0
    errors = validate_site(args.site)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Validated {args.site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
