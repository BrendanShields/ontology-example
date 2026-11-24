"""Violations: the one shape every gate reports in.

A violation is written to be acted on by whoever caused it, person or agent:
it says what was found, what would have been accepted and how to fix it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Violation:
    rule: str
    severity: str  # ERROR blocks, WARNING informs
    message: str
    file: str | None = None  # repository-relative
    line: int | None = None
    subject: str | None = None  # the work item or identifier concerned
    found: str | None = None
    allowed: tuple[str, ...] = ()  # the closed set that would have been accepted
    suggestions: tuple[str, ...] = ()  # nearest existing alternatives
    fix: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity == ERROR

    def location(self) -> str:
        if self.file and self.line:
            return f"{self.file}:{self.line}"
        return self.file or self.subject or "-"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["allowed"] = list(self.allowed)
        data["suggestions"] = list(self.suggestions)
        return {k: v for k, v in data.items() if v not in (None, [], ())}


def errors(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.blocking]


def warnings(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if not v.blocking]


def sort_key(v: Violation) -> tuple:
    return (v.severity != ERROR, v.file or "", v.line or 0, v.subject or "", v.rule, v.message)


def render_text(violations: list[Violation]) -> str:
    lines: list[str] = []
    for v in sorted(violations, key=sort_key):
        lines.append(f"{v.location()}: {v.severity}[{v.rule}] {v.message}")
        if v.allowed:
            lines.append(f"    allowed: {', '.join(v.allowed)}")
        if v.suggestions:
            lines.append(f"    did you mean: {', '.join(v.suggestions)}")
        if v.fix:
            lines.append(f"    fix: {v.fix}")
    return "\n".join(lines)


def render_json(violations: list[Violation]) -> str:
    return json.dumps([v.to_dict() for v in sorted(violations, key=sort_key)], indent=2)


def summary(violations: list[Violation]) -> str:
    return f"{len(errors(violations))} error(s), {len(warnings(violations))} warning(s)"
