Some GitHub releases attest each file inside an archive rather than the archive blob itself. Make mise accept those safely. This is security-sensitive; the fallback must fail closed.

Add thorough focused tests, preserve existing archive-level verification, and commit the finished change. You may use `ask_user` for consequential trust-boundary or scope questions; do not guess toward permissiveness.
