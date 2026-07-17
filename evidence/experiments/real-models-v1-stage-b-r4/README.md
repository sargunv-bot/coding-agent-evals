# Experiment evidence

Each directory under `runs/` is keyed by the immutable experiment cell ID. `transcript.jsonl` is the canonical raw OpenCode event stream; `model.patch` is the complete candidate diff; `matrix-record.json` contains deterministic scoring and normalized usage; `verifier/` contains hidden-verifier output; and `proctor-review.json`, when present, contains non-overriding qualitative scores with per-dimension rationale. `artifacts.json` records byte sizes and SHA-256 digests for every run artifact.
