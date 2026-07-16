#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cat /tests/hidden_sigstore_tests.rs.inc >> /app/crates/mise-sigstore/src/lib.rs
cat /tests/hidden_file_tests.rs.inc >> /app/src/file.rs
cd /app

set +e
(
  set -e
  cargo test --locked -p mise-sigstore hidden_slsa_subject_coverage -- --nocapture
  cargo test --locked --bin mise hidden_archive_content_security -- --nocapture
) > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e
if [[ $status -eq 0 ]]; then
  printf '{"reward":1,"archive_safety":1,"subject_coverage":1,"fail_closed":1}\n' > /logs/verifier/reward.json
  test_status=passed
else
  printf '{"reward":0,"archive_safety":0,"subject_coverage":0,"fail_closed":0}\n' > /logs/verifier/reward.json
  test_status=failed
fi
printf '{"results":{"tool":{"name":"ce-05-verifier"},"summary":{"tests":1,"passed":%s,"failed":%s},"tests":[{"name":"archive-content SLSA fail-closed behavior","status":"%s"}]}}\n' "$(( status == 0 ))" "$(( status != 0 ))" "$test_status" > /logs/verifier/ctrf.json
exit "$status"
