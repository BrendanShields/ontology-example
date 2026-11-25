"""Acceptance tests for the ledger and its commands: REQ-0021, REQ-0023, REQ-0024.

The Evaluations are staged from the two example replays under data/, through
`call-qa` itself. What a command printed is read for identifiers, states and
exit codes only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from call_qa_agent import cli
from call_qa_agent.domain.publication import Refused
from call_qa_agent.generated import AuditRecord, PublicationState, Review, ReviewOutcome
from call_qa_agent.ledger import SYSTEM, Corrupt, Ledger
from pydantic import ValidationError

from .test_publication import CRITICAL_FAILURE, NOTHING_APPLIED, STANDS

DATA = Path(__file__).resolve().parents[2] / "data"
CARD = "retail-banking-v1"
STANDING = "CALL-0001"  # its Evaluation is FINAL
UNDER_REVIEW = "CALL-0002"  # its Evaluation is NEEDS_REVIEW
KEY = (CRITICAL_FAILURE.call, CRITICAL_FAILURE.scorecard)


def evaluate(call: str, *more: str) -> int:
    return cli.main(
        [
            "evaluate",
            str(DATA / "calls" / f"{call}.yaml"),
            "--scorecard",
            str(DATA / "scorecards" / f"{CARD}.yaml"),
            "--replay",
            str(DATA / "replays" / f"{call}.json"),
            *more,
        ]
    )


@pytest.fixture
def path(tmp_path) -> Path:
    return tmp_path / "ledger.jsonl"


@pytest.fixture
def run(path, capsys):
    """Run a ledger command of `call-qa`. Returns (exit code, stdout, stderr).

    What `evaluate` prints is an Evaluation with its rationales. It is dropped
    here, so that no failing assertion can show it.
    """

    def command(name: str, call: str, *more: str) -> tuple[int, str, str]:
        if name == "stage":
            code = evaluate(call, "--stage", str(path), *more)
        else:
            code = cli.main([name, str(path), call, CARD, *more])
        captured = capsys.readouterr()
        return code, "" if name == "stage" else captured.out, captured.err

    return command


def confirm(reviewer: str = "QA-0007") -> tuple[str, ...]:
    return ("--reviewer", reviewer, "--outcome", "CONFIRMED")


def overturn(reviewer: str = "QA-0007") -> tuple[str, ...]:
    return ("--reviewer", reviewer, "--outcome", "OVERTURNED")


def states(path: Path) -> list[tuple[str, str, str]]:
    """(Call, PublicationState entered, actor) of every AuditRecord in the file, in order."""
    held = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records = [line["audit_record"] for line in held if "audit_record" in line]
    return [(r["call"], r["publication_state"], r["actor"]) for r in records]


class TestCommands:
    """The path of an Evaluation through `call-qa`, and what each exit code means."""

    def test_evaluate_writes_nothing_unless_asked_to_stage(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        code = evaluate(UNDER_REVIEW)
        capsys.readouterr()  # the Evaluation, with its rationales: not for a failure message

        assert code == 0
        assert list(tmp_path.iterdir()) == []

    def test_an_evaluation_that_stands_is_published_without_a_person(self, run, path):
        assert run("stage", STANDING)[0] == 0
        assert run("publish", STANDING)[0] == 0

        assert states(path) == [(STANDING, "STAGED", SYSTEM), (STANDING, "PUBLISHED", SYSTEM)]

    def test_an_evaluation_under_review_waits_for_a_person(self, run, path):
        code, _, staged = run("stage", UNDER_REVIEW)
        assert code == 0 and "needs a Review" in staged

        code, _, refused = run("publish", UNDER_REVIEW)
        assert code == 1  # refused, not failed
        assert json.loads(refused[refused.index("{") :])["rejections"][0]["rejection_rule"] == (
            "REVIEW_REQUIRED"
        )
        assert states(path) == [(UNDER_REVIEW, "STAGED", SYSTEM)]

        assert run("review", UNDER_REVIEW, *confirm())[0] == 0
        assert run("publish", UNDER_REVIEW)[0] == 0
        assert states(path) == [
            (UNDER_REVIEW, "STAGED", SYSTEM),
            (UNDER_REVIEW, "PUBLISHED", SYSTEM),
        ]

    def test_an_overturned_evaluation_is_withheld_for_good(self, run, path):
        run("stage", UNDER_REVIEW)
        assert run("review", UNDER_REVIEW, *overturn())[0] == 0
        withheld = path.read_text(encoding="utf-8")

        assert run("publish", UNDER_REVIEW)[0] == 1
        assert run("review", UNDER_REVIEW, *confirm("QA-0009"))[0] == 1
        assert states(path) == [
            (UNDER_REVIEW, "STAGED", SYSTEM),
            (UNDER_REVIEW, "WITHHELD", "QA-0007"),
        ]
        assert path.read_text(encoding="utf-8") == withheld

    def test_an_evaluation_that_stands_is_not_reviewed(self, run, path):
        run("stage", STANDING)

        assert run("review", STANDING, *confirm())[0] == 1
        assert states(path) == [(STANDING, "STAGED", SYSTEM)]

    @pytest.mark.parametrize("reviewer", [SYSTEM, "QA 0007", ""])
    def test_a_review_names_a_person_and_never_the_system(self, path, reviewer):
        ledger = Ledger(path, at_noon)
        ledger.stage(CRITICAL_FAILURE)
        before = path.read_text(encoding="utf-8")

        for outcome in ReviewOutcome:
            with pytest.raises(Refused):
                ledger.review(*KEY, reviewer, outcome)
        with pytest.raises(Refused):  # so no permit was recorded
            ledger.publish(*KEY)
        assert path.read_text(encoding="utf-8") == before

    def test_the_cli_refuses_a_review_in_the_systems_name(self, run, path):
        run("stage", UNDER_REVIEW)

        assert run("review", UNDER_REVIEW, *confirm(SYSTEM))[0] == 1
        assert run("publish", UNDER_REVIEW)[0] == 1
        assert states(path) == [(UNDER_REVIEW, "STAGED", SYSTEM)]

    def test_show_gives_the_state_and_the_audit_trail_by_identifiers(self, run):
        run("stage", UNDER_REVIEW)
        run("review", UNDER_REVIEW, *confirm())
        run("publish", UNDER_REVIEW)

        code, out, _ = run("show", UNDER_REVIEW, "--json")
        shown = json.loads(out)

        assert code == 0
        assert (shown["call"], shown["scorecard"]) == (UNDER_REVIEW, CARD)
        assert (shown["disposition"], shown["publication_state"]) == ("NEEDS_REVIEW", "PUBLISHED")
        assert [(r["reviewer"], r["review_outcome"]) for r in shown["reviews"]] == [
            ("QA-0007", "CONFIRMED")
        ]
        assert [r["publication_state"] for r in shown["audit_records"]] == ["STAGED", "PUBLISHED"]

    def test_what_is_not_on_the_ledger_is_refused_not_failed(self, run, path):
        assert run("show", UNDER_REVIEW)[0] == 1
        assert run("publish", UNDER_REVIEW)[0] == 1
        assert run("review", UNDER_REVIEW, *confirm())[0] == 1
        assert not path.exists()

    def test_a_ledger_that_cannot_be_written_or_read_is_a_failure(self, run, path, capsys):
        missing = path.parent / "no-such-folder" / "ledger.jsonl"
        code = evaluate(STANDING, "--stage", str(missing))
        capsys.readouterr()
        assert code == 2

        path.write_text("not a line of a ledger\n", encoding="utf-8")
        for name, more in (("show", ()), ("publish", ()), ("review", confirm()), ("stage", ())):
            code, _, said = run(name, STANDING, *more)
            assert code == 2 and "line 1" in said, name
        assert path.read_text(encoding="utf-8") == "not a line of a ledger\n"


class TestAuditTrail:
    """REQ-0021: one AuditRecord for each change of state, carrying identifiers only."""

    def test_one_audit_record_for_each_change_and_none_for_a_refusal(self, run, path):
        run("stage", UNDER_REVIEW)
        run("publish", UNDER_REVIEW)  # refused: REVIEW_REQUIRED
        run("review", UNDER_REVIEW, *confirm())  # recorded, and no change of state
        run("review", UNDER_REVIEW, *confirm("QA-0009"))
        run("publish", UNDER_REVIEW)
        run("review", UNDER_REVIEW, *overturn())  # refused: it is PUBLISHED

        assert states(path) == [
            (UNDER_REVIEW, "STAGED", SYSTEM),
            (UNDER_REVIEW, "PUBLISHED", SYSTEM),
        ]
        found = Ledger(path).entry(UNDER_REVIEW, CARD)
        assert [r.reviewer for r in found.reviews] == ["QA-0007", "QA-0009"]
        assert found.publication_state is PublicationState.PUBLISHED

    def test_every_line_holds_names_states_and_times_and_no_number(self, run, path):
        for call in (STANDING, UNDER_REVIEW):
            run("stage", call)
        run("publish", STANDING)
        run("review", UNDER_REVIEW, *overturn())

        for text in path.read_text(encoding="utf-8").splitlines():
            line = json.loads(text)
            assert set(line) <= {"audit_record", "review", "disposition", "sha256"}
            assert set(line.get("audit_record", {})) <= set(AuditRecord.model_fields)
            assert set(line.get("review", {})) <= set(Review.model_fields)
            leaves = [
                v
                for part in line.values()
                for v in (part.values() if isinstance(part, dict) else [part])
            ]
            # A score is a number and nothing on the ledger is one.
            assert all(type(leaf) is str for leaf in leaves)

    @pytest.mark.parametrize("field", ["text", "rationale", "score", "findings"])
    def test_an_audit_record_has_no_place_for_words_or_a_score(self, field):
        record = {
            "call": "CALL-0001",
            "scorecard": CARD,
            "publication_state": "STAGED",
            "actor": SYSTEM,
            "recorded_at": "2026-11-02T12:00:00Z",
        }
        AuditRecord.model_validate(record)
        with pytest.raises(ValidationError):
            AuditRecord.model_validate({**record, field: "1"})


def at_noon() -> datetime:
    return datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class TestAnotherEvaluation:
    """REQ-0023 and DEC-0012: the Evaluation on the ledger is the one a Review is made of."""

    def test_a_different_evaluation_of_the_same_call_is_refused(self, path):
        ledger = Ledger(path, at_noon)
        assert ledger.stage(CRITICAL_FAILURE) is True
        before = path.read_text(encoding="utf-8")

        # Same Call, same Scorecard, same disposition: only the Findings differ.
        with pytest.raises(Refused):
            ledger.stage(NOTHING_APPLIED)
        with pytest.raises(Refused):
            ledger.stage(STANDS)

        assert path.read_text(encoding="utf-8") == before

    def test_a_review_of_the_first_does_not_publish_a_second(self, path):
        ledger = Ledger(path, at_noon)
        ledger.stage(CRITICAL_FAILURE)
        ledger.review(*KEY, "QA-0007", ReviewOutcome.CONFIRMED)

        with pytest.raises(Refused):
            ledger.stage(NOTHING_APPLIED)

        assert ledger.publish(*KEY) is True
        assert ledger.entry(*KEY).sha256 == Ledger(path).entry(*KEY).sha256
        with pytest.raises(Refused):  # and not once it is PUBLISHED either
            ledger.stage(NOTHING_APPLIED)

    def test_the_cli_says_refused(self, run, path, monkeypatch):
        run("stage", UNDER_REVIEW)
        before = path.read_text(encoding="utf-8")
        monkeypatch.setattr(
            cli,
            "replay",
            lambda *given: NOTHING_APPLIED.model_copy(
                update={"call": UNDER_REVIEW, "scorecard": CARD}
            ),
        )

        code, _, said = run("stage", UNDER_REVIEW)

        assert code == 1 and "Not staged" in said
        assert path.read_text(encoding="utf-8") == before


class TestGivenAgain:
    """REQ-0024: a command given again finds its effect there and records nothing more."""

    def test_every_command_given_twice_leaves_the_ledger_as_it_was(self, run, path):
        script = [
            ("stage", STANDING, ()),
            ("stage", UNDER_REVIEW, ()),
            ("publish", STANDING, ()),
            ("review", UNDER_REVIEW, confirm()),
            ("publish", UNDER_REVIEW, ()),
        ]
        for name, call, more in script:
            assert run(name, call, *more)[0] == 0
            once = path.read_text(encoding="utf-8")
            code, _, said = run(name, call, *more)
            assert code == 0 and "Nothing was recorded" in said
            assert path.read_text(encoding="utf-8") == once

        # The whole script again, on the ledger it produced.
        for name, call, more in script:
            assert run(name, call, *more)[0] == 0
        assert path.read_text(encoding="utf-8") == once
        assert len(once.splitlines()) == len(script)

    @pytest.mark.parametrize("command", ["stage", "review", "publish"])
    def test_a_command_given_twice_at_once_records_one_line(self, path, command):
        """The second is given after the first has read the ledger and before it appends."""
        give = {
            "stage": lambda ledger: ledger.stage(CRITICAL_FAILURE),
            "review": lambda ledger: ledger.review(*KEY, "QA-0007", ReviewOutcome.CONFIRMED),
            "publish": lambda ledger: ledger.publish(*KEY),
        }
        for earlier in ("stage", "review", "publish"):
            if earlier == command:
                break
            give[earlier](Ledger(path, at_noon))
        before = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
        second: list[bool] = []
        other = threading.Thread(
            target=lambda: second.append(give[command](Ledger(path, at_noon))), daemon=True
        )

        def in_the_middle() -> datetime:
            # The clock is read between the read of the ledger and the append.
            other.start()
            other.join(timeout=0.5)
            return at_noon()

        first = give[command](Ledger(path, in_the_middle))
        other.join(timeout=10)

        assert (first, second) == (True, [False])
        assert len(path.read_text(encoding="utf-8").splitlines()) == before + 1
        Ledger(path).entries()  # and it still reads

    def test_eight_publish_commands_at_once_record_one_audit_record(self, run, path):
        run("stage", STANDING)
        argv = [sys.executable, "-m", "call_qa_agent.cli", "publish", str(path), STANDING, CARD]

        started = [
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(8)
        ]

        assert [process.wait(timeout=60) for process in started] == [0] * 8
        assert states(path) == [(STANDING, "STAGED", SYSTEM), (STANDING, "PUBLISHED", SYSTEM)]
        assert run("show", STANDING)[0] == 0


class TestALedgerNobodyWrote:
    """Reading goes through the domain layer, so a line that claims too much is not believed."""

    @staticmethod
    def lines(path: Path) -> list[dict]:
        ledger = Ledger(path, at_noon)
        ledger.stage(CRITICAL_FAILURE)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    @pytest.mark.parametrize(
        "claim",
        [
            "published without a Review",
            "staged a second time",
            "a score beside the AuditRecord",
            "a rationale inside the AuditRecord",
            "withheld by nobody",
            "a Review of a Call that is not there",
            "a Review by the system",
            "not JSON",
        ],
    )
    def test_a_line_that_claims_too_much_is_corrupt(self, path, claim):
        (staged,) = self.lines(path)
        record = {**staged["audit_record"], "recorded_at": "2026-11-02T13:00:00Z"}
        review = {
            "call": record["call"],
            "scorecard": record["scorecard"],
            "reviewer": "QA-0007",
            "review_outcome": "OVERTURNED",
            "reviewed_at": "2026-11-02T13:00:00Z",
        }
        line = {
            "published without a Review": {
                "audit_record": {**record, "publication_state": "PUBLISHED"}
            },
            "staged a second time": staged,
            "a score beside the AuditRecord": {"audit_record": record, "score": 100},
            "a rationale inside the AuditRecord": {"audit_record": {**record, "rationale": "r"}},
            "withheld by nobody": {"audit_record": {**record, "publication_state": "WITHHELD"}},
            "a Review of a Call that is not there": {"review": {**review, "call": "CALL-9999"}},
            "a Review by the system": {
                "review": {**review, "reviewer": SYSTEM, "review_outcome": "CONFIRMED"}
            },
            "not JSON": None,
        }[claim]
        with path.open("a", encoding="utf-8") as ledger:
            ledger.write((json.dumps(line) if line else "{") + "\n")

        with pytest.raises(Corrupt, match="line 2"):
            Ledger(path).entries()

    @pytest.mark.parametrize("cut", ["a line cut short", "a whole line with no end"])
    def test_a_last_line_with_no_end_is_corrupt_and_nothing_is_joined_to_it(self, path, cut):
        ledger = Ledger(path, at_noon)
        ledger.stage(STANDS)
        (staged,) = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        # The line a publication would have written, had its write been whole.
        whole = json.dumps(
            {"audit_record": {**staged["audit_record"], "publication_state": "PUBLISHED"}}
        )
        with path.open("a", encoding="utf-8") as file:
            file.write(whole[:40] if cut == "a line cut short" else whole)
        before = path.read_text(encoding="utf-8")

        with pytest.raises(Corrupt, match="line 2"):
            ledger.entries()
        for command in (
            lambda: ledger.publish(STANDS.call, STANDS.scorecard),
            lambda: ledger.review(*KEY, "QA-0007", ReviewOutcome.CONFIRMED),
            lambda: ledger.stage(STANDS.model_copy(update={"call": "CALL-9201"})),
        ):
            with pytest.raises(Corrupt, match="line 2"):
                command()
        assert path.read_text(encoding="utf-8") == before

    def test_an_empty_line_records_nothing_and_stops_nothing(self, path):
        self.lines(path)
        with path.open("a", encoding="utf-8") as ledger:
            ledger.write("\n")
        ledger = Ledger(path, at_noon)

        assert ledger.review(*KEY, "QA-0007", ReviewOutcome.CONFIRMED) is True
        assert ledger.publish(*KEY) is True
        assert ledger.entry(*KEY).publication_state is PublicationState.PUBLISHED
