#!/usr/bin/env zsh
set -e

cd /app
source ./tests/__init__.zsh
t_setup

integer failures=0
function fail {
  print -ru2 -- "FAIL: $1"
  (( failures += 1 ))
}

# Override the test suite's git shim with a noisy wrapper. It emits operational
# progress on stdout even when callers pass --quiet, exactly like the reported
# third-party wrapper. stderr represents diagnostics that must remain visible.
function git {
  print -r -- 'WRAPPER_STDOUT_MARKER'
  print -ru2 -- 'WRAPPER_STDERR_MARKER'
  return 0
}

local out err
out=$(mktemp)
err=$(mktemp)
ANTIDOTE_HOME="$HOME/.cache/antidote-empty"
rm -rf "$ANTIDOTE_HOME"

if ! antidote-script --kind clone wrapper/noisy >"$out" 2>"$err"; then
  fail 'clone unexpectedly failed'
fi
if grep -q WRAPPER_STDOUT_MARKER "$out"; then
  fail 'git wrapper stdout contaminated generated script output'
fi
if ! grep -q WRAPPER_STDOUT_MARKER "$err"; then
  fail 'redirected wrapper progress was not preserved on stderr'
fi
if ! grep -q WRAPPER_STDERR_MARKER "$err"; then
  fail 'wrapper stderr diagnostic was hidden'
fi

# A command failure must still propagate after output routing changes.
function git {
  print -r -- 'FAILURE_STDOUT_MARKER'
  print -ru2 -- 'FAILURE_STDERR_MARKER'
  return 37
}
: >"$out"
: >"$err"
if antidote-script --kind clone wrapper/failing >"$out" 2>"$err"; then
  fail 'git clone failure was swallowed'
fi
if grep -q FAILURE_STDOUT_MARKER "$out"; then
  fail 'failed git wrapper stdout contaminated generated output'
fi
if ! grep -q FAILURE_STDOUT_MARKER "$err" || ! grep -q FAILURE_STDERR_MARKER "$err"; then
  fail 'failed-command diagnostics were not visible on stderr'
fi

rm -f "$out" "$err"
t_teardown

if (( failures )); then
  exit 1
fi
print -- 'PASS: noisy git output is isolated from generated content'
