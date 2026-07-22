# my-architect

[![CI](https://github.com/MyThingsLab/my-architect/actions/workflows/ci.yml/badge.svg)](https://github.com/MyThingsLab/my-architect/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/MyThingsLab/my-architect/branch/main/graph/badge.svg)](https://codecov.io/gh/MyThingsLab/my-architect) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

The fleet's **autonomous work-breakdown** tool. Given one objective — a
`my-architect`-labeled GitHub issue — it decomposes it into an ordered,
dependency-tagged backlog of *single-session* issues sized for
[`my-coder`](../my-coder) to build, and files them.

It is the unattended counterpart to [`my-director`](../my-director):
my-director produces the same shape of task-issues but through a human
interview; my-architect takes the objective straight from an issue and pulls
its context — including any SOTA reading already done by
[`my-researcher`](../my-researcher) — from the shared `Ledger`, then decomposes
without a human in the loop (creating the issues is still `ASK`-gated, so a
human, or the live ask channel, blesses the batch).

```
objective issue
   │  my-researcher brief (read from the ledger)
   ▼
my-architect  ──►  ordered, dependency-tagged task issues
   │
   ▼
my-coder  ──►  one draft PR per issue  ──►  human merges
```

## What it does

1. **Assemble** (deterministic, no Engine): the objective + the target repo's
   open backlog + matching `my-researcher` briefs → a `BreakdownContext`.
2. **Decompose** (the one Engine call): context → strict-JSON task DAG
   `{"tasks": [{"title", "body", "depends_on", "rationale"}]}`, each task a
   single-session unit of work with tests.
3. **Validate & order**: reject cycles / dangling dependencies, topologically
   sort.
4. **Emit** (`ASK`-gated): file each task as a labeled issue with its
   `Depends on #N` line resolved to the real issue numbers; one
   `kind=breakdown` ledger entry. Never opens a PR, never merges, never writes
   code.

```bash
myarchitect plan --objective-issue 42 --repo MyThingsLab/my-raytracer --engine claude-cli
myarchitect plan --objective-issue 42 --dry-run   # print the DAG, file nothing
```

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../my-things-core -e ".[dev]"
pytest
```

`--engine noop` (the default) costs zero tokens: with no usable Engine reply,
the DAG degrades to a single placeholder task echoing the objective verbatim
— still validated, ordered, and filed like any other run unless `--dry-run`
is also passed.

## License

MIT — see [`LICENSE`](LICENSE).
