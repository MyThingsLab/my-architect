from __future__ import annotations

import json

from mythings.engine import NoopEngine
from mythings.testing import ScriptedEngine

from myarchitect.breakdown import Breakdown, Task, synthesize_breakdown
from myarchitect.context import BreakdownContext


def ctx(**overrides: object) -> BreakdownContext:
    fields: dict[str, object] = {
        "objective_title": "Build a raytracer",
        "objective_body": "Ship a minimal path tracer.",
    }
    fields.update(overrides)
    return BreakdownContext(**fields)  # type: ignore[arg-type]


def well_formed_reply() -> str:
    return json.dumps(
        {
            "tasks": [
                {
                    "title": "Scaffold the scene graph",
                    "body": "Add the node types the tracer walks.",
                    "depends_on": [],
                    "rationale": "everything else builds on this",
                },
                {
                    "title": "Implement ray-sphere intersection",
                    "body": "Core intersection math plus unit tests.",
                    "depends_on": [0],
                    "rationale": "needs the scene graph in place",
                },
            ]
        }
    )


def test_well_formed_reply_parses_into_ordered_tasks_with_correct_depends_on() -> None:
    engine = ScriptedEngine(reply=well_formed_reply())
    breakdown = synthesize_breakdown(engine, ctx())

    assert breakdown.engine_used is True
    assert breakdown.tasks == [
        Task(
            title="Scaffold the scene graph",
            body="Add the node types the tracer walks.",
            depends_on=(),
            rationale="everything else builds on this",
        ),
        Task(
            title="Implement ray-sphere intersection",
            body="Core intersection math plus unit tests.",
            depends_on=(0,),
            rationale="needs the scene graph in place",
        ),
    ]
    (request,) = engine.calls
    assert "Build a raytracer" in request.prompt


def test_fenced_json_reply_still_parses() -> None:
    engine = ScriptedEngine(reply=f"```json\n{well_formed_reply()}\n```")
    breakdown = synthesize_breakdown(engine, ctx())

    assert breakdown.engine_used is True
    assert len(breakdown.tasks) == 2
    assert breakdown.tasks[1].depends_on == (0,)


def test_noop_engine_degrades_to_single_placeholder_task() -> None:
    breakdown = synthesize_breakdown(NoopEngine(), ctx())

    assert breakdown.engine_used is False
    assert breakdown.tasks == [
        Task(
            title="Build a raytracer",
            body="Ship a minimal path tracer.",
            depends_on=(),
            rationale="degraded: no Engine decomposition — placeholder task only",
        )
    ]


def test_non_json_reply_degrades_to_placeholder() -> None:
    engine = ScriptedEngine(reply="sure, here is my plan: do the thing")
    breakdown = synthesize_breakdown(engine, ctx())

    assert breakdown.engine_used is False
    assert breakdown.tasks[0].title == "Build a raytracer"


def test_out_of_range_depends_on_index_is_repaired_not_rejected() -> None:
    reply = json.dumps(
        {
            "tasks": [
                {
                    "title": "Task A",
                    "body": "first",
                    "depends_on": [0, 5, -1],
                    "rationale": "self-ref and out-of-range dropped",
                },
                {
                    "title": "Task B",
                    "body": "second",
                    "depends_on": [0, 3],
                    "rationale": "3 is out of range, dropped",
                },
            ]
        }
    )
    engine = ScriptedEngine(reply=reply)
    breakdown = synthesize_breakdown(engine, ctx())

    assert breakdown.engine_used is True
    assert breakdown.tasks[0].depends_on == ()
    assert breakdown.tasks[1].depends_on == (0,)


def test_breakdown_dataclass_shape() -> None:
    breakdown = Breakdown(tasks=[Task(title="t", body="b")], engine_used=True)
    assert breakdown.tasks[0].depends_on == ()
    assert breakdown.tasks[0].rationale == ""
