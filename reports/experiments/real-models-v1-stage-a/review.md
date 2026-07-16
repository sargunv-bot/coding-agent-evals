# Stage-A real-model smoke review

## Freeze

- Benchmark commit: `1569d815b4043746318483c2da38d138034b7a2c`
- Manifest SHA-256: `6f31122926fdb9d4cc7847e26f87300cb0d044cb616415c512199d76a7cc3519`
- Signed tag: `experiment/real-models-v1-stage-a`
- OpenCode: `1.18.2`
- Cells: 10/10 completed
- Infrastructure errors: 0
- Deterministic passes: 0

## Usage and runtime

| Metric | Total |
|---|---:|
| Candidate runtime | 14,263.5 seconds |
| Input tokens | 1,585,473 |
| Cached input tokens | 51,027,535 |
| Output tokens | 224,646 |
| Reasoning tokens | 138,544 |
| Provider-reported cost | 0.0 |
| Questions | 0 |

Provider-reported zero cost is retained as source data, not interpreted as zero economic or subscription cost. No list-price estimate was generated because no operator-supplied pricing basis was frozen with the experiment.

## Deterministic findings

All five CE-01 candidates made a partial clone-output fix but missed the analogous update path. Three also lost required diagnostics while redirecting output. This is consistent behavioral evidence rather than infrastructure noise.

All five CE-07 candidates missed the same two GOFS caller-validation cases:

- invalid wait-times arguments must return `Result.failure` without network access;
- invalid realtime-bookings arguments must return `Result.failure` without network access.

The repeated miss is the intended consequential ambiguity in the sealed `all-errors-as-result` world. None of the models resolved it through `ask_user`.

## Proctor behavior

The MCP server was enabled in every candidate's generated OpenCode configuration. There were zero question or answer files. One Kimi trajectory explicitly considered asking about validation semantics and then chose not to call the tool. Therefore zero questions is currently a model-behavior result, not evidence of an MCP configuration failure.

No live proctor answer was needed, so Stage A did not exercise answer consistency or candidate response to clarification. A future controlled interaction diagnostic is required before claiming that path is validated with a real model.

## Operational findings

- Explicit provider/model attribution remained intact for all ten cells.
- No provider fallback occurred.
- Raw OpenCode `step_finish` records supplied separate input, cache-read, output, and reasoning counts.
- All candidate and verifier containers/networks were cleaned up.
- Nine candidate commands exited zero. Neuralwatt/Qwen CE-07 exited one despite a normal OpenCode `stop` event and a usable patch; this exit-status discrepancy needs investigation before Stage B.
- Exact task and agent image IDs, endpoint hosts, manifest digest, commit, and OpenCode version were locked.

## Interpretation

The pilot is not evidence that all five models are uniformly incapable. It is evidence that binary pass/fail on these two ambiguity-heavy tasks has a floor effect under the `ask_user` condition when models decline to ask. The patches and failure clusters still contain useful diagnostic signal, but a ranking from 0/10 would be misleading.

## Recommendation before Stage B

1. Investigate the normal-stop/nonzero-exit discrepancy.
2. Add an optional operator-supplied pricing basis if a hypothetical token-cost estimate is desired; keep it separate from provider-reported and subscription cost.
3. Freeze exact generated model configuration/settings or a digest in the execution lock.
4. Run a small `full_info` diagnostic on these same tasks before the 40-cell breadth pass. This checks whether explicit scope removes the observed floor and validates that the tasks remain discriminative.
5. Keep the ten Stage-A outcomes unchanged; do not retry behavioral failures.
