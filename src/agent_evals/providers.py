from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROVIDER_PRIORITY = ("zai", "neuralwatt", "opencode-go")


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


def resolve_model(model: str, providers: dict[str, dict[str, Any]]) -> ProviderRoute:
    for name in PROVIDER_PRIORITY:
        config = providers.get(name)
        if not config or not config.get("enabled", True):
            continue
        models = config.get("models", [])
        if model not in models:
            continue
        base_url = config.get("base_url")
        base_url_env = config.get("base_url_env")
        if base_url_env:
            base_url = os.environ.get(str(base_url_env))
            if not base_url:
                raise RuntimeError(f"base URL environment variable {base_url_env} is not set")
        if not base_url:
            raise ValueError(f"provider {name} requires base_url or base_url_env")
        return ProviderRoute(
            provider=name,
            model=model,
            base_url=str(base_url),
            api_key_env=str(config["api_key_env"]),
        )
    available = {
        name: config.get("models", [])
        for name, config in providers.items()
        if config.get("enabled", True)
    }
    raise LookupError(f"model {model!r} unavailable; configured routes: {available}")
