# Proctor and qualitative review

Candidate agents receive one additional MCP tool:

```text
ask_user(question: string) -> string
```

## Live proctor policy

The proctor is the active SOTA Hermes model acting as Sargun would:

- answer scope, product semantics, compatibility constraints, and consequential preferences;
- clarify intent without disclosing the historical patch, hidden tests, implementation plan, or expected symbol names;
- point the agent back to repository evidence when the answer is already present there;
- decline broad requests such as “what should I code?”;
- keep answers concise and operational;
- record the exact question, answer, proctor identity/model, task, scenario, and timestamp.

For repeated runs, reuse an existing semantically equivalent answer when possible. New materially distinct questions may receive a live answer. Equivalent models and conditions must not receive materially different requirements.

## Final review

After deterministic verification, the proctor reviews a model-blinded patch and trajectory. It reports, separately from executable reward:

- scope discipline;
- code clarity;
- test quality;
- repository fit and taste;
- security/safety;
- mergeability and explicit blockers.

Scores are 1–5 evidence labels, not a substitute for deterministic correctness. A deterministic pass can still be judged unmergeable; a deterministic failure cannot be promoted to a behavioral pass by taste review.

## Transport

`proctor-mcp` is a static stdio MCP server mounted read-only in the agent container. It writes immutable JSON questions to a run-specific queue and blocks until the host proctor writes an answer with provenance. The MCP process has no provider credentials and no network dependency.
