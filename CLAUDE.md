# my-architect — agent instructions

You are developing **my-architect**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `my-things-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** the fleet's **autonomous** work-breakdown. Given one objective
  (a `my-architect`-labeled issue), decompose it into an ordered,
  dependency-tagged backlog of *single-session* issues sized for MyCoder to
  build, and file them. The unattended counterpart to **my-director**, which
  produces the same shape of task-issues but requires a human interview;
  my-architect takes the objective from an issue and pulls its SOTA/context
  from already-published `my-researcher` briefs on the ledger.
- **The single Engine call:** required — synthesize the deterministically
  assembled `BreakdownContext` (objective + the target repo's open backlog +
  matching `my-researcher` briefs) into a task DAG. Strict JSON:
  `{"tasks": [{"title", "body", "depends_on": [<0-based task index>],
  "rationale"}]}`. Against `NoopEngine` or an unparsable/empty reply it
  degrades to a single placeholder task echoing the objective — it never
  fabricates a different objective (same posture as my-director/my-planner).
- **Invariants / rules:** reads other tools' state only via the on-disk
  `Ledger` + `gh` (my-researcher's briefs through the read-only ledger seam
  my-todo uses) — **no package dependency on any other tool**; runtime dep is
  `my-things-core` only. The one side effect is creating issues, every one
  routed through `Policy` as an `Action` — **ASK**-gated, so an unattended run
  degrades `ASK`→`DENY` and nothing public is created without a human (or the
  live ask channel answering). The proposed DAG is validated (no cycles, no
  dangling/self `depends_on`) and topologically ordered before any issue is
  filed. **Never opens a PR, never merges, never writes code.** Writes exactly
  one `kind=breakdown` ledger entry per run.
- **Backlog label:** `my-architect`.

## Testing

Fakes come from `mythings.testing` (opt-in via `pytest_plugins` in
`tests/conftest.py`; see `my-things-core/docs/CONVENTIONS.md`, "Shared test
fixtures"). Never copy fixture code into a conftest — only domain-specific
helpers live there.
