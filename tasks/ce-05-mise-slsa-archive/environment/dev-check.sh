#!/usr/bin/env bash
set -euo pipefail
command -v rg >/dev/null
cd /app
cargo fmt --check
cargo clippy --locked -p mise-sigstore --all-targets -- -D warnings
cargo clippy --locked --bin mise -- -D warnings
cargo build --locked --all-features
cargo test --locked -p mise-sigstore
cargo test --locked --bin mise
