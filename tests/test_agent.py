from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
