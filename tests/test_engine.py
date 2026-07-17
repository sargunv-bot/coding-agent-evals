from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from agent_evals.engine import CommandResult, CommandRunner, PodmanEngine
from agent_evals.task import TaskSpec


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, args, **kwargs):
        command = tuple(args)
        self.commands.append(command)
        if command[:4] == ("podman", "container", "ls", "--all"):
            return CommandResult(command, 0, "c1\nc2\n", "")
        if command[:3] == ("podman", "volume", "ls"):
            return CommandResult(command, 0, "v1\n", "")
        if command[:3] == ("podman", "network", "ls"):
            return CommandResult(command, 0, "", "")
        if command[:3] == ("podman", "image", "ls"):
            return CommandResult(command, 0, "i1\ni1\n", "")
        return CommandResult(command, 0, "", "")


class EngineCleanupTest(unittest.TestCase):
    def test_cleanup_is_label_scoped_and_deduplicates_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FakeRunner()
            result = PodmanEngine(Path(directory), runner=runner, min_free_gib=0).cleanup(
                include_images=True
            )
            self.assertEqual({"containers": 2, "volumes": 1, "networks": 0, "images": 1}, result)
            rendered = [" ".join(command) for command in runner.commands]
            self.assertTrue(
                all(
                    "label=io.sargunv.coding-agent-evals=true" in command
                    for command in rendered
                    if " ls " in command
                )
            )
            self.assertIn(("podman", "image", "rm", "i1"), runner.commands)


class EmptyPatchRunner:
    def __init__(self) -> None:
        self.command: tuple[str, ...] | None = None

    def run(self, args, **kwargs):
        command = tuple(args)
        self.command = command
        logs_mount = next(arg for arg in command if arg.endswith(":/logs"))
        reward = Path(logs_mount.removesuffix(":/logs")) / "verifier" / "reward.json"
        reward.parent.mkdir(parents=True)
        reward.write_text('{"reward": 0}\n')
        return CommandResult(command, 1, "", "")


class EngineVerificationTest(unittest.TestCase):
    def test_empty_candidate_patch_is_graded_as_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            tests.mkdir()
            patch = root / "empty.patch"
            patch.touch()
            task = cast(
                TaskSpec,
                SimpleNamespace(
                    task_id="empty-patch",
                    tests=tests,
                    resources=SimpleNamespace(cpus=1, memory_mb=128),
                    verifier_timeout=30,
                    scenario=lambda _: None,
                ),
            )
            runner = EmptyPatchRunner()
            result = PodmanEngine(root, runner=runner, min_free_gib=0).verify(
                task, control="candidate", patch=patch
            )
            self.assertEqual(result.outcome, "failed")
            self.assertEqual(result.reward, {"reward": 0})
            assert runner.command is not None
            self.assertNotIn("git apply", runner.command[-1])

    def test_environment_audit_runs_offline_as_candidate_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dev_check = root / "dev-check.sh"
            dev_check.write_text("exit 0\n")
            task = cast(
                TaskSpec,
                SimpleNamespace(
                    task_id="dev-ready",
                    dev_check=dev_check,
                    resources=SimpleNamespace(cpus=2, memory_mb=512),
                    verifier_timeout=30,
                ),
            )
            runner = FakeRunner()
            engine = PodmanEngine(root, runner=cast(CommandRunner, runner), min_free_gib=0)
            with patch.object(engine, "build", return_value="sha256:image"):
                result = engine.audit_environment(task)
            self.assertTrue(result.passed)
            command = runner.commands[-1]
            self.assertIn("agent", command)
            self.assertIn("none", command)
            self.assertIn(f"{dev_check}:/tmp/cae-dev-check.sh:ro", command)


if __name__ == "__main__":
    unittest.main()
