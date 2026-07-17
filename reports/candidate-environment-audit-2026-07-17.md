# Candidate environment audit — 2026-07-17

## Decision

Candidate results produced before this repair are environmentally confounded and must not be reused. The interrupted Stage-B run is intentionally not resumable. All previous candidate result records and published candidate evidence will be removed before a fresh sequential campaign.

## Readiness contract

Every task contains an executable `environment/dev-check.sh`. `cae audit-environment [task-id]` builds the candidate image and executes that script:

- as the unprivileged `agent` user;
- with `--network none`;
- within the task CPU, memory, and PID limits;
- after reserving the task's declared storage budget through the host free-space guard;
- without hidden tests, credentials, host homes, or container sockets.

Expensive dependencies, fixtures, toolchains, and normal build products are materialized during image construction so candidate verification is incremental rather than a first-build exercise.

## Final evidence

| Task | Clean offline readiness | Solution-applied readiness | Incremental audit duration | Repair summary |
|---|---|---|---:|---|
| CE-01 Antidote | Pass; complete live-clone suite and 621/621 unit tests | Pass | 17.22 s | Added Make, clitest, man-db, ripgrep, deterministic Asciidoctor 2.0.26, and local bare mirrors for every real-test plugin dependency. Full destructive integration tests run in a temporary candidate-tree copy. |
| CE-02 Horologia | Pass; server, API, and CLI vet/test/build | Pass | 12.21 s | Prewarmed all Linux Go modules, embedded PostgreSQL, and a noninteractive D-Bus Secret Service collection for CLI keyring tests. |
| CE-03 JVL | Pass; fmt, Clippy, build, complete tests and docs | Pass | 9.26 s | Added rustfmt, Clippy, ripgrep, and retained complete Cargo build/test artifacts. |
| CE-04 MapLibre Native | Pass; portability matrix, CMake configure, `mbgl-core` | Pass; 97 affected objects rebuilt and linked | 0.82 s clean | Added GCC/Clang, CMake/Ninja, Linux development libraries, recursive submodules, CMake FetchContent cache, and a compiled `mbgl-core` tree. |
| CE-05 mise | Pass; fmt, task lint, all-feature build, sigstore tests, 934 binary tests | Pass | 73.56 s | Corrected `LIBCLANG_PATH` to LLVM 14; added rustfmt, Clippy, ripgrep; retained all-feature build and task/default test profiles. |
| CE-06 MapLibre FFI | Pass; locked uv sync, Ruff, ty | Pass; generator compiles and its `--check` succeeds | 0.40 s | Switched to pinned Python 3.14, installed pinned uv, materialized the locked environment and offline package cache, and made the readiness script candidate-generator-aware. |
| CE-07 Mobility | Pass; LFS, ABI update/check, JVM/JS/Wasm/Linux Native tests, detekt | Pass for both scenario gold patches | 68.04 s clean | Materialized and verified LFS objects; added git-lfs, libatomic1, and ripgrep; retained Gradle, Konan, Node/Yarn/npm, detekt, ABI, and multiplatform compilation caches. |

All listed solution checks ran in disposable containers after applying the public solution patch, with networking disabled.

## Scope boundaries

“Normal development workflow” is interpreted as the complete contributor surface reasonably relevant and available on the task’s Linux candidate platform, not every product target in a large monorepo.

- CE-02 covers the complete Linux Go server/API/CLI surface. It does not install unrelated Android, web, or mobile SDK stacks.
- CE-05 compiles all optional features and runs the complete `mise-sigstore` and default `mise` binary suites. `cargo test --all-features` is intentionally excluded: its duplicate all-backend test profile exceeded 40 GiB and the task’s 20 GiB writable budget. The all-feature compile gate still catches optional dependency and libclang defects.
- CE-04 validates the task’s C++ core and compiler portability path rather than every graphical demo/application target.
- CE-06 validates the Python workflow generator surface rather than every language target in MapLibre Native.

## Storage behavior

A failed CE-05 all-feature-test experiment briefly violated the 80 GiB host-free-space floor. It was stopped, ten orphaned Buildah working containers were removed, and obsolete model/debug images were deleted. The final task-centric operating policy is:

1. build and audit one repaired task image;
2. run that task’s model cells sequentially;
3. inspect every receipt/transcript;
4. remove model-specific images before proceeding to the next large task.

This avoids retaining seven large prewarmed task images plus all model layers simultaneously.

## Harness verification

- `pytest`: 36 passed, 1 skipped
- Ruff lint and format: pass on `src tests`
- mypy: pass on all source modules
- all task manifests: valid
- all readiness scripts: executable and Bash-syntax-valid
- `git diff --check`: pass
- all seven final Containerfile SHA-256 values recorded in task provenance

## Control calibration

All eight task/scenario packages were recalibrated after environment repair:

- 31 total control executions;
- every no-op failed as expected;
- every gold patch passed twice independently;
- every declared mutant failed as expected;
- zero final infrastructure errors.

CE-06 initially exposed a stale verifier-only `/opt/venv/bin/python` path from the old image. The verifier now uses the repaired image's pinned Python 3.14 system interpreter, where its pinned Pydantic and PyYAML dependencies are installed. All CE-06 controls then calibrated successfully.

## Sequential execution enforcement

The matrix CLI supports exact single-cell execution:

```bash
cae matrix run manifest.toml --providers providers.toml --cell <exact-cell-id>
```

Unknown IDs are rejected before lock creation or image builds. A partial lock builds and records only the selected task image; later task selections append their image provenance. Full matrix behavior remains available when `--cell` is omitted, but it will not be used for the fresh candidate campaign.

## Required next steps

1. Sign and merge the repair commit.
2. Delete all old candidate run records and published candidate evidence.
3. Execute exactly one selected model/task/scenario cell at a time.
4. Inspect environment behavior, transcript, diff, verifier receipt, and clarification exchange before authorizing the next cell.
