"""Acceptance test for REQ-0007: no Evaluation when the model runs out of turns."""

from __future__ import annotations

import pytest
from call_qa_agent.agent import EvaluationIncomplete, Settings, evaluate
from call_qa_agent.generated import RejectionRule

from ..conftest import FakeClaude, proposal, reply


def test_no_evaluation_when_the_model_runs_out_of_turns(call, scorecard):
    # The model records two Findings, then keeps re-recording one of them and never finishes.
    again = reply(("record_finding", proposal("greeting")))
    claude = FakeClaude(
        reply(
            ("record_finding", proposal("greeting")),
            ("record_finding", proposal("recording-notice", cited=[1])),
        ),
        again,
        again,
    )

    with pytest.raises(EvaluationIncomplete) as raised:
        evaluate(call, scorecard, claude.client, Settings(max_turns=3))

    # It stopped at the limit, and what is outstanding is reported in full.
    assert len(claude.requests) == 3
    assert "3 turns" in raised.value.reason
    outstanding = raised.value.rejections
    assert {r.rejection_rule for r in outstanding} == {RejectionRule.MISSING_FINDING}
    assert [r.criterion for r in outstanding] == [
        "identity-verified",
        "request-confirmed",
        "request-resolved",
        "complaint-handled",
    ]
