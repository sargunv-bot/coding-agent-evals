#!/usr/bin/env python3
from __future__ import annotations

import functools
import http.server
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import threading
import tomllib

FIXTURES = pathlib.Path("/opt/ce05-fixtures")
SUBJECT = "dist-manifest.json"


def make_archive(path: pathlib.Path, entries: list[tuple[str, pathlib.Path | bytes]]) -> None:
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        directory = tarfile.TarInfo("./")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        directory.mtime = 0
        archive.addfile(directory)
        for name, source in entries:
            if isinstance(source, pathlib.Path):
                info = archive.gettarinfo(str(source), arcname=name)
                info.mtime = 0
                with source.open("rb") as file:
                    archive.addfile(info, file)
            else:
                info = tarfile.TarInfo(name)
                info.size = len(source)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, __import__("io").BytesIO(source))


def run(command: list[str], *, cwd: pathlib.Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)


def assert_result(result: subprocess.CompletedProcess[str], *, succeeds: bool, label: str) -> None:
    output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    if succeeds:
        assert result.returncode == 0, f"{label} unexpectedly failed\n{output}"
    else:
        assert result.returncode != 0, f"{label} unexpectedly succeeded\n{output}"
        lowered = output.lower()
        assert any(word in lowered for word in ("slsa", "provenance", "subject", "attest")), (
            f"{label} failed for an unrelated reason\n{output}"
        )


def write_registry(path: pathlib.Path, base_url: str, cases: list[str]) -> None:
    for case in cases:
        package = path / "pkgs" / "cae" / case / "registry.yaml"
        package.parent.mkdir(parents=True)
        package.write_text(
            "packages:\n"
            "  - type: http\n"
            f"    name: cae/{case}\n"
            "    description: behavioral verifier fixture\n"
            "    version_constraint: \"true\"\n"
            f"    url: {base_url}/{case}.tar.gz\n"
            "    format: tar.gz\n"
            "    files:\n"
            "      - name: sops\n"
            f"        src: {SUBJECT}\n"
            "    slsa_provenance:\n"
            "      type: http\n"
            f"      url: {base_url}/provenance.intoto.jsonl\n"
        )
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "verifier"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "verifier@invalid"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture registry"], cwd=path, check=True)


def probe(
    binary: pathlib.Path,
    root: pathlib.Path,
    registry: pathlib.Path,
    case: str,
    mode: str,
    succeeds: bool,
) -> None:
    workspace = root / f"{case}-{mode}"
    workspace.mkdir()
    home = workspace / "home"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "MISE_AQUA_BAKED_REGISTRY": "false",
            "MISE_AQUA_REGISTRY_URL": str(registry),
            "MISE_AQUA_SLSA": "true",
            "MISE_CACHE_DIR": str(workspace / "cache"),
            "MISE_CONFIG_DIR": str(workspace / "config"),
            "MISE_DATA_DIR": str(workspace / "data"),
            "MISE_LOG_LEVEL": "debug",
            "MISE_SLSA": "true",
            "MISE_STATE_DIR": str(workspace / "state"),
            "MISE_YES": "true",
        }
    )
    tool = f"aqua:cae/{case}@3.9.0"
    if mode == "lock":
        (workspace / "mise.toml").write_text(
            "[tools]\n" f'\"aqua:cae/{case}\" = \"3.9.0\"\n'
        )
        result = run([str(binary), "lock"], cwd=workspace, env=env)
        assert_result(result, succeeds=True, label=f"{case}/{mode}")
        lock_data = tomllib.loads((workspace / "mise.lock").read_text())
        tools = lock_data["tools"]
        assert len(tools) == 1, f"{case}/{mode} wrote unexpected tools: {sorted(tools)}"
        entries = next(iter(tools.values()))
        platform = entries[0]["platforms.linux-x64"]
        if succeeds:
            assert "provenance" in platform, (
                f"{case}/{mode} did not retain provenance after the positive fixture\n"
                f"platform={platform!r}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        else:
            assert "provenance" not in platform, (
                f"{case}/{mode} retained provenance after archive-content rejection"
            )
    else:
        env["MISE_LOCKFILE"] = "false"
        result = run([str(binary), "install", "--yes", tool], cwd=workspace, env=env)
        assert_result(result, succeeds=succeeds, label=f"{case}/{mode}")


def main() -> None:
    binary = pathlib.Path("/app/target/debug/mise")
    build = subprocess.run(
        ["cargo", "build", "--locked", "--bin", "mise"],
        cwd="/app",
        text=True,
        capture_output=True,
    )
    assert build.returncode == 0, f"mise build failed\n{build.stdout}\n{build.stderr}"

    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        web = root / "web"
        web.mkdir()
        shutil.copy2(FIXTURES / "provenance.intoto.jsonl", web / "provenance.intoto.jsonl")
        binary_fixture = FIXTURES / SUBJECT
        make_archive(web / "complete.tar.gz", [(f"./{SUBJECT}", binary_fixture)])
        make_archive(
            web / "missing-subject.tar.gz",
            [(f"./{SUBJECT}", binary_fixture), ("./README.md", b"unattested documentation\n")],
        )
        make_archive(web / "renamed-subject.tar.gz", [("./renamed-sops", binary_fixture)])

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            registry = root / "registry"
            registry.mkdir()
            cases = ["complete", "missing-subject", "renamed-subject"]
            write_registry(registry, base_url, cases)
            for mode in ("lock", "install"):
                probe(binary, root, registry, "complete", mode, True)
                probe(binary, root, registry, "missing-subject", mode, False)
                probe(binary, root, registry, "renamed-subject", mode, False)
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
