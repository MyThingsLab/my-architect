from __future__ import annotations

import json
from pathlib import Path

import pytest
from mythings.engine import ClaudeCLIEngine, NoopEngine
from mythings.ledger import Ledger
from mythings.testing import FakeGh, ScriptedEngine

from myarchitect import cli, emit
from myarchitect.cli import build_engine, main


def issue_obj(number: int, title: str, body: str = "details") -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "url": f"https://github.com/o/r/issues/{number}",
        "labels": [{"name": "my-architect"}],
    }


def gh_with(view: dict, *, open_issues: list[dict] | None = None) -> FakeGh:
    state = {"n": 200}

    def create(argv: list[str]) -> str:
        state["n"] += 1
        return f"https://github.com/o/r/issues/{state['n']}\n"

    return FakeGh(
        {
            ("issue", "view"): json.dumps(view),
            ("issue", "list"): json.dumps(open_issues or []),
            ("issue", "create"): create,
            ("issue", "edit"): "",
        }
    )


def well_formed_reply() -> str:
    return json.dumps(
        {
            "tasks": [
                {"title": "Task A", "body": "do A", "depends_on": [], "rationale": "first"},
                {"title": "Task B", "body": "do B", "depends_on": [0], "rationale": "second"},
            ]
        }
    )


def test_build_engine_selects_backend() -> None:
    assert isinstance(build_engine("noop"), NoopEngine)
    assert isinstance(build_engine("claude-cli"), ClaudeCLIEngine)


def test_dry_run_prints_dag_and_files_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = gh_with(issue_obj(42, "Build a raytracer"))
    rc = main(
        [
            "plan",
            "--objective-issue",
            "42",
            "--repo",
            "o/r",
            "--dry-run",
            "--ledger",
            str(tmp_path / "l.jsonl"),
        ],
        runner=gh,
    )
    assert rc == 0
    assert not gh.saw("issue", "create")
    out = capsys.readouterr().out
    assert "dry run" in out
    assert "task(s), build order" in out


def test_noop_engine_degrades_and_still_files_the_placeholder_task(tmp_path: Path) -> None:
    gh = gh_with(issue_obj(42, "Build a raytracer"))
    rc = main(
        ["plan", "--objective-issue", "42", "--repo", "o/r", "--ledger", str(tmp_path / "l.jsonl")],
        runner=gh,
    )
    assert rc == 0
    assert gh.saw("issue", "create")
    entries = Ledger(tmp_path / "l.jsonl").read(tool=emit.TOOL, kind=emit.LEDGER_KIND)
    assert len(entries) == 1
    assert entries[0].data["total"] == 1


def test_full_run_wires_objective_through_context_breakdown_and_emit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli, "build_engine", lambda name, model=None: ScriptedEngine(reply=well_formed_reply())
    )
    gh = gh_with(issue_obj(42, "Build a raytracer"), open_issues=[])

    rc = main(
        ["plan", "--objective-issue", "42", "--repo", "o/r", "--ledger", str(tmp_path / "l.jsonl")],
        runner=gh,
    )

    assert rc == 0
    create_calls = [c for c in gh.calls if c[:2] == ["issue", "create"]]
    assert len(create_calls) == 2
    entries = Ledger(tmp_path / "l.jsonl").read(tool=emit.TOOL, kind=emit.LEDGER_KIND)
    assert entries[0].data == {
        "objective": "Build a raytracer",
        "filed": entries[0].data["filed"],
        "total": 2,
        "skipped": [],
    }
    assert len(entries[0].data["filed"]) == 2


def test_invalid_dag_from_engine_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cyclic_reply = json.dumps(
        {
            "tasks": [
                {"title": "A", "body": "a", "depends_on": [1], "rationale": ""},
                {"title": "B", "body": "b", "depends_on": [0], "rationale": ""},
            ]
        }
    )
    monkeypatch.setattr(
        cli, "build_engine", lambda name, model=None: ScriptedEngine(reply=cyclic_reply)
    )
    gh = gh_with(issue_obj(1, "Objective"))

    rc = main(
        ["plan", "--objective-issue", "1", "--repo", "o/r", "--ledger", str(tmp_path / "l.jsonl")],
        runner=gh,
    )

    assert rc == 1
    assert not gh.saw("issue", "create")
    assert "invalid task DAG" in capsys.readouterr().out


def test_unattended_denial_exits_nonzero_and_prints_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    gh = gh_with(issue_obj(1, "Objective"))

    rc = main(
        ["plan", "--objective-issue", "1", "--repo", "o/r", "--ledger", str(tmp_path / "l.jsonl")],
        runner=gh,
    )

    assert rc == 1
    assert not gh.saw("issue", "create")
    assert "skipped:" in capsys.readouterr().out


def test_plan_is_the_only_command() -> None:
    with pytest.raises(SystemExit):
        main(["frobnicate"])


def test_objective_issue_and_repo_are_required() -> None:
    with pytest.raises(SystemExit):
        main(["plan"])
