#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cp /tests/overdue_action_hidden_test.go /app/server/internal/taskengine/overdue_action_hidden_test.go
cd /app/server

set +e
go test ./internal/taskengine -run '^(TestValidateOverdueActionRule|TestHiddenOverdueActionBehaviorMatrix)$' -count=1 > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e

if [[ $status -eq 0 ]]; then
  printf '{"reward":1,"behavioral":1,"regression":1}\n' > /logs/verifier/reward.json
  test_status=passed
else
  printf '{"reward":0,"behavioral":0,"regression":0}\n' > /logs/verifier/reward.json
  test_status=failed
fi
printf '{"results":{"tool":{"name":"ce-02-verifier"},"summary":{"tests":1,"passed":%s,"failed":%s},"tests":[{"name":"overdue action behavior matrix","status":"%s"}]}}\n' "$(( status == 0 ))" "$(( status != 0 ))" "$test_status" > /logs/verifier/ctrf.json
exit "$status"
