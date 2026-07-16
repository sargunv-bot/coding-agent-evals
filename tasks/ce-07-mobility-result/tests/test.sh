#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
scenario="${CAE_SCENARIO:-validation-fail-fast}"

copy_tree() {
  local source=$1
  if [[ -d "$source" ]]; then
    cp -R "$source"/. /app/
  fi
}
copy_tree /tests/common
if [[ "$scenario" == "all-errors-as-result" ]]; then
  copy_tree /scenario-tests
elif [[ "$scenario" != "validation-fail-fast" ]]; then
  printf 'unknown scenario: %s\n' "$scenario" > /logs/verifier/test-stdout.txt
  printf '{"infrastructure_error":true,"reward":0}\n' > /logs/verifier/reward.json
  exit 64
fi

cd /app
set +e
./gradlew --offline --no-daemon \
  :gbfs-v1:jvmTest --tests '*ResultErrorHandlingTest*' \
  :gbfs-v2:jvmTest --tests '*ResultErrorHandlingTest*' \
  :gbfs-v3:jvmTest --tests '*ResultErrorHandlingTest*' \
  :gofs-v1:jvmTest --tests '*ResultErrorHandlingTest*' \
  :gbfs-v1:checkKotlinAbi :gbfs-v1:checkLegacyAbi \
  :gbfs-v2:checkKotlinAbi :gbfs-v2:checkLegacyAbi \
  :gbfs-v3:checkKotlinAbi :gbfs-v3:checkLegacyAbi \
  :gofs-v1:checkKotlinAbi :gofs-v1:checkLegacyAbi \
  > /logs/verifier/test-stdout.txt 2>&1
status=$?
set -e

if [[ $status -eq 0 ]]; then
  printf '{"reward":1,"behavioral":1,"api":1,"regression":1}\n' > /logs/verifier/reward.json
  test_status=passed
else
  printf '{"reward":0,"behavioral":0,"api":0,"regression":0}\n' > /logs/verifier/reward.json
  test_status=failed
fi
printf '{"results":{"tool":{"name":"ce-07-verifier"},"summary":{"tests":1,"passed":%s,"failed":%s},"tests":[{"name":"Result API and error semantics","status":"%s"}]}}\n' "$(( status == 0 ))" "$(( status != 0 ))" "$test_status" > /logs/verifier/ctrf.json
exit "$status"
