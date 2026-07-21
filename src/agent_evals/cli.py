from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .agent import AgentRunner
from .engine import DEFAULT_MIN_FREE_GIB, PodmanEngine
from .evidence import export_experiment_evidence
from .experiment import ExperimentSpec
from .matrix import MatrixRunner
from .proctor import ProctorQueue
from .providers import load_routes, resolve_model
from .report import write_experiment_report
from .review import ProctorReview
from .review_packets import finalize_review, prepare_review_packets
from .task import TaskSpec, TaskValidationError, discover_tasks


def _repo_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "tasks").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("not inside coding-agent-evals; pass --repo-root")


def _task(repo: Path, task_id: str) -> TaskSpec:
    path = repo / "tasks" / task_id
    if not path.is_dir():
        raise SystemExit(f"unknown task {task_id!r}")
    try:
        return TaskSpec.load(path)
    except TaskValidationError as exc:
        raise SystemExit(str(exc)) from exc


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cae")
    parser.add_argument("--repo-root")
    parser.add_argument(
        "--min-free-gib",
        type=int,
        default=int(os.environ.get("CAE_MIN_FREE_GIB", DEFAULT_MIN_FREE_GIB)),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor")
    commands.add_parser("list")
    validate = commands.add_parser("validate")
    validate.add_argument("task_id", nargs="?")

    build = commands.add_parser("build")
    build.add_argument("task_id")

    commands.add_parser("build-tools")
    build_agent = commands.add_parser("build-agent")
    build_agent.add_argument("task_id")

    run = commands.add_parser("run")
    run.add_argument("task_id")
    run.add_argument("model")
    run.add_argument("--provider", required=True)
    run.add_argument("--providers", type=Path, default=Path("providers.toml"))
    run.add_argument("--scenario")
    run.add_argument("--mode", choices=("baseline", "ask_user", "full_info"), default="ask_user")

    verify = commands.add_parser("verify")
    verify.add_argument("task_id")
    verify.add_argument(
        "--control", required=True, choices=("no-op", "gold", "mutant", "candidate")
    )
    verify.add_argument("--patch", type=Path)
    verify.add_argument("--scenario")

    audit = commands.add_parser("audit-task")
    audit.add_argument("task_id")
    audit.add_argument("--gold-repeats", type=int, default=2)
    audit.add_argument("--scenario")

    audit_environment = commands.add_parser("audit-environment")
    audit_environment.add_argument("task_id", nargs="?")

    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--include-images", action="store_true")

    proctor = commands.add_parser("proctor")
    proctor_sub = proctor.add_subparsers(dest="proctor_command", required=True)
    pending = proctor_sub.add_parser("pending")
    pending.add_argument("queue", type=Path)
    ask = proctor_sub.add_parser("ask")
    ask.add_argument("queue", type=Path)
    ask.add_argument("--run-id", required=True)
    ask.add_argument("--task-id", required=True)
    ask.add_argument("question")
    answer = proctor_sub.add_parser("answer")
    answer.add_argument("queue", type=Path)
    answer.add_argument("question_id")
    answer.add_argument("answer")
    answer.add_argument("--proctor", required=True)

    route = commands.add_parser("route")
    route.add_argument("model")
    route.add_argument("--provider", required=True)
    route.add_argument("--providers", type=Path, required=True)

    matrix = commands.add_parser("matrix")
    matrix_commands = matrix.add_subparsers(dest="matrix_command", required=True)
    for name in ("plan", "run", "status", "resume"):
        matrix_command = matrix_commands.add_parser(name)
        matrix_command.add_argument("manifest", type=Path)
        matrix_command.add_argument("--providers", type=Path, required=True)
        if name in {"run", "resume"}:
            matrix_command.add_argument("--cell", help="run exactly one expanded cell ID")

    report = commands.add_parser("report")
    report.add_argument("manifest", type=Path)
    report.add_argument("--providers", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)

    evidence = commands.add_parser("export-evidence")
    evidence.add_argument("experiment_id")
    evidence.add_argument("--output", type=Path, required=True)

    review = commands.add_parser("review-template")
    review.add_argument("run_id")
    review.add_argument("task_id")
    review.add_argument("--proctor", default="Hermes Agent")
    review.add_argument("--proctor-model", required=True)
    review.add_argument("--output", type=Path, required=True)

    review_packets = commands.add_parser("review-packets")
    review_packets.add_argument("experiment_id")
    review_packets.add_argument("--output", type=Path, required=True)
    review_packets.add_argument("--mapping", type=Path, required=True)

    review_finalize = commands.add_parser("review-finalize")
    review_finalize.add_argument("packet_id")
    review_finalize.add_argument("--mapping", type=Path, required=True)
    review_finalize.add_argument("--response", type=Path, required=True)
    review_finalize.add_argument("--proctor", default="Hermes Agent")
    review_finalize.add_argument("--proctor-model", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = _repo_root(args.repo_root)
    engine = PodmanEngine(repo, min_free_gib=args.min_free_gib)

    if args.command == "doctor":
        _print(engine.check_prerequisites())
        return 0
    if args.command == "list":
        _print([asdict(task) | {"root": str(task.root)} for task in discover_tasks(repo / "tasks")])
        return 0
    if args.command == "validate":
        tasks = [_task(repo, args.task_id)] if args.task_id else discover_tasks(repo / "tasks")
        validation_results = {task.task_id: task.validate() for task in tasks}
        _print(validation_results)
        return 1 if any(validation_results.values()) else 0
    if args.command == "build":
        digest = engine.build(_task(repo, args.task_id))
        _print({"task_id": args.task_id, "image_id": digest})
        return 0
    if args.command == "build-tools":
        _print(AgentRunner(repo, engine).build_tools())
        return 0
    if args.command == "build-agent":
        task = _task(repo, args.task_id)
        _print(
            {"task_id": task.task_id, "image": AgentRunner(repo, engine).build_agent_image(task)}
        )
        return 0
    if args.command == "run":
        route = resolve_model(args.provider, args.model, load_routes(args.providers))
        run_result = AgentRunner(repo, engine).run(
            _task(repo, args.task_id),
            route,
            scenario=args.scenario,
            instruction_mode=args.mode,
        )
        _print(asdict(run_result))
        return 0
    if args.command == "verify":
        verification_result = engine.verify(
            _task(repo, args.task_id),
            control=args.control,
            patch=args.patch,
            scenario=args.scenario,
        )
        _print(asdict(verification_result))
        return 0 if verification_result.expectation_met else 1
    if args.command == "audit-task":
        task = _task(repo, args.task_id)
        audit_results = [
            engine.verify(task, control="no-op", scenario=args.scenario),
            engine.verify(task, control="gold", scenario=args.scenario),
        ]
        for _ in range(max(0, args.gold_repeats - 1)):
            audit_results.append(engine.verify(task, control="gold", scenario=args.scenario))
        mutant_roots = [task.root / "mutants"]
        if args.scenario:
            mutant_roots.append(task.scenario(args.scenario).root / "mutants")
        mutants = sorted(mutant for root in mutant_roots for mutant in root.glob("*.patch"))
        for mutant in mutants:
            audit_results.append(
                engine.verify(task, control="mutant", patch=mutant, scenario=args.scenario)
            )
        _print([asdict(result) for result in audit_results])
        return 0 if all(result.expectation_met for result in audit_results) else 1
    if args.command == "audit-environment":
        tasks = [_task(repo, args.task_id)] if args.task_id else discover_tasks(repo / "tasks")
        environment_results = [engine.audit_environment(task) for task in tasks]
        _print([asdict(result) for result in environment_results])
        return 0 if all(result.passed for result in environment_results) else 1
    if args.command == "cleanup":
        _print(engine.cleanup(include_images=args.include_images))
        return 0
    if args.command == "proctor":
        queue = ProctorQueue(args.queue)
        if args.proctor_command == "pending":
            _print([asdict(question) for question in queue.pending()])
        elif args.proctor_command == "ask":
            _print(asdict(queue.ask(args.run_id, args.task_id, args.question)))
        else:
            _print(asdict(queue.answer(args.question_id, args.answer, args.proctor)))
        return 0
    if args.command == "route":
        _print(resolve_model(args.provider, args.model, load_routes(args.providers)).redacted())
        return 0
    if args.command == "matrix":
        providers = load_routes(args.providers)
        experiment = ExperimentSpec.load(args.manifest, repo, providers)
        matrix_runner = MatrixRunner(repo, engine, experiment, experiment.routes(providers))
        if args.matrix_command == "plan":
            _print(matrix_runner.plan())
        elif args.matrix_command == "status":
            _print(matrix_runner.status())
        else:
            _print(matrix_runner.run(cell_id=args.cell))
        return 0
    if args.command == "report":
        providers = load_routes(args.providers)
        experiment = ExperimentSpec.load(args.manifest, repo, providers)
        _print(write_experiment_report(repo, experiment, args.output)["totals"])
        return 0
    if args.command == "export-evidence":
        _print(export_experiment_evidence(repo, args.experiment_id, args.output))
        return 0
    if args.command == "review-template":
        review = ProctorReview(
            run_id=args.run_id,
            task_id=args.task_id,
            proctor=args.proctor,
            proctor_model=args.proctor_model,
        )
        review.write(args.output)
        _print({"output": str(args.output)})
        return 0
    if args.command == "review-packets":
        _print(prepare_review_packets(repo, args.experiment_id, args.output, args.mapping))
        return 0
    if args.command == "review-finalize":
        review = finalize_review(
            repo,
            args.mapping,
            args.packet_id,
            args.response,
            proctor=args.proctor,
            proctor_model=args.proctor_model,
        )
        _print({"output": str(repo / next(
            entry["review_path"]
            for entry in json.loads(args.mapping.read_text())["packets"]
            if entry["packet_id"] == args.packet_id
        )), "review": asdict(review)})
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
