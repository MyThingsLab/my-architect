from __future__ import annotations

import json
from pathlib import Path

from mythings.github import Issue
from mythings.ledger import Ledger
from mythings.testing import FakeGh, ledger_entry

from myarchitect.context import (
    MAX_DETAIL_LEN,
    MAX_OPEN_ISSUES,
    MAX_TITLE_LEN,
    BreakdownContext,
    assemble,
    truncate,
)


def issue_obj(number: int, title: str) -> dict:
    return {
        "number": number,
        "title": title,
        "body": "",
        "url": f"https://github.com/o/r/issues/{number}",
        "labels": [],
    }


def test_assemble_bundles_objective_backlog_and_matching_research(tmp_path: Path) -> None:
    runner = FakeGh({("issue", "list"): json.dumps([issue_obj(2, "unrelated task")])})
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(
        ledger_entry(
            "myresearcher", "research", "success", "raytracer SOTA", topic="build a raytracer"
        )
    )
    ledger.append(ledger_entry("myresearcher", "research", "success", "unrelated", topic="widgets"))
    objective = Issue(number=1, title="Build a raytracer", body="details", url="https://x/1")

    ctx = assemble(objective, runner=runner, repo="o/r", ledger=ledger)

    assert ctx.objective_title == "Build a raytracer"
    assert ctx.objective_body == "details"
    assert ctx.open_issue_titles == ("unrelated task",)
    assert [e.data["topic"] for e in ctx.research] == ["build a raytracer"]


def test_assemble_degrades_cleanly_with_empty_backlog_and_no_research(tmp_path: Path) -> None:
    runner = FakeGh({("issue", "list"): "[]"})
    ledger = Ledger(tmp_path / "ledger.jsonl")
    objective = Issue(number=1, title="Build a raytracer", body="details", url="https://x/1")

    ctx = assemble(objective, runner=runner, repo="o/r", ledger=ledger)

    assert ctx.open_issue_titles == ()
    assert ctx.research == ()


def test_truncate_caps_oversized_inputs() -> None:
    ctx = BreakdownContext(
        objective_title="t" * (MAX_TITLE_LEN + 50),
        objective_body="b" * 5000,
        open_issue_titles=tuple(f"issue {i}" for i in range(MAX_OPEN_ISSUES + 10)),
        research=(
            ledger_entry("myresearcher", "research", "success", "d" * (MAX_DETAIL_LEN + 50)),
        ),
    )

    capped = truncate(ctx)

    assert len(capped.objective_title) == MAX_TITLE_LEN
    assert len(capped.objective_body) <= 4000
    assert len(capped.open_issue_titles) == MAX_OPEN_ISSUES
    assert len(capped.research[0].detail) == MAX_DETAIL_LEN


def test_truncate_is_a_noop_for_small_inputs() -> None:
    ctx = BreakdownContext(objective_title="short", objective_body="short body")
    assert truncate(ctx) == ctx
