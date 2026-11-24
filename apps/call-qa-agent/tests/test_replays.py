"""The example replays under data/ do what the README says they do."""

from __future__ import annotations

import json
from pathlib import Path

from call_qa_agent.agent import Trace
from call_qa_agent.cli import load_call, load_scorecard
from call_qa_agent.replay import load_steps, replay

DATA = Path(__file__).resolve().parents[1] / "data"


def run(call_id: str):
    trace = Trace()
    evaluation = replay(
        load_call(DATA / "calls" / f"{call_id}.yaml"),
        load_scorecard(DATA / "scorecards" / "retail-banking-v1.yaml"),
        load_steps(DATA / "replays" / f"{call_id}.json"),
        trace,
    )
    return evaluation, trace


def test_the_clean_call_passes_and_stands():
    evaluation, trace = run("CALL-0001")

    # complaint-handled did not apply, so 85 of 85 applicable points were met.
    assert (evaluation.score, evaluation.evaluation_outcome, evaluation.disposition) == (
        100,
        "PASS",
        "FINAL",
    )
    assert not any(step.rejected for step in trace.steps)


def test_the_call_that_skips_identity_verification_fails_and_goes_to_a_person():
    evaluation, trace = run("CALL-0002")

    assert (evaluation.score, evaluation.evaluation_outcome, evaluation.disposition) == (
        35,
        "FAIL",
        "NEEDS_REVIEW",
    )
    rules = [
        json.loads(step.result)["rejections"][0]["rejection_rule"]
        for step in trace.steps
        if step.rejected
    ]
    assert rules == [
        "UNKNOWN_CRITERION",
        "MISSING_CITATION",
        "UNKNOWN_UTTERANCE",
        "MISSING_FINDING",
    ]
