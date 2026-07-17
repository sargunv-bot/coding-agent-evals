#!/usr/bin/env bash
set -euo pipefail
command -v rg >/dev/null
cd /app
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked