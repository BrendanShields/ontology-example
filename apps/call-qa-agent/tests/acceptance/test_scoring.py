"""Acceptance tests for the computed part of an Evaluation: REQ-0004, REQ-0005, REQ-0006."""

from __future__ import annotations

import pytest
from call_qa_agent.domain import scoring
from call_qa_agent.generated import Call, Criterion, Scorecard
from hypothesis import given
from hypothesis import strategies as st

from ..conftest import finding

OUTCOMES = ("MET", "NOT_MET", "NOT_APPLICABLE")
CALL = Call.model_validate(
    {
        "call_id": "CALL-9000",
        "representative": "REP-9000",
        "utterances": [{"sequence": 1, "speaker": "CUSTOMER", "text": "Hello."}],
    }
)


@st.composite
def judged_scorecards(draw, critical: bool | None = None):
    """A Scorecard with one Finding per Criterion, in any combination of outcomes."""
    count = draw(st.integers(min_value=1, max_value=8))
    criteria, findings = [], []
    for index in range(count):
        criteria.append(
            Criterion(
                criterion_id=f"c{index}",
                statement="Something the Representative is expected to do.",
                weight=draw(st.integers(min_value=1, max_value=50)),
                critical=draw(st.booleans()) if critical is None else critical,
            )
        )
        findings.append(finding(f"c{index}", draw(st.sampled_from(OUTCOMES)), cited=[1]))
    scorecard = Scorecard(
        scorecard_id="generated-v1",
        criteria=criteria,
        pass_mark=draw(st.integers(min_value=0, max_value=100)),
    )
    return scorecard, findings


class TestScoreIsComputedFromFindings:
    """REQ-0004: the weight met as a percentage of the weight that applied, rounded down."""

    def test_worked_example(self, scorecard):
        # greeting (5) and recording-notice (10) met, identity-verified (30) not met,
        # the rest not applicable: 15 of 45 applied, which is 33.3 per cent.
        findings = [
            finding("greeting"),
            finding("recording-notice"),
            finding("identity-verified", "NOT_MET"),
            finding("request-confirmed", "NOT_APPLICABLE"),
            finding("request-resolved", "NOT_APPLICABLE"),
            finding("complaint-handled", "NOT_APPLICABLE"),
        ]
        assert scoring.score(findings, scorecard) == 33

    @given(judged_scorecards())
    def test_score_is_the_floored_share_of_applicable_weight(self, judged):
        scorecard, findings = judged
        weight = {c.criterion_id: c.weight for c in scorecard.criteria}
        met = sum(weight[f.criterion] for f in findings if f.finding_outcome == "MET")
        applied = sum(
            weight[f.criterion] for f in findings if f.finding_outcome != "NOT_APPLICABLE"
        )

        result = scoring.score(findings, scorecard)

        assert 0 <= result <= 100
        assert result == (met * 100 // applied if applied else 0)

    @given(judged_scorecards())
    def test_a_finding_that_does_not_apply_never_changes_the_score(self, judged):
        scorecard, findings = judged
        applicable = [f for f in findings if f.finding_outcome != "NOT_APPLICABLE"]
        assert scoring.score(findings, scorecard) == scoring.score(applicable, scorecard)


@given(judged_scorecards(critical=True))
def test_failed_critical_criterion_fails_and_needs_review(judged):
    """REQ-0005: a NOT_MET critical Criterion means FAIL and NEEDS_REVIEW, whatever the score."""
    scorecard, findings = judged
    evaluation = scoring.conclude(CALL, scorecard, findings)

    if any(f.finding_outcome == "NOT_MET" for f in findings):
        assert evaluation.evaluation_outcome == "FAIL"
        assert evaluation.disposition == "NEEDS_REVIEW"


def test_one_failed_critical_criterion_outweighs_a_high_score():
    scorecard = Scorecard(
        scorecard_id="example-v1",
        pass_mark=50,
        criteria=[
            Criterion(criterion_id="minor", statement="A small thing.", weight=1, critical=True),
            Criterion(criterion_id="major", statement="A big thing.", weight=99),
        ],
    )
    evaluation = scoring.conclude(
        CALL, scorecard, [finding("minor", "NOT_MET", [1]), finding("major", "MET", [1])]
    )

    assert evaluation.score == 99
    assert (evaluation.evaluation_outcome, evaluation.disposition) == ("FAIL", "NEEDS_REVIEW")


@given(judged_scorecards(critical=False))
def test_pass_only_at_or_above_the_pass_mark(judged):
    """REQ-0006: with no critical Criterion failed, PASS if and only if score >= pass mark."""
    scorecard, findings = judged
    evaluation = scoring.conclude(CALL, scorecard, findings)

    passed = evaluation.evaluation_outcome == "PASS"
    assert passed == (evaluation.score >= scorecard.pass_mark)


def test_an_evaluation_in_which_nothing_applied_goes_to_a_person(scorecard):
    findings = [finding(c.criterion_id, "NOT_APPLICABLE", []) for c in scorecard.criteria]
    evaluation = scoring.conclude(CALL, scorecard, findings)

    assert evaluation.score == 0
    assert evaluation.disposition == "NEEDS_REVIEW"


@pytest.mark.parametrize(
    "criteria",
    [["c0", "c0"], ["c0"], [], ["c0", "c1", "c1"], ["c0", "zz"]],
    ids=["duplicate", "one-missing", "none", "one-extra", "unknown-criterion"],
)
def test_no_evaluation_from_duplicate_or_missing_findings(criteria):
    """REQ-0010: exactly one Finding for each Criterion, or no Evaluation at all."""
    scorecard = Scorecard(
        scorecard_id="example-v1",
        pass_mark=50,
        criteria=[
            Criterion(criterion_id=name, statement="A thing.", weight=1) for name in ("c0", "c1")
        ],
    )
    with pytest.raises(ValueError):
        scoring.conclude(CALL, scorecard, [finding(name, cited=[1]) for name in criteria])
