from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from agent_evals.agent import AgentRunner
from agent_evals.providers import ProviderRoute
from agent_evals.task import TaskSpec


class AgentRunnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = ProviderRoute("test", "model", "https://example.com/v1", "TEST_KEY")

    def test_candidate_run_requires_explicit_gate(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "candidate runs are gated"),
        ):
            AgentRunner(Path(directory)).run(cast(TaskSpec, None), self.route)

    def test_transcript_is_host_owned_and_world_writable_before_container_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transcript = AgentRunner._prepare_transcript(Path(directory))

            self.assertEqual(0o666, transcript.stat().st_mode & 0o777)
            with transcript.open("a") as stream:
                stream.write('{"type":"error","error":"candidate timeout"}\n')

    def test_only_ask_user_mode_exposes_proctor_mcp(self) -> None:
        self.assertNotIn("mcp", AgentRunner.opencode_config(self.route, "baseline"))
        self.assertNotIn("mcp", AgentRunner.opencode_config(self.route, "full_info"))
        ask_config = AgentRunner.opencode_config(self.route, "ask_user")
        self.assertEqual(ask_config["mcp"]["proctor"]["command"], ["/opt/cae/proctor-mcp"])
        self.assertEqual(ask_config["mcp"]["proctor"]["timeout"], 30 * 60 * 1000)

    def test_custom_provider_uses_environment_interpolation(self) -> None:
        config = AgentRunner.opencode_config(self.route, "baseline")
        provider = config["provider"]["cae"]
        self.assertEqual(provider["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(provider["options"]["apiKey"], "{env:CAE_PROVIDER_API_KEY}")

    def test_model_config_digest_is_canonical_and_mode_sensitive(self) -> None:
        baseline = AgentRunner.opencode_config_sha256(self.route, "baseline")
        self.assertEqual(baseline, AgentRunner.opencode_config_sha256(self.route, "baseline"))
        self.assertNotEqual(baseline, AgentRunner.opencode_config_sha256(self.route, "ask_user"))

    def test_patch_capture_uses_pre_agent_head_even_with_multiple_root_commits(self) -> None:
        shell = AgentRunner.agent_shell("cae/model")
        self.assertLess(shell.index("base=$(git rev-parse HEAD)"), shell.index("opencode run"))
        self.assertIn('git diff --cached --binary --full-index "$base"', shell)
        self.assertNotIn("rev-list --max-parents=0", shell)
        self.assertIn("|| exit 125", shell)

    def test_patch_capture_includes_changes_committed_by_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            bin_dir = root / "bin"
            logs = root / "logs"
            repo.mkdir()
            bin_dir.mkdir()
            logs.mkdir()
            instruction = root / "instruction.txt"
            instruction.write_text("Commit the change.\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "tracked.txt").write_text("before\n")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            git_env = os.environ | {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
            }
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, env=git_env, check=True)
            opencode = bin_dir / "opencode"
            opencode.write_text(
                "#!/bin/bash\n"
                "printf 'after\\n' > tracked.txt\n"
                "git add tracked.txt\n"
                "git commit -q -m candidate\n"
                'printf \'{"type":"step_finish","part":{"reason":"stop"}}\\n\'\n'
            )
            opencode.chmod(0o755)
            shell = AgentRunner.agent_shell(
                "cae/test", instruction_path=str(instruction), log_dir=str(logs)
            )
            subprocess.run(
                ["bash", "-c", shell],
                cwd=repo,
                env=git_env | {"PATH": f"{bin_dir}:{os.environ['PATH']}"},
                check=True,
            )
            patch = (logs / "model.patch").read_text()
            self.assertIn("-before", patch)
            self.assertIn("+after", patch)

    def test_completion_status_preserves_nonzero_exit_discrepancy_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps({"type": "step_finish", "part": {"reason": "stop"}}))
            self.assertEqual("completed", AgentRunner._completion_status(path, 1))
            self.assertEqual("timeout", AgentRunner._completion_status(path, 124))

    def test_completion_status_uses_terminal_step_and_rejects_proctor_transport_error(self) -> None:
        tool_calls = {"type": "step_finish", "part": {"reason": "tool-calls"}}
        stop = {"type": "step_finish", "part": {"reason": "stop"}}
        proctor_error = {
            "type": "tool_use",
            "part": {
                "tool": "proctor_ask_user",
                "state": {"status": "error", "error": "MCP error -32001: Request timed out"},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in (tool_calls, stop)))
            self.assertEqual("completed", AgentRunner._completion_status(path, 0))
            path.write_text(json.dumps(tool_calls))
            self.assertEqual("incomplete", AgentRunner._completion_status(path, 0))
            path.write_text("\n".join(json.dumps(event) for event in (proctor_error, stop)))
            self.assertEqual("proctor_error", AgentRunner._completion_status(path, 0))

    def test_extracts_step_usage_without_double_counting_other_events(self) -> None:
        events = [
            {
                "type": "step_finish",
                "part": {
                    "tokens": {
                        "input": 120,
                        "output": 30,
                        "reasoning": 5,
                        "cache": {"read": 80, "write": 10},
                    },
                    "cost": 0.012,
                },
            },
            {"type": "message", "part": {"tokens": {"input": 999, "output": 999}}},
            {
                "type": "step_finish",
                "part": {
                    "tokens": {
                        "input_tokens": 20,
                        "output_tokens": 10,
                        "cached_input_tokens": 4,
                    }
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events))
            usage = AgentRunner._extract_usage(path)
        self.assertEqual(140, usage.input_tokens)
        self.assertEqual(84, usage.cached_input_tokens)
        self.assertEqual(40, usage.output_tokens)
        self.assertEqual(5, usage.reasoning_tokens)
        self.assertEqual(0.012, usage.provider_reported_cost)


if __name__ == "__main__":
    unittest.main()
