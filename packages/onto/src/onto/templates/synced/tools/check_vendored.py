#!/usr/bin/env python3
"""Check the vendored pstack files against their provenance record.

    python tools/check_vendored.py            verify the pinned copies are untouched
    python tools/check_vendored.py --diff     also show how each adapted skill differs

The copies under .claude/pstack/upstream/ are what was taken from pstack at the
pinned commit, byte for byte. The skills under .claude/skills/ are adapted from
them. Keeping both means an upstream upgrade can be reviewed as two diffs: what
upstream changed, and what this repository changed on top.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / ".claude" / "pstack" / "provenance.json"


def main(argv: list[str]) -> int:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    problems = 0
    for entry in record["files"]:
        copy = ROOT / entry["copy"]
        if not copy.is_file():
            print(f"missing   {entry['copy']}")
            problems += 1
            continue
        if hashlib.sha256(copy.read_bytes()).hexdigest() != entry["sha256"]:
            print(f"changed   {entry['copy']} no longer matches the pinned upstream file")
            problems += 1
            continue
        adapted = entry.get("adapted_as")
        if adapted and not (ROOT / adapted).is_file():
            print(f"missing   {adapted}, recorded as adapted from {entry['upstream_path']}")
            problems += 1
        elif adapted and "--diff" in argv:
            diff = difflib.unified_diff(
                copy.read_text(encoding="utf-8").splitlines(keepends=True),
                (ROOT / adapted).read_text(encoding="utf-8").splitlines(keepends=True),
                fromfile=entry["copy"],
                tofile=adapted,
                n=1,
            )
            sys.stdout.writelines(diff)
    upstream = record["upstream"]
    print(
        f"{len(record['files'])} file(s) pinned to {upstream['repository']} @ "
        f"{upstream['commit'][:12]}: {'OK' if not problems else f'{problems} problem(s)'}"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
