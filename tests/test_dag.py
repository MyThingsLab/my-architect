from __future__ import annotations

import pytest

from myarchitect.breakdown import Task
from myarchitect.dag import topological_order, validate


def task(title: str, depends_on: tuple[int, ...] = ()) -> Task:
    return Task(title=title, body="body", depends_on=depends_on)


def test_linear_chain_orders_correctly() -> None:
    tasks = [task("A"), task("B", (0,)), task("C", (1,))]
    assert topological_order(tasks) == [0, 1, 2]


def test_diamond_orders_with_the_join_last() -> None:
    tasks = [task("A"), task("B", (0,)), task("C", (0,)), task("D", (1, 2))]
    order = topological_order(tasks)
    assert order[0] == 0
    assert order[-1] == 3
    assert set(order[1:3]) == {1, 2}


def test_cycle_raises_naming_a_task_in_the_cycle() -> None:
    tasks = [task("A", (1,)), task("B", (0,))]
    with pytest.raises(ValueError, match="A"):
        validate(tasks)


def test_out_of_range_depends_on_raises() -> None:
    with pytest.raises(ValueError, match="out-of-range"):
        validate([task("A", (5,))])


def test_self_dependency_raises() -> None:
    with pytest.raises(ValueError, match="itself"):
        validate([task("A", (0,))])


def test_tie_breaking_is_deterministic_across_two_calls() -> None:
    tasks = [task("A"), task("B"), task("C", (0, 1))]
    assert topological_order(tasks) == topological_order(tasks) == [0, 1, 2]


def test_topological_order_raises_on_the_same_bad_dag_as_validate() -> None:
    with pytest.raises(ValueError):
        topological_order([task("A", (0,))])
