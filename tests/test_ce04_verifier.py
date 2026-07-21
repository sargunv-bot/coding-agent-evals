from __future__ import annotations

import importlib.util
import json
from pathlib import Path

VERIFIER_PATH = (
    Path(__file__).parents[1]
    / "tasks"
    / "ce-04-maplibre-source-location"
    / "tests"
    / "compile_behavior.py"
)
SPEC = importlib.util.spec_from_file_location("ce04_compile_behavior", VERIFIER_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def test_reuses_production_compile_flags_without_source_or_outputs(tmp_path: Path) -> None:
    database = tmp_path / "compile_commands.json"
    database.write_text(
        json.dumps(
            [
                {
                    "file": "/app/src/mbgl/layout/symbol_instance.cpp",
                    "arguments": [
                        "/usr/bin/ccache",
                        "/usr/bin/clang++",
                        "-I/app/src",
                        "-std=gnu++20",
                        "-MD",
                        "-MT",
                        "target",
                        "-MF",
                        "target.d",
                        "-c",
                        "/app/src/mbgl/layout/symbol_instance.cpp",
                        "-o",
                        "target.o",
                    ],
                }
            ]
        )
    )

    assert VERIFIER.compile_flags(database) == ["-I/app/src"]
