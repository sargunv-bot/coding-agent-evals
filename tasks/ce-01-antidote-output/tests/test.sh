#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier

started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set +e
zsh /tests/test_behavior.zsh > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e

if [[ $status -eq 0 ]]; then
  reward=1
  test_status=passed
else
  reward=0
  test_status=failed
fi

python3 - "$reward" "$test_status" "$started" <<'PY'
import json, pathlib, sys
reward, status, started = sys.argv[1:]
out = pathlib.Path('/logs/verifier')
(out / 'reward.json').write_text(json.dumps({'reward': int(reward), 'behavioral': int(reward)}, indent=2) + '\n')
(out / 'ctrf.json').write_text(json.dumps({
    'results': {
        'tool': {'name': 'ce-01-verifier'},
        'summary': {'tests': 1, 'passed': int(status == 'passed'), 'failed': int(status != 'passed')},
        'tests': [{'name': 'noisy git output isolation', 'status': status}],
    },
    'started_at': started,
}, indent=2) + '\n')
PY

exit "$status"
