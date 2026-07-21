#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path("/app")
EXPECTED = json.loads(pathlib.Path("/tests/expected-client-methods.json").read_text())


def client_block(text: str, module: str) -> str:
    package = "dev.sargunv.mobilitydata." + module.replace("-", ".")
    client = "GofsV1Client" if module == "gofs-v1" else {
        "gbfs-v1": "GbfsV1Client",
        "gbfs-v2": "GbfsV2Client",
        "gbfs-v3": "GbfsV3Client",
    }[module]
    marker = f"final class {package}/{client} "
    start = text.find(marker)
    if start < 0:
        raise AssertionError(f"missing public ABI class {package}/{client}")
    end = text.find("\n}\n", start)
    if end < 0:
        raise AssertionError(f"unterminated ABI class {package}/{client}")
    return text[start:end]


for module, expected_names in EXPECTED.items():
    text = (ROOT / module / "api" / f"{module}.klib.api").read_text()
    block = client_block(text, module)
    suspend_lines = [line.strip() for line in block.splitlines() if "final suspend fun" in line]
    if not suspend_lines:
        raise AssertionError(f"{module}: no public suspend client methods")
    for line in suspend_lines:
        if ": kotlin/Result<" not in line:
            raise AssertionError(f"{module}: public client method does not return Result: {line}")
    for name in expected_names:
        if not any(re.search(rf"(?:\.|\s){re.escape(name)}\(", line) for line in suspend_lines):
            raise AssertionError(f"{module}: original public client method disappeared: {name}")

print("PASS: every public client fetch method returns Result and original API methods remain")
