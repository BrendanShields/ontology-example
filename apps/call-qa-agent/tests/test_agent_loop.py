"""The agent loop, driven through the real SDK against a scripted API.

These tests check the request the agent builds and how it reacts to what comes
back. They do not check Claude's judgement: nothing here calls a model.
"""

from __future__ import annotations

import json

import pytest
from call_qa_agent.agent import EvaluationIncomplete, Settings, Trace, evaluate

from .conftest import FakeClaude, proposal, reply

ALL = (
    "greeting",
    "recording-notice",
    "identity-verified",
    "request-confirmed",
    "request-resolved",
    "complaint-handled",
)


def record(criterion: str, **overrides) -> tuple[str, dict]:
    return ("record_finding", {**proposal(criterion), **overrides})


def test_a_rejected_finding_goes_back_to_the_model_which_corrects_it(call, scorecard):
    claude = FakeClaude(
        # Turn 1: two findings in one message. The second cites an Utterance that does not exist.
        reply(record("greeting"), record("recording-notice", cited_utterances=[99])),
        # Turn 2: the correction, and the rest.
        reply(
            record("recording-notice", cited_utterances=[1]),
            *(record(c) for c in ALL[2:5]),
            record("complaint-handled", finding_outcome="NOT_APPLICABLE", cited_utterances=[]),
        ),
        # Turn 3: done.
        reply(("finish_evaluation", {})),
    )
    trace = Trace()

    evaluation = evaluate(call, scorecard, claude.client, Settings(), trace)

    assert [f.criterion for f in evaluation.findings] == list(ALL)
    assert (evaluation.score, evaluation.evaluation_outcome, evaluation.disposition) == (
        100,
        "PASS",
        "FINAL",
    )
    assert trace.requests == 3

    # Both tool calls of turn 1 are answered in one user message, in order.
    results = claude.body(1)["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_01", "toolu_02"]
    assert results[0]["is_error"] is False
    # The rejected one carries the Rejection as the ontology shapes it.
    rejection = json.loads(results[1]["content"])["rejections"][0]
    assert results[1]["is_error"] is True
    assert rejection["rejection_rule"] == "UNKNOWN_UTTERANCE"
    assert rejection["criterion"] == "recording-notice"


def test_the_request_is_compiled_from_the_ontology_and_the_scorecard(call, scorecard):
    claude = FakeClaude(reply(*(record(c) for c in ALL)), reply(("finish_evaluation", {})))

    evaluate(call, scorecard, claude.client, Settings())
    body = claude.body(0)

    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"] == {"effort": "high"}
    assert "thinking" not in body  # adaptive by default on current models

    record_tool, finish_tool = body["tools"]
    assert record_tool["name"] == "record_finding" and record_tool["strict"] is True
    schema = record_tool["input_schema"]
    # The Criterion is a closed list: the model cannot name one the Scorecard lacks.
    assert schema["properties"]["criterion"]["enum"] == list(ALL)
    assert schema["properties"]["finding_outcome"]["enum"] == ["MET", "NOT_MET", "NOT_APPLICABLE"]
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == sorted(schema["properties"])
    assert finish_tool["name"] == "finish_evaluation"

    # Scorecard in the cached system prompt, Call in the user message.
    (system,) = body["system"]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "identity-verified: The Representative verifies" in system["text"]
    assert "[2] REPRESENTATIVE: Good morning" in body["messages"][0]["content"]
    assert "Good morning" not in system["text"]


def test_refusal_fallback_is_on_by_default_and_can_be_turned_off(call, scorecard):
    script = (reply(*(record(c) for c in ALL)), reply(("finish_evaluation", {})))

    with_fallback = FakeClaude(*script)
    evaluate(call, scorecard, with_fallback.client, Settings())
    assert with_fallback.body(0)["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in with_fallback.requests[0].headers["anthropic-beta"]

    without = FakeClaude(*script)
    evaluate(call, scorecard, without.client, Settings(refusal_fallback=False))
    assert "fallbacks" not in without.body(0)
    assert "anthropic-beta" not in without.requests[0].headers


def test_stopping_without_finishing_is_a_finish_when_everything_is_recorded(call, scorecard):
    claude = FakeClaude(
        reply(*(record(c) for c in ALL)), reply(stop_reason="end_turn", text="Done.")
    )

    evaluation = evaluate(call, scorecard, claude.client, Settings())

    assert len(evaluation.findings) == len(ALL)


def test_stopping_early_is_answered_with_what_is_missing(call, scorecard):
    claude = FakeClaude(
        reply(record("greeting")),
        reply(stop_reason="end_turn", text="That covers it."),
        reply(*(record(c) for c in ALL[1:])),
        reply(("finish_evaluation", {})),
    )

    evaluation = evaluate(call, scorecard, claude.client, Settings())

    nudge = claude.body(2)["messages"][-1]
    assert nudge["role"] == "user" and "MISSING_FINDING" in nudge["content"]
    assert len(evaluation.findings) == len(ALL)


def test_a_declined_request_produces_no_evaluation(call, scorecard):
    claude = FakeClaude(reply(stop_reason="refusal"))

    with pytest.raises(EvaluationIncomplete) as raised:
        evaluate(call, scorecard, claude.client, Settings())

    assert "declined" in raised.value.reason
    assert len(raised.value.rejections) == len(ALL)


def test_bedrock_model_ids_carry_the_provider_prefix():
    assert Settings(platform="bedrock").model_id == "anthropic.claude-opus-5-5"
    assert Settings(platform="bedrock", model="anthropic.claude-opus-5-5").model_id == (
        "anthropic.claude-opus-5-5"
    )
    assert Settings().model_id == "claude-opus-5-5"
    # On Bedrock a fallback needs a named model: there is no server-side default.
    assert not Settings(platform="bedrock").middleware_fallback
    assert Settings(
        platform="bedrock", fallback_model="anthropic.claude-opus-5"
    ).middleware_fallback
