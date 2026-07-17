#!/usr/bin/env bash
set -euo pipefail
command -v rg >/dev/null

cd /app/server
before_gen=$(mktemp)
after_gen=$(mktemp)
trap 'rm -f "$before_gen" "$after_gen"' EXIT
git diff --binary -- internal/database/gen >"$before_gen"
go run github.com/sqlc-dev/sqlc/cmd/sqlc generate
git diff --binary -- internal/database/gen >"$after_gen"
cmp "$before_gen" "$after_gen"
sqlc version
test -z "$(gofmt -l internal/taskengine)"
go vet ./...
go test ./...
go build ./cmd/server

cd /app/api
go vet ./...
go test ./...
go build ./...

cd /app/cli
go vet ./...
dbus-run-session -- bash -c 'eval "$(printf benchmark-keyring | gnome-keyring-daemon --unlock --components=secrets)"; go test ./...'
go build -o /tmp/tend .
