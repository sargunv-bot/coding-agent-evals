Our CI target support policy is trapped in a hand-written workflow and keeps drifting. Make it declarative, generate the checked-in workflow from manifests, and enforce that it stays in sync.

Preserve current CI behavior unless it is clearly duplicated policy. Keep normal contributor workflow simple, test the generator, and commit the finished change.
