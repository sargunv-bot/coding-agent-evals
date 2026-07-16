# Coding Agent Evals

Private, personalized coding-agent evaluations derived from Sargun Vohra's recent engineering work.

The suite emphasizes:

- terse, realistically ambiguous prompts;
- deterministic behavioral and regression checks;
- rootless Podman isolation;
- fresh, networkless verifier containers;
- a live SOTA proctor for clarification and qualitative review;
- explicit separation of historical replay and sealed transfer scenarios;
- task-level evidence rather than one opaque leaderboard score.

## Task set

| ID | Repository | Focus | Verification slice |
|---|---|---|---|
| CE-01 | `mattmc3/antidote` | Shell subprocess stream separation | Noisy Git shim under Zsh |
| CE-02 | `sargunv/horologia` | Go domain validation matrix | Targeted task-engine tests |
| CE-03 | `sargunv/jvl` | Rust JSON Schema/LSP traversal | Real LSP completion client |
| CE-04 | `maplibre/maplibre-native` | C++ source-location portability | GCC and Clang, C++17 and C++20 |
| CE-05 | `jdx/mise` | Fail-closed SLSA archive verification | `mise-sigstore` plus filtered archive tests |
| CE-06 | `maplibre/maplibre-native-ffi` | Declarative CI generation | Python generator and mutated manifests |
| CE-07 | `sargunv/mobility-data-kt` | Kotlin `Result` API migration | MockEngine tests and API baselines |

CE-07 has two intended worlds with the same initial prompt:

- `validation-fail-fast`: caller preconditions still throw;
- `all-errors-as-result`: caller preconditions become `Result.failure`.

## Installation

The runner has no runtime Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install --no-build-isolation -e .
```

Using `PYTHONPATH=src python3 -m agent_evals.cli` is also supported during development.

Prerequisites:

- Python 3.11 or newer;
- rootless Podman;
- `git`;
- enough storage to remain above the configured free-space floor.

## Structural and control validation

```bash
cae doctor
cae validate
cae build ce-01-antidote-output
cae audit-task ce-01-antidote-output --gold-repeats 2
scripts/calibrate.sh
```

`calibrate.sh` writes normalized control evidence and a suite summary under
`reports/calibration/`.

`audit-task` requires:

- no-op fails with a valid verifier receipt;
- gold passes;
- every patch under `mutants/` applies and fails;
- repeated gold runs remain stable.

Scenario task example:

```bash
cae audit-task ce-07-mobility-result \
  --scenario validation-fail-fast
cae audit-task ce-07-mobility-result \
  --scenario all-errors-as-result
```

## Isolation model

### Candidate phase

- unprivileged `agent` user;
- no container socket or host-home mount;
- CPU, memory, PID, and timeout limits;
- internal-only Podman network;
- exact-host TLS CONNECT proxy permitting only the selected provider host;
- provider credential inherited into Podman without being written to config or command arguments;
- local stdio MCP proctor tool;
- hidden tests and gold patches absent.

### Verifier phase

- fresh immutable task image;
- candidate represented only by a full-index binary Git patch;
- hidden tests mounted read-only;
- `--network none`;
- no provider credential or proctor transport;
- root with only verifier-required `DAC_OVERRIDE` and `FOWNER` capabilities;
- structured reward and CTRF receipts.

Artifact capture stages the ephemeral candidate tree before diffing. This preserves new files, deletions, executable modes, renames, and binary changes. The candidate-mutated container is never reused as the verifier.

## Provider configuration

Copy the example without committing it:

```bash
cp providers.example.toml providers.toml
```

Set the endpoint and credential environment variables referenced by that file. Provider
selection is always explicit: the harness has no priority order and never falls back to
another provider.

Inspect the redacted route:

```bash
cae route glm-5.2 --provider zai --providers providers.toml
```

The command reports the provider, model, endpoint, and credential variable name—never the credential value.

## Building agent tools

```bash
cae build-tools
cae build-agent ce-01-antidote-output
```

This pins:

- OpenCode `1.18.2`;
- a digest-pinned Node 22 build image;
- static `proctor-mcp` and `egress-proxy` binaries.

No model is invoked by either command.

## Candidate runs and live proctoring

Candidate execution is intentionally gated:

```bash
CAE_ALLOW_CANDIDATE_RUN=1 cae run \
  ce-07-mobility-result glm-5.2 \
  --provider zai \
  --providers providers.toml \
  --scenario validation-fail-fast \
  --mode ask_user
```

The runner prints:

```text
[CAE_RUN] id=... proctor_queue=.../.runs/.../proctor
```

OpenCode receives:

```text
ask_user(question: string) -> string
```

When it asks, the MCP server emits `[PROCTOR_QUESTION]` and blocks. The live Hermes proctor answers as Sargun would:

```bash
cae proctor pending .runs/<run-id>/proctor
cae proctor answer .runs/<run-id>/proctor <question-id> \
  '<scope or product clarification>' \
  --proctor 'Hermes Agent / <model>'
```

The proctor clarifies intent and consequential preferences but does not reveal hidden tests, symbol names, the historical patch, or an implementation plan. See [`docs/proctor.md`](docs/proctor.md).

Modes:

- `baseline`: ambiguity withheld and no MCP clarification tool;
- `ask_user`: ambiguity withheld with live MCP moderation;
- `full_info`: scenario policy included initially and no MCP clarification tool.

## Qualitative review

After deterministic verification, generate a model-blinded review record:

```bash
cae review-template <run-id> <task-id> \
  --proctor-model '<model>' \
  --output .runs/<run-id>/proctor-review.json
```

Review covers scope discipline, code clarity, tests, repository fit/taste, security, and mergeability. It cannot promote a deterministic failure into a behavioral pass.

## Real-model experiment manifests

Paid model runs are described by operator-authored manifests under `experiments/`. Each
model entry names one exact provider and model pair. Plan and inspect the expansion before
enabling candidate execution:

```bash
cae matrix plan experiments/real-models-v1-stage-a.toml --providers providers.toml
CAE_ALLOW_CANDIDATE_RUN=1 cae matrix run \
  experiments/real-models-v1-stage-a.toml --providers providers.toml
cae matrix status experiments/real-models-v1-stage-a.toml --providers providers.toml
cae matrix resume experiments/real-models-v1-stage-a.toml --providers providers.toml
```

The first run requires a clean, signed benchmark commit and freezes a local lock containing
the commit, manifest digest, explicit routes, image IDs, OpenCode version, and expanded
cells. Resume refuses drift. Completed model failures are outcomes, not retry candidates;
only infrastructure errors receive the manifest's bounded retry.

While an `ask_user` matrix is active, the live proctor can wait for unanswered questions:

```bash
scripts/watch_proctor.py --wait --timeout 900
```

Results record input, cached-input, output, and reasoning tokens. Provider-reported cost is
retained when available but is secondary for subscription-backed routes. Generate a
normalized report with:

```bash
cae report experiments/real-models-v1-stage-a.toml \
  --providers providers.toml \
  --output reports/experiments/real-models-v1-stage-a
```

## Static results site

The production results browser is the Astro project under `web/`. It is task-first,
generates real static task/model/run routes, and reads committed result data only; it
never executes an evaluation or reads `.runs`.

```bash
cd web
npm ci --ignore-scripts
npm run lint
npm run check
npm test
RESULTS_DATA_ROOT=.. TASK_DATA_ROOT=.. BASE_PATH=/coding-agent-evals/ npm run build
npm run validate
```

For a separate live-results checkout, set `RESULTS_DATA_ROOT` to that checkout and
keep `TASK_DATA_ROOT` pointed at the trusted source checkout. Build-time ingestion
publishes only allowlisted files proven committed by Git, rejects path and symlink
escapes, recomputes evidence hashes, and displays optional-input warnings. See
[`docs/results-site.md`](docs/results-site.md) and `web/THIRD_PARTY_NOTICES.md`.

## Storage and cleanup

The default floor is 80 GiB free. Override it explicitly when appropriate:

```bash
cae --min-free-gib 120 doctor
CAE_MIN_FREE_GIB=120 cae build ce-05-mise-slsa-archive
```

Cleanup is label-scoped and never prunes unrelated Podman state:

```bash
cae cleanup
cae cleanup --include-images
```

Evaluation outputs under `.runs/`, local caches, provider configuration, and credentials are ignored by Git.

## Reproducibility and provenance

Each task records:

- exact upstream repository;
- exact base and historical gold commits;
- prompt, Containerfile, gold-patch, and mutant SHA-256 values;
- upstream licensing/distribution status;
- scenario-specific gold checksums where applicable.

Historical gold artifacts are evaluator-only. The benchmark repository is private because several replay sources are owner-authorized rather than generally redistributable.

## Licensing

Repository-authored benchmark infrastructure and task specifications are Apache-2.0. Upstream repositories and historical patches retain their original rights and license terms; see each task's `provenance.toml`.
