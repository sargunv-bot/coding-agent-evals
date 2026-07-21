# Corrected behavioral evaluation reviews

This package contains the authoritative model-blind qualitative reviews produced after the 2026-07-21 verifier repair and targeted reruns.

- 16 authoritative candidate patches are represented.
- Candidate provider/model identity was removed from every reviewer packet.
- Reviewer assignment prohibited a reviewer model from reviewing its own candidate output.
- Every finalized review attests `blinded_to_model_identity: true` and `can_override_deterministic: false`.
- Historical model-identified reviews are retained as history but superseded for corrected comparisons.
- `index.json` keeps deterministic outcome and qualitative mergeability separate.

The individual review JSON documents include per-dimension scores and rationales, blockers, strengths, summary, and overall reasoning.
