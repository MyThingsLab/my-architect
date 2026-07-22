from __future__ import annotations

from dataclasses import dataclass

from mythings.github import GitHub, Runner, _gh
from mythings.isolation import in_github_actions
from mythings.ledger import Ledger
from mythings.policy import ALLOW, Action, Decision, Policy, PolicyResult

from myarchitect.breakdown import Task

TOOL = "myarchitect"
LEDGER_KIND = "breakdown"
BACKLOG_LABEL = "my-architect"  # applied to every issue this tool files


class DefaultPolicy:
    # Filing a public GitHub issue is my-architect's one side effect: ASK by
    # default (same classification my-director/my-planner give issue-create).
    # Writing the ledger entry is not a public mutation and never reaches
    # Policy.
    def evaluate(self, action: Action) -> PolicyResult:
        if action.kind == "issue-create":
            return PolicyResult(
                Decision.ASK, reason="creates a public issue", rule="public-content"
            )
        return ALLOW


@dataclass(frozen=True)
class EmitResult:
    filed: dict[int, int]  # original task index -> filed issue number
    skipped: list[str]  # human-readable reasons, in the order encountered


def _depends_on_line(task: Task, index_to_number: dict[int, int]) -> str:
    refs = ", ".join(f"#{index_to_number[dep]}" for dep in task.depends_on)
    return f"{task.body}\n\nDepends on {refs}."


def emit(
    tasks: list[Task],
    order: list[int],
    *,
    repo: str,
    label: str,
    objective_title: str,
    policy: Policy,
    ledger: Ledger,
    runner: Runner = _gh,
    unattended: bool | None = None,
) -> EmitResult:
    """File `tasks` as GitHub issues in `order` (a `dag.topological_order` result).

    Each `gh issue create` is its own `Action(kind="issue-create")` routed
    through `policy`. Running this attended is the human's explicit opt-in,
    so `ASK` proceeds when attended and only degrades to `DENY` when
    unattended (mirrors MyPlanner's and MyProjector's tracking-issue-edit
    gate) -- nothing is created by an unattended (CI-dispatched) run without
    a human, or the live ask channel, blessing it first. The first denial
    stops the whole batch -- everything already filed stays filed, but
    nothing later in `order` is attempted, so the result is never a
    half-wired DAG with a task referencing a dependency that doesn't exist.

    Dependency resolution is two-phase because `depends_on` indices refer to
    other tasks in this same batch, which don't have real issue numbers until
    they too are filed: phase one creates every issue this run gets to (with
    its body as authored, no dependency line yet) and records its number in
    `index_to_number`; phase two revisits each created issue whose task has
    `depends_on` and edits its body to append the resolved `Depends on #N`
    line. Because `order` is topological, every dependency of a created task
    was itself created earlier in phase one, so phase two never looks up a
    missing index. Exactly one `kind=breakdown` ledger entry summarizes the
    run. Never opens a PR, never merges, never writes code.
    """
    unattended = in_github_actions() if unattended is None else unattended
    gh = GitHub(repo, runner=runner)

    index_to_number: dict[int, int] = {}
    skipped: list[str] = []
    for pos, i in enumerate(order):
        task = tasks[i]
        gate = policy.evaluate(
            Action(kind="issue-create", payload={"repo": repo, "title": task.title})
        )
        decision = gate.under(unattended=unattended)
        proceed = decision is Decision.ALLOW or (decision is Decision.ASK and not unattended)
        if not proceed:
            reason = gate.reason or gate.rule or "denied"
            skipped.append(f"{task.title}: {reason}")
            for j in order[pos + 1 :]:
                skipped.append(f"{tasks[j].title}: batch stopped ({task.title!r} was denied)")
            break
        issue = gh.create_issue(title=task.title, body=task.body)
        gh.add_labels(issue.number, [label])
        index_to_number[i] = issue.number

    for i, number in index_to_number.items():
        task = tasks[i]
        if not task.depends_on:
            continue
        body = _depends_on_line(task, index_to_number)
        runner(["issue", "edit", str(number), "--repo", repo, "--body", body])

    filed_count = len(index_to_number)
    outcome = "denied" if filed_count == 0 else "success"
    detail = f"{objective_title}: filed {filed_count}/{len(tasks)} task(s)"
    ledger.record(
        TOOL,
        LEDGER_KIND,
        outcome,
        detail,
        objective=objective_title,
        filed=sorted(index_to_number.values()),
        total=len(tasks),
        skipped=skipped,
    )
    return EmitResult(filed=index_to_number, skipped=skipped)
