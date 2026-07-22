from __future__ import annotations

from myarchitect.breakdown import Task


def validate(tasks: list[Task]) -> None:
    """Raise `ValueError` if `tasks` is not a buildable dependency DAG.

    Checks every `depends_on` index for the two failure modes an Engine reply
    can still produce even after `breakdown._parse_tasks`'s own repair pass
    (self-reference, out-of-range), plus the one that repair can't catch on
    its own: a dependency cycle across several tasks. Called by
    `topological_order` before it orders anything, so a caller that only
    needs ordering still gets the same guarantee.
    """
    n = len(tasks)
    for i, task in enumerate(tasks):
        for dep in task.depends_on:
            if dep == i:
                raise ValueError(f"task {i} ({task.title!r}) depends on itself")
            if not (0 <= dep < n):
                raise ValueError(f"task {i} ({task.title!r}) depends on out-of-range index {dep}")
    _check_acyclic(tasks)


def _check_acyclic(tasks: list[Task]) -> None:
    # DFS with a recursion-stack color mark: hitting a "visiting" node means
    # the path back to it is a cycle.
    UNVISITED, VISITING, DONE = 0, 1, 2
    state = [UNVISITED] * len(tasks)

    def visit(i: int, path: list[int]) -> None:
        if state[i] == DONE:
            return
        if state[i] == VISITING:
            cycle = path[path.index(i) :] + [i]
            names = " -> ".join(tasks[j].title for j in cycle)
            raise ValueError(f"dependency cycle: {names}")
        state[i] = VISITING
        path.append(i)
        for dep in tasks[i].depends_on:
            visit(dep, path)
        path.pop()
        state[i] = DONE

    for i in range(len(tasks)):
        visit(i, [])


def topological_order(tasks: list[Task]) -> list[int]:
    """Return `tasks` indices in a valid build order: every index appears
    after all the indices in its own `depends_on`.

    Raises `ValueError` (via `validate`) on a cycle or a malformed
    `depends_on` entry. Ties (tasks with no ordering constraint between them)
    break by ascending original index, so the same DAG always orders the
    same way.
    """
    validate(tasks)
    n = len(tasks)
    in_degree = [len(task.depends_on) for task in tasks]
    dependents: list[list[int]] = [[] for _ in range(n)]
    for j, task in enumerate(tasks):
        for dep in task.depends_on:
            dependents[dep].append(j)

    ready = sorted(i for i in range(n) if in_degree[i] == 0)
    order: list[int] = []
    while ready:
        i = ready.pop(0)
        order.append(i)
        newly_ready = []
        for j in dependents[i]:
            in_degree[j] -= 1
            if in_degree[j] == 0:
                newly_ready.append(j)
        ready = sorted(ready + newly_ready)
    return order
