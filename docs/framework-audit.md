# Skeptical audit: coding-agent benchmarks and harnesses

**Research cutoff:** 2026-07-15 (UTC)  
**Scope:** DeepSWE/DataCurve, SWE-bench family, Terminal-Bench/Harbor, SWE-smith, repository-level generation benchmarks, OpenHands, Inspect AI, METR, and interactive/clarification benchmarks.  
**Method:** official sites, first-party papers, current source, task files, and repository metadata. Source claims below are pinned where practical.

## Executive judgment

DeepSWE is currently the strongest *task-authoring pattern* in this group, not a perfect ground truth. Its best ideas are original unmerged tasks, broad repository coverage, short behavior-oriented prompts, immutable base commits, shallow histories, behavioral held-out tests, regression tests, repeated flake checks, reference implementations used only for review, and a pristine separate verifier environment. Its principal weaknesses are that the tasks are professionally authored counterfactual features rather than observed maintainer work, the public release immediately begins a new contamination clock, its QA/error-rate claims partly rely on an LLM analyzer rather than independent human adjudication, and its long-horizon emphasis under-samples localization/refactoring and makes full sweeps expensive.

For a personalized benchmark built from GitHub history, **reuse DeepSWE's curation and grading discipline plus Harbor's task/runtime format**, but do not simply convert historical PRs into SWE-bench-style replay tasks and call them contamination-resistant. Public commits measure rediscovery under possible memorization. Maintain two explicitly different sets:

1. **Historical replay set:** authentic past issues/commits; high provenance and personal relevance, but explicitly contamination-prone.
2. **Sealed transfer set:** new, private/unmerged tasks or counterfactual variants derived from the user's recurring engineering patterns; reference solutions and tests never exposed to the agent or public web.

Use deterministic executable grading as the authority. Use LLM judges only for diagnostics, rubric coverage, and auditing disagreements. For interaction, copy HiL-Bench's blocker registry and precision/recall framing, but prefer deterministic answer oracles or replayed real follow-ups over an unconstrained LLM user simulator.

---

## 1. Keep datasets, harnesses, and standards separate

| Item | What it actually is | Verdict for personalized GitHub benchmark |
|---|---|---|
| **DeepSWE v1.1** | 113-task benchmark dataset **plus** task definitions; runs through Pier/Harbor-compatible tooling | **Reuse design pattern; selectively reuse format, not tasks** |
| **SWE-bench / Lite / Verified / Multimodal / Multilingual** | GitHub issue→PR datasets; repo-specific executable grader; repository also contains a patch-evaluation harness | **Mine schemas and Docker techniques; reject as quality template** |
| **SWE-bench Pro / Live / Multi-SWE-bench** | Independent descendants: longer tasks, continuously refreshed tasks, and multilingual tasks | **Useful source/mining ideas; do not inherit grading assumptions** |
| **Terminal-Bench** | Broad terminal-task dataset; old repository also contains legacy harness | **Useful task diversity and canary idea; not a coding-history dataset** |
| **SWE-smith** | Environment builder and synthetic bug/task generator; 52k training instances | **Reuse mutation/filtering machinery for challenge generation, not as gold benchmark** |
| **RepoBench** | Repository-level *line completion* dataset, exact/similarity grading | **Reject as agent benchmark; use only for retrieval/localization microdiagnostics** |
| **DevEval (SEKE)** | Manually annotated function/method generation in 115 real repos | **Reject as end-to-end benchmark; useful unit-level slice** |
| **DevBench (OpenCompass)** | 22-project lifecycle benchmark: design, setup, implementation, acceptance/unit-test generation | **Borrow lifecycle decomposition; implementation and LLM-judge quality are dated/weak** |
| **Harbor** | Agent-agnostic evaluation harness, task/dataset format, runtime adapters, trajectories, cloud execution | **Primary harness candidate** |
| **Pier** | DataCurve's Harbor-compatible fork, emphasizing agent network allowlists and trajectory critique | **Use only if its extra operations justify fork risk; current Harbor now covers much of the isolation gap** |
| **OpenHands/benchmarks** | OpenHands-specific benchmark runners; V0→V1 migration repository | **Adapter reference, not neutral foundation** |
| **Inspect AI** | General eval framework: datasets, agents, sandboxes, scoring, limits, logs, human intervention | **Strong alternative/control plane, especially for interaction and auditability** |
| **METR Task Standard 0.5** | Portable task-family specification and reference driver, deliberately agent-agnostic | **Borrow conceptual separation; do not adopt as primary format without an active runtime need** |
| **Ambig-SWE / ClarEval / HiL-Bench / SWE-Together / SWE-Interact** | Interactive or clarification benchmark datasets and their bespoke runners | **Borrow metrics/protocols; avoid wholesale adoption** |

---

## 2. DeepSWE/DataCurve audit

### What is unusually good

- **Originality at construction time.** Tasks and reference patches were written from scratch and not merged upstream. This is materially better than mining a public fix. The v1.1 repository contains all 113 task packages and states that each pins a repository/base commit.
- **Task realism is behavior-oriented.** 113 tasks across 91 active repositories and five languages; median repository contributes one task. Prompts avoid exposing a prescribed internal design and tests target public APIs/observable effects.
- **Grading architecture is strong.** Every task has a prompt, Docker environment, verifier, and review-only reference patch. Since v1.1, Pier extracts the agent's committed patch and grades it in a pristine verifier container, reducing test tampering and environment-state reward hacking.
- **QA is substantially better specified than SWE-bench.** Human review checks prompt↔verifier bijection, acceptance breadth, realism, and environment cleanliness; authoring runs verifiers three times and includes regression checks and diagnostic frontier-agent rollouts.
- **Operational telemetry is first-class.** Leaderboards include pass rate, cost, output tokens, steps, and trajectories, rather than presenting pass rate alone.
- **Licensing is unusually careful.** DeepSWE is Apache-2.0 for DataCurve's contributions and has a per-task provenance table for permissively licensed upstream code.

### Skeptical caveats

- **“Contamination free” is time-bounded, not permanent.** At creation there was no public gold patch. As of publication, the repository itself publicly exposes instructions, hidden tests, and reference patches. Future training or retrieval can ingest them. The right wording is “novel before release and leakage-resistant during a correctly isolated run,” not timelessly contamination-free.
- **Counterfactual plausibility is not maintainer acceptance.** Reviewers ask whether a maintainer *might* accept the task; there is no upstream issue lifecycle, code review, deployment, or maintainer acceptance. The result may be more demanding than SWE-bench yet less representative of the user's actual maintenance mix.
- **Long-horizon skew.** DataCurve itself notes under-representation of bug localization and refactoring, ≥500-star selection bias, only five languages, and standardized mini-swe-agent rather than model-native products.
- **Verifier audit is not an independent gold study.** The headline 0.3% false-positive / 1.1% false-negative estimates come from an LLM analyzer inspecting trajectories, verifier output, and reference solutions. DataCurve acknowledges analyzer errors. Treat the large gap versus its SWE-bench Pro sample as evidence of a problem, not as a calibrated absolute error rate.
- **Public tests enable benchmark-specific overfitting outside the sandbox.** Separate verifier containers hide them from the evaluated process, but an agent vendor can tune against the public corpus.
- **Expense.** Published runs are long (often tens of minutes and tens to hundreds of thousands of output tokens). At the site's July 2026 prices, a complete 113-task pass can readily cost hundreds to thousands of dollars per agent configuration before repeats and judge audits.
- **Pier creates ecosystem/fork cost.** DeepSWE's own README says Pier began as a Harbor fork because older Harbor blocked model API access in air-gapped tasks. Harbor at the inspected July 15 commit supports baseline and phase-specific no-network/allowlist policies and separate verifiers, so reassess whether Pier remains necessary.

**Primary sources:** [DeepSWE site/methodology](https://deepswe.datacurve.ai/blog/deepswe), [task format at inspected commit `6db64a4`](https://github.com/datacurve-ai/deep-swe/blob/6db64a40f3318d8659238ff34a8cc4b491c49205/README.md), [license provenance](https://github.com/datacurve-ai/deep-swe/blob/6db64a40f3318d8659238ff34a8cc4b491c49205/PROVENANCE.md), [Apache-2.0](https://github.com/datacurve-ai/deep-swe/blob/6db64a40f3318d8659238ff34a8cc4b491c49205/LICENSE).

---

## 3. Benchmark dataset audit

Ratings are relative: **High / Medium / Low**. “Contamination” means resistance of evaluation signal, not merely whether a canary string exists.

| Dataset | Realism & provenance | Contamination | Environment & grading | Interaction | Cost / maintenance / license | Recommendation |
|---|---|---|---|---|---|---|
| **DeepSWE** | High engineering scope; original tasks on real repos, but synthetic/counterfactual | High at creation; medium after public release | High: pinned Docker, separate verifier, behavioral + regression tests; review process | None in base dataset | High cost; active July 2026; Apache-2.0 + upstream licenses | **Reuse authoring/QA pattern** |
| **SWE-bench full/Lite** | Real issue/PR provenance, but concentrated Python projects; issue text often leaks solution shape | Low: issue, PR, tests, and fix public; full git history can expose gold | Medium reproducibility after Docker; grader uses FAIL_TO_PASS/PASS_TO_PASS tests inherited from historical PR, not a purpose-built acceptance suite | None | 120GB/16GB/8 CPU guidance; active; MIT code, upstream licenses still apply | **Reject as gold-quality template** |
| **SWE-bench Verified** | 500 engineer-screened solvable tasks, improving validity over full/Lite | Still low; verification does not remove public-fix contamination | Same fundamental patch/test grader; better task validity, not necessarily complete behavioral grading | None | Same resource profile; maintained; MIT | **Use only as compatibility baseline** |
| **SWE-bench Multimodal** | Real visual/UI issues; 100 dev + 500 private-test tasks | Better leaderboard secrecy for test split, but source PRs remain public | Private test evaluation improves anti-overfit; still PR-derived | Images, not user dialogue | Cloud submission friction; MIT | **Borrow sealed-test operation, not task derivation** |
| **SWE-bench Multilingual** | 300 tasks, 9 languages, 42 repos | Public-history contamination | Docker and language diversity are useful; task-specific grader burden grows | None | Moderate/high; MIT harness | **Borrow language coverage strategy** |
| **SWE-bench Pro** | Longer issue-resolution tasks, but only a small repository pool and public historical fixes | Low; DataCurve found agents reading gold from shipped `.git` history | Docker images exist, but project changelog acknowledges outdated/unintended tests and leaderboard issues; DataCurve's audit reports substantial misgrading | None | High; maintained unevenly; MIT | **Reject task/grader design** |
| **SWE-bench Live** | Continuously mined fresh PRs; 743 MultiLang tasks/381 repos plus Windows set reported May 2026 | Better temporal freshness, never immunity; monthly public release restarts leakage clock | Strong automation/RepoLaunch ambition, multi-OS; automated curation raises false-positive/flake burden | None | High build/maintenance; active June 2026; MIT | **Reuse rolling refresh and environment automation, with human QA** |
| **Multi-SWE-bench** | 1,632 tasks, 7 languages, 68 annotators | Public PR-derived | Docker, open images/code; historical patch semantics remain | None | High; active to Dec 2025 inspected commit; Apache-2.0 | **Useful diversity reference, not gold design** |
| **Terminal-Bench 2.x** | Broad end-to-end terminal work: coding, servers, security, data/ML; not personalized repo maintenance | Medium-low after public release; embeds a canary but canaries detect ingestion, not prevent memorization | Self-contained Docker/Compose, oracle solution, pytest verifier; task quality is heterogeneous and many goals are artifact/state checks | No human dialogue in core set | Often expensive; official harness is now Harbor; Apache-2.0 | **Reuse packaging, oracle smoke tests, and non-code task categories** |
| **SWE-smith** | Synthetic bugs grounded in real repos; scales to 52k | Better than public PR replay for generated mutations, but public dataset and low semantic novelty limit durability | Keeps mutations that break ≥1 existing test, then validates reproducibility; existing tests can be weak or implementation-local | None | Efficient generation (~$0.02 issue text claimed), Docker/Linux burden; active; MIT | **Use to generate training/challenge candidates; human-review eval set** |
| **RepoBench v1.1** | Real repositories, but target is one masked line (Python/Java) | Dataset is public and exact target is original source | EM/Edit Similarity/CodeBLEU reward textual match, not executable repository behavior | None | Cheap; last source update Aug 2024; CC-BY-4.0 | **Reject as agent outcome benchmark** |
| **DevEval (SEKE)** | 1,825 functions/methods from 115 repos with manually written requirements/tests | Public source targets; function-level extraction | Executes tests but mutates shared repo in-place and warns against parallel runs; Conda/manual archives harm reproducibility | None | Cheap/moderate; stale Sep 2024; no top-level license detected | **Only a unit-level diagnostic; do not redistribute without license clarification** |
| **DevBench (OpenCompass)** | 22 curated repos across design→setup→implementation→test lifecycle | Public and small | Docker support; acceptance/unit tests plus LLM judge for design; dated baseline, sparse setup tests acknowledged | Multi-agent workflow, not real user clarification | Stale May 2024; Apache-2.0 | **Borrow lifecycle taxonomy only** |
| **SWE-Lancer** | Real paid freelance tasks and manager decisions, economically grounded | Private/proprietary data portions help; code moved into OpenAI preparedness repo | Mixed IC SWE tasks and managerial decisions; not a clean fit for personal GitHub history | Some decision tasks, not agent-user coding loop | Operational/legal complexity; old repo moved | **Use “economic value” framing, not implementation** |

**SWE-bench sources:** [dataset sizes and variants at `f7bbbb2`](https://github.com/SWE-bench/SWE-bench/blob/f7bbbb2ccdf479001d6467c9e34af59e44a840f9/docs/guides/datasets.md), [Docker/resource guidance](https://github.com/SWE-bench/SWE-bench/blob/f7bbbb2ccdf479001d6467c9e34af59e44a840f9/README.md), [paper](https://arxiv.org/abs/2310.06770), [Verified report](https://openai.com/index/introducing-swe-bench-verified/), [Multimodal](https://arxiv.org/abs/2410.03859).  
**Descendants:** [SWE-bench Pro source `ca10a60`](https://github.com/scaleapi/SWE-bench_Pro-os/blob/ca10a60a5fcae51e6948ffe1485d4153d421e6c5/README.md), [SWE-bench Live `70ec57e`](https://github.com/microsoft/SWE-bench-Live/blob/70ec57e852e3f2d195790fe71f553e272c691833/README.md), [Multi-SWE-bench `24f493f`](https://github.com/multi-swe-bench/multi-swe-bench/blob/24f493f8a103e72312ded4f6b9c89f081d69cb09/README.md).  
**Other datasets:** [Terminal-Bench source `d28711d`](https://github.com/harbor-framework/terminal-bench/blob/d28711d0da2675d0bb1d56de45ae5df6082438a3/README.md), [SWE-smith `9b74ac0`](https://github.com/SWE-bench/SWE-smith/blob/9b74ac08118a85c39c356802f7961893af73e07f/README.md), [RepoBench `e0cfd34`](https://github.com/Leolty/repobench/blob/e0cfd34c9e7cd8f057efd32b9280b9719ae12a91/README.md), [DevEval `c165345`](https://github.com/seketeam/DevEval/blob/c1653455e0a18480a29aa07ba51636070f113316/README.md), [DevBench `bb593c1`](https://github.com/open-compass/DevEval/blob/bb593c1f9c535ff0dde0c9f4807d58c9566c3a6c/README.md).

---

## 4. Harness and task-standard audit

### Harbor — preferred implementation base

At inspected commit [`d3e606d`](https://github.com/harbor-framework/harbor/tree/d3e606d9f7d1e111bb22d3d820ebed03ec300eb3) (2026-07-15), Harbor is actively maintained and supports many native coding agents, local Docker and numerous cloud sandboxes, arbitrary metadata, resource limits, network baselines and phase-specific allowlists, separate verifier containers, structured rewards/artifacts, ATIF trajectories, and sequential multi-step tasks with optional native session resume. It is Apache-2.0.

**Strengths:** direct fit for directory-per-task GitHub work; agent/harness adapters; deterministic task packages; provider portability; cloud parallelism; separate verification; active ecosystem.  
**Risks:** fast-moving schema/API, large adapter surface, cloud-provider semantic differences (especially network policies), and operational complexity. Pin Harbor version, image digests, agent version, model endpoint, prompts, resource/time limits, and network policy in every run manifest.

Sources: [task structure](https://github.com/harbor-framework/harbor/blob/d3e606d9f7d1e111bb22d3d820ebed03ec300eb3/docs/content/docs/tasks/index.mdx), [multi-step/resume](https://github.com/harbor-framework/harbor/blob/d3e606d9f7d1e111bb22d3d820ebed03ec300eb3/docs/content/docs/tasks/multi-step.mdx), [network policy](https://github.com/harbor-framework/harbor/blob/d3e606d9f7d1e111bb22d3d820ebed03ec300eb3/docs/content/docs/tasks/network-policy.mdx), [separate verifier](https://github.com/harbor-framework/harbor/blob/d3e606d9f7d1e111bb22d3d820ebed03ec300eb3/docs/content/news/separate-verifier-sandboxes.mdx).

### Inspect AI — strongest audit/intervention alternative

At inspected commit [`ea007a7`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/ea007a79c556e30fb391c5e98ce2bf80b2362fbf) (2026-07-15), Inspect is a mature MIT-licensed general evaluation framework. It provides per-sample Docker/Compose or external sandboxes, arbitrary custom scorers, model-graded scoring, full transcripts, retries/eval sets, time/message/turn/token/cost limits, scanner-based transcript audit, checkpointing, third-party agent bridges, and real human intervention. Its ACP support lets a human interrupt, redirect, approve tools, or answer structured `ask_user` calls, with all intervention logged.

**Strengths:** excellent experiment records, human-in-loop functionality, limits, multi-agent composition, and forensic analysis.  
**Risks:** more Python framework work to express a coding benchmark; CLI coding agents generally rely on the separate Inspect SWE package; arbitrary flexibility makes cross-project task portability weaker than a simple directory standard; checkpointing was still development-only at the inspected commit.

Sources: [agents](https://inspect.aisi.org.uk/agents.html), [sandboxing](https://inspect.aisi.org.uk/sandboxing.html), [agent bridge](https://inspect.aisi.org.uk/agent-bridge.html), [human intervention/ACP](https://inspect.aisi.org.uk/intervention.html), [tool approval](https://inspect.aisi.org.uk/approval.html), [logging](https://inspect.aisi.org.uk/eval-logs.html), [limits](https://inspect.aisi.org.uk/setting-limits.html).

### OpenHands evaluation harness

The dedicated [OpenHands benchmarks repository at `4e5469e`](https://github.com/OpenHands/benchmarks/tree/4e5469e0caaf54d1ad827d18b524bdfb79d58430) is MIT-licensed and provides active SWE-bench/SWE-bench Pro runners, local Docker and a high-parallel remote runtime, rich tool-call logs, and a pinned Agent SDK submodule. Its README explicitly warns that V0→V1 migration is in progress and that benchmark commits and SDK commits have compatibility coupling.

**Verdict:** valuable implementation evidence for OpenHands itself, but reject as the neutral benchmark substrate. Otherwise changes in OpenHands SDK, benchmark runner, and evaluated agent are entangled. Run OpenHands through Harbor/Inspect for cross-agent comparisons; retain the OpenHands runner only for reproduction.

### METR Task Standard 0.5

[`METR/task-standard` at `03236e9`](https://github.com/METR/task-standard/tree/03236e9a1a0d3c9f9d63f6c9e60a9278a59d22ff) cleanly separates environment, instruction, optional score function, driver, agent, permissions, and auxiliary VMs. It also specifies that agents run unprivileged and without internet unless requested. The standard deliberately does **not** define the agent or interaction transport. MIT-licensed.

**Verdict:** excellent conceptual checklist and useful if interoperability with METR infrastructure matters. It was still pre-1.0, explicitly unstable, and the inspected repository's last commit was February 2025. Harbor is more immediately useful for coding agents. Borrow the agent/task separation and permission model rather than introducing a second task representation.

---

## 5. Clarification and interactive-agent benchmarks

| Benchmark | What it measures | Strengths | Problems / recommendation |
|---|---|---|---|
| **Ambig-SWE** | Detection, question asking, and implementation on an underspecified SWE-bench Verified variant | Separates full, hidden, and interactive conditions; simulated user holds full spec; accepted at ICLR 2026 | GPT-4o-generated removal of details from already contaminated SWE-bench tasks; old OpenHands fork is difficult to maintain; MIT. **Borrow three-condition experiment, not dataset/runtime.** [Paper](https://arxiv.org/abs/2502.13069), [source `ed58236`](https://github.com/sani903/InteractiveSWEAgents/tree/ed58236332ad039b54f968145d7bed9ba988f262). |
| **Ask or Assume?** | Uncertainty-aware single/multi-agent clarification scaffold on Ambig-SWE | Separates intent monitor from executor; studies calibrated query use | Inherits Ambig-SWE's construction and SWE-bench contamination; spot-check rather than full independent reannotation. **Agent-design prior, not benchmark foundation.** [Paper](https://arxiv.org/abs/2603.26233). |
| **ClarEval** | Controlled ambiguity “unit tests” over HumanEval; ATC/KQC/EAR metrics | Deterministic simulator and clear efficiency metrics | Function puzzles, not repositories; GitHub README at inspected commit is only `# test24`, no detected license, effectively unreproducible from repo. **Reject implementation; retain metric ideas.** [Paper](https://arxiv.org/abs/2603.00187), [source](https://github.com/JialinLi13/ClarEval). |
| **HiL-Bench** | Selective escalation on human-validated progressive blockers; full/no-tool/ask-human modes; Ask-F1 | Best process formulation: blocker recall vs question precision prevents question spam; blockers emerge through work | SWE tasks are heavily modified from SWE-bench Pro, inheriting its base quality/contamination; `ask_human` answer quality depends on a judge model; no repository license detected. **Reuse blocker registry, modes, and metrics; write private tasks.** [Paper](https://arxiv.org/abs/2604.09408), [source `352d14c`](https://github.com/hilbenchauthors/hil-bench/tree/352d14c861f2531949dfa91848d4b2fe46b8a247). |
| **SWE-Together** | 109 interactive sessions reconstructed from real user-agent sessions; reactive user simulator; correctness + user-correction burden | Most directly relevant provenance pattern; pinned repo/base, Docker, real intent/follow-up shape; multiple native agents | LLM simulator and agentic correctness judge add variance and model dependence; task specs expose reference patch/intents; expensive (agent + Gemini simulator + Anthropic judge + sandbox); privacy/licensing of original sessions must be checked. Apache-2.0 code. **Borrow replay structure and correction metric; use real/private deterministic follow-ups where possible.** [Source `811a70a`](https://github.com/Togetherbench/SWE-Together/tree/811a70a28ff20bfbeabf9a8b5ec42152d16c9b4f), [paper](https://arxiv.org/abs/2606.29957). |
| **SWE-Interact** | 75 multi-turn adaptations: 25 each from DeepSWE, SWE-bench Pro, and SWE Atlas Refactoring; persona-conditioned LLM user inspects workspace and progressively reveals requirements | Runs in Harbor; preserves original verifiers; explicitly compares single-turn and multi-turn; user simulator has grounded shell access | Artificially stages fully known requirements rather than measuring spontaneous clarification; source quality is mixed and 25 tasks inherit SWE-bench Pro flaws; simulator roughly doubles/triples steps and can multiply tokens/cost; persona narrow (“Expert Nitpicker”). Apache-2.0. **Borrow Harbor MCP user-tool pattern, not mixed task corpus.** [Source `b32f98c`](https://github.com/scaleapi/SWE-Interact/tree/b32f98c3b8f76ca65e84341d1f30e5af7135f85d), [paper](https://arxiv.org/abs/2606.30573). |

**Key distinction:** interactive debugging (for example [Debug2Fix](https://arxiv.org/abs/2602.18571)) improves the agent's environment-observation tools; it is not human clarification. It is still valuable to expose debugger primitives in bug tasks, but report it as harness/tooling capability rather than user interaction.

---

## 6. Concrete design for a personalized GitHub-history benchmark

### A. Corpus and provenance

1. Export the user's repositories, issues, PRs, review comments, CI logs, and commits with immutable IDs and timestamps.
2. Label each candidate's provenance: `historical-public`, `historical-private`, `unmerged`, `counterfactual`, or `newly-authored`.
3. Stratify by the user's actual work mix rather than benchmark fashion: bug localization, refactor, dependency/API migration, test repair, feature work, docs/config/CI, review follow-up, and multi-repo tasks.
4. Preserve repository and dependency licenses. The benchmark wrapper license cannot relicense upstream source; keep a per-task provenance/license manifest like DeepSWE. For private tasks, document non-redistributability explicitly.

### B. Two evaluation sets, never one blended score

- **Historical replay:** task starts immediately before the user's change and uses the original issue/review context available then. Strip later commits and remote access. Report as “personal-history replay,” not uncontaminated reasoning.
- **Sealed transfer:** create new tasks from recurring patterns in history (same architectural habits, different bug/feature), or private mutations reviewed by the user. Keep prompt, verifier, and reference patch private. Rotate tasks rather than publishing gold.

Add a small **fresh live set** quarterly. Once a sealed task is published, move it to the replay set.

### C. Task package

Adopt Harbor's directory model and pin its schema/runtime:

```text
task.toml                 # provenance, repo, base SHA, image digest, limits, license
instruction.md            # only initial user-visible context
environment/Dockerfile    # dependencies pinned; shallow/no future git history
tests/                    # hidden behavioral + regression verifier
solution/                 # sealed reference patch; reviewer aid only
pre_artifacts.sh          # exports patch/commits to pristine verifier
interaction/              # optional blocker registry and deterministic responses
```

- Disable internet during agent work except exact model/API endpoints; do not expose GitHub search.
- Use a shallow snapshot with no descendants of the base commit and no gold branches/tags/reflogs.
- Grade a patch/artifact in a pristine separate verifier, never the agent-mutated container.
- Pin image digests and package lockfiles; run oracle/no-op smoke tests in CI.

### D. Grader construction and audit

1. Write tests from the behavioral specification, not by copying only the original PR's tests.
2. Include focused acceptance tests, property/metamorphic tests where appropriate, and a bounded regression suite.
3. Verify: base fails, reference passes, tests pass repeatedly, and no-op/trivial/stub patches fail.
4. Build a bank of plausible wrong patches from historical failed attempts and frontier-agent rollouts. Use mutation testing to estimate verifier sensitivity.
5. Human-review prompt↔verifier bijection and alternate correct implementations. Any test importing a newly invented private helper is suspect.
6. Use LLM judges only to audit verifier disagreements and classify failures. Manually adjudicate all leaderboard-impacting disagreement samples.
7. Version any changed task/verifier as a new benchmark release; never silently rewrite historical results.

### E. Interaction protocol

Create paired conditions for a subset:

- `full_info`: all blocker resolutions in prompt.
- `baseline`: blockers withheld, no ask tool.
- `ask_user`: blockers withheld, structured ask tool available.

Each blocker record should include when it becomes discoverable, acceptable question paraphrases, deterministic answer, and whether it is truly unresolvable from the repository. Score:

- final executable correctness;
- blocker recall;
- question precision/relevance;
- redundant question count and turns-to-resolution;
- human correction/nudge burden;
- whether the agent updated implementation after the answer.

Do **not** let a free-form LLM user simulator be the only oracle. If simulating richer reviews, fix the simulator model/version/prompt, log its workspace observations, run repeats, and report simulator sensitivity separately.

### F. Agent-vs-model comparisons

For personalized utility, the native product scaffold is part of what the user is choosing. Therefore:

- primary leaderboard: native agents (Codex, Claude Code, OpenHands, etc.) with their normal tools;
- controlled secondary study: one common minimal scaffold (for example mini-swe-agent) to isolate model differences;
- never compare a native-agent result to a minimal-harness result without labeling the harness;
- record agent version, system prompt hash, model endpoint/snapshot, reasoning level, tools, limits, retries, and environment.

### G. Reporting

Use a scorecard, not a single pass percentage:

- task success and stable success across ≥3 runs;
- results by repo/task type/difficulty and historical vs sealed status;
- regression severity and verifier-audit disagreement;
- tokens, model cost, wall-clock, steps/tool calls;
- clarification Ask-F1 and user-correction burden;
- infrastructure/error/timeout rate kept separate from capability failure.

Start with 20–30 carefully reviewed tasks. A small benchmark with defensible graders and useful failure analysis is more valuable than hundreds of mined PRs.

---

## 7. Reuse / reject decision

### Reuse directly

- **Harbor task format/runtime**, pinned to a release, including separate verifiers, network policy, artifacts, trajectories, and optional multi-step/session resume.
- **DeepSWE QA checklist:** original or sealed tasks, short behavioral prompts, broad repo sampling, shallow history, known-correct reference, behavioral + regression tests, flake runs, diagnostic rollouts, manual prompt↔verifier review, license provenance.
- **Inspect AI concepts/components** when human intervention, approval, transcript scanning, strict limits, or forensic logging exceed Harbor's needs.
- **HiL-Bench metrics:** blocker registry, full/baseline/ask modes, precision/recall balance.
- **SWE-smith generators** for producing candidates and plausible wrong patches, followed by human acceptance.
- **SWE-bench Live's rolling refresh** and **Terminal-Bench's oracle/no-op smoke discipline and canary**, with the caveat that a canary detects leakage but does not make a benchmark clean.

### Reuse only as diagnostics

- RepoBench retrieval/cross-file completion tasks.
- DevEval function-level implementation.
- DevBench lifecycle decomposition.
- Common minimal scaffold runs to isolate models.
- LLM trajectory judges for taxonomy and verifier audit.

### Reject as the core design

- Public-PR replay presented as contamination-resistant.
- SWE-bench FAIL_TO_PASS/PASS_TO_PASS tests as sufficient acceptance criteria.
- Shipping full `.git` history or allowing unrestricted internet/GitHub search.
- Exact-match/CodeBLEU as engineering correctness.
- One shared mutable repository for parallel grading.
- A free-form LLM judge or user simulator as the sole source of truth.
- OpenHands' migrating benchmark repository as the cross-agent foundation.
- ClarEval's current code release and any dataset with no clear redistribution license.
- A single aggregate leaderboard that mixes model, harness, task provenance, interaction burden, and infrastructure failures.

## Bottom line

The best practical stack is **DeepSWE-style private task curation on Harbor**, with **Inspect-style transcript/intervention auditing where needed**. The central methodological choice is not which public benchmark to clone; it is preserving the distinction between authentic-but-contaminated history and novel sealed tasks. If that distinction is explicit and the verifier is purpose-built, adversarially audited, and isolated, the resulting benchmark can be both personalized and substantially more trustworthy than SWE-bench.