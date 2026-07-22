from __future__ import annotations

import json
import re

from mythings.github import GitHub, Issue, Runner
from mythings.ledger import Ledger, LedgerEntry

RESEARCH_KIND = "research"


def read_objective(runner: Runner, repo: str, number: int) -> Issue:
    """Fetch a single issue by number -- the objective my-architect decomposes.

    `GitHub.list_issues` only lists issues matching a filter, with no
    guarantee a specific number is within its `limit`, so this calls `gh
    issue view` directly rather than listing and searching.
    """
    raw = json.loads(
        runner(
            [
                "issue",
                "view",
                str(number),
                "--repo",
                repo,
                "--json",
                "number,title,body,url,labels",
            ]
        )
    )
    return Issue(
        number=raw["number"],
        title=raw["title"],
        body=raw.get("body", "") or "",
        url=raw["url"],
        labels=[lbl["name"] for lbl in raw.get("labels", [])],
    )


def read_open_issues(runner: Runner, repo: str) -> list[str]:
    """Return the titles of `repo`'s currently open issues.

    Used to steer the Engine away from proposing duplicate backlog items.
    """
    return [issue.title for issue in GitHub(repo, runner=runner).list_issues()]


def read_research(ledger: Ledger, objective_title: str) -> list[LedgerEntry]:
    """Return `kind=research` ledger entries whose topic word-overlaps `objective_title`.

    Reads the shared, on-disk `Ledger` only — the same read-only seam `my-todo`
    uses to read another tool's entries — so my-architect never imports
    my-researcher as a package.
    """
    objective_words = _words(objective_title)
    if not objective_words:
        return []
    matches = []
    for entry in ledger.read(kind=RESEARCH_KIND):
        topic = str(entry.data.get("topic", entry.detail))
        if _words(topic) & objective_words:
            matches.append(entry)
    return matches


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))
