# Static results browser: architecture and requirements

## Purpose and trust model

The results browser publishes committed evaluation output as a static GitHub Pages site. It never runs an evaluation, contacts a model provider, reads `.runs`, or requires credentials. The committed deterministic verifier result is the authoritative behavioral result. Blinded proctor review is displayed as a separate, non-overriding assessment of code quality and mergibility.

Provider and model attribution is explicit on every cell. Canonical transcripts remain JSONL, candidate changes remain patches, and verifier output remains plain text so that published evidence can be independently downloaded and hashed.

## Inputs

The generator accepts a repository-like data root and reads only:

- `reports/experiments/<experiment-id>/results.json`;
- `reports/experiments/<experiment-id>/subjective-summary.md`;
- `reports/experiments/<experiment-id>/summary.md`;
- `reports/experiments/<experiment-id>/evidence/index.json`;
- `evidence/runs/<cell-id>/matrix-record.json`;
- `evidence/runs/<cell-id>/proctor-review.json`;
- `evidence/runs/<cell-id>/artifacts.json` and the committed artifacts it names; and
- `experiments/<experiment-id>.toml` for description, stage, planned models/cells, and proctor attribution.

The generator does not inspect uncommitted run directories. Inputs may be absent, truncated, malformed, or temporarily disagree while `results-live` is being updated.

## Output contract

`cd web && RESULTS_DATA_ROOT=<root> TASK_DATA_ROOT=<trusted-root> BASE_PATH=<path> npm run build` produces:

- `/index.html` and `/tasks/index.html`: task-first landing and task index;
- `/tasks/<task-id>/index.html`: task provenance and all associated runs;
- `/models/index.html` and `/models/<provider--model>/index.html`: model views;
- `/runs/<experiment-id>/<cell-id>/index.html`: semantic run detail, diff, transcript, verifier result, review, and evidence;
- `/glossary/index.html`: plain-language terminology;
- `/evidence/<experiment-id>/<cell-id>/...`: allowlisted, Git-committed evidence with recomputed hashes; and
- `/.nojekyll`.

Directory and row traversal is sorted and no wall-clock timestamp is emitted, so identical inputs and arguments produce byte-identical output. Astro replaces `dist/` on each build, and the evidence preparation step removes stale copied evidence first.

## Partial and malformed data behavior

Discovery is the union of results rows, evidence-index entries, and committed evidence run directories. Thus a completed evidence cell can appear before an aggregate `results.json` update. Matrix-record data fills missing result fields when available.

A malformed optional document does not abort the site build. The affected experiment or cell remains browsable with `Unavailable` values and a visible warning. Unsafe artifact paths (absolute paths, `..` traversal, or symlinks) are rejected. Only explicit allowlisted files that `git ls-files` proves committed are copied. Artifact hashes are recomputed during generation and mismatches are shown. A missing experiment tree produces a valid empty site.

Validation is separate from ingestion tolerance. `npm run validate` verifies required pages, real run deep links, and the absence of hash-only routing.

## Accessibility and progressive enhancement

Pages use landmarks, headings, labeled controls, tables with captions and header scopes, status text, and links that work without JavaScript. JavaScript provides the persisted theme toggle and interactive React evidence viewers; task/model/run navigation, verifier results, final transcript messages, artifact metadata, and raw patch/JSONL downloads remain available in static HTML. Focus styles, reduced-motion compatibility, readable contrast, dark-theme support, and constrained horizontal evidence overflow are baseline requirements.

The frontend is Astro with React islands, Tailwind CSS, and daisyUI. Candidate patches use the pinned `@pierre/diffs` React renderer. Transcript composition adapts Vercel AI Elements' pinned Conversation, Message, and Tool patterns; candidate final messages are rendered with `react-markdown` and GFM while raw HTML remains disabled.

## GitHub Pages deployment

The Pages workflow:

1. checks out `main` as trusted Astro/site code;
2. checks out `results-live` into a separate `results-live/` directory for committed live data;
3. runs `npm ci`, lint, Astro type checking, Vitest, builds with the Pages base path, and validates output;
4. configures Pages and uploads `web/dist` with immutable-SHA-pinned official actions; and
5. deploys with the official deploy action and the minimal Pages/OIDC permissions.

It runs on site-code pushes to `main`, manual dispatch, and `repository_dispatch` with event type `results_updated`. Branch data is treated only as data and no code from `results-live` is executed.

## Non-goals

The site is not an evaluation runner, review editor, database, authentication boundary, or replacement for artifact manifests. It does not infer that subjective scores can repair a deterministic failure, and it does not hide provider/model identity in published output.
