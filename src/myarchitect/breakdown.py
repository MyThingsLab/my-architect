from __future__ import annotations

import json
import re
from dataclasses import dataclass

from mythings.engine import Engine, EngineRequest

from myarchitect.context import BreakdownContext

# Mirrors the fence-stripping note on mythings.engine.ClaudeCLIEngine: models
# routinely wrap JSON replies in a ```json fence despite instructions not to.
# ClaudeCLIEngine already strips one for its own callers, but this parser
# tolerates it independently too, since other Engine implementations (or the
# fakes used in tests) hand us raw text.
_FENCE_RE = re.compile(r"^```[\w+-]*\n?(.*?)\n?```$", re.DOTALL)

# The single Engine judgment step: turn one objective (plus the deterministically
# assembled BreakdownContext) into an ordered task DAG. Same posture as
# my-director's plan.synthesize — the objective is fixed by the human/issue;
# the model only decomposes it, never restates or second-guesses it.
SYSTEM = (
    "You decompose one fixed objective into an ordered, dependency-tagged backlog "
    "of single-session tasks for a fleet of autonomous coding workers. Each task "
    "becomes a GitHub issue one worker picks up and closes with a single pull "
    "request, so it must be a single focused change plus its tests — small, "
    "self-contained, independently buildable. Do NOT restate or second-guess the "
    "objective; only break it into tasks. Reply with ONLY a JSON object, nothing "
    'else: {"tasks": [{"title": "<imperative, <=100 chars>", "body": "<what to '
    'build and why, concrete enough for a worker to act on>", "depends_on": '
    "[<0-based index into this tasks list of a task that must land first>], "
    '"rationale": "<why this task, one sentence>"}]}'
)


@dataclass(frozen=True)
class Task:
    """One task-issue in the proposed backlog.

    `depends_on` holds 0-based indices into the enclosing `Breakdown.tasks`
    list — not GitHub issue numbers, which don't exist until the tasks are
    filed (a later step).
    """

    title: str
    body: str
    depends_on: tuple[int, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class Breakdown:
    tasks: list[Task]
    engine_used: bool


def _strip_code_fence(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1) if match else text


def _request(ctx: BreakdownContext) -> EngineRequest:
    backlog = "\n".join(f"- {title}" for title in ctx.open_issue_titles) or "(none)"
    research = "\n".join(f"- {entry.detail}" for entry in ctx.research) or "(none)"
    prompt = (
        f"OBJECTIVE:\n{ctx.objective_title}\n\n{ctx.objective_body}\n\n"
        f"TARGET REPO'S OPEN BACKLOG (avoid proposing duplicates):\n{backlog}\n\n"
        f"RESEARCH BRIEFS (SOTA / context):\n{research}"
    )
    return EngineRequest(prompt=prompt, system=SYSTEM)


def _degraded_tasks(ctx: BreakdownContext) -> list[Task]:
    # No usable Engine reply: a single placeholder task that echoes the
    # objective verbatim, same posture as my-director/my-planner — never a
    # fabricated different objective.
    return [
        Task(
            title=ctx.objective_title,
            body=ctx.objective_body,
            depends_on=(),
            rationale="degraded: no Engine decomposition — placeholder task only",
        )
    ]


def _parse_tasks(text: str) -> list[Task] | None:
    if not text.strip():
        return None
    try:
        obj = json.loads(_strip_code_fence(text))
        raw = obj["tasks"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(raw, list) or not raw:
        return None

    fields: list[tuple[str, str, list[int], str]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        raw_depends = item.get("depends_on", [])
        if not isinstance(raw_depends, list) or not all(isinstance(d, int) for d in raw_depends):
            return None
        body = str(item.get("body", ""))
        rationale = str(item.get("rationale", ""))
        fields.append((title, body, raw_depends, rationale))

    # Repair (don't reject) out-of-range or self-referential depends_on indices:
    # a single malformed reference shouldn't discard an otherwise-usable
    # decomposition. Deduplicated and sorted for determinism.
    count = len(fields)
    return [
        Task(
            title=title,
            body=body,
            depends_on=tuple(sorted({d for d in raw_depends if 0 <= d < count and d != i})),
            rationale=rationale,
        )
        for i, (title, body, raw_depends, rationale) in enumerate(fields)
    ]


def synthesize_breakdown(engine: Engine, ctx: BreakdownContext) -> Breakdown:
    """Make the one Engine call that turns `ctx` into an ordered task DAG.

    JSON contract (enforced by `SYSTEM`, the request's system prompt): the
    reply must be a JSON object shaped
    `{"tasks": [{"title": str, "body": str, "depends_on": [int, ...], "rationale": str}]}`,
    where each `depends_on` entry is a 0-based index into that same `tasks`
    list. A whole-reply ```json fence is tolerated and stripped before
    parsing. Any `depends_on` index that is out of range or refers to the
    task itself is dropped rather than treated as fatal.

    Against `NoopEngine`, an empty reply, or a reply that isn't valid JSON
    (or is missing/malforms the `tasks` list), this degrades to a single
    placeholder `Task` that echoes the objective verbatim — it never
    fabricates a different objective, the same posture as my-director and
    my-planner. `Breakdown.engine_used` records which path was taken.
    """
    result = engine.run(_request(ctx))
    tasks = _parse_tasks(result.text)
    if tasks is None:
        return Breakdown(tasks=_degraded_tasks(ctx), engine_used=False)
    return Breakdown(tasks=tasks, engine_used=True)
