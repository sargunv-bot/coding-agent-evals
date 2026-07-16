from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agent_evals.providers import resolve_model


class ProviderRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.providers = {
            "zai": {"base_url_env": "ZAI_URL", "api_key_env": "ZAI_KEY", "models": ["same"]},
            "neuralwatt": {
                "base_url": "https://neuralwatt.invalid/v1",
                "api_key_env": "NW_KEY",
                "models": ["same", "nw-only"],
            },
            "opencode-go": {
                "base_url": "https://opencode.invalid/v1",
                "api_key_env": "OC_KEY",
                "models": ["same"],
            },
        }

    @patch.dict(
        os.environ,
        {"ZAI_URL": "https://zai.invalid/v1", "ZAI_KEY": "super-secret-value"},
        clear=False,
    )
    def test_selects_explicit_provider_for_same_model(self) -> None:
        route = resolve_model("zai", "same", self.providers)
        self.assertEqual("zai", route.provider)
        self.assertEqual("ZAI_KEY", route.redacted()["api_key_env"])
        self.assertNotIn("super-secret-value", str(route.redacted()))

    def test_does_not_fall_back_to_another_provider(self) -> None:
        with self.assertRaisesRegex(LookupError, "not configured for provider"):
            resolve_model("opencode-go", "nw-only", self.providers)

    def test_unknown_provider_is_explicit(self) -> None:
        with self.assertRaisesRegex(LookupError, "not configured"):
            resolve_model("missing", "same", self.providers)

    def test_missing_endpoint_environment_is_explicit(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            resolve_model("zai", "same", self.providers)


if __name__ == "__main__":
    unittest.main()
