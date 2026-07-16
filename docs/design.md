# Personalized Coding-Agent Evaluation Suite — Research & Design

**Status:** Proposed; no model evaluations have been run.
**Date:** 2026-07-16
**Owner:** Sargun Vohra

## 1. Objective

Build a small, high-signal coding-agent evaluation suite from Sargun's recent public engineering work. It should answer practical questions such as:

- Which available model is most likely to complete the kinds of work Sargun actually does?
- Does the model investigate ambiguity or guess?
- When does it ask a useful clarification question?
- Does it preserve regressions and security invariants?
- How much time, output, and tool activity does it consume?

This is not intended to become a leaderboard or a statistically representative measure of all software engineering.

## 2. Non-goals

- Reproducing SWE-bench's issue/patch scoring model.
- Rewarding similarity to a historical gold patch.
- Generating thousands of low-quality synthetic bugs.
- Running multiple agent scaffolds in the first experiment.
- Treating a seven-task macro-average as a universal model ranking.
- Executing the model matrix before Sargun approves the suite.

## 3. Research findings

### 3.1 DeepSWE practices worth adopting

DeepSWE v1.1 packages each task using the Harbor format and runs it through Pier. The strongest practices are:

1. An agent container checked out at a specific base commit.
2. No future Git history visible to the agent.
3. The agent commits its changes.
4. Only the committed binary patch is exported.
5. A separate pristine verifier container applies and grades that patch.
6. Hidden behavioral tests and structured CTRF reports.
7. Pinned dependencies and air-gapped task environments.
8. Full trajectories, output tokens, steps, latency, and cost alongside pass rate.

These mechanics are more valuable to this project than DeepSWE's prompt style. Released DeepSWE prompts are detailed specifications; Sargun's prompts should remain terse and ambiguous.

### 3.2 Framework audit

| Framework | Reuse | Reject / defer |
|---|---|---|
| Pier + Harbor task format | Best task packaging, separate verifier, CLI agents, ATIF trajectories, per-agent network allowlists, and native OpenCode MCP configuration | Released Pier v0.3.0 does not support Podman. PR #14 adds rootless Podman support and substantial tests but is unreviewed, unmerged, and lacks functional CI evidence. |
| Harbor | Stable upstream task schema and broad adapter ecosystem | Released Harbor also lacks Podman support; several competing Podman PRs remain open. Pier currently has the isolation and trajectory features most relevant here. |
| Terminal-Bench 3 | Borrow its task-review, no-op/oracle, reward-hacking, deterministic-verifier, and test/instruction-alignment checks | Dataset is not specifically a personalized coding benchmark |
| Inspect AI | Excellent custom/host tools, MCP bridges, human baselines, transcript capture | Duplicates sandbox/agent orchestration if Pier already works; consider only if clarification integration in Pier is awkward |
| METR Task Standard | Borrow reproducibility, resource declaration, and task-family validation principles | VM/task-family runner is unnecessary for seven repository tasks |
| SWE-smith | Environment-building ideas only | Mutation-generated test failures optimize scale, not task quality |
| OpenHands / SWE-agent | Possible future scaffold comparisons | Too much platform and agent variance for a model-focused first experiment |

**Recommendation:** author Harbor-compatible tasks and compare two pinned runners in Phase 0 rather than choosing by README: (a) current Harbor plus the smallest auditable rootless-Podman adapter, and (b) Pier PR #14 (`6263c12c`). Validate rootless networking, phase-specific filtered egress, separate verifiers, OpenCode custom providers, MCP clarification calls, ATIF completeness, artifact extraction, and cleanup. Prefer current Harbor if behavior is comparable because it is the larger, more active upstream; retain Pier only if its OpenCode trajectory or egress behavior is materially better. Do not create a bespoke task schema.

### 3.3 DeepSWE quality audit

DeepSWE v1.1 is materially better than v1, but its public score should not be treated as self-validating. Earlier audits found eight broken golds; a July 14 v1.1 rerun reports that most were fixed and 112/113 reference solutions now pass. Remaining concerns include one failing gold, unavailable per-trial patch/verifier receipts, incompletely disclosed exclusions, timeout/result inconsistencies, and metadata errors. This reinforces using DeepSWE's isolation ideas while independently validating every task with no-op, gold, targeted mutants, and repeat flake checks.

## 4. Benchmark tracks and contamination

The initial tasks are **historical replay tasks**. Their upstream PRs and gold changes are public, so this suite must not claim to be contamination-free.

Mitigations:

- All source changes are from March–July 2026 and therefore recent.
- The agent environment has no GitHub or general internet access.
- Future commits and branches are deleted from the task checkout.
- The gold patch is never present in the agent container and is never used for grading.
- Results are labeled `historical-replay`, not novel-task performance.
- If the suite becomes important, add a private `transfer` sibling for each task with a counterfactual requirement and unpublished tests.

## 5. Proposed core task suite

### CE-01 — Antidote subprocess output isolation

- **Source:** https://github.com/mattmc3/antidote/pull/240
- **Base:** `61a07ca521e8f811bbcd6da74a244119209980cb`
- **Historical gold:** `f4c883c757c449e44f31af8d611a6b3441ce45a4`
- **Language/domain:** Zsh; process I/O and shell correctness
- **Historical size:** 2 files, +6/−6
- **Target class:** short diagnostic task, 30 minutes

**Agent prompt**

> A git wrapper on PATH writes progress to stdout even for `git --quiet`, and antidote is leaking that text into generated plugin scripts. Fix it without hiding useful diagnostics.

**Behavioral verifier**

- Put a fake `git` wrapper first on `PATH`.
- The wrapper emits unique markers to both stdout and stderr for quiet clone/pull operations.
- Generated antidote script output must not contain the stdout marker.
- Diagnostic stderr must remain observable.
- Exit status from failed git commands must remain meaningful.
- Existing project tests must pass.

**Clarification profile:** no question should be necessary. If asked whether diagnostics should remain visible, answer card says “Yes—keep diagnostics on stderr; only prevent stdout from becoming generated content.”

### CE-02 — Horologia overdue-action validation matrix

- **Source:** https://github.com/sargunv/horologia/pull/62
- **Base:** `1e90747f596becdb06d8cd8729f9a3df7853cdac`
- **Historical gold:** `9b6335019e5f66d04ea2b5ff22d50d4d69d94ea4`
- **Language/domain:** Go; domain validation
- **Historical size:** 2 files, +38/−5
- **Target class:** small behavioral bug, 45 minutes

**Agent prompt**

> Overdue action validation is rejecting one-off and dependency-driven tasks that should be valid. Fix the rules and cover the behavior matrix.

**Behavioral verifier**

- Every overdue action still requires a due date.
- `advance_recurrence` requires a recurring task and valid recurrence data.
- `set_status` and `clear_due_date` accept one-off, recurring, and dependency-driven tasks when their own prerequisites are satisfied.
- Unknown actions remain invalid.
- Existing task-engine tests pass.

**Clarification profile:** optional diagnostic clarification. An agent can infer the action matrix from code. A useful question about which actions are recurrence-specific receives the fixed matrix; generic requests for implementation guidance receive “Please inspect the task-engine model and make a reasonable choice.”

### CE-03 — JVL composed-schema completions

- **Source:** https://github.com/sargunv/jvl/pull/27
- **Base:** `5e38284088677a138458b3b938f35da62b987398`
- **Historical gold:** `ac0c74d42890fad44238728159f1061d52dfcc8a`
- **Language/domain:** Rust; LSP and JSON Schema traversal
- **Historical size:** 3 files, +418/−30
- **Target class:** medium algorithmic task, 90 minutes

**Agent prompt**

> JSON-schema completions are incomplete for composed schemas. Handle the composition cases and nullable types, without duplicate suggestions. Add realistic LSP tests.

**Behavioral verifier**

- Property completion traverses `oneOf`, `anyOf`, and `allOf` branches.
- Value completion works when composition occurs at parent and leaf schema levels.
- Nested compositions work.
- Fragment `$ref` inside composition continues to work.
- Both scalar `type` and array-valued `type`, including `null`, produce the right suggestions.
- Equivalent suggestions are deduplicated without nondeterministic output.
- Hover behavior and unrelated schema resolution do not regress.
- Unit and end-to-end LSP completion tests pass.

**Clarification profile:** bounded scope ambiguity. If asked whether to expand general `$ref` behavior, answer “No new resolver semantics; preserve existing fragment-reference behavior and focus composition walking in completion collection.”

### CE-04 — MapLibre Native source-location portability

- **Source:** https://github.com/maplibre/maplibre-native/pull/4318
- **Base:** `5602ad8bd357c1ffb2b63b8d45de1d85123fdb58`
- **Historical gold:** `f6d70e954b07fdadf6a5adda8da49e73178298c6`
- **Language/domain:** C++; portability and diagnostics
- **Historical size:** 7 files, +60/−43
- **Target class:** medium systems task, 90 minutes

**Agent prompt**

> OpenHarmony's C++ environment has no `<source_location>`. Give core a standards-safe fallback without extending `std`, and keep call sites useful for diagnostics.

**Behavioral verifier**

- A native C++20 build uses `std::source_location` where available.
- A forced fallback build is exercised under a language/library mode where `std::source_location` is unavailable.
- Fallback captures file, function, and line at the call site and exposes a compatible diagnostic surface.
- No declarations are injected into `namespace std`.
- Existing bucket/layout callers compile in both modes.
- The source is present in the relevant build manifests.

**Clarification profile:** repository-answerable portability ambiguity. The agent should inspect existing callers. A question about column behavior gets “Zero is acceptable in the fallback.”

### CE-05 — mise fail-closed SLSA archive verification

- **Source:** https://github.com/jdx/mise/pull/9898
- **Base:** `5aea2e1d0df40673dd5fbd7607109e0ebb136d02`
- **Historical gold:** `3fd427f3be122bd70a2b00f3e21b1a05c74d8d6e`
- **Language/domain:** Rust; software supply-chain security
- **Historical size:** 5 files, +556/−27
- **Target class:** long security task, 180 minutes

**Agent prompt**

> Some GitHub releases attest each file inside an archive rather than the archive blob itself. Make mise accept those safely. This is security-sensitive; the fallback must fail closed.

**Behavioral verifier / hard gates**

- Fallback runs only when archive-level verification fails specifically because no subject matches.
- Every regular archive file is matched by normalized name and SHA-256.
- Unsupported archive formats fail.
- Unsafe paths fail.
- Symlinks, hardlinks, and non-regular entries fail.
- Duplicate paths fail.
- Missing, extra, or partially attested regular files fail.
- Other signature/provenance failures do not silently enter the fallback.
- Existing archive-level verification remains unchanged.
- Any security-gate failure marks the run `unsafe`, regardless of partial score.

**Clarification profile:** asking about the trust boundary is useful. Fixed answers disclose policy, never implementation. Broad “what should I code?” questions are refused.

### CE-06 — MapLibre Native FFI manifest-driven CI

- **Source:** https://github.com/maplibre/maplibre-native-ffi/pull/233
- **Base:** `4fa163923d35aae4099417206a7345b52c2fbdc2`
- **Historical gold:** `c0da43b1c0b48bc88b8d9964e8aff86e55d2285d`
- **Language/domain:** Python, TOML, YAML, repository tooling
- **Historical size:** 19 files, +674/−93
- **Target class:** long architecture/tooling task, 180 minutes

**Agent prompt**

> Our CI target support policy is trapped in a hand-written workflow and keeps drifting. Make it declarative, generate the checked-in workflow from manifests, and enforce that it stays in sync.

**Behavioral verifier**

- Variant dimensions and runners come from a checked-in manifest.
- Each binding/example declares its own constraints and build/test/run task.
- Manifest parsing is strict and rejects unknown fields, values, variants, and malformed task names.
- Generation is deterministic.
- `--check` reports drift and exits nonzero without rewriting the workflow.
- Normal generation rewrites the file atomically or safely.
- Existing permissions, concurrency behavior, pinned actions, setup steps, required aggregate job, and relevant target policy are preserved.
- Generated files are marked and formatting/lint orchestration includes manifests, generator, and generated output.

**Clarification profile:** one architectural question is expected or at least reasonable. Fixed cards define that manifests should be per subproject plus a central variant catalog, generated output remains checked in, and current CI semantics should be preserved unless they are clearly duplicated policy.

## 6. Core interaction task and reserves

### CE-07 — Mobility Data Kotlin `Result` error propagation

- **Source:** https://github.com/sargunv/mobility-data-kt/pull/53
- **Base:** `541fc977a939501693a195057d0d1ce39188b522`
- **Historical gold:** `1334676fae7409daa93cd6316285c24b5a7af571`
- **Language/domain:** Kotlin Multiplatform, Ktor, public API migration
- **Historical size:** 27 files, +686/−460
- **Target class:** medium cross-module task, 120 minutes

**Agent prompt**

> Make the public Ktor clients return `Result` instead of throwing. Apply it consistently across GBFS v1–v3 and GOFS, including public API and tests.

**Paired intended-world scenarios**

- `validation-fail-fast` (historical): transport, HTTP, and deserialization failures become `Result.failure`; caller argument/precondition validation continues to throw immediately.
- `all-errors-as-result` (sealed counterfactual): caller validation is also represented as `Result.failure`.

The initial prompt is identical. In `full_info`, the selected policy is stated. In `baseline`, it is withheld. In `ask_user`, a question that distinguishes caller misuse from operational failure receives the fixed scenario answer. Tests also check Ktor `expectSuccess`, coroutine cancellation, API dumps, documentation snippets, and consistency across modules.

### CE-R1 — dprint clang-format config mapping in Wasm

- **Source:** https://github.com/sargunv/dprint-clang-format/commit/c973157cf63ade43448bfc101dad8d605abe619c
- **Base:** `00d14b3b57de7eab6c8c93631655d6cc0d28d419`
- **Historical gold:** `c973157cf63ade43448bfc101dad8d605abe619c`
- **Prompt:** “The dprint plugin accepts `register_config` but ignores the settings. Make normal dprint configuration keys affect clang-format correctly and keep the Wasm build/runtime working.”
- **Use:** systems/toolchain reserve; requires a large, carefully pinned LLVM/Wasm image.

### CE-R2 — Jolt benchmark corpus parity

- **Source:** https://github.com/sargunv/jolt/commit/7913d130819572b312c7d5362611839118c4b114
- **Base:** `ca27b2f266ea11e1849b302e82c6f2530c8a55ea`
- **Historical gold:** `7913d130819572b312c7d5362611839118c4b114`
- **Prompt:** “The formatter benchmark can silently compare incomplete corpora. Make validation reject missing or unexpected source files and give useful deterministic diagnostics before comparing contents.”
- **Use:** inexpensive Python reserve with excellent Linux reproducibility; useful if a short core task proves flaky or too implementation-revealing.

## 7. Clarification protocol

### 7.1 Tool surface

Every OpenCode run receives one additional tool:

```text
ask_user(question: string) -> string
```

Pier's current OpenCode adapter natively translates task `mcp_servers` entries into `opencode.json` and records custom tool calls in its ATIF trajectory. The compatibility spike therefore only needs to validate the moderator transport; no Pier fork should be required.

The task container cannot read answer cards. The tool calls a host-side moderator over a narrow local channel. It has no general network access.

### 7.2 Fixed answer cards

Each task contains a private moderator file with:

- card ID;
- semantic topic;
- exact response text;
- whether the topic is blocking, useful, repository-answerable, or out of scope;
- maximum disclosure level.

Sargun maps free-form questions to cards for the first run. Later semantically equivalent questions receive exactly the same text. Unmatched questions receive:

> No additional requirement is specified. Please inspect the repository and make a reasonable choice, documenting any consequential assumption.

This keeps interaction natural while preventing later models from receiving richer requirements.

### 7.3 Clarification analysis

Clarifications are reported separately, not folded blindly into task score:

- useful and blocking;
- useful but optional;
- answerable from repository context;
- redundant;
- solution-fishing;
- missed blocking ambiguity;
- unsupported assumption made without asking.

No reward is granted merely for asking. Good autonomy and good clarification are both acceptable when behavior is correct.

### 7.4 Paired interaction conditions

For tasks with a registered consequential blocker, run three explicitly labeled conditions sharing the same intended-world scenario:

- `full_info`: the blocker resolution is included in the initial prompt;
- `baseline`: it is withheld and no clarification tool is available;
- `ask_user`: it is withheld and `ask_user` is available.

Use this only where two or more reasonable intended worlds imply incompatible correct behavior. Each blocker records when it becomes discoverable, acceptable question paraphrases, the deterministic answer in each scenario, and whether repository evidence can resolve it. Report blocker recall, question precision, redundant-question count, turns to resolution, and whether the implementation changed after the answer. This adapts the strongest parts of HiL-Bench's blocker/Ask-F1 framing without adopting its SWE-bench-derived corpus or LLM user simulator.

CE-07 is the best initial paired-interaction candidate: “return failures as `Result`” leaves it consequentially unclear whether caller precondition errors should remain fail-fast. Two sealed intended-world variants can use the same initial prompt while returning different fixed answer cards.

## 8. Execution architecture

```text
Host runner
  ├─ Pier/Harbor task controller
  ├─ provider proxy (credentials, token accounting, limits)
  ├─ clarification moderator
  └─ results store
       ├─ ATIF trajectory
       ├─ model/tool calls
       ├─ clarification transcript + card IDs
       ├─ committed binary patch
       ├─ timing/token/step/resource metrics
       └─ verifier artifacts / CTRF

Agent container (rootless, no GitHub/internet)
  ├─ repository at base commit on main
  ├─ future Git history removed
  ├─ pinned dependencies and tools
  ├─ OpenCode CLI, identical version/config for all models
  └─ ask_user tool only

Separate verifier container
  ├─ pristine base checkout
  ├─ hidden tests and mutation fixtures
  ├─ applies committed patch
  └─ emits structured requirement-level results
```

Secrets remain host-side. The task sees only a loopback/allowlisted model proxy and clarification endpoint.

## 9. Task quality gates before model execution

Every task must pass:

1. **Environment rebuild:** image builds twice from pinned inputs.
2. **No-op baseline:** essential new behavior fails.
3. **Gold baseline:** historical patch passes all behavioral and regression tests.
4. **Targeted mutants:** deliberately broken variants fail the intended requirement.
5. **Test/instruction alignment:** every hidden assertion traces to prompt text, a repository invariant, or an answer card.
6. **Isolation check:** agent cannot read hidden tests, solution, answer cards, or future history.
7. **Cheat review:** common test tampering, generated-file spoofing, and grader bypasses fail.
8. **Flake check:** verifier passes repeatedly under constrained CPU/memory.
9. **License/provenance review:** record upstream license and avoid publishing source/gold patches under an incompatible license.

## 10. Reporting and scoring

Do not lead with one aggregate number. Report a task-by-model matrix containing:

- requirement-level behavioral score;
- full pass/fail;
- regression status;
- security hard-gate status;
- clarification transcript/classification;
- wall time;
- output and reasoning tokens where available;
- model calls and agent steps;
- tests run before completion;
- patch size and touched scope;
- short blinded trajectory review.

If an aggregate is desired, use only:

1. equal-weight macro-average behavioral score;
2. number of fully solved tasks;
3. number of unsafe/invalid runs;
4. median time and output tokens.

Never use gold-patch textual similarity. Do not report pass@k as the main result.

## 11. Model and elicitation plan

Hold the coding agent constant: one pinned OpenCode CLI release, same tool surface, same base system instructions, fresh container and conversation for every task.

### Initial screen

Run two tasks once for each candidate:

- Z.AI Coding Plan `glm-5.2` at its documented high/max coding setting;
- OpenCode Go `kimi-k2.7-code`;
- NeuralWatt `qwen3.5-397b`;
- OpenCode Go `mimo-v2.5-pro`;
- OpenCode Go `deepseek-v4-pro`.

Suggested screen tasks: CE-01 and CE-03. They are inexpensive but distinguish shell diagnosis from multi-file algorithmic work.

DeepSWE v1.1 currently reports the two directly overlapping models at approximately 44% for GLM-5.2 max and 31% for Kimi K2.7 Code, which makes them the evidence-backed favorites. Qwen, MiMo, and DeepSeek remain exploratory candidates from the configured inventory.

### Full suite

Promote the three strongest screen configurations to the remaining five tasks and the CE-07 interaction conditions. Repeat only:

- close or surprising outcomes;
- safety failures;
- one deterministic sample of passed tasks to estimate variance.

This avoids an expensive blind Cartesian product while retaining comparable evidence.

### Limits

- Short task: 30–45 minutes.
- Medium task: 90 minutes.
- Long task: 180 minutes.
- Proxy-enforced aggregate model-output/step cap per task.
- Provider defaults unless a model's documented reasoning mode is necessary; record every setting.
- Same network, tool, and repository permissions for all models.

## 12. Implementation phases after approval

### Phase 0 — Compatibility spike

- Create a local private repository, tentatively `~/coding-agent-evals`.
- Pin OpenCode and the Harbor task schema.
- Compare pinned current Harbor plus a minimal Podman adapter against Pier PR #14 at `6263c12c`.
- Validate rootless Podman lifecycle, phase-specific filtered egress, separate verifier, MCP clarification, ATIF output, artifact extraction, and cleanup.
- Run a toy no-op/gold task only; do not run candidate models.
- Validate the host-side `ask_user` bridge with a fake scripted agent.

### Phase 1 — Package calibration tasks

- Implement CE-01 and CE-02.
- Add no-op, gold, mutant, isolation, and flake checks.
- Have Sargun approve prompts and answer cards.

### Phase 2 — Package medium tasks

- Implement CE-03, CE-04, and CE-07.
- Ensure C++ fallback is exercised genuinely on Linux rather than statically string-matched.
- Validate CE-07's paired intended worlds with fixed blocker cards in `full_info`, `baseline`, and `ask_user` conditions.

### Phase 3 — Package long tasks

- Implement CE-05 and CE-06.
- Perform adversarial verifier review, especially for fail-closed security and generated-file spoofing.

### Phase 4 — Dry validation

- Rebuild every image.
- Run no-op, gold, and all mutants.
- Produce a task audit report.
- Stop and request explicit approval before any model matrix execution.

### Phase 5 — Model evaluation

Not authorized by the current request. Execute only after Sargun reviews the validated task audit and model configuration matrix.

## 13. Decisions requested from Sargun

1. Approve the seven core tasks, or swap a core task for CE-R1/CE-R2.
2. Approve the Harbor-compatible task format and a Phase-0 comparison of pinned Pier PR #14 against a thin Harbor/Podman adapter.
3. Approve the fixed-card clarification protocol.
4. Decide whether exact historical replay is sufficient for v1 or whether every task should also get a private counterfactual transfer variant.
5. Decide whether task files/results should stay local/private initially or live in a new private GitHub repository.
