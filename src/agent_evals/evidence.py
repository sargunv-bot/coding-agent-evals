from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .review import ProctorReview

_SECRET_PATTERNS = (
    re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
)


class EvidenceExportError(RuntimeError):
    pass


def export_experiment_evidence(repo_root: Path, experiment_id: str, output: Path) -> dict:
    repo_root = repo_root.resolve()
    runs_root = repo_root / ".runs"
    experiment_root = runs_root / "experiments" / experiment_id
    result_root = experiment_root / "results"
    if not result_root.is_dir():
        raise EvidenceExportError(f"experiment results not found: {experiment_id}")

    output = output.resolve()
    if repo_root not in output.parents:
        raise EvidenceExportError("evidence output must be inside the repository")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    exported: list[dict] = []
    for result_path in sorted(result_root.glob("*.json")):
        record = json.loads(result_path.read_text())
        attempts = record.get("attempts") or []
        result = attempts[-1].get("result") if attempts else None
        if not isinstance(result, dict):
            continue
        run_id = result.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise EvidenceExportError(f"missing run_id in {result_path.name}")
        run_root = _contained(runs_root / run_id, runs_root)
        destination = output / "runs" / result_path.stem
        destination.mkdir(parents=True)

        artifacts: list[tuple[Path, Path]] = [
            (run_root / "logs/agent/opencode.jsonl", destination / "transcript.jsonl"),
            (run_root / "logs/agent/model.patch", destination / "model.patch"),
            (run_root / "config/instruction.txt", destination / "instruction.txt"),
            (run_root / "config/opencode.json", destination / "opencode.json"),
        ]
        verification = result.get("verification")
        if isinstance(verification, dict) and verification.get("run_dir"):
            verifier_root = _contained(Path(str(verification["run_dir"])), runs_root)
            artifacts.extend(
                [
                    (
                        verifier_root / "logs/verifier/test-stdout.txt",
                        destination / "verifier/stdout.txt",
                    ),
                    (
                        verifier_root / "logs/verifier/test-stderr.txt",
                        destination / "verifier/stderr.txt",
                    ),
                ]
            )

        for source, target in artifacts:
            if source.is_file():
                _copy_checked(source, target, repo_root)

        sanitized = json.loads(json.dumps(record))
        sanitized_result = sanitized["attempts"][-1]["result"]
        sanitized_result["patch_path"] = "model.patch"
        sanitized_result["trajectory_path"] = "transcript.jsonl"
        if isinstance(sanitized_result.get("verification"), dict):
            sanitized_result["verification"]["run_dir"] = "verifier"
        matrix_record = destination / "matrix-record.json"
        matrix_record.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n")
        _scan(matrix_record.read_bytes(), matrix_record, repo_root)

        review_source = experiment_root / "reviews" / f"{result_path.stem}.json"
        if review_source.is_file():
            review_data = json.loads(review_source.read_text())
            review = ProctorReview(**review_data)
            errors = review.validate()
            if errors:
                detail = "; ".join(errors)
                raise EvidenceExportError(f"invalid review {review_source.name}: {detail}")
            _copy_checked(review_source, destination / "proctor-review.json", repo_root)

        manifest = _artifact_manifest(destination)
        (destination / "artifacts.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        exported.append(
            {
                "cell_id": result_path.stem,
                "run_id": run_id,
                "artifacts": len(manifest),
            }
        )

    lock_source = experiment_root / "lock.json"
    if lock_source.is_file():
        _copy_checked(lock_source, output / "execution-lock.json", repo_root)
    summary = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "runs": exported,
    }
    (output / "index.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (output / "README.md").write_text(
        "# Experiment evidence\n\n"
        "Each directory under `runs/` is keyed by the immutable experiment cell ID. "
        "`transcript.jsonl` is the canonical raw OpenCode event stream; `model.patch` is "
        "the complete candidate diff; `matrix-record.json` contains deterministic scoring "
        "and normalized usage; `verifier/` contains hidden-verifier output; and "
        "`proctor-review.json`, when present, contains non-overriding qualitative scores "
        "with per-dimension rationale. `artifacts.json` records byte sizes and SHA-256 "
        "digests for every run artifact.\n"
    )
    return summary


def _contained(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise EvidenceExportError(f"artifact path escapes run root: {path}")
    return resolved


def _copy_checked(source: Path, target: Path, repo_root: Path) -> None:
    data = source.read_bytes()
    _scan(data, source, repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _scan(data: bytes, source: Path, repo_root: Path) -> None:
    if str(repo_root).encode() in data:
        raise EvidenceExportError(f"host repository path found in {source}")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(data):
            raise EvidenceExportError(f"credential-like material found in {source}")
    for name, value in os.environ.items():
        credential_name = name.endswith("_API_KEY") or name.endswith("_TOKEN")
        if credential_name and len(value) >= 12 and value.encode() in data:
            raise EvidenceExportError(f"environment credential {name} found in {source}")


def _artifact_manifest(root: Path) -> list[dict[str, Any]]:
    manifest = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == "artifacts.json":
            continue
        data = path.read_bytes()
        manifest.append(
            {
                "path": str(path.relative_to(root)),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return manifest
