"""Competency questions: the questions the ontology exists to answer, as SPARQL files.

Each ontology/cq/*.rq file starts with a comment header:

    # CQ-03: Which decisions about a term are still in force?
    # bind: term          <- variables the caller supplies (optional)
    # expect: none        <- any row is a problem (optional)

`onto cq` runs them from the command line; ontology/cq/test_competency_questions.py
pins their answers on this repository's data, so a change to the ontology that
breaks a question fails the build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .graph import WorkGraph

_TITLE = re.compile(r"^#\s*(CQ-\d+)\s*:\s*(.+)$")
_FIELD = re.compile(r"^#\s*(bind|expect)\s*:\s*(.*)$", re.I)


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    path: Path
    sparql: str
    binds: tuple[str, ...] = ()
    expect_none: bool = False


def load(cfg: Config) -> dict[str, Question]:
    questions: dict[str, Question] = {}
    for path in sorted(cfg.cq_dir.glob("*.rq")):
        text = path.read_text(encoding="utf-8")
        identifier = "-".join(path.stem.split("-")[:2])
        question, binds, expect_none = path.stem, (), False
        for line in text.splitlines():
            if not line.startswith("#"):
                break
            if title := _TITLE.match(line):
                identifier, question = title.group(1), title.group(2).strip()
            elif found := _FIELD.match(line):
                key, value = found.group(1).lower(), found.group(2).strip()
                if key == "bind":
                    binds = tuple(v.strip() for v in value.split(",") if v.strip())
                else:
                    expect_none = value.lower() == "none"
        questions[identifier] = Question(identifier, question, path, text, binds, expect_none)
    return questions


def run(graph: WorkGraph, question: Question, **bindings: str) -> list[dict[str, str]]:
    missing = [name for name in question.binds if name not in bindings]
    if missing:
        raise ValueError(f"{question.id} needs a value for: {', '.join(missing)}")
    return graph.select(question.sparql, **bindings)


def table(rows: list[dict[str, str]]) -> str:
    """Rows as an aligned text table."""
    if not rows:
        return "(no rows)"
    columns = list(dict.fromkeys(key for row in rows for key in row))
    widths = {c: max(len(c), *(len(row.get(c, "")) for row in rows)) for c in columns}
    lines = ["  ".join(c.ljust(widths[c]) for c in columns).rstrip()]
    lines.append("  ".join("-" * widths[c] for c in columns))
    lines += ["  ".join(row.get(c, "").ljust(widths[c]) for c in columns).rstrip() for row in rows]
    return "\n".join(lines)
