#!/usr/bin/env bash
set -euo pipefail
cd /app
command -v rg >/dev/null
command -v clitest >/dev/null
command -v asciidoctor >/dev/null
make buildman
test_root="$(mktemp -d)"
trap 'rm -rf "$test_root"' EXIT
cp -a /app/. "$test_root/"
cd "$test_root"
make test
make unittest
