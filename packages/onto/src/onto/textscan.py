"""Find denied synonyms in code and prose.

Text is split into words the way identifiers are read: `ScorecardRubric`,
`scorecard_rubric` and "scorecard rubric" all become (scorecard, rubric). A
denied synonym matches when its words appear next to each other, so `Rubric`
is found in `rubric_id`, `load_rubrics()` and "the rubric", but not inside
"rubricate".
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from .glossary import Term

# An acronym run (QA), a capitalised or lower-case word (Scorecard, mark), or digits.
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
# What may sit between two words of one name: nothing (camelCase), "_", "-" or a space.
_JOINER = re.compile(r"[ _\-]?\Z")
# Put this on a line to accept a denied synonym there, e.g. where code maps an
# external system's field name. Uses are reported, so they stay visible.
PRAGMA = "onto: allow-term"


def split_words(name: str) -> tuple[str, ...]:
    """'EvaluationForm' -> ('evaluation', 'form')."""
    return tuple(m.group(0).lower() for m in _WORD.finditer(name))


@dataclass(frozen=True)
class Hit:
    line: int
    column: int
    text: str  # what was written
    synonym: str  # the denied synonym it matches
    term: Term  # what to write instead
    suppressed: bool = False  # the line carries the allow pragma


class DeniedMatcher:
    def __init__(self, entries: list[tuple[str, Term]]):
        self._entries = [(split_words(synonym), synonym, term) for synonym, term in entries]
        self._first_words = {words[0] for words, _, _ in self._entries if words}

    def find(self, text: str) -> list[Hit]:
        if not self._entries:
            return []
        tokens = [(m.start(), m.end(), m.group(0).lower()) for m in _WORD.finditer(text)]
        line_starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
        lines = text.split("\n")
        hits: list[Hit] = []
        for index, (start, _, word) in enumerate(tokens):
            if _singular(word) not in self._first_words and word not in self._first_words:
                continue
            for words, synonym, term in self._entries:
                end = self._match_at(text, tokens, index, words)
                if end is None:
                    continue
                line = bisect.bisect_right(line_starts, start)
                hits.append(
                    Hit(
                        line=line,
                        column=start - line_starts[line - 1] + 1,
                        text=text[start:end],
                        synonym=synonym,
                        term=term,
                        suppressed=PRAGMA in lines[line - 1],
                    )
                )
        return hits

    @staticmethod
    def _match_at(text: str, tokens: list, index: int, words: tuple[str, ...]) -> int | None:
        """End offset if the denied words start at tokens[index], else None."""
        count = len(words)
        if not count or index + count > len(tokens):
            return None
        for offset, expected in enumerate(words):
            start, end, actual = tokens[index + offset]
            last = offset == count - 1
            if actual != expected and not (last and _singular(actual) == expected):
                return None
            if not last and not _JOINER.match(text[end : tokens[index + offset + 1][0]]):
                return None
        start, end = tokens[index][0], tokens[index + count - 1][1]
        if count == 1 and _hyphenated(text, start, end):
            # One word joined to others by hyphens is part of a different name:
            # "call-qa-agent" does not use the denied synonym "Agent".
            return None
        return end


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _hyphenated(text: str, start: int, end: int) -> bool:
    before = start >= 2 and text[start - 1] == "-" and text[start - 2].isalnum()
    after = end + 1 < len(text) and text[end] == "-" and text[end + 1].isalnum()
    return before or after
