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

`python3 -m sitegen build --data-root <root> --output _site --base-path <path>` produces:

- `/index.html`: experiment index;
- `/experiments/<id>/index.html`: experiment summary and filterable cell table;
- `/experiments/<id>/cells/<cell-id>/index.html`: semantic cell detail page;
- `/data/site.json`, `/data/experiments/<id>.json`, and per-cell JSON: stable machine-readable data;
- `/artifacts/<experiment-id>/<cell-id>/...`: copied committed evidence, including canonical transcript JSONL, patch, verifier output, and manifests;
- `/assets/site.css` and `/assets/site.js`: intentionally small baseline assets with stable classes and data attributes for a separate design pass; and
- `/.nojekyll`.

All generated JSON uses sorted keys and stable indentation. Directory and row traversal is sorted. No wall-clock timestamp is emitted, so identical inputs and arguments produce byte-identical output. The output directory is replaced atomically enough for CI: generation occurs in a sibling temporary directory and is renamed only after successful generation.

## Partial and malformed data behavior

Discovery is the union of results rows, evidence-index entries, and committed evidence run directories. Thus a completed evidence cell can appear before an aggregate `results.json` update. Matrix-record data fills missing result fields when available.

A malformed optional document does not abort the site build. The affected experiment or cell remains browsable with `Unavailable` values and a visible warning. Unsafe artifact paths (absolute paths or `..` traversal) are rejected. Artifact hashes are recomputed during generation and mismatches are shown; the published detail JSON preserves expected and actual hashes. A missing experiment tree produces a valid empty site.

Validation is separate from ingestion tolerance. `python3 -m sitegen validate --site _site` verifies required pages/data, JSON readability, internal root-relative URLs under the configured base path, and referenced local files. It fails only when the generated site itself is inconsistent.

## Accessibility and progressive enhancement

Pages use landmarks, headings, labeled controls, tables with captions and header scopes, status text, and links that work without JavaScript. JavaScript only adds client-side filtering and result counts. Focus styles, reduced-motion compatibility, readable contrast, and horizontal table overflow are baseline requirements. CSS custom properties, component classes, `data-*` hooks, and the standalone asset files are extension points; visual polish is intentionally out of scope.

## GitHub Pages deployment

The Pages workflow:

1. checks out `main` at the workspace root for trusted generator/site code;
2. checks out `results-live` into a separate `results-live/` directory for committed live data;
3. runs unit tests, builds with the repository Pages base path, and validates output;
4. configures Pages and uploads `_site` with the official Pages actions; and
5. deploys with the official deploy action and the minimal Pages/OIDC permissions.

It runs on site-code pushes to `main`, manual dispatch, and `repository_dispatch` with event type `results_updated`. Branch data is treated only as data and no code from `results-live` is executed.

## Non-goals

The site is not an evaluation runner, review editor, database, authentication boundary, or replacement for artifact manifests. It does not infer that subjective scores can repair a deterministic failure, and it does not hide provider/model identity in published output.
