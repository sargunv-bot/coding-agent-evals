from __future__ import annotations

import json
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .review import ProctorReview

IDENTITY_KEYS = {"model", "modelid", "provider", "providerid"}
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
            if key.lower().replace("_", "") not in IDENTITY_KEYS
        }
    if isinstance(value, list):
        return [_sanitize(item, replacements) for item in value]
    if isinstance(value, str):
        sanitized = value
        for identity in replacements:
            if identity:
                sanitized = sanitized.replace(identity, "[candidate-identity-withheld]")
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
    if not results_root.is_dir():
        raise ReviewPacketError(f"experiment results not found: {results_root}")
    if _inside(mapping_path, output_root):
        raise ReviewPacketError("trusted mapping must be outside the reviewer packet tree")

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
        (packet / "instruction.txt").write_bytes(instruction.read_bytes())
        (packet / "patch.diff").write_bytes(patch.read_bytes())

        trajectory_data = json.loads(trajectory.read_text())
        identities = [
            str(cell.get("provider", "")),
            str(cell.get("model", "")),
            str(result.get("provider", "")),
            str(result.get("model", "")),
            str(cell.get("cell_id", "")),
        ]
        sanitized = _sanitize(trajectory_data, sorted(set(identities), key=len, reverse=True))
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
    mapping_path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n")
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
    mapping = json.loads(mapping_path.read_text())
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

    review = ProctorReview(
        run_id=entry["run_id"],
        task_id=entry["task_id"],
        proctor=proctor,
        proctor_model=proctor_model,
        blinded_to_model_identity=True,
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
    output_path = repo_root / entry["review_path"]
    review.write(output_path)
    return review
