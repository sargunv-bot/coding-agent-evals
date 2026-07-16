# Coding Agent Evals

Private, personalized coding-agent evaluations derived from Sargun Vohra's recent engineering work.

The suite is designed around:

- terse, realistically ambiguous prompts;
- deterministic behavioral and regression checks;
- rootless Podman isolation;
- pristine verifier environments;
- a host-side SOTA proctor for clarification and qualitative review;
- explicit separation of historical replay from sealed transfer tasks;
- raw task evidence rather than a single leaderboard score.

## Status

Under construction. Candidate-model evaluation is intentionally disabled until task packages pass no-op, gold, mutant, isolation, and flake validation.

## Licensing

Repository-authored benchmark infrastructure and task specifications are Apache-2.0. Upstream repositories, source snapshots, and historical patches retain their own licenses; see per-task provenance manifests.
