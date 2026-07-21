#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /app
set +e
(
  set -e
  cargo test --locked -p mise-sigstore
  python3 /tests/verify_cli.py
) > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e
python3 - "$status" <<'PY'
import json
import pathlib
import sys
status = int(sys.argv[1])
pathlib.Path("/logs/verifier/reward.json").write_text(json.dumps({"reward": 1 if status == 0 else 0}) + "\n")
PY
exit "$status"
