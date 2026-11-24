"""Acceptance tests for the guarded write path: REQ-0001, REQ-0002, REQ-0003."""

from __future__ import annotations

from call_qa_agent.generated import RejectionRule

from ..conftest import proposal


class TestOneFindingPerCriterion:
    """REQ-0001: exactly one Finding for each Criterion of the Scorecard."""

    def test_a_finding_for_a_criterion_outside_the_scorecard_is_rejected(self, session, scorecard):
        (rejection,) = session.record_finding(proposal("empathy"))

        assert rejection.rejection_rule == RejectionRule.UNKNOWN_CRITERION
        # The Rejection says what would have been accepted.
        assert rejection.allowed_values == [c.criterion_id for c in scorecard.criteria]
        assert session.findings == []

    def test_a_second_finding_for_the_same_criterion_is_rejected(self, session):
        assert session.record_finding(proposal("greeting")) == []
        (rejection,) = session.record_finding(proposal("greeting", "NOT_MET"))

        assert rejection.rejection_rule == RejectionRule.DUPLICATE_FINDING
        assert [f.finding_outcome for f in session.findings] == ["MET"]

    def test_an_evaluation_cannot_be_completed_while_a_criterion_has_no_finding(
        self, session, scorecard
    ):
        session.record_finding(proposal("greeting"))
        rejections = session.finish()

        assert session.evaluation is None
        assert {r.rejection_rule for r in rejections} == {RejectionRule.MISSING_FINDING}
        assert [r.criterion for r in rejections] == [
            c.criterion_id for c in scorecard.criteria if c.criterion_id != "greeting"
        ]

    def test_a_complete_evaluation_has_one_finding_per_criterion(self, session, scorecard):
        for criterion in scorecard.criteria:
            assert session.record_finding(proposal(criterion.criterion_id)) == []
        assert session.finish() == []

        judged = [f.criterion for f in session.evaluation.findings]
        assert judged == [c.criterion_id for c in scorecard.criteria]


def test_finding_citing_an_utterance_outside_the_call_is_rejected(session, call):
    """REQ-0002: a Finding may cite only Utterances of its Call."""
    beyond = len(call.utterances) + 1
    (rejection,) = session.record_finding(proposal("greeting", cited=[2, beyond]))

    assert rejection.rejection_rule == RejectionRule.UNKNOWN_UTTERANCE
    assert str(beyond) in rejection.detail
    assert session.findings == []


class TestJudgedFindingCitesAnUtterance:
    """REQ-0003: a Finding that is MET or NOT_MET cites at least one Utterance."""

    def test_met_without_a_citation_is_rejected(self, session):
        (rejection,) = session.record_finding(proposal("greeting", "MET", cited=[]))
        assert rejection.rejection_rule == RejectionRule.MISSING_CITATION
        assert session.findings == []

    def test_not_met_without_a_citation_is_rejected(self, session):
        (rejection,) = session.record_finding(proposal("greeting", "NOT_MET", cited=[]))
        assert rejection.rejection_rule == RejectionRule.MISSING_CITATION

    def test_not_applicable_needs_no_citation(self, session):
        assert (
            session.record_finding(proposal("complaint-handled", "NOT_APPLICABLE", cited=[])) == []
        )
        assert len(session.findings) == 1


def test_a_proposal_that_is_not_a_finding_is_rejected_with_the_accepted_fields(session):
    (rejection,) = session.record_finding({"criterion": "greeting", "finding_outcome": "PROBABLY"})

    assert rejection.rejection_rule == RejectionRule.MALFORMED_FINDING
    assert rejection.criterion == "greeting"
    assert "finding_outcome" in rejection.detail and "rationale" in rejection.detail
    assert "cited_utterances" in rejection.allowed_values
