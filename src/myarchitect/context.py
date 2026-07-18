from __future__ import annotations

from dataclasses import dataclass

from mythings.github import Issue, Runner
from mythings.ledger import Ledger, LedgerEntry

from myarchitect.sources import read_open_issues, read_research

MAX_OPEN_ISSUES = 50
MAX_RESEARCH_ENTRIES = 10
MAX_TITLE_LEN = 200
MAX_BODY_LEN = 4000
MAX_DETAIL_LEN = 2000


@dataclass(frozen=True)
class BreakdownContext:
    """The deterministically assembled context handed to the single Engine call.

    Bundles the objective (a `my-architect`-labeled issue), the target repo's
    open backlog (titles only, to avoid proposing duplicates), and any
    `my-researcher` briefs whose topic matches the objective.
    """

    objective_title: str
    objective_body: str
    open_issue_titles: tuple[str, ...] = ()
    research: tuple[LedgerEntry, ...] = ()


def assemble(objective: Issue, *, runner: Runner, repo: str, ledger: Ledger) -> BreakdownContext:
    """Deterministically assemble a `BreakdownContext` — no Engine call, no side effects."""
    open_titles = read_open_issues(runner, repo)
    research = read_research(ledger, objective.title)
    return truncate(
        BreakdownContext(
            objective_title=objective.title,
            objective_body=objective.body,
            open_issue_titles=tuple(open_titles),
            research=tuple(research),
        )
    )


def truncate(ctx: BreakdownContext) -> BreakdownContext:
    """Bound an assembled `BreakdownContext` so the eventual prompt stays a sane size."""
    return BreakdownContext(
        objective_title=ctx.objective_title[:MAX_TITLE_LEN],
        objective_body=ctx.objective_body[:MAX_BODY_LEN],
        open_issue_titles=tuple(
            title[:MAX_TITLE_LEN] for title in ctx.open_issue_titles[:MAX_OPEN_ISSUES]
        ),
        research=tuple(_truncate_entry(entry) for entry in ctx.research[:MAX_RESEARCH_ENTRIES]),
    )


def _truncate_entry(entry: LedgerEntry) -> LedgerEntry:
    if len(entry.detail) <= MAX_DETAIL_LEN:
        return entry
    return LedgerEntry(
        tool=entry.tool,
        kind=entry.kind,
        outcome=entry.outcome,
        detail=entry.detail[:MAX_DETAIL_LEN],
        data=entry.data,
        ts=entry.ts,
    )
