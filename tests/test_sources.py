from __future__ import annotations

import json
from pathlib import Path

from mythings.ledger import Ledger
from mythings.testing import FakeGh, ledger_entry

from myarchitect.sources import read_open_issues, read_research


def issue_obj(number: int, title: str) -> dict:
    return {
        "number": number,
        "title": title,
        "body": "",
        "url": f"https://github.com/o/r/issues/{number}",
        "labels": [],
    }


def gh_for(issues: list[dict]) -> FakeGh:
    return FakeGh({("issue", "list"): json.dumps(issues)})


def test_read_open_issues_returns_titles() -> None:
    runner = gh_for([issue_obj(1, "add raytracer"), issue_obj(2, "fix scaffold")])
    assert read_open_issues(runner, "o/r") == ["add raytracer", "fix scaffold"]


def test_read_open_issues_degrades_cleanly_on_empty_backlog() -> None:
    runner = gh_for([])
    assert read_open_issues(runner, "o/r") == []


def test_read_research_matches_overlapping_topic(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(
        ledger_entry(
            "myresearcher", "research", "success", "raytracer SOTA", topic="build a raytracer"
        )
    )
    ledger.append(
        ledger_entry("myresearcher", "research", "success", "unrelated brief", topic="widgets")
    )

    matches = read_research(ledger, "Build a raytracer")

    assert [m.data["topic"] for m in matches] == ["build a raytracer"]


def test_read_research_excludes_non_matching_entries(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(ledger_entry("myresearcher", "research", "success", "unrelated", topic="widgets"))

    assert read_research(ledger, "Build a raytracer") == []


def test_read_research_degrades_cleanly_when_ledger_is_empty(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    assert read_research(ledger, "Build a raytracer") == []


def test_read_research_ignores_non_research_kinds(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(
        ledger_entry("myplanner", "plan", "success", "raytracer plan", topic="raytracer")
    )
    assert read_research(ledger, "Build a raytracer") == []
