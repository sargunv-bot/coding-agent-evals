#!/usr/bin/env bash
set -uo pipefail

cd /app || exit 0
mkdir -p /logs/artifacts
git config --global --add safe.directory /app 2>/dev/null || true

base_commit="$(git rev-list --max-parents=0 HEAD | head -n1)"
git add --all 2>/dev/null || true
git diff --cached --binary --full-index "${base_commit}" -- \
  > /logs/artifacts/model.patch 2>/dev/null || true
printf '[pre_artifacts] captured %s bytes\n' "$(wc -c < /logs/artifacts/model.patch)"
