Some GitHub releases attest each file inside an archive rather than the archive blob itself. Make mise accept those safely. This is security-sensitive; the fallback must fail closed.

Add thorough focused tests, preserve existing archive-level verification, fail closed rather than guessing toward permissiveness, and commit the finished change.
