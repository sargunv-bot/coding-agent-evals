from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .engine import PodmanEngine
from .providers import ProviderRoute
from .task import TaskSpec

NODE_IMAGE = (
    "docker.io/library/node@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3"
)
OPENCODE_VERSION = "1.18.2"
PROCTOR_TIMEOUT_MS = 30 * 60 * 1000
LABEL = "io.sargunv.coding-agent-evals=true"


def _token_count(tokens: dict, *keys: str) -> int:
    for key in keys:
        value = tokens.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    return 0


@dataclass(frozen=True)
class AgentUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    provider_reported_cost: float | None = None


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    task_id: str
    scenario: str | None
    provider: str
    model: str
    endpoint_host: str
    instruction_mode: str
    started_at: str
    finished_at: str
    duration_seconds: float
    agent_exit_code: int
    agent_completion_status: str
    agent_exit_discrepancy: bool
    model_config_sha256: str
    patch_path: str
    trajectory_path: str
    usage: AgentUsage
    verification: dict | None


class AgentRunner:
    def __init__(self, root: Path, engine: PodmanEngine | None = None) -> None:
        self.root = root.resolve()
        self.engine = engine or PodmanEngine(self.root)
        self.build_dir = self.root / "build"

    @property
    def proxy_image(self) -> str:
        return "localhost/coding-agent-evals/egress-proxy:dev"

    def agent_image(self, task: TaskSpec) -> str:
        return f"localhost/coding-agent-evals/{task.task_id}-opencode:dev"

    @staticmethod
    def agent_shell(
        model_arg: str,
        *,
        instruction_path: str = "/run/cae/instruction.txt",
        log_dir: str = "/logs/agent",
    ) -> str:
        instruction = shlex.quote(instruction_path)
        transcript = shlex.quote(f"{log_dir}/opencode.jsonl")
        patch = shlex.quote(f"{log_dir}/model.patch")
        return (
            "set -o pipefail; "
            "base=$(git rev-parse HEAD) || exit 125; "
            f"opencode run --model={model_arg} --format=json --thinking --auto "
            f'-- "$(cat {instruction})" '
            f"2>&1 </dev/null | stdbuf -oL tee {transcript}; "
            "agent_status=${PIPESTATUS[0]}; "
            "git add --all || exit 125; "
            f'git diff --cached --binary --full-index "$base" -- > {patch} '
            "|| exit 125; "
            "exit $agent_status"
        )

    @staticmethod
    def opencode_config(route: ProviderRoute, instruction_mode: str) -> dict:
        if instruction_mode not in {"baseline", "ask_user", "full_info"}:
            raise ValueError(f"unknown instruction mode: {instruction_mode}")
        config = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "cae": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": route.provider,
                    "options": {
                        "baseURL": route.base_url,
                        "apiKey": "{env:CAE_PROVIDER_API_KEY}",
                    },
                    "models": {route.model: {"name": route.model}},
                }
            },
        }
        if instruction_mode == "ask_user":
            config["mcp"] = {
                "proctor": {
                    "type": "local",
                    "command": ["/opt/cae/proctor-mcp"],
                    "enabled": True,
                    "timeout": PROCTOR_TIMEOUT_MS,
                }
            }
        return config

    @classmethod
    def opencode_config_text(cls, route: ProviderRoute, instruction_mode: str) -> str:
        return json.dumps(cls.opencode_config(route, instruction_mode), indent=2) + "\n"

    @classmethod
    def opencode_config_sha256(cls, route: ProviderRoute, instruction_mode: str) -> str:
        config = cls.opencode_config_text(route, instruction_mode).encode()
        return hashlib.sha256(config).hexdigest()

    def build_tools(self) -> dict[str, str]:
        self.engine.ensure_space()
        self.build_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.build_dir, 0o755)
        proctor = self.build_dir / "proctor-mcp"
        command = [
            "podman",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{self.root / 'cmd/proctor-mcp'}:/src:ro",
            "-v",
            f"{self.build_dir}:/out",
            "-w",
            "/src",
            "docker.io/library/golang@sha256:09fb8a652cf7a990b714c46a9f0f5fd2d5bc2222d995166b91907c1c05b7d0e8",
            "sh",
            "-c",
            "CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/proctor-mcp main.go",
        ]
        self._checked(command)
        proctor.chmod(0o755)
        self._checked(
            [
                "podman",
                "build",
                "--label",
                LABEL,
                "-t",
                self.proxy_image,
                "-f",
                str(self.root / "cmd/egress-proxy/Containerfile"),
                str(self.root / "cmd/egress-proxy"),
            ]
        )
        return {"proctor_mcp": str(proctor), "proxy_image": self.proxy_image}

    def build_agent_image(self, task: TaskSpec) -> str:
        self.engine.ensure_space()
        work = self.root / ".cache" / "agent-images" / task.task_id
        work.mkdir(parents=True, exist_ok=True)
        containerfile = work / "Containerfile"
        containerfile.write_text(
            f"""FROM {NODE_IMAGE} AS tools
RUN npm install --global opencode-ai@{OPENCODE_VERSION} && opencode --version

FROM {self.engine.image_name(task)}
USER root
RUN mkdir -p /opt/agent-tools/bin /opt/agent-tools/lib/node_modules /home/agent/.config/opencode \
    && chown -R agent:agent /home/agent/.config
COPY --from=tools /usr/local/bin/node /opt/agent-tools/bin/node
COPY --from=tools /usr/local/lib/node_modules/opencode-ai \
    /opt/agent-tools/lib/node_modules/opencode-ai
RUN ln -s ../lib/node_modules/opencode-ai/bin/opencode.exe /opt/agent-tools/bin/opencode
USER agent
ENV PATH=/opt/agent-tools/bin:$PATH OPENCODE_FAKE_VCS=git
"""
        )
        self._checked(
            [
                "podman",
                "build",
                "--label",
                LABEL,
                "--label",
                f"io.sargunv.coding-agent-evals.task={task.task_id}",
                "-t",
                self.agent_image(task),
                "-f",
                str(containerfile),
                str(work),
            ],
            timeout=1800,
        )
        return self.agent_image(task)

    def run(
        self,
        task: TaskSpec,
        route: ProviderRoute,
        *,
        scenario: str | None = None,
        instruction_mode: str = "ask_user",
        initial_clarification: str | None = None,
    ) -> AgentRunResult:
        started_monotonic = time.monotonic()
        started_at = datetime.now(UTC).isoformat()
        if os.environ.get("CAE_ALLOW_CANDIDATE_RUN") != "1":
            raise RuntimeError("candidate runs are gated; set CAE_ALLOW_CANDIDATE_RUN=1 explicitly")
        self.engine.ensure_space()
        key = os.environ.get(route.api_key_env)
        if not key:
            raise RuntimeError(f"missing credential environment variable {route.api_key_env}")
        endpoint = urlsplit(route.base_url)
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise RuntimeError("provider base URL must be HTTPS with a hostname")

        self.build_tools()
        self.build_agent_image(task)

        nonce = f"{os.getpid()}-{time.time_ns()}"
        run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{task.task_id}-{nonce}"
        run_dir = self.root / ".runs" / run_id
        logs = run_dir / "logs" / "agent"
        queue = run_dir / "proctor"
        config_dir = run_dir / "config"
        for path in (logs, queue / "questions", queue / "answers", config_dir):
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o777 if "config" not in path.parts else 0o755)

        scenario_spec = task.scenario(scenario) if scenario else None
        instruction = task.instruction.read_text().strip()
        if instruction_mode == "full_info":
            clarification = initial_clarification or (
                scenario_spec.full_info_addendum if scenario_spec else None
            )
            if not clarification:
                raise ValueError("full_info mode requires an initial clarification")
            instruction += "\n\nUser clarification:\n" + clarification

        config_path = config_dir / "opencode.json"
        config_path.write_text(self.opencode_config_text(route, instruction_mode))
        config_path.chmod(0o644)
        model_config_sha256 = self.opencode_config_sha256(route, instruction_mode)
        instruction_path = config_dir / "instruction.txt"
        instruction_path.write_text(instruction + "\n")
        instruction_path.chmod(0o644)
        proctor_display = str(queue) if instruction_mode == "ask_user" else "disabled"
        print(f"[CAE_RUN] id={run_id} proctor_queue={proctor_display}", flush=True)

        network = f"cae-net-{nonce}"
        proxy = f"cae-proxy-{nonce}"
        agent_container = f"cae-agent-{nonce}"
        self._checked(
            [
                "podman",
                "network",
                "create",
                "--internal",
                "--disable-dns",
                "--label",
                LABEL,
                network,
            ]
        )
        agent_exit = 125
        verification: dict | None = None
        try:
            self._checked(
                [
                    "podman",
                    "run",
                    "-d",
                    "--name",
                    proxy,
                    "--network",
                    "podman",
                    "--label",
                    LABEL,
                    "-e",
                    f"CAE_ALLOWED_HOSTS={endpoint.hostname}",
                    self.proxy_image,
                ]
            )
            self._checked(["podman", "network", "connect", network, proxy])
            proxy_ip = self._checked(
                [
                    "podman",
                    "inspect",
                    proxy,
                    "--format",
                    f'{{{{(index .NetworkSettings.Networks "{network}").IPAddress}}}}',
                ]
            ).stdout.strip()
            if not proxy_ip:
                raise RuntimeError("could not resolve proxy IP on internal network")
            proxy_url = f"http://{proxy_ip}:3128"

            patch_path = logs / "model.patch"
            model_arg = shlex.quote(f"cae/{route.model}")
            proctor_args = []
            if instruction_mode == "ask_user":
                proctor_args = [
                    "-v",
                    f"{queue}:/proctor",
                    "-v",
                    f"{self.build_dir / 'proctor-mcp'}:/opt/cae/proctor-mcp:ro",
                    "-e",
                    "CAE_PROCTOR_QUEUE=/proctor",
                ]
            shell = self.agent_shell(model_arg)
            command = [
                "podman",
                "run",
                "--rm",
                "--name",
                agent_container,
                "--network",
                network,
                "--label",
                LABEL,
                "--cap-drop",
                "all",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "2048",
                "--cpus",
                str(task.resources.cpus),
                "--memory",
                f"{task.resources.memory_mb}m",
                "-v",
                f"{logs}:/logs/agent",
                *proctor_args,
                "-v",
                f"{config_path}:/home/agent/.config/opencode/opencode.json:ro",
                "-v",
                f"{instruction_path}:/run/cae/instruction.txt:ro",
                "-e",
                "CAE_PROVIDER_API_KEY",
                "-e",
                f"HTTPS_PROXY={proxy_url}",
                "-e",
                f"HTTP_PROXY={proxy_url}",
                "-e",
                f"NO_PROXY={proxy_ip},localhost,127.0.0.1",
                "-e",
                "NODE_USE_ENV_PROXY=1",
                "-e",
                f"CAE_RUN_ID={run_id}",
                "-e",
                f"CAE_TASK_ID={task.task_id}",
                "-e",
                f"CAE_SCENARIO={scenario or ''}",
                self.agent_image(task),
                "bash",
                "-c",
                shell,
            ]
            env = os.environ.copy()
            env["CAE_PROVIDER_API_KEY"] = key
            try:
                process = subprocess.run(command, text=True, env=env, timeout=task.agent_timeout)
                agent_exit = process.returncode
            except subprocess.TimeoutExpired:
                agent_exit = 124
                with (logs / "opencode.jsonl").open("a") as stream:
                    stream.write(
                        json.dumps(
                            {
                                "type": "error",
                                "error": "candidate timeout",
                                "timeout_seconds": task.agent_timeout,
                            }
                        )
                        + "\n"
                    )

            event_path = logs / "opencode.jsonl"
            usage = self._extract_usage(event_path)
            completion_status = self._completion_status(event_path, agent_exit)
            trajectory_path = logs / "trajectory.json"
            self._write_atif(event_path, trajectory_path, run_id, route, usage)
            if patch_path.exists():
                verification_result = self.engine.verify(
                    task, control="candidate", patch=patch_path, scenario=scenario
                )
                verification = asdict(verification_result)
            result = AgentRunResult(
                run_id=run_id,
                task_id=task.task_id,
                scenario=scenario,
                provider=route.provider,
                model=route.model,
                endpoint_host=endpoint.hostname,
                instruction_mode=instruction_mode,
                started_at=started_at,
                finished_at=datetime.now(UTC).isoformat(),
                duration_seconds=round(time.monotonic() - started_monotonic, 6),
                agent_exit_code=agent_exit,
                agent_completion_status=completion_status,
                agent_exit_discrepancy=(completion_status == "completed") != (agent_exit == 0),
                model_config_sha256=model_config_sha256,
                patch_path=str(patch_path),
                trajectory_path=str(trajectory_path),
                usage=usage,
                verification=verification,
            )
            (run_dir / "run-result.json").write_text(json.dumps(asdict(result), indent=2) + "\n")
            return result
        finally:
            subprocess.run(
                ["podman", "rm", "-f", agent_container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["podman", "rm", "-f", proxy], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["podman", "network", "rm", network],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    @staticmethod
    def _completion_status(source: Path, exit_code: int) -> str:
        if exit_code == 124:
            return "timeout"
        if not source.exists():
            return "incomplete"
        events: list[dict] = []
        for line in source.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(event)
            part = event.get("part")
            if event.get("type") != "tool_use" or not isinstance(part, dict):
                continue
            state = part.get("state")
            if (
                part.get("tool") == "proctor_ask_user"
                and isinstance(state, dict)
                and state.get("status") == "error"
            ):
                return "proctor_error"
        for event in reversed(events):
            if event.get("type") == "error":
                return "error"
            if event.get("type") == "step_finish":
                part = event.get("part")
                reason = part.get("reason") if isinstance(part, dict) else None
                return "completed" if reason == "stop" else "incomplete"
        return "incomplete"

    @staticmethod
    def _extract_usage(source: Path) -> AgentUsage:
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0
        costs: list[float] = []
        if not source.exists():
            return AgentUsage()
        for line in source.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "step_finish":
                continue
            part = event.get("part")
            if not isinstance(part, dict):
                continue
            tokens = part.get("tokens")
            if not isinstance(tokens, dict):
                continue
            cache_value = tokens.get("cache")
            cache = cache_value if isinstance(cache_value, dict) else {}

            input_tokens += _token_count(tokens, "input", "input_tokens", "prompt_tokens")
            output_tokens += _token_count(tokens, "output", "output_tokens", "completion_tokens")
            reasoning_tokens += _token_count(tokens, "reasoning", "reasoning_tokens")
            cached = cache.get("read")
            if not isinstance(cached, int) or isinstance(cached, bool):
                cached = _token_count(
                    tokens, "cached_input_tokens", "cache_read_input_tokens", "cache_read"
                )
            cached_input_tokens += max(0, cached)
            cost = part.get("cost")
            if isinstance(cost, int | float) and not isinstance(cost, bool):
                costs.append(float(cost))
        return AgentUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            provider_reported_cost=round(sum(costs), 12) if costs else None,
        )

    def _write_atif(
        self,
        source: Path,
        destination: Path,
        run_id: str,
        route: ProviderRoute,
        usage: AgentUsage,
    ) -> None:
        steps: list[dict] = []
        if source.exists():
            for line in source.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                part = event.get("part") or {}
                if event.get("type") in {"text", "reasoning", "tool_use", "error"}:
                    steps.append(
                        {
                            "step_id": len(steps) + 1,
                            "source": "agent",
                            "message": part.get("text", "") if isinstance(part, dict) else "",
                            "event": event,
                        }
                    )
        payload = {
            "schema_version": "ATIF-v1.7",
            "session_id": run_id,
            "agent": {"name": "opencode", "version": OPENCODE_VERSION, "model_name": route.model},
            "steps": steps,
            "final_metrics": {"total_steps": len(steps), "usage": asdict(usage)},
        }
        destination.write_text(json.dumps(payload, indent=2) + "\n")

    def _checked(self, command: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        if result.returncode != 0:
            details = f"{' '.join(command)}\n{result.stderr[-4000:]}"
            raise RuntimeError(f"command failed ({result.returncode}): {details}")
        return result
