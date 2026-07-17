#!/usr/bin/env bash
set -euo pipefail
command -v rg >/dev/null
command -v git-lfs >/dev/null
cd /app
git lfs fsck

before_diff="$(git diff --binary | sha256sum)"
before_status="$(git status --porcelain)"
./gradlew --offline --no-daemon --stacktrace updateKotlinAbi updateLegacyAbi
test "$before_diff" = "$(git diff --binary | sha256sum)"
test "$before_status" = "$(git status --porcelain)"

./gradlew --offline --no-daemon --stacktrace \
    jvmTest jsNodeTest wasmJsNodeTest linuxX64Test detekt checkKotlinAbi checkLegacyAbi
test "$before_diff" = "$(git diff --binary | sha256sum)"
test "$before_status" = "$(git status --porcelain)"
