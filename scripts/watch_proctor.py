#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def pending(runs: Path) -> list[dict]:
    rows: list[dict] = []
    for question_path in sorted(runs.glob("*/proctor/questions/*.json")):
        answer_path = question_path.parents[1] / "answers" / question_path.name
        if answer_path.exists():
            continue
        try:
            question = json.loads(question_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "run_id": question_path.parents[2].name,
                "queue": str(question_path.parents[1]),
                "question_id": question.get("question_id"),
                "task_id": question.get("task_id"),
                "question": question.get("question"),
                "asked_at": question.get("asked_at"),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Watch for unanswered coding-eval proctor questions"
    )
    parser.add_argument("--runs", type=Path, default=Path(".runs"))
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    started = time.monotonic()
    while True:
        rows = pending(args.runs)
        if rows or not args.wait:
            print(json.dumps(rows, indent=2, sort_keys=True))
            return 0
        if args.timeout and time.monotonic() - started >= args.timeout:
            print("[]")
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
