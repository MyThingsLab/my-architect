from __future__ import annotations

import argparse
from pathlib import Path

from mythings.engine import ClaudeCLIEngine, Engine, NoopEngine
from mythings.github import Runner, _gh
from mythings.ledger import Ledger

from myarchitect import context, dag, emit, sources
from myarchitect.breakdown import Task, synthesize_breakdown
from myarchitect.emit import BACKLOG_LABEL, DefaultPolicy

_ENGINE_NAMES = ("noop", "claude-cli")


def build_engine(name: str, *, model: str | None = None) -> Engine:
    if name == "claude-cli":
        return ClaudeCLIEngine(model=model)
    return NoopEngine()


def render_dag(tasks: list[Task], order: list[int]) -> str:
    lines = [f"{len(tasks)} task(s), build order:"]
    for pos, i in enumerate(order, 1):
        deps = ", ".join(str(d) for d in tasks[i].depends_on) or "none"
        lines.append(f"  {pos}. [{i}] {tasks[i].title} (depends on task(s): {deps})")
    return "\n".join(lines)


def _run_plan(args: argparse.Namespace, runner: Runner) -> int:
    ledger = Ledger(args.ledger)
    objective = sources.read_objective(runner, args.repo, args.objective_issue)
    ctx = context.assemble(objective, runner=runner, repo=args.repo, ledger=ledger)

    engine = build_engine(args.engine, model=args.engine_model)
    breakdown = synthesize_breakdown(engine, ctx)

    try:
        order = dag.topological_order(breakdown.tasks)
    except ValueError as exc:
        print(f"invalid task DAG: {exc}")
        return 1

    print(render_dag(breakdown.tasks, order))

    if args.dry_run:
        print("(dry run -- nothing filed)")
        return 0

    result = emit.emit(
        breakdown.tasks,
        order,
        repo=args.repo,
        label=args.label,
        objective_title=objective.title,
        policy=DefaultPolicy(),
        ledger=ledger,
        runner=runner,
    )
    for i, number in sorted(result.filed.items()):
        print(f"  filed #{number}: {breakdown.tasks[i].title}")
    for reason in result.skipped:
        print(f"  skipped: {reason}")
    return 0 if result.filed else 1


def main(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="myarchitect",
        description="Decompose one objective issue into an ordered, dependency-tagged "
        "backlog of task issues.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="assemble context, decompose, and file task issues")
    plan.add_argument(
        "--objective-issue", type=int, required=True, help="issue number to decompose"
    )
    plan.add_argument("--repo", required=True, help='target repo, e.g. "MyThingsLab/my-raytracer"')
    plan.add_argument("--engine", choices=sorted(_ENGINE_NAMES), default="noop")
    plan.add_argument("--engine-model", help="model for --engine claude-cli")
    plan.add_argument(
        "--dry-run", action="store_true", help="print the proposed DAG and file nothing"
    )
    plan.add_argument("--label", default=BACKLOG_LABEL, help="label applied to every filed issue")
    plan.add_argument("--ledger", type=Path, default=Path(".mythings/ledger.jsonl"))

    args = parser.parse_args(argv)
    return _run_plan(args, runner or _gh)


if __name__ == "__main__":
    raise SystemExit(main())
