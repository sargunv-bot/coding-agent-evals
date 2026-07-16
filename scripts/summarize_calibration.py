#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

EXPECTED = {
    "ce-01-antidote-output",
    "ce-02-horologia-overdue",
    "ce-03-jvl-completions",
    "ce-04-maplibre-source-location",
    "ce-05-mise-slsa-archive",
    "ce-06-maplibre-ffi-ci",
    "ce-07-validation-fail-fast",
    "ce-07-all-errors-as-result",
}


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "reports" / "calibration"
    actual = {path.stem for path in root.glob("ce-*.json") if path.stat().st_size}
    missing = sorted(EXPECTED - actual)
    if missing:
        raise SystemExit(f"missing calibration records: {', '.join(missing)}")

    summary = {}
    for stem in sorted(EXPECTED):
        path = root / f"{stem}.json"
        rows = json.loads(path.read_text())
        if not all(row["expectation_met"] for row in rows):
            raise SystemExit(f"calibration expectation failed: {path}")
        for row in rows:
            row["run_dir"] = Path(row["run_dir"]).name
        path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        summary[stem] = {
            "controls": len(rows),
            "expectations_met": sum(row["expectation_met"] for row in rows),
            "gold_passes": sum(
                row["control"] == "gold" and row["outcome"] == "passed" for row in rows
            ),
            "infrastructure_errors": sum(row["outcome"] == "infrastructure_error" for row in rows),
            "mutants_rejected": sum(
                row["control"] == "mutant" and row["outcome"] == "failed" for row in rows
            ),
            "runtime_seconds": round(sum(row["duration_seconds"] for row in rows), 3),
        }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
