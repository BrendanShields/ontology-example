"""Evidence: what a test run showed, recorded as typed work items.

Evidence is derived, so it is never written by hand and never committed. It
lives in work/evidence/ (git-ignored), one file per Test, overwritten by each
run. CI collects it fresh and publishes it with the provenance bundle.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata

from . import frontmatter
from .workspace import WorkItem, Workspace

PASSED = "passed"


@dataclass
class Collection:
    returncode: int
    output: str
    ok: bool  # the run itself worked, whatever the tests said


def evidence_id(test_id: str) -> str:
    """EVD-0003 is the evidence of TST-0003."""
    return "EVD-" + test_id.split("-", 1)[1]


def covers(path: str, nodeid: str) -> bool:
    """True if a Test's path selects the node: a test, a class, a file or a parametrisation."""
    return nodeid == path or nodeid.startswith((path + "::", path + "["))


def record(
    ws: Workspace, outcomes: dict[str, str], deselected: frozenset[str] | set[str] = frozenset()
) -> list[str]:
    """Write one Evidence file for each Test whose pytest nodes all ran. Returns their ids.

    A Test whose nodes did not run, or ran only in part, gets no evidence from
    this run: saying nothing is better than a pass that was never observed.
    """
    written: list[str] = []
    commit = _head_commit(ws)
    run_url = _run_url()
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for test in ws.of_class("Test"):
        path = str(test.meta.get("path", ""))
        ran = {node: outcome for node, outcome in outcomes.items() if covers(path, node)}
        if not path or not ran or any(covers(path, node) for node in deselected):
            continue
        meta: dict = {
            "id": evidence_id(test.id),
            "of_test": test.id,
            "result": "pass" if all(o == PASSED for o in ran.values()) else "fail",
        }
        if commit:
            meta["commit_sha"] = commit
        if run_url:
            meta["run_url"] = run_url
        meta["recorded_at"] = now
        body = "\n".join(f"- `{node}`: {outcome}" for node, outcome in sorted(ran.items()))
        ws.cfg.evidence_dir.mkdir(parents=True, exist_ok=True)
        target = ws.cfg.evidence_dir / f"{meta['id']}.md"
        target.write_text(frontmatter.render(meta, body), encoding="utf-8")
        written.append(meta["id"])
    ws.reload()
    return written


def tests_for(ws: Workspace, scope: set[str] | None) -> list[WorkItem]:
    """The Test items to run for a scope (None: all of them)."""
    tests = ws.of_class("Test")
    if scope is None:
        return tests
    return [t for t in tests if t.id in scope or set(t.values("verifies")) & scope]


def collect(ws: Workspace, tests: list[WorkItem]) -> Collection:
    """Run the pytest nodes of the given Tests and record their evidence."""
    paths = sorted({str(t.meta["path"]) for t in tests if t.meta.get("path")})
    if not paths:
        return Collection(0, "no tests to run", ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--onto-evidence",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]
    if not _plugin_installed():
        command += ["-p", "onto.pytest_plugin"]
    done = subprocess.run(
        [*command, *paths], cwd=ws.cfg.root, capture_output=True, text=True, check=False
    )
    ws.reload()
    # 0: all passed, 1: some failed. Anything else means pytest could not run them.
    return Collection(
        done.returncode, (done.stdout + done.stderr).strip(), done.returncode in (0, 1)
    )


def _plugin_installed() -> bool:
    return any(ep.name == "onto" for ep in metadata.entry_points(group="pytest11"))


def _head_commit(ws: Workspace) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(ws.cfg.root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _run_url() -> str | None:
    """The CI run, if there is one: $ONTO_RUN_URL, or the GitHub Actions run."""
    explicit = os.environ.get("ONTO_RUN_URL")
    if explicit:
        return explicit
    server, repo, run = (
        os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    )
    if server and repo and run:
        return f"{server}/{repo}/actions/runs/{run}"
    return None
