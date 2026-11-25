"""Acceptance tests for the publication state machine: REQ-0016 to REQ-0020, REQ-0022, REQ-0025.

These call the domain layer directly, with Evaluations the real
`scoring.conclude` built. The ledger and the commands are in test_ledger.py,
and every sequence of commands within a bound is in tests/bounded.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from call_qa_agent.domain import publication, scoring
from call_qa_agent.domain.publication import Refused
from call_qa_agent.generated import (
    AuditRecord,
    Call,
    Criterion,
    Disposition,
    Evaluation,
    PublicationState,
    RejectionRule,
    Review,
    ReviewOutcome,
    Scorecard,
)

from ..conftest import finding

NOON = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
SCORECARD = Scorecard(
    scorecard_id="publication-v1",
    pass_mark=50,
    criteria=[
        Criterion(criterion_id="c0", statement="First.", weight=1, critical=True),
        Criterion(criterion_id="c1", statement="Second.", weight=1),
    ],
)
CALL = Call.model_validate(
    {
        "call_id": "CALL-9200",
        "representative": "REP-9200",
        "utterances": [
            {"sequence": 1, "speaker": "CUSTOMER", "text": "x"},
            {"sequence": 2, "speaker": "REPRESENTATIVE", "text": "y"},
        ],
    }
)


def concluded(first: str, second: str) -> Evaluation:
    return scoring.conclude(
        CALL, SCORECARD, [finding("c0", first, [1]), finding("c1", second, [2])]
    )


STANDS = concluded("MET", "MET")
# The two ways an Evaluation comes to need a Review (scoring.conclude).
CRITICAL_FAILURE = concluded("NOT_MET", "MET")
NOTHING_APPLIED = concluded("NOT_APPLICABLE", "NOT_APPLICABLE")
UNDER_REVIEW = pytest.mark.parametrize("evaluation", [CRITICAL_FAILURE, NOTHING_APPLIED])


def staged(evaluation: Evaluation) -> list[AuditRecord]:
    return [publication.stage(evaluation, [], actor="system", recorded_at=NOON)]


def made(outcome: ReviewOutcome, call: str = CALL.call_id, minutes: int = 5) -> Review:
    return Review(
        call=call,
        scorecard=SCORECARD.scorecard_id,
        reviewer="QA-0007",
        review_outcome=outcome,
        reviewed_at=NOON + timedelta(minutes=minutes),
    )


def publish(evaluation: Evaluation, reviews: list[Review], records: list[AuditRecord]):
    return publication.publish(
        evaluation.call,
        evaluation.scorecard,
        evaluation.disposition,
        reviews,
        records,
        actor="system",
        recorded_at=NOON + timedelta(hours=1),
    )


def test_the_fixtures_have_the_dispositions_the_tests_assume():
    assert STANDS.disposition == Disposition.FINAL
    assert {CRITICAL_FAILURE.disposition, NOTHING_APPLIED.disposition} == {Disposition.NEEDS_REVIEW}


def test_the_table_of_changes_covers_every_publication_state():
    assert set(publication.CHANGES) == {None, *PublicationState}
    assert publication.CHANGES[PublicationState.PUBLISHED] == ()
    assert publication.CHANGES[PublicationState.WITHHELD] == ()


class TestStagingAndPublishing:
    """REQ-0022 and REQ-0025."""

    def test_a_complete_evaluation_is_staged(self):
        (record,) = staged(STANDS)

        assert record == AuditRecord(
            call="CALL-9200",
            scorecard="publication-v1",
            publication_state=PublicationState.STAGED,
            actor="system",
            recorded_at=NOON,
        )
        assert publication.publication_state([record]) is PublicationState.STAGED
        assert publication.publication_state([]) is None

    def test_an_evaluation_is_not_staged_twice(self):
        with pytest.raises(Refused) as refused:
            publication.stage(STANDS, staged(STANDS), actor="system", recorded_at=NOON)
        assert refused.value.rejections == []

    def test_an_evaluation_that_stands_is_published_without_a_review(self):
        record = publish(STANDS, [], staged(STANDS))

        assert record.publication_state == PublicationState.PUBLISHED
        assert (record.call, record.scorecard, record.actor) == (
            "CALL-9200",
            "publication-v1",
            "system",
        )

    @UNDER_REVIEW
    def test_an_evaluation_a_review_confirmed_is_published(self, evaluation):
        records = staged(evaluation)
        confirmed = made(ReviewOutcome.CONFIRMED)
        assert publication.review(confirmed, evaluation.disposition, records) is None

        assert publish(evaluation, [confirmed], records).publication_state == "PUBLISHED"

    def test_where_another_call_stands_permits_nothing_for_this_one(self):
        other = STANDS.model_copy(update={"call": "CALL-9201"})

        with pytest.raises(Refused):  # CALL-9200 is not staged: only CALL-9201 is
            publish(STANDS, [], staged(other))
        with pytest.raises(Refused):
            publication.review(
                made(ReviewOutcome.OVERTURNED), CRITICAL_FAILURE.disposition, staged(other)
            )
        with pytest.raises(Refused):
            publication.stage(STANDS, staged(other), actor="system", recorded_at=NOON)

    def test_what_is_not_staged_is_not_published(self):
        with pytest.raises(Refused) as refused:
            publish(STANDS, [], [])
        assert refused.value.rejections == []


class TestReviewRequired:
    """REQ-0016 and REQ-0017: no Review that CONFIRMED it, no publication."""

    @UNDER_REVIEW
    def test_publishing_without_a_review_is_answered_with_review_required(self, evaluation):
        with pytest.raises(Refused) as refused:
            publish(evaluation, [], staged(evaluation))

        (rejection,) = refused.value.rejections
        assert rejection.rejection_rule == RejectionRule.REVIEW_REQUIRED
        assert rejection.allowed_values == ["CONFIRMED"]
        assert "CALL-9200" in rejection.detail and "publication-v1" in rejection.detail

    @UNDER_REVIEW
    def test_a_review_of_another_call_permits_nothing(self, evaluation):
        elsewhere = made(ReviewOutcome.CONFIRMED, call="CALL-9201")

        with pytest.raises(Refused) as refused:
            publish(evaluation, [elsewhere], staged(evaluation))

        assert [r.rejection_rule for r in refused.value.rejections] == ["REVIEW_REQUIRED"]

    def test_the_guard_reads_the_disposition_and_not_the_reason_for_it(self):
        # Nothing failed here: no Criterion applied. It needs a Review all the same (DEC-0010).
        assert not any(f.finding_outcome == "NOT_MET" for f in NOTHING_APPLIED.findings)

        with pytest.raises(Refused) as refused:
            publish(NOTHING_APPLIED, [], staged(NOTHING_APPLIED))

        assert [r.rejection_rule for r in refused.value.rejections] == ["REVIEW_REQUIRED"]


class TestReview:
    """REQ-0019 and REQ-0020."""

    @UNDER_REVIEW
    def test_an_overturned_evaluation_is_withheld_in_the_reviewers_name(self, evaluation):
        overturned = made(ReviewOutcome.OVERTURNED)

        record = publication.review(overturned, evaluation.disposition, staged(evaluation))

        assert record == AuditRecord(
            call="CALL-9200",
            scorecard="publication-v1",
            publication_state=PublicationState.WITHHELD,
            actor="QA-0007",
            recorded_at=overturned.reviewed_at,
        )

    @pytest.mark.parametrize("outcome", list(ReviewOutcome))
    def test_an_evaluation_that_stands_is_not_reviewed(self, outcome):
        with pytest.raises(Refused) as refused:
            publication.review(made(outcome), STANDS.disposition, staged(STANDS))
        assert refused.value.rejections == []

    @pytest.mark.parametrize("outcome", list(ReviewOutcome))
    def test_what_is_not_staged_is_not_reviewed(self, outcome):
        with pytest.raises(Refused):
            publication.review(made(outcome), Disposition.NEEDS_REVIEW, [])


class TestFinalStates:
    """REQ-0018: PUBLISHED and WITHHELD lead nowhere."""

    @staticmethod
    def ended(state: PublicationState) -> tuple[list[Review], list[AuditRecord]]:
        """A critical-failure Evaluation that a Review CONFIRMED, taken to `state`."""
        records = staged(CRITICAL_FAILURE)
        reviews = [made(ReviewOutcome.CONFIRMED)]
        if state is PublicationState.PUBLISHED:
            return reviews, [*records, publish(CRITICAL_FAILURE, reviews, records)]
        overturned = made(ReviewOutcome.OVERTURNED, minutes=10)
        last = publication.review(overturned, CRITICAL_FAILURE.disposition, records)
        return [*reviews, overturned], [*records, last]

    @pytest.mark.parametrize("state", [PublicationState.PUBLISHED, PublicationState.WITHHELD])
    def test_nothing_changes_a_final_state(self, state):
        reviews, records = self.ended(state)
        assert publication.publication_state(records) is state

        with pytest.raises(Refused) as refused:
            publish(CRITICAL_FAILURE, reviews, records)
        assert refused.value.rejections == []  # not REVIEW_REQUIRED: no Review would help
        for outcome in ReviewOutcome:
            with pytest.raises(Refused):
                publication.review(made(outcome, minutes=20), Disposition.NEEDS_REVIEW, records)
        with pytest.raises(Refused):
            publication.stage(CRITICAL_FAILURE, records, actor="system", recorded_at=NOON)
