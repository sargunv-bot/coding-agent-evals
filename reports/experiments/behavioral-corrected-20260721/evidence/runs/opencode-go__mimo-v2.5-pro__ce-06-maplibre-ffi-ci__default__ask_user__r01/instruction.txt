Our CI target support policy is trapped in a hand-written workflow and keeps drifting. Make it declarative, generate the checked-in workflow from manifests, and enforce that it stays in sync. Contributors must use `mise run ci:generate-workflow` to generate it and `mise run ci:generate-workflow -- --check` for a non-mutating drift check.

Preserve current CI behavior unless it is clearly duplicated policy. Keep normal contributor workflow simple, test the generator, and commit the finished change. You may use `ask_user` for consequential architecture or scope questions.
