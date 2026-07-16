from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .agent import AgentRunner
from .engine import DEFAULT_MIN_FREE_GIB, PodmanEngine
from .proctor import ProctorQueue
from .providers import load_routes, resolve_model
from .review import ProctorReview
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
    route.add_argument("--providers", type=Path, required=True)

    review = commands.add_parser("review-template")
    review.add_argument("run_id")
    review.add_argument("task_id")
    review.add_argument("--proctor", default="Hermes Agent")
    review.add_argument("--proctor-model", required=True)
    review.add_argument("--output", type=Path, required=True)
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
        results = {task.task_id: task.validate() for task in tasks}
        _print(results)
        return 1 if any(results.values()) else 0
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
        route = resolve_model(args.model, load_routes(args.providers))
        result = AgentRunner(repo, engine).run(
            _task(repo, args.task_id),
            route,
            scenario=args.scenario,
            instruction_mode=args.mode,
        )
        _print(asdict(result))
        return 0
    if args.command == "verify":
        result = engine.verify(
            _task(repo, args.task_id),
            control=args.control,
            patch=args.patch,
            scenario=args.scenario,
        )
        _print(asdict(result))
        return 0 if result.expectation_met else 1
    if args.command == "audit-task":
        task = _task(repo, args.task_id)
        results = [
            engine.verify(task, control="no-op", scenario=args.scenario),
            engine.verify(task, control="gold", scenario=args.scenario),
        ]
        for _ in range(max(0, args.gold_repeats - 1)):
            results.append(engine.verify(task, control="gold", scenario=args.scenario))
        mutant_roots = [task.root / "mutants"]
        if args.scenario:
            mutant_roots.append(task.scenario(args.scenario).root / "mutants")
        mutants = sorted(mutant for root in mutant_roots for mutant in root.glob("*.patch"))
        for mutant in mutants:
            results.append(
                engine.verify(task, control="mutant", patch=mutant, scenario=args.scenario)
            )
        _print([asdict(result) for result in results])
        return 0 if all(result.expectation_met for result in results) else 1
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
        _print(resolve_model(args.model, load_routes(args.providers)).redacted())
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
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
