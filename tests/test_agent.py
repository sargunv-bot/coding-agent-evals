from __future__ import annotations

import json
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

    def test_only_ask_user_mode_exposes_proctor_mcp(self) -> None:
        self.assertNotIn("mcp", AgentRunner.opencode_config(self.route, "baseline"))
        self.assertNotIn("mcp", AgentRunner.opencode_config(self.route, "full_info"))
        ask_config = AgentRunner.opencode_config(self.route, "ask_user")
        self.assertEqual(ask_config["mcp"]["proctor"]["command"], ["/opt/cae/proctor-mcp"])

    def test_custom_provider_uses_environment_interpolation(self) -> None:
        config = AgentRunner.opencode_config(self.route, "baseline")
        provider = config["provider"]["cae"]
        self.assertEqual(provider["npm"], "@ai-sdk/openai-compatible")
        self.assertEqual(provider["options"]["apiKey"], "{env:CAE_PROVIDER_API_KEY}")

    def test_model_config_digest_is_canonical_and_mode_sensitive(self) -> None:
        baseline = AgentRunner.opencode_config_sha256(self.route, "baseline")
        self.assertEqual(baseline, AgentRunner.opencode_config_sha256(self.route, "baseline"))
        self.assertNotEqual(baseline, AgentRunner.opencode_config_sha256(self.route, "ask_user"))

    def test_completion_status_preserves_nonzero_exit_discrepancy_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps({"type": "step_finish", "part": {"reason": "stop"}}))
            self.assertEqual("completed", AgentRunner._completion_status(path, 1))
            self.assertEqual("timeout", AgentRunner._completion_status(path, 124))

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
