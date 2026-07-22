from __future__ import annotations

from pathlib import Path

from mythings.ledger import Ledger
from mythings.policy import ALLOW, Action, Decision, PolicyResult
from mythings.testing import FakeGh

from myarchitect import emit
from myarchitect.breakdown import Task
from myarchitect.dag import topological_order
from myarchitect.emit import DefaultPolicy, EmitResult
from myarchitect.emit import emit as run_emit


def fake_gh() -> FakeGh:
    # Stateful wiring over the shared FakeGh: issue create hands out
    # sequential numbers; edit records the bodies it was asked to write so
    # tests can assert the back-patched "Depends on #N" lines.
    state = {"n": 100}
    edits: dict[int, str] = {}

    def issue_create(argv: list[str]) -> str:
        state["n"] += 1
        return f"https://github.com/o/r/issues/{state['n']}\n"

    def issue_edit(argv: list[str]) -> str:
        # Two distinct call shapes hit "issue edit": add_labels (no --body)
        # and the depends_on back-patch (--body <text>). Only the latter is
        # interesting here.
        if "--body" in argv:
            number = int(argv[2])
            edits[number] = argv[argv.index("--body") + 1]
        return ""

    gh = FakeGh({("issue", "create"): issue_create, ("issue", "edit"): issue_edit})
    gh.edits = edits
    return gh


def diamond() -> list[Task]:
    return [
        Task(title="A", body="do A"),
        Task(title="B", body="do B", depends_on=(0,)),
        Task(title="C", body="do C", depends_on=(0,)),
        Task(title="D", body="do D", depends_on=(1, 2)),
    ]


def test_diamond_files_all_issues_with_backpatched_depends_on(tmp_path: Path) -> None:
    # DefaultPolicy classifies issue-create as ASK; attended (unattended=False)
    # is the human's explicit opt-in, so this proceeds -- see
    # test_unattended_ask_degrades_to_deny for the CI-side counterpart.
    tasks = diamond()
    order = topological_order(tasks)
    gh = fake_gh()
    ledger = Ledger(tmp_path / "ledger.jsonl")

    result = run_emit(
        tasks,
        order,
        repo="o/r",
        label="my-architect",
        objective_title="Ship the thing",
        policy=DefaultPolicy(),
        ledger=ledger,
        runner=gh,
        unattended=False,
    )

    assert len(result.filed) == 4
    assert result.skipped == []
    a_number = result.filed[0]
    d_number = result.filed[3]
    assert f"Depends on #{a_number}" in gh.edits[result.filed[1]]
    assert f"Depends on #{a_number}" in gh.edits[result.filed[2]]
    b_number, c_number = result.filed[1], result.filed[2]
    d_body = gh.edits[d_number]
    assert f"#{b_number}" in d_body and f"#{c_number}" in d_body
    assert result.filed[0] not in gh.edits  # A has no dependencies, never patched


def test_add_labels_applied_to_every_filed_issue(tmp_path: Path) -> None:
    gh = fake_gh()
    tasks = [Task(title="A", body="a")]
    run_emit(
        tasks,
        [0],
        repo="o/r",
        label="my-architect",
        objective_title="Ship it",
        policy=DefaultPolicy(),
        ledger=Ledger(tmp_path / "l.jsonl"),
        runner=gh,
        unattended=False,
    )
    edit_labels = next(c for c in gh.calls if c[:2] == ["issue", "edit"] and "--add-label" in c)
    assert "--add-label" in edit_labels and "my-architect" in edit_labels


def test_denied_task_stops_the_batch_and_reports_skips(tmp_path: Path) -> None:
    class DenyAll:
        def evaluate(self, action: Action) -> PolicyResult:
            return PolicyResult(Decision.DENY, reason="no")

    tasks = diamond()
    order = topological_order(tasks)
    gh = fake_gh()
    ledger = Ledger(tmp_path / "ledger.jsonl")

    result = run_emit(
        tasks,
        order,
        repo="o/r",
        label="my-architect",
        objective_title="Ship the thing",
        policy=DenyAll(),
        ledger=ledger,
        runner=gh,
        unattended=False,
    )

    assert result.filed == {}
    assert len(result.skipped) == 4
    assert not gh.saw("issue", "create")
    (entry,) = ledger.read(tool=emit.TOOL, kind=emit.LEDGER_KIND)
    assert entry.outcome == "denied"


def test_unattended_ask_degrades_to_deny(tmp_path: Path) -> None:
    # The same DefaultPolicy ASK that succeeds attended (previous tests) is
    # denied the moment the run is unattended (CI-dispatched) -- nothing
    # public is created without a human, or the live ask channel, first.
    tasks = [Task(title="A", body="a")]
    gh = fake_gh()
    result = run_emit(
        tasks,
        [0],
        repo="o/r",
        label="my-architect",
        objective_title="Ship it",
        policy=DefaultPolicy(),
        ledger=Ledger(tmp_path / "l.jsonl"),
        runner=gh,
        unattended=True,
    )
    assert result.filed == {}
    assert not gh.saw("issue", "create")


def test_partial_batch_stop_leaves_earlier_issues_filed(tmp_path: Path) -> None:
    # A -> B -> C: deny only the second task (B); A is already filed and stays
    # filed, C is never attempted since the batch stops cleanly.
    tasks = [
        Task(title="A", body="a"),
        Task(title="B", body="b", depends_on=(0,)),
        Task(title="C", body="c", depends_on=(1,)),
    ]
    order = topological_order(tasks)
    calls = {"n": 0}

    class DenySecond:
        def evaluate(self, action: Action) -> PolicyResult:
            calls["n"] += 1
            return ALLOW if calls["n"] == 1 else PolicyResult(Decision.DENY, reason="stop")

    gh = fake_gh()
    result = run_emit(
        tasks,
        order,
        repo="o/r",
        label="my-architect",
        objective_title="Ship it",
        policy=DenySecond(),
        ledger=Ledger(tmp_path / "l.jsonl"),
        runner=gh,
        unattended=False,
    )
    assert list(result.filed.keys()) == [0]
    assert len(result.skipped) == 2


def test_exactly_one_ledger_entry_per_run(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    run_emit(
        diamond(),
        topological_order(diamond()),
        repo="o/r",
        label="my-architect",
        objective_title="Ship the thing",
        policy=DefaultPolicy(),
        ledger=ledger,
        runner=fake_gh(),
        unattended=False,
    )
    assert len(ledger.read(kind=emit.LEDGER_KIND)) == 1


def test_default_policy_allows_non_issue_create_actions() -> None:
    result = DefaultPolicy().evaluate(Action(kind="bash"))
    assert result.decision == Decision.ALLOW


def test_emit_result_is_a_plain_dataclass() -> None:
    result = EmitResult(filed={0: 1}, skipped=["x"])
    assert result.filed == {0: 1}
    assert result.skipped == ["x"]
