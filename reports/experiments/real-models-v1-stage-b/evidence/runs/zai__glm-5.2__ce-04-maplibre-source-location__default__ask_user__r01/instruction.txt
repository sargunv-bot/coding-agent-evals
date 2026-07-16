OpenHarmony's C++ environment has no `<source_location>`. Give core a standards-safe fallback without extending `std`, and keep call sites useful for diagnostics.

Support the normal standard-library path too, update relevant build manifests, and commit the finished change. You may use `ask_user` if consequential scope is genuinely unclear.
