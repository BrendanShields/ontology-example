"""Shared fixtures: the example Scorecard and Calls, and a fake Claude API."""

from __future__ import annotations

import json
from pathlib import Path

import anthropic
import httpx2
import pytest
from call_qa_agent.cli import load_call, load_scorecard
from call_qa_agent.generated import Call, Finding, Scorecard
from call_qa_agent.session import EvaluationSession

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def scorecard() -> Scorecard:
    return load_scorecard(DATA / "scorecards" / "retail-banking-v1.yaml")


@pytest.fixture
def call() -> Call:
    return load_call(DATA / "calls" / "CALL-0001.yaml")


@pytest.fixture
def session(call, scorecard) -> EvaluationSession:
    return EvaluationSession(call, scorecard)


def proposal(criterion: str, outcome: str = "MET", cited: list[int] | None = None) -> dict:
    """A proposed Finding as the model would send it."""
    return {
        "criterion": criterion,
        "finding_outcome": outcome,
        "cited_utterances": [2] if cited is None else cited,
        "rationale": "Because of what was said.",
    }


def finding(criterion: str, outcome: str = "MET", cited: list[int] | None = None) -> Finding:
    return Finding.model_validate(proposal(criterion, outcome, cited))


class FakeClaude:
    """The Claude API, scripted. Requests go through the real SDK and a mock transport,

    so the tests exercise the request the agent actually builds and the
    response parsing it actually relies on. Nothing leaves the process.
    """

    def __init__(self, *replies: dict) -> None:
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []
        self.client = anthropic.Anthropic(
            api_key="test-key",
            max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self._handle)),
        )

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("the agent made more requests than the test scripted")
        return httpx2.Response(200, json=self.replies.pop(0))

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


def reply(*tool_calls: tuple[str, dict], stop_reason: str = "tool_use", text: str = "") -> dict:
    """One assistant message in the API's wire format."""
    content: list[dict] = [{"type": "text", "text": text}] if text else []
    for number, (name, tool_input) in enumerate(tool_calls, start=1):
        content.append(
            {"type": "tool_use", "id": f"toolu_{number:02d}", "name": name, "input": tool_input}
        )
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
