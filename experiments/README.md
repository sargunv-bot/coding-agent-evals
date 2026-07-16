# Experiment manifests

Experiment manifests are operator-authored, committed descriptions of paid model runs. The harness never chooses a provider and never falls back to another provider. Every `[[models]]` entry must name one exact `provider` and `model` pair declared in the local ignored `providers.toml`.

## Schema

```toml
[experiment]
id = "lowercase-stable-id"
description = "human purpose"
stage = "stage-name"
repeats = 1
concurrency = 1
infrastructure_retries = 1
proctor_model = "provider/model"

[[models]]
provider = "explicit-provider"
model = "exact-model-name"

[[cells]]
task = "task-id"
scenario = "optional-scenario-id"
mode = "baseline | ask_user | full_info"
```

For live Stage-A proctoring, `concurrency` must be `1`. Infrastructure retries may be `0` or `1`. A deterministic model failure, timeout, no-op, or failed verifier is a completed outcome and is never retried.

## Lifecycle

```bash
cae matrix plan experiments/<name>.toml --providers providers.toml
CAE_ALLOW_CANDIDATE_RUN=1 cae matrix run experiments/<name>.toml --providers providers.toml
cae matrix status experiments/<name>.toml --providers providers.toml
cae matrix resume experiments/<name>.toml --providers providers.toml
cae report experiments/<name>.toml --providers providers.toml --output reports/experiments/<name>
```

The first paid `run` requires a clean, validly signed Git commit. Before calling a model it writes an ignored lock under `.runs/experiments/<id>/lock.json` containing the signed benchmark commit, manifest SHA-256, explicit redacted routes, OpenCode version, exact task/agent image IDs, and expanded cells. Resume refuses a changed commit, manifest, or route.

Normalized reports record input, cached-input, output, and reasoning tokens. Provider-reported cost is retained when present but is secondary because these providers are subscription-backed.
