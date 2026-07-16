from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from pathlib import Path

from agent_evals.review import ProctorReview


class ProctorReviewTests(unittest.TestCase):
    def review(self, **overrides: object) -> ProctorReview:
        values: dict[str, object] = {
            "run_id": "run",
            "task_id": "task",
            "proctor": "Hermes Agent",
            "proctor_model": "test-model",
        }
        values.update(overrides)
        return ProctorReview(**values)  # type: ignore[arg-type]

    def test_template_is_blinded_and_non_overriding(self) -> None:
        review = self.review()
        self.assertTrue(review.blinded_to_model_identity)
        self.assertFalse(review.can_override_deterministic)
        self.assertEqual(review.validate(), [])

    def test_cannot_override_deterministic_grade(self) -> None:
        errors = self.review(can_override_deterministic=True).validate()
        self.assertIn("qualitative review cannot override deterministic grading", errors)

    def test_json_schema_matches_review_fields_and_forbids_override(self) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "schemas/proctor-review.schema.json"
        schema = json.loads(schema_path.read_text())
        review_fields = set(asdict(self.review()))
        self.assertEqual(review_fields, set(schema["properties"]))
        self.assertEqual(review_fields, set(schema["required"]))
        self.assertEqual(schema["properties"]["can_override_deterministic"], {"const": False})

    def test_completed_review_requires_summary_and_valid_scores(self) -> None:
        errors = self.review(mergeable=True, blockers=["x"], scope_discipline=6).validate()
        self.assertIn("scope_discipline must be between 1 and 5", errors)
        self.assertIn("a mergeable patch cannot have blockers", errors)
        self.assertIn("completed review requires a summary", errors)


if __name__ == "__main__":
    unittest.main()
