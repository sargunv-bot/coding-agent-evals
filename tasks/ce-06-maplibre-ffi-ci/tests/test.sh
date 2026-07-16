#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /app
set +e
/opt/venv/bin/python /tests/verify_workflow.py > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e
if [[ $status -eq 0 ]]; then
  printf '{"reward":1,"determinism":1,"strictness":1,"structure":1}\n' > /logs/verifier/reward.json
  test_status=passed
else
  printf '{"reward":0,"determinism":0,"strictness":0,"structure":0}\n' > /logs/verifier/reward.json
  test_status=failed
fi
printf '{"results":{"tool":{"name":"ce-06-verifier"},"summary":{"tests":1,"passed":%s,"failed":%s},"tests":[{"name":"manifest-driven deterministic workflow generation","status":"%s"}]}}\n' "$(( status == 0 ))" "$(( status != 0 ))" "$test_status" > /logs/verifier/ctrf.json
exit "$status"
