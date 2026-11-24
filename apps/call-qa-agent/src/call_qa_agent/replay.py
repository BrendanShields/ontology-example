"""Replay a recorded sequence of tool calls against the guarded write path.

A replay stands in for the model: it makes the same tool calls, in order,
through the same `run_tool`. It needs no credentials, which is what lets the
write path be demonstrated and tested offline.
"""

from __future__ import annotations

import json
from pathlib import Path

from .agent import EvaluationIncomplete, Step, Trace
from .generated import Call, Evaluation, Scorecard
from .session import EvaluationSession
from .tools import run_tool


def load_steps(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["steps"] if isinstance(data, dict) else data


def replay(
    call: Call, scorecard: Scorecard, steps: list[dict], trace: Trace | None = None
) -> Evaluation:
    """Run the steps. Returns the Evaluation or raises EvaluationIncomplete."""
    trace = trace if trace is not None else Trace()
    session = EvaluationSession(call, scorecard)
    for step in steps:
        text, rejected = run_tool(session, step["tool"], step.get("input", {}))
        trace.steps.append(Step(step["tool"], step.get("input", {}), text, rejected))
        if session.evaluation is not None:
            return session.evaluation
    raise EvaluationIncomplete(
        "the recorded steps ended before the Evaluation was complete", session.outstanding()
    )
