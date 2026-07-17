from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_evals.task import TaskSpec

MANIFEST = """
schema_version = "1.1"
[task]
name = "personal/test"
[metadata]
task_id = "test-task"
repository_url = "https://example.invalid/repo"
base_commit_hash = "1111111111111111111111111111111111111111"
gold_commit_hash = "2222222222222222222222222222222222222222"
track = "sealed"
upstream_license = "MIT"
[agent]
timeout_sec = 10
[verifier]
timeout_sec = 10
[environment]
cpus = 1
memory_mb = 512
storage_mb = 512
"""


class TaskSpecTest(unittest.TestCase):
    def test_valid_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "test-task"
            (root / "environment").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "solution").mkdir()
            (root / "task.toml").write_text(MANIFEST)
            (root / "environment" / "Containerfile").write_text("FROM scratch\n")
            dev_check = root / "environment" / "dev-check.sh"
            dev_check.write_text("exit 0\n")
            dev_check.chmod(0o755)
            (root / "instruction.md").write_text("Do the task.\n")
            (root / "tests" / "test.sh").write_text("exit 0\n")
            (root / "solution" / "solution.patch").write_text("patch\n")
            self.assertEqual([], TaskSpec.load(root).validate())

    def test_bad_sha_and_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "test-task"
            root.mkdir()
            (root / "task.toml").write_text(MANIFEST.replace("1" * 40, "bad"))
            errors = TaskSpec.load(root).validate()
            self.assertTrue(any("base_commit_hash" in error for error in errors))
            self.assertIn("missing environment/dev-check.sh", errors)
            self.assertTrue(any("missing" in error for error in errors))

    def test_dev_check_must_be_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "test-task"
            (root / "environment").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "solution").mkdir()
            (root / "task.toml").write_text(MANIFEST)
            (root / "environment" / "Containerfile").write_text("FROM scratch\n")
            (root / "environment" / "dev-check.sh").write_text("exit 0\n")
            (root / "instruction.md").write_text("Do the task.\n")
            (root / "tests" / "test.sh").write_text("exit 0\n")
            (root / "solution" / "solution.patch").write_text("patch\n")
            self.assertIn(
                "environment/dev-check.sh must be executable",
                TaskSpec.load(root).validate(),
            )


if __name__ == "__main__":
    unittest.main()
