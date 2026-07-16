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

An optional frozen pricing table may be attached to a model only when the operator has a
defensible comparison basis:

```toml
pricing = { basis = "published-list-2026-07-16", currency = "USD", input_per_million = 1.0, cached_input_per_million = 0.1, output_per_million = 2.0, reasoning_per_million = 2.0 }
```

All four token-category rates are required. Reports keep this derived estimate separate
from provider-reported cost. Subscription routes should normally omit pricing rather than
pretend a list-price estimate is marginal spend.

`full_info` cells must actually provide information: either select a task scenario with a
sealed full-info addendum or set an operator-authored `initial_clarification`. The latter is
part of the signed manifest and is rejected in other modes.

For live Stage-A proctoring, `concurrency` must be `1`. Infrastructure retries may be `0` or `1`. A deterministic model failure, timeout, no-op, or failed verifier is a completed outcome and is never retried.

## Lifecycle

```bash
cae matrix plan experiments/<name>.toml --providers providers.toml
CAE_ALLOW_CANDIDATE_RUN=1 cae matrix run experiments/<name>.toml --providers providers.toml
cae matrix status experiments/<name>.toml --providers providers.toml
cae matrix resume experiments/<name>.toml --providers providers.toml
cae report experiments/<name>.toml --providers providers.toml --output reports/experiments/<name>
```

The first paid `run` requires a clean, validly signed Git commit. Before calling a model it writes an ignored lock under `.runs/experiments/<id>/lock.json` containing the signed benchmark commit, manifest SHA-256, explicit redacted routes, OpenCode version, canonical generated model configurations and SHA-256 digests, exact task/agent image IDs, and expanded cells. Resume refuses a changed commit, manifest, route, or generated configuration.

Normalized reports record input, cached-input, output, and reasoning tokens. Provider-reported cost is retained when present but is secondary because these providers are subscription-backed.

`cae export-evidence <experiment-id> --output <reports-path>` publishes an allowlisted,
credential-scanned bundle containing canonical JSONL transcripts, candidate patches, exact
instructions/configuration, deterministic verifier output, normalized matrix records, and
schema-valid proctor reviews. It intentionally does not copy mutable `.runs/` wholesale.
