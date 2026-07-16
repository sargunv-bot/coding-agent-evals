#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cp /tests/composition_hidden.rs /app/tests/composition_hidden.rs
cp /tests/composition-hidden-schema.json /app/tests/composition-hidden-schema.json
cd /app

set +e
cargo test --locked --test composition_hidden --test lsp_completion > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e

if [[ $status -eq 0 ]]; then
  printf '{"reward":1,"behavioral":1,"regression":1}\n' > /logs/verifier/reward.json
  test_status=passed
else
  printf '{"reward":0,"behavioral":0,"regression":0}\n' > /logs/verifier/reward.json
  test_status=failed
fi
printf '{"results":{"tool":{"name":"ce-03-verifier"},"summary":{"tests":1,"passed":%s,"failed":%s},"tests":[{"name":"composed schema LSP behavior","status":"%s"}]}}\n' "$(( status == 0 ))" "$(( status != 0 ))" "$test_status" > /logs/verifier/ctrf.json
exit "$status"
