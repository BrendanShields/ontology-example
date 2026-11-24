"""The agent: Claude reads a Call and proposes Findings through the tools.

The loop is written out by hand rather than taken from the SDK's tool runner.
The runner is a beta helper that derives tool schemas from function signatures;
here the schemas come from the ontology, the loop has to stop the moment the
Evaluation is complete, and it has to run unchanged on Amazon Bedrock.

What the model controls is small on purpose (DEC-0006): it proposes Findings.
Whether a Finding is accepted, and everything computed from the accepted ones,
is decided by `session.py` and the domain layer.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field, replace

import anthropic

from .generated import Call, Evaluation, Rejection, Scorecard
from .prompts import call_message, system_prompt
from .session import EvaluationSession
from .tools import render_rejections, run_tool, tool_definitions

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class EvaluationIncomplete(Exception):
    """No Evaluation was produced. `rejections` holds what was still outstanding (REQ-0007)."""

    def __init__(self, reason: str, rejections: list[Rejection]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rejections = rejections


@dataclass(frozen=True)
class Settings:
    model: str = DEFAULT_MODEL
    platform: str = "anthropic"  # "anthropic" (Claude API) or "bedrock" (Amazon Bedrock)
    effort: str = "high"  # judging a Call against obligations is not a task to economise on
    max_turns: int = 8  # model requests per Call, before giving up (REQ-0007)
    max_tokens: int = 16000
    # If a safety classifier declines the request, retry it on another model
    # instead of failing. On the Claude API the server picks the model
    # ("default"). On Bedrock the fallback model has to be named.
    refusal_fallback: bool = True
    fallback_model: str | None = None
    aws_region: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            model=env.get("CALL_QA_MODEL", cls.model),
            platform=env.get("CALL_QA_PLATFORM", cls.platform),
            effort=env.get("CALL_QA_EFFORT", cls.effort),
            max_turns=int(env.get("CALL_QA_MAX_TURNS", cls.max_turns)),
            refusal_fallback=env.get("CALL_QA_REFUSAL_FALLBACK", "on").lower() != "off",
            fallback_model=env.get("CALL_QA_FALLBACK_MODEL"),
            aws_region=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION"),
        )

    @property
    def model_id(self) -> str:
        """The model id as the platform spells it: Bedrock ids carry an `anthropic.` prefix."""
        if self.platform == "bedrock" and not self.model.startswith("anthropic."):
            return f"anthropic.{self.model}"
        return self.model

    @property
    def middleware_fallback(self) -> bool:
        """Bedrock has no server-side fallback: the SDK's middleware does it, given a model."""
        return self.platform == "bedrock" and self.refusal_fallback and bool(self.fallback_model)


@dataclass
class Step:
    """One tool call the model made, and what came back. Collected for `--trace`."""

    tool: str
    tool_input: object
    result: str
    rejected: bool
    served_by: str | None = None


@dataclass
class Trace:
    steps: list[Step] = field(default_factory=list)
    requests: int = 0


def make_client(settings: Settings):
    """A client for the configured platform. Credentials come from the environment."""
    if settings.platform == "bedrock":
        middleware = []
        if settings.middleware_fallback:
            middleware.append(
                anthropic.BetaRefusalFallbackMiddleware([{"model": settings.fallback_model}])
            )
        return anthropic.AnthropicBedrockMantle(
            aws_region=settings.aws_region, middleware=middleware
        )
    if settings.platform == "anthropic":
        return anthropic.Anthropic()
    raise ValueError(f"unknown platform {settings.platform!r}: use 'anthropic' or 'bedrock'")


def evaluate(
    call: Call,
    scorecard: Scorecard,
    client,
    settings: Settings | None = None,
    trace: Trace | None = None,
) -> Evaluation:
    """Evaluate one Call. Returns a complete Evaluation or raises EvaluationIncomplete."""
    settings = settings or Settings()
    trace = trace if trace is not None else Trace()
    session = EvaluationSession(call, scorecard)
    request = {
        "model": settings.model_id,
        "max_tokens": settings.max_tokens,
        # Thinking is adaptive by default on the current models, so it is not
        # set here. Effort is, because its default differs between them.
        "output_config": {"effort": settings.effort},
        # Scorecard and tools are the same for every Call: cache them.
        "system": [
            {
                "type": "text",
                "text": system_prompt(scorecard),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": tool_definitions(scorecard),
    }
    messages: list[dict] = [{"role": "user", "content": call_message(call)}]
    # One fallback state per Call keeps follow-up requests on the model that accepted.
    pinned = anthropic.BetaFallbackState() if settings.middleware_fallback else None

    for _ in range(settings.max_turns):
        with pinned or contextlib.nullcontext():
            response = _send(client, settings, {**request, "messages": messages})
        trace.requests += 1

        # Check why the model stopped before reading what it wrote.
        if response.stop_reason == "refusal":
            raise EvaluationIncomplete(
                "the model declined to evaluate this Call", session.outstanding()
            )
        if response.stop_reason == "max_tokens":
            raise EvaluationIncomplete("the model's reply was cut off", session.outstanding())

        messages.append({"role": "assistant", "content": response.content})
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            # The model stopped without calling a tool. If everything is
            # recorded that is a finish; otherwise say what is missing.
            missing = session.finish()
            if session.evaluation is not None:
                return session.evaluation
            messages.append(
                {
                    "role": "user",
                    "content": "The Evaluation is not complete.\n"
                    + render_rejections(missing)
                    + "\nRecord the missing Findings, then call finish_evaluation.",
                }
            )
            continue

        # Run every tool call of the turn and answer them in one message.
        results = []
        for block in calls:
            if session.evaluation is not None:
                text, rejected = "The Evaluation is already complete.", True
            else:
                text, rejected = run_tool(session, block.name, block.input)
            trace.steps.append(Step(block.name, block.input, text, rejected, response.model))
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": text,
                    "is_error": rejected,
                }
            )
        messages.append({"role": "user", "content": results})
        if session.evaluation is not None:
            return session.evaluation

    raise EvaluationIncomplete(
        f"the model did not complete the Evaluation within {settings.max_turns} turns",
        session.outstanding(),
    )


def _send(client, settings: Settings, request: dict):
    if settings.platform == "anthropic" and settings.refusal_fallback:
        return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **request)
    if settings.middleware_fallback:
        return client.beta.messages.create(**request)  # the middleware acts on beta requests
    return client.messages.create(**request)


def with_overrides(settings: Settings, **overrides) -> Settings:
    """Settings with the given fields replaced, ignoring overrides that are None."""
    return replace(settings, **{k: v for k, v in overrides.items() if v is not None})
