# Stage-B r4 partial invalidation

Eighteen completed cells remain valid and are retained. They did not invoke a failed
clarification transport and their canonical OpenCode streams terminate normally with
`step_finish(reason="stop")`.

The following two cells are intentionally excluded from this report and evidence bundle:

- `zai__glm-5.2__ce-05-mise-slsa-archive__default__ask_user__r01`
- `zai__glm-5.2__ce-06-maplibre-ffi-ci__default__ask_user__r01`

Both invoked `proctor_ask_user`. OpenCode 1.18.2 used its MCP SDK's 60-second request
timeout while the benchmark proctor server allowed 30 minutes. Valid host answers arrived
after the client timeout and were never delivered to the candidate. These are
infrastructure-invalid outcomes, not behavioral failures.

The transport and incomplete-turn safeguards were repaired in
[PR #20](https://github.com/sargunv-bot/coding-agent-evals/pull/20). Only these two invalid
cells and cells not yet executed under r4 require execution under the repaired freeze.
Raw local r4 artifacts are preserved for diagnosis.
