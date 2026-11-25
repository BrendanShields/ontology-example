"""The ledger: an append-only file of the Reviews and AuditRecords of Evaluations.

This is the only place the app keeps anything (DEC-0011). The domain layer
decides whether a change is permitted (`domain/publication.py`); this module
reads the file, asks, and appends one line for what was permitted. A line is a
JSON object, of one of four shapes:

    {"audit_record": {...}, "disposition": "...", "sha256": "..."}   an Evaluation was staged
    {"review": {...}}                                                 a Review CONFIRMED it
    {"review": {...}, "audit_record": {...}}                          a Review OVERTURNED it
    {"audit_record": {...}}                                           it was published

A line holds identifiers, states and times. It never holds the text of an
Utterance, a rationale or a score (REQ-0021, DEC-0009). The Evaluation itself
is not kept: `sha256` is a digest of it, so that the Evaluation a Review was
made of can be told from another of the same Call against the same Scorecard
(DEC-0012).

A command given again finds its effect already there and appends nothing
(REQ-0024). That holds for two commands given at once as well: a command that
may append holds an exclusive lock on the file from before it reads until
after it has appended, so the second one reads what the first one wrote.

Reading the file runs every line through the domain layer again, so a line
that records a change the state machine does not permit fails the read with
`Corrupt`. So does a last line with no end, which is what a write that was cut
short leaves: appending after it would join two lines into one. One such line
stops every command on the file, for every Call, until a person has removed
it. Nothing here repairs a ledger.

What this is not. That read checks that the lines agree with the rules, not
who wrote them: a line that was removed is not noticed, and a staging line
with another disposition reads as true. The lock is `flock`, which holds
between processes on one machine and may not hold on a network file system.
A reviewer is whatever identifier the caller gives, as long as it is not the
system's own. It is a record, not an access control.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .domain import publication
from .generated import (
    AuditRecord,
    Disposition,
    Evaluation,
    PublicationState,
    Review,
    ReviewOutcome,
)

SYSTEM = "call-qa-agent"  # the actor of a change no person made
_SHAPES = (
    {"audit_record", "disposition", "sha256"},
    {"review"},
    {"review", "audit_record"},
    {"audit_record"},
)


class Corrupt(Exception):
    """The ledger file does not hold what this module writes. Names the line, quotes nothing."""


@dataclass(frozen=True)
class Entry:
    """What the ledger holds on the Evaluation of one Call against one Scorecard."""

    sha256: str
    disposition: Disposition
    reviews: tuple[Review, ...] = ()
    records: tuple[AuditRecord, ...] = ()

    @property
    def publication_state(self) -> PublicationState:
        return publication.publication_state(self.records)


def digest(evaluation: Evaluation) -> str:
    """What tells one Evaluation from another. Nothing of the Evaluation can be read from it."""
    whole = json.dumps(evaluation.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(whole.encode("utf-8")).hexdigest()


def is_identifier(value: str) -> bool:
    return bool(value) and not any(character.isspace() for character in value)


def _person(reviewer: str) -> bool:
    """Whether a Review can name this reviewer: an identifier, and not the system's own."""
    return is_identifier(reviewer) and reviewer != SYSTEM


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class Ledger:
    """The ledger in one file. Every command reads it first: nothing is held between them."""

    def __init__(self, path: Path, now: Callable[[], datetime] = _now) -> None:
        self.path = path
        self.now = now

    def entries(self) -> dict[tuple[str, str], Entry]:
        """Every Evaluation on the ledger, by Call and Scorecard. Raises Corrupt or OSError."""
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as lines:
            return self._read(lines)

    def entry(self, call: str, scorecard: str) -> Entry | None:
        return self.entries().get((call, scorecard))

    def stage(self, evaluation: Evaluation) -> bool:
        """Stage an Evaluation. False if this very Evaluation is on the ledger already.

        Raises `publication.Refused` if another Evaluation of the same Call against the
        same Scorecard is (DEC-0012).
        """
        with self._alone(create=True) as (entries, ledger):
            found = entries.get((evaluation.call, evaluation.scorecard))
            if found is not None and found.sha256 == digest(evaluation):
                return False
            record = publication.stage(
                evaluation, found.records if found else (), actor=SYSTEM, recorded_at=self.now()
            )
            _append(
                ledger,
                {
                    "audit_record": _plain(record),
                    "disposition": Disposition(evaluation.disposition).value,
                    "sha256": digest(evaluation),
                },
            )
            return True

    def review(self, call: str, scorecard: str, reviewer: str, outcome: ReviewOutcome) -> bool:
        """Record a Review. False if this reviewer's Review with this outcome is recorded already.

        Raises `publication.Refused` if the Evaluation is not one to review, or the reviewer
        is not one a Review can name.
        """
        if not _person(reviewer):
            # The actor of a WITHHELD AuditRecord is the reviewer. Were it the system's own
            # name, the trail could not tell a person's permit from the system's.
            raise publication.Refused(
                "a reviewer is an identifier with no spaces, "
                f"and not {SYSTEM}, which is the system's own"
            )
        with self._alone() as (entries, ledger):
            found = _staged(entries, call, scorecard)
            if any(
                (made.reviewer, made.review_outcome) == (reviewer, outcome.value)
                for made in found.reviews
            ):
                return False
            made = Review(
                call=call,
                scorecard=scorecard,
                reviewer=reviewer,
                review_outcome=outcome,
                reviewed_at=self.now(),
            )
            record = publication.review(made, found.disposition, found.records)
            line = {"review": _plain(made)}
            if record is not None:
                line["audit_record"] = _plain(record)
            _append(ledger, line)
            return True

    def publish(self, call: str, scorecard: str) -> bool:
        """Publish an Evaluation. False if it is PUBLISHED already.

        Raises `publication.Refused`, with a REVIEW_REQUIRED Rejection when a Review is
        what is missing.
        """
        with self._alone() as (entries, ledger):
            found = _staged(entries, call, scorecard)
            if found.publication_state is PublicationState.PUBLISHED:
                return False
            record = publication.publish(
                call,
                scorecard,
                found.disposition,
                found.reviews,
                found.records,
                actor=SYSTEM,
                recorded_at=self.now(),
            )
            _append(ledger, {"audit_record": _plain(record)})
            return True

    @contextmanager
    def _alone(
        self, create: bool = False
    ) -> Iterator[tuple[dict[tuple[str, str], Entry], TextIO | None]]:
        """What the ledger holds and the file to append to, with no other writer until the exit.

        Without the lock two commands given at once both read the ledger as it was, and
        both append. A ledger that is not there holds nothing, and only staging creates it.
        """
        flags = os.O_RDWR | os.O_APPEND | (os.O_CREAT if create else 0)
        try:
            descriptor = os.open(self.path, flags, 0o644)
        except FileNotFoundError:
            if create:
                raise
            yield {}, None
            return
        with os.fdopen(descriptor, "a+", encoding="utf-8") as ledger:
            fcntl.flock(ledger, fcntl.LOCK_EX)  # let go of when the file is closed
            ledger.seek(0)
            yield self._read(ledger), ledger

    def _read(self, lines: Iterable[str]) -> dict[tuple[str, str], Entry]:
        entries: dict[tuple[str, str], Entry] = {}
        for number, text in enumerate(lines, start=1):
            if not text.endswith("\n"):
                raise Corrupt(
                    f"{self.path}: line {number} has no end: the write of it was cut short"
                )
            if not text.strip():
                continue  # an empty line records nothing
            try:
                _apply(entries, json.loads(text))
            except (ValueError, KeyError, TypeError):
                # A line that is not JSON, not a valid Review or AuditRecord, or not a
                # change the domain layer permits. The error could echo the line: dropped.
                raise Corrupt(
                    f"{self.path}: line {number} is not one this ledger could hold"
                ) from None
        return entries


def _staged(entries: dict[tuple[str, str], Entry], call: str, scorecard: str) -> Entry:
    found = entries.get((call, scorecard))
    if found is None:
        raise publication.Refused(f"no Evaluation of {call} against {scorecard} is staged")
    return found


def _append(ledger: TextIO, line: dict) -> None:
    ledger.write(json.dumps(line, sort_keys=True) + "\n")  # one write of one whole line
    ledger.flush()


def _plain(model: Review | AuditRecord) -> dict:
    return model.model_dump(mode="json")


def _apply(entries: dict[tuple[str, str], Entry], line: dict) -> None:
    """Fold one line into what is known, through the domain layer. Raises if it does not fit."""
    if not isinstance(line, dict) or set(line) not in _SHAPES:
        raise ValueError("not a line of the ledger")
    record = AuditRecord.model_validate(line["audit_record"]) if "audit_record" in line else None
    made = Review.model_validate(line["review"]) if "review" in line else None
    if made is not None and not _person(made.reviewer):
        raise ValueError("not a reviewer a Review can name")

    if "disposition" in line:
        key = (record.call, record.scorecard)
        staged = PublicationState(record.publication_state) is PublicationState.STAGED
        if key in entries or not staged or not isinstance(line["sha256"], str):
            raise ValueError("not the staging of an Evaluation that is not on the ledger yet")
        entries[key] = Entry(line["sha256"], Disposition(line["disposition"]), records=(record,))
        return

    key = (made.call, made.scorecard) if made is not None else (record.call, record.scorecard)
    found = entries[key]
    if made is not None:
        expected = publication.review(made, found.disposition, found.records)
        found = replace(found, reviews=(*found.reviews, made))
    else:
        expected = publication.publish(
            *key,
            found.disposition,
            found.reviews,
            found.records,
            actor=record.actor,
            recorded_at=record.recorded_at,
        )
    if expected != record:
        raise ValueError("the AuditRecord is not the one this change gives")
    entries[key] = replace(found, records=(*found.records, record)) if record else found
