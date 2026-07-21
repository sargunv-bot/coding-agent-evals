from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.review_packets import (
    ReviewPacketError,
    finalize_review,
    prepare_review_packets,
)


class ReviewPacketTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        run_id = "run-123"
        run = root / ".runs" / run_id
        (run / "config").mkdir(parents=True)
        (run / "logs" / "agent").mkdir(parents=True)
        (run / "config" / "instruction.txt").write_text("fix the behavior\n")
        patch = run / "logs" / "agent" / "model.patch"
        patch.write_text("diff --git a/x b/x\n")
        trajectory = run / "logs" / "agent" / "trajectory.json"
        trajectory.write_text(json.dumps({
            "model": "secret-model",
            "nested": {"providerID": "secret-provider"},
            "message": "secret-model via secret-provider",
        }))

        results = root / ".runs" / "experiments" / "exp" / "results"
        results.mkdir(parents=True)
        result = {
            "state": "completed",
            "cell": {
                "cell_id": "secret-provider__secret-model__task__default__r01",
                "provider": "secret-provider",
                "model": "secret-model",
                "task_id": "task",
            },
            "attempts": [{
                "kind": "completed",
                "result": {
                    "run_id": run_id,
                    "task_id": "task",
                    "provider": "secret-provider",
                    "model": "secret-model",
                    "patch_path": str(patch),
                    "trajectory_path": str(trajectory),
                },
            }],
        }
        result_path = results / "cell.json"
        result_path.write_text(json.dumps(result))
        return result_path, run

    def response(self) -> dict[str, object]:
        rationales = {
            name: "specific rationale"
            for name in (
                "scope_discipline",
                "code_clarity",
                "test_quality",
                "repository_fit",
                "security_and_safety",
            )
        }
        return {
            "scope_discipline": 4,
            "code_clarity": 4,
            "test_quality": 3,
            "repository_fit": 4,
            "security_and_safety": 5,
            "mergeable": True,
            "blockers": [],
            "strengths": ["direct"],
            "summary": "mergeable",
            "rating_rationales": rationales,
            "overall_reasoning": "The patch is direct and adequately tested.",
        }

    def test_packet_is_opaque_and_mapping_is_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            packets = root / "packets"
            mapping = root / "trusted" / "mapping.json"
            result = prepare_review_packets(root, "exp", packets, mapping)
            self.assertEqual(result["packets"], 1)
            packet_dirs = list(packets.iterdir())
            self.assertEqual(len(packet_dirs), 1)
            self.assertEqual(
                {path.name for path in packet_dirs[0].iterdir()},
                {"instruction.txt", "patch.diff", "trajectory.json"},
            )
            packet_text = "\n".join(path.read_text() for path in packet_dirs[0].iterdir())
            self.assertNotIn("secret-model", packet_text)
            self.assertNotIn("secret-provider", packet_text)
            sanitized = json.loads((packet_dirs[0] / "trajectory.json").read_text())
            self.assertNotIn("model", sanitized)
            self.assertNotIn("providerID", sanitized["nested"])
            self.assertIn("secret-model", mapping.read_text())

    def test_mapping_cannot_live_in_packet_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            packets = root / "packets"
            with self.assertRaisesRegex(ReviewPacketError, "outside"):
                prepare_review_packets(root, "exp", packets, packets / "mapping.json")

    def test_finalize_attaches_trusted_fields_and_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            packets = root / "packets"
            mapping = root / "trusted" / "mapping.json"
            prepare_review_packets(root, "exp", packets, mapping)
            packet_id = json.loads(mapping.read_text())["packets"][0]["packet_id"]
            response = root / "response.json"
            response.write_text(json.dumps(self.response()))
            review = finalize_review(
                root,
                mapping,
                packet_id,
                response,
                proctor="Hermes Agent",
                proctor_model="reviewer-model",
            )
            self.assertTrue(review.blinded_to_model_identity)
            self.assertFalse(review.can_override_deterministic)
            canonical = root / ".runs" / "experiments" / "exp" / "reviews" / "cell.json"
            self.assertTrue(canonical.is_file())
            written = json.loads(canonical.read_text())
            self.assertEqual(written["run_id"], "run-123")
            self.assertEqual(written["proctor_model"], "reviewer-model")

    def test_reviewer_cannot_supply_trusted_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            packets = root / "packets"
            mapping = root / "trusted" / "mapping.json"
            prepare_review_packets(root, "exp", packets, mapping)
            packet_id = json.loads(mapping.read_text())["packets"][0]["packet_id"]
            payload = self.response() | {"blinded_to_model_identity": False}
            response = root / "response.json"
            response.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ReviewPacketError, "unexpected"):
                finalize_review(
                    root,
                    mapping,
                    packet_id,
                    response,
                    proctor="Hermes Agent",
                    proctor_model="reviewer-model",
                )


if __name__ == "__main__":
    unittest.main()
