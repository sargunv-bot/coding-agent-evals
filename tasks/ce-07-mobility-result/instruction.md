Make the public Ktor clients return `Result` instead of throwing for operational failures. Transport, HTTP, and decoding failures must become `Result.failure`; invalid caller arguments and other programmer/precondition misuse must still throw immediately before any network request. Apply this consistently across GBFS v1–v3 and GOFS, including public API and tests.

Commit the finished change. You may use `ask_user` if consequential error-semantics or compatibility scope is genuinely unclear.
