from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from .task import TaskSpec

LABEL = "io.sargunv.coding-agent-evals=true"
LABEL_KEY = "io.sargunv.coding-agent-evals"
DEFAULT_MIN_FREE_GIB = 80


class EngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
        timeout: int | None = None,
        cwd: Path | None = None,
    ) -> CommandResult:
        completed = subprocess.run(
            list(args),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
        )
        result = CommandResult(
            tuple(args), completed.returncode, completed.stdout, completed.stderr
        )
        if check and result.returncode:
            rendered = " ".join(shlex.quote(part) for part in result.args)
            raise EngineError(
                f"command failed ({result.returncode}): {rendered}\n{result.stderr.strip()}"
            )
        return result


@dataclass(frozen=True)
class VerificationResult:
    task_id: str
    scenario: str | None
    control: str
    outcome: str
    exit_code: int
    expected_pass: bool
    expectation_met: bool
    run_dir: str
    reward: dict[str, object] | None
    duration_seconds: float
    command_stderr: str


@dataclass(frozen=True)
class EnvironmentAuditResult:
    task_id: str
    image_id: str
    exit_code: int
    passed: bool
    duration_seconds: float
    stdout: str
    stderr: str


class PodmanEngine:
    def __init__(
        self,
        repo_root: Path,
        *,
        runner: CommandRunner | None = None,
        min_free_gib: int = DEFAULT_MIN_FREE_GIB,
    ):
        self.repo_root = repo_root.resolve()
        self.runner = runner or CommandRunner()
        self.min_free_bytes = min_free_gib * 1024**3
        self.runs = self.repo_root / ".runs"

    def check_prerequisites(self) -> dict[str, object]:
        version = self.runner.run(["podman", "version", "--format", "json"])
        try:
            version_data = json.loads(version.stdout)
        except json.JSONDecodeError as exc:
            raise EngineError("podman returned invalid version JSON") from exc
        info = self.runner.run(["podman", "info", "--format", "json"])
        info_data = json.loads(info.stdout)
        rootless = bool(info_data.get("host", {}).get("security", {}).get("rootless"))
        if not rootless:
            raise EngineError("the benchmark requires rootless Podman")
        free = shutil.disk_usage(self.repo_root).free
        return {
            "rootless": rootless,
            "client_version": version_data.get("Client", {}).get("Version"),
            "free_bytes": free,
            "minimum_free_bytes": self.min_free_bytes,
        }

    def ensure_space(self, estimated_bytes: int = 0) -> None:
        free = shutil.disk_usage(self.repo_root).free
        remaining = free - estimated_bytes
        if remaining < self.min_free_bytes:
            raise EngineError(
                f"storage guard: operation would leave {remaining / 1024**3:.1f} GiB free; "
                f"minimum is {self.min_free_bytes / 1024**3:.1f} GiB"
            )

    @staticmethod
    def image_name(task: TaskSpec) -> str:
        return f"localhost/coding-agent-evals/{task.task_id}:dev"

    def build(self, task: TaskSpec) -> str:
        self.ensure_space(task.resources.storage_mb * 1024**2)
        errors = task.validate()
        if errors:
            raise EngineError("task validation failed: " + "; ".join(errors))
        image = self.image_name(task)
        self.runner.run(
            [
                "podman",
                "build",
                "--label",
                LABEL,
                "--label",
                f"{LABEL_KEY}.task={task.task_id}",
                "--tag",
                image,
                "--file",
                str(task.containerfile),
                str(self.repo_root),
            ],
            timeout=max(600, task.verifier_timeout),
        )
        inspected = self.runner.run(["podman", "image", "inspect", image, "--format", "{{.Id}}"])
        return inspected.stdout.strip()

    def audit_environment(self, task: TaskSpec) -> EnvironmentAuditResult:
        """Run the task's normal development checks as the offline candidate user."""
        image_id = self.build(task)
        started = time.monotonic()
        result = self.runner.run(
            [
                "podman",
                "run",
                "--rm",
                "--user",
                "agent",
                "--network",
                "none",
                "--cap-drop",
                "all",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "1024",
                "--cpus",
                str(task.resources.cpus),
                "--memory",
                f"{task.resources.memory_mb}m",
                "--env",
                "HOME=/home/agent",
                "--volume",
                f"{task.dev_check}:/tmp/cae-dev-check.sh:ro",
                self.image_name(task),
                "bash",
                "/tmp/cae-dev-check.sh",
            ],
            check=False,
            timeout=task.verifier_timeout,
        )
        return EnvironmentAuditResult(
            task_id=task.task_id,
            image_id=image_id,
            exit_code=result.returncode,
            passed=result.returncode == 0,
            duration_seconds=time.monotonic() - started,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def verify(
        self,
        task: TaskSpec,
        *,
        control: str,
        patch: Path | None = None,
        scenario: str | None = None,
    ) -> VerificationResult:
        if control not in {"no-op", "gold", "mutant", "candidate"}:
            raise ValueError(f"unsupported control {control!r}")
        scenario_spec = task.scenario(scenario) if scenario else None
        if control == "gold":
            patch = scenario_spec.gold_patch if scenario_spec else task.gold_patch
        if control in {"gold", "mutant", "candidate"} and patch is None:
            raise ValueError(f"{control} requires a patch")
        if patch is not None and not patch.is_file():
            raise FileNotFoundError(patch)
        self.ensure_space(1024**3)
        scenario_part = f"-{scenario}" if scenario else ""
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        run_id = f"{timestamp}-{task.task_id}{scenario_part}-{control}-{time.time_ns()}"
        run_dir = self.runs / run_id
        logs = run_dir / "logs"
        candidate = run_dir / "candidate"
        for directory in (run_dir, logs, candidate):
            directory.mkdir(parents=True, exist_ok=True)
        logs.chmod(0o777)
        candidate.chmod(0o755)
        has_patch = patch is not None and patch.stat().st_size > 0
        if has_patch:
            assert patch is not None
            target = candidate / "patch"
            shutil.copyfile(patch, target)
            target.chmod(0o444)

        shell = "git config --global --add safe.directory /app; "
        if has_patch:
            shell += "git apply --check /candidate/patch && git apply /candidate/patch && "
        shell += "bash /tests/test.sh"
        scenario_tests = (
            scenario_spec.tests if scenario_spec and scenario_spec.tests.is_dir() else candidate
        )
        command = [
            "podman",
            "run",
            "--rm",
            "--user",
            "root",
            "--network",
            "none",
            "--cap-drop",
            "all",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "1024",
            "--cpus",
            str(task.resources.cpus),
            "--memory",
            f"{task.resources.memory_mb}m",
            "--env",
            "HOME=/root",
            "--env",
            f"CAE_SCENARIO={scenario or ''}",
            "--label",
            LABEL,
            "--label",
            f"{LABEL_KEY}.task={task.task_id}",
            "--label",
            f"{LABEL_KEY}.run={run_id}",
            "--volume",
            f"{task.tests}:/tests:ro",
            "--volume",
            f"{logs}:/logs",
            "--volume",
            f"{candidate}:/candidate:ro",
            "--volume",
            f"{scenario_tests}:/scenario-tests:ro",
            self.image_name(task),
            "bash",
            "-c",
            shell,
        ]
        started = time.monotonic()
        result = self.runner.run(command, check=False, timeout=task.verifier_timeout)
        duration = time.monotonic() - started
        reward_path = logs / "verifier" / "reward.json"
        reward = json.loads(reward_path.read_text()) if reward_path.exists() else None
        valid_verifier_receipt = isinstance(reward, dict) and "reward" in reward
        passed = result.returncode == 0 and bool(reward and reward.get("reward") == 1)
        expected_pass = control in {"gold", "candidate"}
        infrastructure_exit = result.returncode in {125, 126, 127}
        if not valid_verifier_receipt or infrastructure_exit:
            outcome = "infrastructure_error"
            expectation_met = False
        else:
            outcome = "passed" if passed else "failed"
            expectation_met = passed == expected_pass
        verification = VerificationResult(
            task_id=task.task_id,
            scenario=scenario,
            control=control,
            outcome=outcome,
            exit_code=result.returncode,
            expected_pass=expected_pass,
            expectation_met=expectation_met,
            run_dir=str(run_dir),
            reward=reward,
            duration_seconds=duration,
            command_stderr=result.stderr[-8000:],
        )
        (run_dir / "verification.json").write_text(
            json.dumps(asdict(verification), indent=2, sort_keys=True) + "\n"
        )
        return verification

    def cleanup(self, *, include_images: bool = False) -> dict[str, int]:
        removed = {"containers": 0, "volumes": 0, "networks": 0, "images": 0}
        kinds = (("container", "containers"), ("volume", "volumes"), ("network", "networks"))
        for podman_kind, result_key in kinds:
            list_args = ["podman", podman_kind, "ls", "-q", "--filter", f"label={LABEL_KEY}=true"]
            if podman_kind == "container":
                list_args.insert(3, "--all")
            ids = self.runner.run(list_args).stdout.split()
            if ids:
                rm_args = ["podman", podman_kind, "rm"]
                if podman_kind == "container":
                    rm_args.append("--force")
                self.runner.run([*rm_args, *ids])
                removed[result_key] = len(ids)
        if include_images:
            ids = self.runner.run(
                ["podman", "image", "ls", "-q", "--filter", f"label={LABEL_KEY}=true"]
            ).stdout.split()
            if ids:
                unique = sorted(set(ids))
                self.runner.run(["podman", "image", "rm", *unique])
                removed["images"] = len(unique)
        return removed
