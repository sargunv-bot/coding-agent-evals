#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for manifest in sorted((root / "tasks").glob("ce-*/task.toml")):
        task = manifest.parent
        data = tomllib.loads(manifest.read_text())
        metadata = data["metadata"]
        gold = task / "solution/solution.patch"
        containerfile = task / "environment/Containerfile"
        instruction = task / "instruction.md"
        lines = [
            'schema_version = "1.0"',
            f"task_id = {quote(metadata['task_id'])}",
            f"repository_url = {quote(metadata['repository_url'])}",
            f"base_commit = {quote(metadata['base_commit_hash'])}",
            f"gold_commit = {quote(metadata['gold_commit_hash'])}",
            f"track = {quote(metadata['track'])}",
            f"upstream_license = {quote(metadata['upstream_license'])}",
            'distribution = "private-evaluation-only"',
            f"gold_patch_sha256 = {quote(sha256(gold))}",
            f"gold_patch_bytes = {gold.stat().st_size}",
            f"instruction_sha256 = {quote(sha256(instruction))}",
            f"containerfile_sha256 = {quote(sha256(containerfile))}",
            "",
            "[mutants]",
        ]
        for mutant in sorted((task / "mutants").glob("*.patch")):
            lines.append(f"{quote(mutant.name)} = {quote(sha256(mutant))}")
        scenarios = sorted((task / "scenarios").glob("*/scenario.toml"))
        if scenarios:
            lines += ["", "[scenarios]"]
            for scenario_manifest in scenarios:
                scenario_data = tomllib.loads(scenario_manifest.read_text())
                gold_path = (scenario_manifest.parent / scenario_data["gold_patch"]).resolve()
                lines.append(f"{quote(scenario_data['scenario_id'])} = {quote(sha256(gold_path))}")
            lines += ["", "[scenario_mutants]"]
            for scenario_manifest in scenarios:
                scenario_id = tomllib.loads(scenario_manifest.read_text())["scenario_id"]
                for mutant in sorted((scenario_manifest.parent / "mutants").glob("*.patch")):
                    key = f"{scenario_id}/{mutant.name}"
                    lines.append(f"{quote(key)} = {quote(sha256(mutant))}")
        (task / "provenance.toml").write_text("\n".join(lines) + "\n")
        print(task.name)


if __name__ == "__main__":
    main()
