#!/usr/bin/env bash
set -euo pipefail
command -v rg >/dev/null
cd /app
python3 -c 'import sys; assert sys.version_info[:2] == (3, 14)'
uv sync --offline --locked
uv run --offline ruff check .
uv run --offline ty check
generator=.mise/tasks/ci/generate-workflow
if [[ -f "$generator" ]]; then
    python3 -c 'from pathlib import Path; compile(Path(".mise/tasks/ci/generate-workflow").read_text(), ".mise/tasks/ci/generate-workflow", "exec")'
    "$generator" --check
fi
