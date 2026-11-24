"""EARS: the Easy Approach to Requirements Syntax.

A requirement is one sentence in one of five shapes. The check is deliberately
shallow: it recognises the shape, it does not judge the content.
"""

from __future__ import annotations

import re

_SHALL = r"the\s.+?\sshall\s\S.*"

PATTERNS: dict[str, tuple[str, re.Pattern[str]]] = {
    "ubiquitous": (
        "The <system> shall <response>.",
        re.compile(r"^The\s.+?\sshall\s\S.*$", re.S),
    ),
    "event-driven": (
        "When <trigger>, the <system> shall <response>.",
        re.compile(rf"^When\s.+?,\s+{_SHALL}$", re.S),
    ),
    "state-driven": (
        "While <state>, the <system> shall <response>.",
        re.compile(rf"^While\s.+?,\s+(?:when\s.+?,\s+)?{_SHALL}$", re.S),
    ),
    "unwanted-behaviour": (
        "If <trigger>, then the <system> shall <response>.",
        re.compile(rf"^If\s.+?,\s+then\s+{_SHALL}$", re.S),
    ),
    "optional-feature": (
        "Where <feature>, the <system> shall <response>.",
        re.compile(rf"^Where\s.+?,\s+{_SHALL}$", re.S),
    ),
}

TEMPLATES = tuple(template for template, _ in PATTERNS.values())

_BACKTICKED = re.compile(r"`([^`\s]+)`")


def classify(text: str) -> str | None:
    """The name of the EARS pattern the sentence follows, or None."""
    sentence = " ".join(text.split())
    for name, (_, pattern) in PATTERNS.items():
        if pattern.match(sentence):
            return name
    return None


def bound_terms(text: str) -> list[str]:
    """The names written in backticks: the terms the sentence binds to the glossary."""
    return list(dict.fromkeys(_BACKTICKED.findall(text)))
