#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
out="$root/reports/calibration"
mkdir -p "$out"

python3 -m agent_evals.cli validate > "$out/structure.json"
python3 -m agent_evals.cli audit-task ce-01-antidote-output --gold-repeats 2 \
  > "$out/ce-01-antidote-output.json"
python3 -m agent_evals.cli audit-task ce-02-horologia-overdue --gold-repeats 2 \
  > "$out/ce-02-horologia-overdue.json"
python3 -m agent_evals.cli audit-task ce-03-jvl-completions --gold-repeats 2 \
  > "$out/ce-03-jvl-completions.json"
python3 -m agent_evals.cli audit-task ce-04-maplibre-source-location --gold-repeats 2 \
  > "$out/ce-04-maplibre-source-location.json"
python3 -m agent_evals.cli audit-task ce-05-mise-slsa-archive --gold-repeats 2 \
  > "$out/ce-05-mise-slsa-archive.json"
python3 -m agent_evals.cli audit-task ce-06-maplibre-ffi-ci --gold-repeats 2 \
  > "$out/ce-06-maplibre-ffi-ci.json"
python3 -m agent_evals.cli audit-task ce-07-mobility-result \
  --scenario validation-fail-fast --gold-repeats 2 \
  > "$out/ce-07-validation-fail-fast.json"
python3 -m agent_evals.cli audit-task ce-07-mobility-result \
  --scenario all-errors-as-result --gold-repeats 2 \
  > "$out/ce-07-all-errors-as-result.json"

python3 scripts/summarize_calibration.py
