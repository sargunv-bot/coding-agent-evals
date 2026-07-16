from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderRoute:
    provider: str
    model: str
    base_url: str
    api_key_env: str

    def credential(self) -> str:
        value = os.environ.get(self.api_key_env)
        if not value:
            raise RuntimeError(f"credential environment variable {self.api_key_env} is not set")
        return value

    def redacted(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
        }


def load_routes(path: Path) -> dict[str, dict[str, Any]]:
    data = tomllib.loads(path.read_text())
    providers = data.get("providers")
    if not isinstance(providers, dict):
        raise ValueError("providers.toml must contain [providers.*] tables")
    return providers


def resolve_model(provider: str, model: str, providers: dict[str, dict[str, Any]]) -> ProviderRoute:
    config = providers.get(provider)
    if not config:
        raise LookupError(f"provider {provider!r} is not configured")
    if not config.get("enabled", True):
        raise LookupError(f"provider {provider!r} is disabled")
    if model not in config.get("models", []):
        raise LookupError(f"model {model!r} is not configured for provider {provider!r}")

    base_url = config.get("base_url")
    base_url_env = config.get("base_url_env")
    if base_url_env:
        base_url = os.environ.get(str(base_url_env))
        if not base_url:
            raise RuntimeError(f"base URL environment variable {base_url_env} is not set")
    if not base_url:
        raise ValueError(f"provider {provider} requires base_url or base_url_env")
    api_key_env = config.get("api_key_env")
    if not api_key_env:
        raise ValueError(f"provider {provider} requires api_key_env")
    return ProviderRoute(
        provider=provider,
        model=model,
        base_url=str(base_url),
        api_key_env=str(api_key_env),
    )
