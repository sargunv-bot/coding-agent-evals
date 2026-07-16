from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_evals.evidence import EvidenceExportError, export_experiment_evidence


class EvidenceExportTest(unittest.TestCase):
    def _fixture(self, root: Path, transcript: str = '{"type":"text"}\n') -> Path:
        run_id = "run-1"
        run = root / ".runs" / run_id
        verifier = root / ".runs" / "verify-1"
        (run / "logs/agent").mkdir(parents=True)
        (run / "config").mkdir()
        (verifier / "logs/verifier").mkdir(parents=True)
        (run / "logs/agent/opencode.jsonl").write_text(transcript)
        (run / "logs/agent/model.patch").write_text("diff --git a/a b/a\n")
        (run / "config/instruction.txt").write_text("Fix it.\n")
        (run / "config/opencode.json").write_text("{}\n")
        (verifier / "logs/verifier/test-stdout.txt").write_text("failed\n")
        (verifier / "logs/verifier/test-stderr.txt").write_text("")

        results = root / ".runs/experiments/exp/results"
        results.mkdir(parents=True)
        record = {
            "schema_version": 1,
            "experiment_id": "exp",
            "cell": {"cell_id": "cell"},
            "state": "completed",
            "attempts": [
                {
                    "attempt": 1,
                    "kind": "completed",
                    "result": {
                        "run_id": run_id,
                        "patch_path": str(run / "logs/agent/model.patch"),
                        "trajectory_path": str(run / "logs/agent/trajectory.json"),
                        "verification": {"run_dir": str(verifier), "outcome": "failed"},
                    },
                }
            ],
        }
        (results / "cell.json").write_text(json.dumps(record))
        return root / "reports/evidence"

    def test_exports_allowlisted_artifacts_and_sanitizes_host_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = self._fixture(root)
            summary = export_experiment_evidence(root, "exp", output)
            run = output / "runs/cell"
            self.assertEqual(1, len(summary["runs"]))
            self.assertTrue((run / "transcript.jsonl").is_file())
            self.assertTrue((run / "verifier/stdout.txt").is_file())
            self.assertFalse((run / "trajectory.json").exists())
            record = (run / "matrix-record.json").read_text()
            self.assertNotIn(str(root), record)
            self.assertIn('"patch_path": "model.patch"', record)
            self.assertTrue((run / "artifacts.json").is_file())
            self.assertTrue((output / "README.md").is_file())

    def test_rejects_credential_like_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = self._fixture(root, "Bearer abcdefghijklmnopqrstuvwxyz\n")
            with self.assertRaisesRegex(EvidenceExportError, "credential-like"):
                export_experiment_evidence(root, "exp", output)


if __name__ == "__main__":
    unittest.main()
