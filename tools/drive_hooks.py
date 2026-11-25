#!/usr/bin/env python3
"""Drive every hook in .claude/settings.json the way Claude Code does, and time it.

    uv run python tools/drive_hooks.py              the table: decision, exit code, latency
    uv run python tools/drive_hooks.py --runs 9     median of nine runs per case

Each case is a JSON event in the shape the hooks reference documents, piped to
the command settings.json registers for that event and tool, in a scratch copy
of the ontology layer with its own git history. Nothing in this repository is
written. A case whose tool no matcher names is reported as "no hook": that is
what Claude Code would do with it too.

Exits 1 if a decision is not the expected one, or if a hook that runs on every
edit takes longer than --budget seconds.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from onto.testing import Scratch, scratch_repo

ROOT = Path(__file__).resolve().parents[1]
ONTO = '"$CLAUDE_PROJECT_DIR"/bin/onto'
PER_EDIT = ("PreToolUse", "PostToolUse")

GLOSSARY = "ontology/domains/call-qa.yaml"
GENERATED = "apps/call-qa-agent/src/call_qa_agent/generated.py"
DOMAIN = "apps/call-qa-agent/src/call_qa_agent/domain/example.py"
REQUEST = "work/OCR-0001.md"


@dataclass
class Case:
    name: str
    event: str
    expect: str
    tool: str = ""
    tool_input: Callable[[Scratch], dict] | None = None
    prepare: Callable[[Scratch], None] | None = None
    extra: dict | None = None


def edit(rel: str, old: str = "a", new: str = "b") -> Callable[[Scratch], dict]:
    return lambda repo: {"file_path": str(repo.root / rel), "old_string": old, "new_string": new}


def write(rel: str, content: str = "x = 1\n") -> Callable[[Scratch], dict]:
    return lambda repo: {"file_path": str(repo.root / rel), "content": content}


def request_in_progress(repo: Scratch) -> None:
    repo.item("OCR-0001", status="in_progress")


def append(rel: str) -> Callable[[Scratch], None]:
    """What a shell command does: change the file without any hook seeing it."""

    def run(repo: Scratch) -> None:
        with (repo.root / rel).open("a", encoding="utf-8") as stream:
            stream.write("\n# appended\n")

    return run


def symlink(repo: Scratch) -> None:
    (repo.root / "notes.yaml").symlink_to(repo.root / GLOSSARY)


def cases(repo: Scratch) -> list[Case]:
    same_file = (repo.root / "ONTO.TOML").exists()  # does this volume ignore letter case?
    pre = "PreToolUse"
    post = "PostToolUse"
    return [
        Case("a normal file", pre, "allow", "Edit", edit("README.md")),
        Case("a generated file", pre, "deny", "Edit", edit(GENERATED)),
        Case("a generated file, MultiEdit", pre, "deny", "MultiEdit", edit(GENERATED)),
        Case("evidence", pre, "deny", "Write", write("work/evidence/EVD-0001.md")),
        Case("an ontology source, no request", pre, "deny", "Edit", edit(GLOSSARY)),
        Case(
            "an ontology source, request in progress",
            pre,
            "ask",
            "Edit",
            edit(GLOSSARY),
            request_in_progress,
        ),
        Case(".claude/settings.json", pre, "ask", "Edit", edit(".claude/settings.json")),
        Case("onto.toml", pre, "ask", "Edit", edit("onto.toml")),
        Case("a CI workflow", pre, "ask", "Write", write(".github/workflows/ci.yml")),
        Case(
            "a request, status set to in_progress",
            pre,
            "ask",
            "Edit",
            edit(REQUEST, "status: draft", "status: in_progress"),
        ),
        Case("a request, title reworded", pre, "allow", "Edit", edit(REQUEST, "A request", "B")),
        Case(
            "a notebook path under evidence",
            pre,
            "deny",
            "NotebookEdit",
            lambda repo: {
                "notebook_path": str(repo.root / "work/evidence/notes.ipynb"),
                "new_source": "x = 1",
                "edit_mode": "insert",
            },
        ),
        Case("a symlink to an ontology source", pre, "deny", "Edit", edit("notes.yaml"), symlink),
        Case(
            "an ontology source in capitals",
            pre,
            "deny" if same_file else "allow",
            "Edit",
            edit("ONTOLOGY/Domains/Call-QA.yaml"),
        ),
        Case(
            "a shell command that edits an ontology source",
            pre,
            "no hook",
            "Bash",
            lambda repo: {"command": f"sed -i '' 's/a/b/' {repo.root / GLOSSARY}"},
        ),
        Case("a clean domain file", post, "allow", "Write", write(DOMAIN), write_file(DOMAIN)),
        Case(
            "a denied synonym in a domain file",
            post,
            "block",
            "Write",
            write(DOMAIN, "rubric = 1\n"),
            write_file(DOMAIN, "rubric = 1\n"),
        ),
        Case("a work item", post, "allow", "Edit", edit(REQUEST)),
        Case("a normal file", post, "allow", "Edit", edit("README.md")),
        Case("a subagent starts", "SubagentStart", "context", "implementer"),
        Case("nothing to answer for", "Stop", "allow"),
        Case("a work item changed, its test passes", "Stop", "allow", prepare=reword_test),
        Case(
            "an ontology source changed by a shell command",
            "Stop",
            "block",
            prepare=append(GLOSSARY),
        ),
        Case(
            "a generated file changed by a shell command",
            "Stop",
            "block",
            prepare=append(GENERATED),
        ),
        Case(
            "the same, after one forced continuation",
            "Stop",
            "error",
            prepare=append(GENERATED),
            extra={"stop_hook_active": True},
        ),
        Case("the session ends", "SessionEnd", "allow", extra={"reason": "other"}),
    ]


def write_file(rel: str, content: str = "x = 1\n") -> Callable[[Scratch], None]:
    def run(repo: Scratch) -> None:
        repo.write(rel, content)

    return run


def reword_test(repo: Scratch) -> None:
    repo.item("TST-0001", title="Reworded")


def build(folder: Path) -> Scratch:
    repo = scratch_repo(folder, ROOT)
    repo.write("README.md", "a\n")
    repo.item("REQ-0001", status="in_progress")
    repo.item("TASK-0001", status="in_progress")
    repo.item("TST-0001")
    repo.item("OCR-0001", status="draft")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo


def git(repo: Scratch, *args: str) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(repo.root), *identity, *args], check=True)


def commands(settings: dict, case: Case) -> list[str]:
    """The commands Claude Code would run for the case: the matcher is a list of exact names."""
    found = []
    for group in settings.get("hooks", {}).get(case.event, []):
        matcher = group.get("matcher", "")
        if matcher in ("", "*") or case.tool in matcher.split("|"):
            found += [hook["command"] for hook in group["hooks"] if hook.get("type") == "command"]
    return found


def payload(repo: Scratch, case: Case) -> dict:
    event = {
        "session_id": "drive-hooks",
        "transcript_path": str(repo.root / "transcript.jsonl"),
        "cwd": str(repo.root),
        "permission_mode": "default",
        "hook_event_name": case.event,
    }
    if case.event in PER_EDIT:
        event |= {
            "tool_name": case.tool,
            "tool_input": case.tool_input(repo),
            "tool_use_id": "toolu_drive_hooks",
        }
        if case.event == "PostToolUse":
            event["tool_response"] = {"success": True}
    elif case.event == "SubagentStart":
        event |= {"agent_id": "agent-drive-hooks", "agent_type": case.tool}
    elif case.event == "Stop":
        event["stop_hook_active"] = False
    return event | (case.extra or {})


def answer(done: subprocess.CompletedProcess) -> str:
    """What Claude Code makes of the exit code and the output."""
    if done.returncode == 2:
        return "block"
    if done.returncode != 0:
        return "error"
    try:
        specific = json.loads(done.stdout).get("hookSpecificOutput", {})
    except ValueError:
        return "allow"
    return specific.get("permissionDecision") or ("context" if specific else "allow")


def drive(repo: Scratch, settings: dict, case: Case, runs: int) -> tuple[str, str, float | None]:
    """(answer, exit codes, median seconds) for one case, restoring the scratch copy after it."""
    hooks = commands(settings, case)
    if not hooks:
        return "no hook", "-", None
    if case.prepare:
        case.prepare(repo)
    env = {k: v for k, v in os.environ.items() if k not in ("ONTO_ROOT", "ONTO_TASK")}
    env |= {"CLAUDE_PROJECT_DIR": str(repo.root)}
    stdin = json.dumps(payload(repo, case))
    answers, codes, seconds = [], [], []
    try:
        for command in hooks:
            # The scratch copy has no bin/onto of its own: run this repository's, on the copy.
            argv = command.replace(ONTO, f'"{ROOT / "bin/onto"}"')
            timings = []
            for _ in range(runs):
                started = time.perf_counter()
                done = subprocess.run(
                    argv, shell=True, input=stdin, capture_output=True, text=True, env=env
                )
                timings.append(time.perf_counter() - started)
            answers.append(answer(done))
            codes.append(str(done.returncode))
            seconds.append(statistics.median(timings))
    finally:
        git(repo, "checkout", "-q", "--", ".")
        git(repo, "clean", "-qfd")
    worst = next((a for a in ("block", "error", "ask", "context") if a in answers), "allow")
    return worst, ",".join(codes), sum(seconds)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5, help="runs per case; the median is shown")
    parser.add_argument(
        "--budget", type=float, default=0.5, help="seconds a per-edit hook may take"
    )
    args = parser.parse_args(argv)

    settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    failed = False
    with tempfile.TemporaryDirectory() as folder:
        repo = build(Path(folder).resolve())
        print(f"{'event':13} {'tool':12} {'case':46} {'answer':8} {'exit':4} {'median':>7}")
        for case in cases(repo):
            got, codes, seconds = drive(repo, settings, case, args.runs)
            # A PreToolUse block is how the guard says deny.
            expected = "block" if case.expect == "deny" else case.expect
            notes = []
            if got != expected:
                notes.append(f"expected {case.expect}")
            if seconds is not None and case.event in PER_EDIT and seconds > args.budget:
                notes.append(f"over the {args.budget}s budget")
            failed = failed or bool(notes)
            shown = "deny" if got == "block" and case.event == "PreToolUse" else got
            took = f"{seconds:6.2f}s" if seconds is not None else "      -"
            line = f"{case.event:13} {case.tool or '-':12} {case.name:46} {shown:8} {codes:4}"
            print(f"{line} {took}" + (f"  <- {'; '.join(notes)}" if notes else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
