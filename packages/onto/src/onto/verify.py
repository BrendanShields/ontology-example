"""`onto verify`: run every gate and leave one index of what they showed.

The index (verify.json, next to the provenance bundles) is what a reviewer or
an auditor opens first: which commit, which ontology, which gates held, which
requirement is verified by which evidence. It is written whether or not the
gates hold, so a failure can be inspected.

Two rules shape it:

* It is built from typed fields: ids, counts, statuses, rule names, paths and
  hashes. Never from what a gate printed, a violation's message or an
  exception's text, because any of those can quote an Utterance or a Finding.
* Everything that differs between two runs on the same tree (the commit, the
  times) sits under `varies_per_run`. The rest is the same on every rerun.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .config import DEFAULT_PROV, Config, ConfigError, find_root
from .gates import base_commit, branch_scope
from .workspace import Workspace

INDEX = "verify.json"
PASSED, FAILED, ERRORED = "passed", "failed", "error"
RESULTS = ("pass", "fail")
SEVERITIES = ("error", "warning")
VERDICTS = ("untested", "failing", "no evidence", "verified")
RULE_NAME = re.compile(r"[A-Za-z][\w:.-]*")


def run(scope: str, out_dir: Path | None = None) -> int:
    """Run the gates in order, write the index, say where it is. 1 if a gate did not hold."""
    if out_dir is not None and out_dir.exists() and not out_dir.is_dir():
        raise ValueError(
            f"--out {out_dir} is a file: name the folder the index and the bundles go in"
        )
    try:
        cfg = Workspace.at().cfg
        sources = _sources(cfg)
    except Exception as exc:
        _retract(scope, out_dir, exc)
        raise
    out_dir = (out_dir or cfg.prov_dir).resolve()
    index: dict = {
        "schema_version": 1,
        "ok": False,
        "scope": scope,
        "scope_applied": scope,
        "base_ref": cfg.base_ref,
        "ontology_sources": sources,
        "generated_files": [],
        "gates": [],
        "trace": None,
        "evidence": [],
        "provenance_bundles": [],
        "varies_per_run": {"commit": _git(cfg, "rev-parse", "HEAD"), "started_at": _now()},
    }
    try:
        _run_gates(cfg, scope, out_dir, index)
        # Only a run that reached its end can say the gates hold.
        index["ok"] = all(gate["status"] == PASSED for gate in index["gates"])
    finally:
        index["varies_per_run"]["finished_at"] = _now()
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / INDEX
        target.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    for gate in index["gates"]:
        counts = ", ".join(
            f"{value} {key}" for key, value in gate["counts"].items() if key != "by_rule"
        )
        print(
            f"{gate['status']:8} {gate['command']:36} {counts or gate.get('reason', '')}".rstrip()
        )
    if index["scope_applied"] != scope:
        print(f"onto verify: no base branch found for {cfg.base_ref}: every item was checked")
    held = (
        "every gate holds" if index["ok"] else "a gate does not hold: rerun its command to see why"
    )
    print(f"onto verify: {held}. Index: {cfg.rel(target)}")
    return 0 if index["ok"] else 1


def _retract(scope: str, out_dir: Path | None, exc: Exception) -> None:
    """Without a configuration no gate ran: an index from an earlier run must not go on
    saying that they hold. With no `--out`, only an index that is already there is rewritten,
    because where a new one belongs is one of the things that could not be read."""
    if out_dir is None:
        try:
            out_dir = find_root() / DEFAULT_PROV
        except ConfigError:
            return
        if not (out_dir / INDEX).is_file():
            return
    index = {
        "schema_version": 1,
        "ok": False,
        "scope": scope,
        "reason": type(exc).__name__,
        "gates": [],
        "varies_per_run": {"started_at": _now()},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / INDEX).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def _run_gates(cfg: Config, scope: str, out_dir: Path, index: dict) -> None:
    varies = index["varies_per_run"]
    varies["base_commit"] = base_commit(cfg)
    # A branch whose base cannot be found answers for everything, and the index says so.
    if _scope(Workspace.at(cfg.root), scope) is None:
        index["scope_applied"] = "all"
    varies["uncommitted_files"] = len((_git(cfg, "status", "--porcelain") or "").splitlines())
    seconds: dict[str, float] = varies.setdefault("seconds", {})

    def gate(name: str, measure, *options: str) -> None:
        """Record one gate. `measure` returns (exit status, counts) and may raise."""
        entry = {"name": name, "command": " ".join(("onto", name, *options))}
        started = time.perf_counter()
        try:
            code, counts = measure()
            entry |= {"exit_status": code, "status": PASSED if code == 0 else FAILED}
        except (Exception, SystemExit) as exc:
            # The class says what kind of failure it was. The text could quote anything.
            counts = {}
            entry |= {"exit_status": None, "status": ERRORED, "reason": type(exc).__name__}
        entry["counts"] = counts
        seconds[name] = round(time.perf_counter() - started, 2)
        index["gates"].append(entry)

    def gen_check() -> tuple[int, dict]:
        from . import gen

        results = gen.generate(cfg, check=True)
        sources = cfg.generated_files()
        index["generated_files"] = [
            {
                "path": r.path,
                "source": sources.get(r.path),
                "sha256": _sha256(cfg.root / r.path),
                "status": r.status,
            }
            for r in sorted(results, key=lambda r: r.path)
        ]
        drift = sum(1 for r in results if r.status == "drift")
        return (1 if drift else 0), {"files": len(results), "drift": drift}

    def violations_of(argv: list[str]):
        def measure() -> tuple[int, dict]:
            code, printed = _onto(argv)
            return code, _violation_counts(_json(printed))

        return measure

    def collect() -> tuple[int, dict]:
        code, _ = _onto(["evidence", "collect", "--scope", scope])
        ws = Workspace.at(cfg.root)
        in_scope = _scope(ws, scope)
        found = [e for e in ws.of_class("Evidence") if in_scope is None or e.id in in_scope]
        index["evidence"] = [
            {
                "id": e.id,
                "of_test": _id(ws, e.meta.get("of_test")),
                "result": _one_of(e.meta.get("result"), RESULTS),
            }
            for e in sorted(found, key=lambda e: e.id)
        ]
        varies["evidence"] = {
            e.id: {
                "recorded_at": _timestamp(e.meta.get("recorded_at")),
                "commit_sha": _commit(e.meta.get("commit_sha")),
            }
            for e in sorted(found, key=lambda e: e.id)
        }
        results = Counter(entry["result"] for entry in index["evidence"])
        return code, {"evidence": len(found), "pass": results["pass"], "fail": results["fail"]}

    def trace() -> tuple[int, dict]:
        code, printed = _onto(["trace", "--scope", scope, "--format", "json"])
        parsed = _json(printed)
        if not isinstance(parsed, dict):  # nothing in scope on this branch
            return code, {"in_scope": 0} if code == 0 else {}
        ws = Workspace.at(cfg.root)
        index["trace"] = {
            "coverage": {k: v for k, v in parsed.get("coverage", {}).items() if isinstance(v, int)},
            "requirements": [_requirement(ws, row) for row in parsed.get("requirements", [])],
            "violations": [_violation(ws, v) for v in parsed.get("violations", [])],
        }
        return code, index["trace"]["coverage"] | _violation_counts(parsed.get("violations"))

    def emit() -> tuple[int, dict]:
        # `prov emit` prints the path of each bundle it wrote, one per line.
        code, printed = _onto(["prov", "emit", "--scope", scope, "--out", str(out_dir)])
        bundles = sorted(
            line
            for line in printed.splitlines()
            if line.endswith(".ttl") and (cfg.root / line).is_file()
        )
        index["provenance_bundles"] = bundles
        return code, {"bundles": len(bundles)}

    gate("gen --check", gen_check)
    for name in ("validate", "check-terms"):
        gate(name, violations_of([name, "--format", "json"]))
    gate("evidence collect", collect, "--scope", scope)
    gate("trace", trace, "--scope", scope)
    # `onto rules` has no scope: a bound rule holds for the whole context or not at all.
    gate("rules", violations_of(["rules", "--format", "json"]), "--format", "json")
    gate("prov emit", emit, "--scope", scope)


# --- running a command of this CLI -----------------------------------------------


def _onto(argv: list[str]) -> tuple[int, str]:
    """Run an onto command in this process, as the CLI would. Its output is held back."""
    from . import cli

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return code, out.getvalue()


def _json(printed: str):
    try:
        return json.loads(printed)
    except ValueError:
        return None


# --- typed fields only -----------------------------------------------------------


def _violation_counts(parsed) -> dict:
    """Errors and warnings of a gate's JSON report, and how many of each rule."""
    if isinstance(parsed, dict):
        parsed = parsed.get("violations", parsed.get("problems"))  # `onto rules` says problems
    if not isinstance(parsed, list):
        return {}
    found = [v for v in parsed if isinstance(v, dict)]
    counts: dict = {
        "errors": sum(1 for v in found if v.get("severity") == "error"),
        "warnings": sum(1 for v in found if v.get("severity") == "warning"),
    }
    by_rule = Counter(_rule(v.get("rule")) for v in found)
    if by_rule:
        counts["by_rule"] = dict(sorted(by_rule.items()))
    return counts


def _violation(ws: Workspace, violation: dict) -> dict:
    file, line = violation.get("file"), violation.get("line")
    kept = {
        "rule": _rule(violation.get("rule")),
        "severity": _one_of(violation.get("severity"), SEVERITIES),
        "subject": _id(ws, violation.get("subject")),
        "file": file if isinstance(file, str) and (ws.cfg.root / file).is_file() else None,
        "line": line if isinstance(line, int) else None,
    }
    return {key: value for key, value in kept.items() if value is not None}


def _requirement(ws: Workspace, row: dict) -> dict:
    """A row of the trace matrix, each value checked against the closed set it comes from."""
    enum = ws.schema.enum_values
    return {
        "id": _id(ws, row.get("id")),
        "status": _one_of(row.get("status"), enum("StatusEnum")),
        "risk_tier": _one_of(row.get("risk_tier"), enum("RiskTierEnum")),
        "tasks": sorted(t for t in row.get("tasks", ()) if _id(ws, t)),
        "tests": {
            test: _one_of(result, RESULTS)
            for test, result in sorted(row.get("tests", {}).items())
            if _id(ws, test)
        },
        "verdict": _one_of(row.get("verdict"), VERDICTS),
    }


def _id(ws: Workspace, value) -> str | None:
    """The value if it is the id of a work item, else nothing: an id field is not free text."""
    return value if isinstance(value, str) and value in ws.by_id else None


def _one_of(value, allowed) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _rule(value) -> str:
    return value if isinstance(value, str) and RULE_NAME.fullmatch(value) else "unnamed"


def _timestamp(value) -> str | None:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return str(value)


def _commit(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) else None


def _scope(ws: Workspace, scope: str) -> set[str] | None:
    return None if scope == "all" else branch_scope(ws)


# --- files and git -----------------------------------------------------------------


def _sources(cfg: Config) -> list[dict]:
    paths = {cfg.workflow_schema, *cfg.gate_shapes, *(ctx.schema for ctx in cfg.contexts.values())}
    return [{"path": cfg.rel(p), "sha256": _sha256(p)} for p in sorted(paths, key=cfg.rel)]


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _git(cfg: Config, *args: str) -> str | None:
    done = subprocess.run(
        ["git", "-C", str(cfg.root), *args], capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 else None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
