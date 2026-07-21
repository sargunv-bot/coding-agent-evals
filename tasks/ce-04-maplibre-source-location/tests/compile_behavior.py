#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shlex
import subprocess

ROOT = pathlib.Path("/app")
BUILD = ROOT / "build-linux-opengl"
TEST_SOURCE = pathlib.Path("/tests/source_location_behavior.cpp")
FALLBACK_SOURCE = pathlib.Path("/tests/source_location_fallback.cpp")
MACRO_PROBE_SOURCE = pathlib.Path("/tests/source_location_macro_probe.cpp")
OUTPUT_ROOT = pathlib.Path("/tmp/ce04")


def compile_flags(database_path: pathlib.Path = BUILD / "compile_commands.json") -> list[str]:
    database = json.loads(database_path.read_text())
    entry = next(
        item
        for item in database
        if pathlib.Path(item["file"]).as_posix().endswith("src/mbgl/layout/symbol_instance.cpp")
    )
    command = list(entry.get("arguments") or shlex.split(entry["command"]))
    result: list[str] = []
    skip_next = False
    for index, argument in enumerate(command):
        if skip_next:
            skip_next = False
            continue
        if index == 0 or (index == 1 and pathlib.Path(command[0]).name == "ccache"):
            continue
        if argument == "-c" or argument.endswith("src/mbgl/layout/symbol_instance.cpp"):
            continue
        if argument in {"-o", "-MF", "-MT", "-MQ"}:
            skip_next = True
            continue
        if argument in {"-MD", "-MMD", "-DNDEBUG"} or argument.startswith("-std="):
            continue
        result.append(argument)
    return result


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        raise AssertionError(
            f"command failed ({completed.returncode}): {shlex.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def fallback_source(compiler: str, flags: list[str]) -> pathlib.Path:
    command = [
        compiler,
        *flags,
        "-std=c++17",
        "-DMLN_SYMBOL_GUARDS=1",
        "-E",
        "-P",
        str(MACRO_PROBE_SOURCE),
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        raise AssertionError(
            f"preprocessor failed ({completed.returncode}): {shlex.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    _, begin, remainder = completed.stdout.partition("CE04_EXPRESSION_BEGIN")
    expression, end, _ = remainder.partition("CE04_EXPRESSION_END")
    if not begin or not end or not expression.strip():
        raise AssertionError("could not extract the expanded SYM_GUARD_LOC expression")
    generated = OUTPUT_ROOT / f"fallback-{compiler.replace('+', 'x')}.cpp"
    generated.write_text(
        FALLBACK_SOURCE.read_text().replace(
            "CE04_SOURCE_LOCATION_EXPRESSION",
            expression.strip(),
        )
    )
    return generated


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    flags = compile_flags()
    fallback_sources: list[pathlib.Path] = []
    for compiler in ("g++", "clang++"):
        generated_fallback = fallback_source(compiler, flags)
        fallback_sources.append(generated_fallback)
        for standard, source in (("c++20", TEST_SOURCE), ("c++17", generated_fallback)):
            output = OUTPUT_ROOT / f"{compiler.replace('+', 'x')}-{standard}"
            run(
                [
                    compiler,
                    *flags,
                    f"-std={standard}",
                    "-DMLN_SYMBOL_GUARDS=1",
                    str(source),
                    "-o",
                    str(output),
                ]
            )
            run([str(output)])

    tidy_sources = [("c++20", TEST_SOURCE), *[("c++17", path) for path in fallback_sources]]
    for standard, source in tidy_sources:
        run(
            [
                "clang-tidy",
                "--checks=-*,cert-dcl58-cpp",
                "--warnings-as-errors=*",
                "--header-filter=^/app/",
                str(source),
                "--",
                *flags,
                f"-std={standard}",
                "-DMLN_SYMBOL_GUARDS=1",
            ]
        )


if __name__ == "__main__":
    main()
