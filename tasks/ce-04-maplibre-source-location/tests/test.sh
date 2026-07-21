#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier /tmp/ce04
cd /app

set +e
(
  set -e
  cmake --build build-linux-opengl --target mbgl-core --parallel 2
  python3 /tests/compile_behavior.py
) > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e

if [[ $status -eq 0 ]]; then
  printf '{"reward":1,"native":1,"fallback":1,"manifests":1}\n' > /logs/verifier/reward.json
  test_status=passed
else
  printf '{"reward":0,"native":0,"fallback":0,"manifests":0}\n' > /logs/verifier/reward.json
  test_status=failed
fi
printf '{"results":{"tool":{"name":"ce-04-verifier"},"summary":{"tests":1,"passed":%s,"failed":%s},"tests":[{"name":"source location native and fallback behavior","status":"%s"}]}}\n' "$(( status == 0 ))" "$(( status != 0 ))" "$test_status" > /logs/verifier/ctrf.json
exit "$status"
