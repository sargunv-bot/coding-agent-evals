#!/usr/bin/env python3
"""Fetch exact replay commits and export historical binary patches.

This script is a maintainer tool. Gold patches remain evaluator-only and are never
copied into agent images.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    task_id: str
    repo: str
    base: str
    gold: str


TASKS = (
    Task(
        "ce-01-antidote-output",
        "mattmc3/antidote",
        "61a07ca521e8f811bbcd6da74a244119209980cb",
        "f4c883c757c449e44f31af8d611a6b3441ce45a4",
    ),
    Task(
        "ce-02-horologia-overdue",
        "sargunv/horologia",
        "1e90747f596becdb06d8cd8729f9a3df7853cdac",
        "9b6335019e5f66d04ea2b5ff22d50d4d69d94ea4",
    ),
    Task(
        "ce-03-jvl-completions",
        "sargunv/jvl",
        "5e38284088677a138458b3b938f35da62b987398",
        "ac0c74d42890fad44238728159f1061d52dfcc8a",
    ),
    Task(
        "ce-04-maplibre-source-location",
        "maplibre/maplibre-native",
        "5602ad8bd357c1ffb2b63b8d45de1d85123fdb58",
        "f6d70e954b07fdadf6a5adda8da49e73178298c6",
    ),
    Task(
        "ce-05-mise-slsa-archive",
        "jdx/mise",
        "5aea2e1d0df40673dd5fbd7607109e0ebb136d02",
        "3fd427f3be122bd70a2b00f3e21b1a05c74d8d6e",
    ),
    Task(
        "ce-06-maplibre-ffi-ci",
        "maplibre/maplibre-native-ffi",
        "4fa163923d35aae4099417206a7345b52c2fbdc2",
        "c0da43b1c0b48bc88b8d9964e8aff86e55d2285d",
    ),
    Task(
        "ce-07-mobility-result",
        "sargunv/mobility-data-kt",
        "541fc977a939501693a195057d0d1ce39188b522",
        "1334676fae7409daa93cd6316285c24b5a7af571",
    ),
)


def run(*args: str, cwd: Path | None = None, capture: bool = False) -> bytes:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=capture)
    return result.stdout if capture else b""


def fetch(task: Task, cache: Path, tasks_dir: Path) -> None:
    checkout = cache / task.task_id
    checkout.mkdir(parents=True, exist_ok=True)
    if not (checkout / ".git").exists():
        run("git", "init", "--quiet", str(checkout))
        run("git", "remote", "add", "origin", f"https://github.com/{task.repo}.git", cwd=checkout)
    run(
        "git",
        "fetch",
        "--quiet",
        "--depth=2",
        "--filter=blob:none",
        "origin",
        task.gold,
        cwd=checkout,
    )
    parent = run("git", "rev-parse", f"{task.gold}^", cwd=checkout, capture=True).decode().strip()
    if parent != task.base:
        raise RuntimeError(f"{task.task_id}: expected gold parent {task.base}, got {parent}")
    patch = run("git", "diff", "--binary", task.base, task.gold, cwd=checkout, capture=True)
    solution = tasks_dir / task.task_id / "solution"
    solution.mkdir(parents=True, exist_ok=True)
    (solution / "solution.patch").write_bytes(patch)
    print(f"{task.task_id}: {len(patch):,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_ids", nargs="*")
    parser.add_argument("--cache", type=Path, default=Path(".cache/upstreams"))
    parser.add_argument("--tasks", type=Path, default=Path("tasks"))
    args = parser.parse_args()
    selected = [task for task in TASKS if not args.task_ids or task.task_id in args.task_ids]
    unknown = set(args.task_ids) - {task.task_id for task in TASKS}
    if unknown:
        parser.error(f"unknown task IDs: {', '.join(sorted(unknown))}")
    for task in selected:
        fetch(task, args.cache, args.tasks)


if __name__ == "__main__":
    main()
