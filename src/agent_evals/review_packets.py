from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .review import ProctorReview

IDENTITY_KEYS = {"model", "modelid", "modelname", "provider", "providerid", "providername"}
SCORE_FIELDS = (
    "scope_discipline",
    "code_clarity",
    "test_quality",
    "repository_fit",
    "security_and_safety",
)
RESPONSE_FIELDS = {
    *SCORE_FIELDS,
    "mergeable",
    "blockers",
    "strengths",
    "summary",
    "rating_rationales",
    "overall_reasoning",
    "model_identity_blinded",
}


class ReviewPacketError(RuntimeError):
    pass


def _final_result(document: dict[str, Any]) -> dict[str, Any]:
    for attempt in reversed(document.get("attempts", [])):
        if attempt.get("kind") == "completed" and isinstance(attempt.get("result"), dict):
            return attempt["result"]
    raise ReviewPacketError("result has no completed attempt")


def _sanitize(value: Any, replacements: list[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item, replacements)
            for key, item in value.items()
            if re.sub(r"[^a-z0-9]", "", key.lower()) not in IDENTITY_KEYS
        }
    if isinstance(value, list):
        return [_sanitize(item, replacements) for item in value]
    if isinstance(value, str):
        sanitized = value
        for identity in replacements:
            if identity:
                sanitized = re.sub(
                    re.escape(identity),
                    "[candidate-identity-withheld]",
                    sanitized,
                    flags=re.IGNORECASE,
                )
        return sanitized
    return value


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def prepare_review_packets(
    repo_root: Path,
    experiment_id: str,
    output_root: Path,
    mapping_path: Path,
) -> dict[str, Any]:
    experiment_root = repo_root / ".runs" / "experiments" / experiment_id
    results_root = experiment_root / "results"
    mappings_root = experiment_root / "review-mappings"
    if not results_root.is_dir():
        raise ReviewPacketError(f"experiment results not found: {results_root}")
    if _inside(output_root, experiment_root):
        raise ReviewPacketError("reviewer packets must be outside the experiment evidence tree")
    if _inside(mapping_path, output_root):
        raise ReviewPacketError("trusted mapping must be outside the reviewer packet tree")
    if not _inside(mapping_path, mappings_root):
        raise ReviewPacketError(f"trusted mapping must be inside {mappings_root}")
    if mapping_path.exists():
        raise ReviewPacketError(f"trusted mapping already exists: {mapping_path}")

    output_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    for result_path in sorted(results_root.glob("*.json")):
        document = json.loads(result_path.read_text())
        if document.get("state") != "completed":
            continue
        result = _final_result(document)
        cell = document["cell"]
        run_id = result["run_id"]
        task_id = result["task_id"]
        run_root = repo_root / ".runs" / run_id
        instruction = run_root / "config" / "instruction.txt"
        patch = Path(result["patch_path"])
        trajectory = Path(result["trajectory_path"])
        for required in (instruction, patch, trajectory):
            if not required.is_file():
                raise ReviewPacketError(f"missing review input: {required}")

        packet_id = secrets.token_hex(16)
        packet = output_root / packet_id
        packet.mkdir()
        identities = [
            str(cell.get("provider", "")),
            str(cell.get("model", "")),
            str(result.get("provider", "")),
            str(result.get("model", "")),
            str(cell.get("cell_id", "")),
        ]
        replacements = sorted(set(identities), key=len, reverse=True)
        (packet / "instruction.txt").write_text(_sanitize(instruction.read_text(), replacements))
        (packet / "patch.diff").write_text(_sanitize(patch.read_text(), replacements))

        trajectory_data = json.loads(trajectory.read_text())
        sanitized = _sanitize(trajectory_data, replacements)
        (packet / "trajectory.json").write_text(
            json.dumps(sanitized, indent=2, sort_keys=True) + "\n"
        )
        entries.append(
            {
                "packet_id": packet_id,
                "cell_id": cell["cell_id"],
                "run_id": run_id,
                "task_id": task_id,
                "result_path": str(result_path.relative_to(repo_root)),
                "review_path": str(
                    (experiment_root / "reviews" / f"{result_path.stem}.json").relative_to(repo_root)
                ),
            }
        )

    mapping = {"experiment_id": experiment_id, "packets": entries}
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with mapping_path.open("x") as stream:
        stream.write(json.dumps(mapping, indent=2, sort_keys=True) + "\n")
    return {"experiment_id": experiment_id, "packets": len(entries), "output": str(output_root)}


def finalize_review(
    repo_root: Path,
    mapping_path: Path,
    packet_id: str,
    response_path: Path,
    *,
    proctor: str,
    proctor_model: str,
) -> ProctorReview:
    experiments_root = repo_root / ".runs" / "experiments"
    if not _inside(mapping_path, experiments_root):
        raise ReviewPacketError("trusted mapping must be inside the experiment tree")
    mapping = json.loads(mapping_path.read_text())
    experiment_root = experiments_root / mapping["experiment_id"]
    mappings_root = experiment_root / "review-mappings"
    results_root = experiment_root / "results"
    reviews_root = experiment_root / "reviews"
    if not _inside(mapping_path, mappings_root):
        raise ReviewPacketError("trusted mapping is outside the canonical mapping directory")
    if not _inside(results_root, experiment_root) or not _inside(reviews_root, experiment_root):
        raise ReviewPacketError("experiment result or review directory escapes the experiment tree")
    matches = [entry for entry in mapping["packets"] if entry["packet_id"] == packet_id]
    if len(matches) != 1:
        raise ReviewPacketError(f"unknown or duplicate packet id: {packet_id}")
    entry = matches[0]
    response = json.loads(response_path.read_text())
    if not isinstance(response, dict):
        raise ReviewPacketError("review response must be a JSON object")
    unexpected = sorted(set(response) - RESPONSE_FIELDS)
    missing = sorted(RESPONSE_FIELDS - set(response))
    if unexpected or missing:
        raise ReviewPacketError(f"review response fields: missing={missing}, unexpected={unexpected}")
    if any(type(response[name]) is not int for name in SCORE_FIELDS):
        raise ReviewPacketError("all five review scores must be integers")
    if response["model_identity_blinded"] is not True:
        raise ReviewPacketError("model_identity_blinded must be true")
    if type(response["mergeable"]) is not bool:
        raise ReviewPacketError("mergeable must be a boolean")

    result_path = repo_root / entry["result_path"]
    if not _inside(result_path, results_root) or not result_path.is_file():
        raise ReviewPacketError("deterministic result path is outside canonical results")
    output_path = repo_root / entry["review_path"]
    expected_output = reviews_root / result_path.name
    if output_path.resolve() != expected_output.resolve() or not _inside(output_path, reviews_root):
        raise ReviewPacketError("review path is outside canonical reviews")


    review = ProctorReview(
        run_id=entry["run_id"],
        task_id=entry["task_id"],
        proctor=proctor,
        proctor_model=proctor_model,
        blinded_to_model_identity=response["model_identity_blinded"],
        scope_discipline=response["scope_discipline"],
        code_clarity=response["code_clarity"],
        test_quality=response["test_quality"],
        repository_fit=response["repository_fit"],
        security_and_safety=response["security_and_safety"],
        mergeable=response["mergeable"],
        blockers=response["blockers"],
        strengths=response["strengths"],
        summary=response["summary"],
        rating_rationales=response["rating_rationales"],
        overall_reasoning=response["overall_reasoning"],
        deterministic_result_path=entry["result_path"],
        can_override_deterministic=False,
    )
    errors = review.validate()
    if errors:
        raise ReviewPacketError("; ".join(errors))
    if not review.blinded_to_model_identity or review.can_override_deterministic:
        raise ReviewPacketError("finalized review must be blinded and non-overriding")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x") as stream:
            stream.write(json.dumps(asdict(review), indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise ReviewPacketError(f"review already exists: {output_path}") from exc
    return review
