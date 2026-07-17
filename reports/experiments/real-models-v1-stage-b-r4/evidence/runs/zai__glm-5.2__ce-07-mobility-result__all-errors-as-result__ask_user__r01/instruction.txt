Make the public Ktor clients return `Result` instead of throwing. Apply it consistently across GBFS v1–v3 and GOFS, including public API and tests.

Commit the finished change. You may use `ask_user` if consequential error-semantics or compatibility scope is genuinely unclear.
