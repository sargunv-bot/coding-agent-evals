#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /app

set +e
{
  python3 /tests/check_alternative.py
  alternative_status=$?
  if [[ $alternative_status -eq 0 ]]; then
    cargo test --locked --bin mise github:: -- --nocapture
    status=$?
  elif [[ $alternative_status -eq 1 ]]; then
    # The candidate chose the independently supported bridge design, but its
    # semantics are unsafe. Preserve the checker's focused behavioral reason.
    status=1
  else
    # This is not the bridge design. Exercise the batch-subject design used by
    # upstream without requiring every candidate to expose those private names.
    cat /tests/hidden_sigstore_tests.rs.inc >> /app/crates/mise-sigstore/src/lib.rs
    cargo test --locked -p mise-sigstore hidden_slsa_subject_coverage -- --nocapture
    sigstore_status=$?
    if [[ $sigstore_status -ne 0 ]]; then
      status=$sigstore_status
    else
    # The batch-subject design can be exercised directly. Append its archive
    # safety checks only after confirming that API exists, so an independently
    # designed candidate is not rejected for missing private gold symbols.
      cat /tests/hidden_file_tests.rs.inc >> /app/src/file.rs
      cargo test --locked --bin mise hidden_archive_content_security -- --nocapture
      status=$?
    fi
  fi
} > /logs/verifier/test-stdout.txt 2>&1
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
