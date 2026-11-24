"""The guarded write path: the only way a Finding gets into an Evaluation.

Whoever proposes Findings, a language model or a test, goes through an
EvaluationSession. A proposal that breaks a rule is not recorded: the session
answers with Rejections that say which rule was broken and what would have
been accepted, and the proposer can correct itself and try again.
"""

from __future__ import annotations

from pydantic import ValidationError

from .domain import guardrails, scoring
from .generated import Call, Evaluation, Finding, Rejection, RejectionRule, Scorecard


class EvaluationSession:
    def __init__(self, call: Call, scorecard: Scorecard) -> None:
        self.call = call
        self.scorecard = scorecard
        self.findings: list[Finding] = []
        self.evaluation: Evaluation | None = None

    def record_finding(self, proposal: object) -> list[Rejection]:
        """Record a proposed Finding, or say why not. An empty list means it was recorded."""
        if self.evaluation is not None:
            raise RuntimeError("the Evaluation is already complete")
        try:
            finding = Finding.model_validate(proposal)
        except ValidationError as error:
            return [_malformed(error, proposal)]
        rejections = guardrails.check_finding(finding, self.call, self.scorecard, self.findings)
        if not rejections:
            self.findings.append(finding)
        return rejections

    def outstanding(self) -> list[Rejection]:
        """What still stands between the recorded Findings and a complete Evaluation."""
        return guardrails.check_complete(self.scorecard, self.findings)

    def finish(self) -> list[Rejection]:
        """Complete the Evaluation, or say what is missing. An empty list means it is complete."""
        rejections = self.outstanding()
        if not rejections and self.evaluation is None:
            self.evaluation = scoring.conclude(self.call, self.scorecard, self.findings)
        return rejections


def _malformed(error: ValidationError, proposal: object) -> Rejection:
    """A Rejection for a proposal that is not a well-formed Finding at all."""
    problems = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "finding"
        problems.append(f"{where}: {item['msg']}")
    criterion = proposal.get("criterion") if isinstance(proposal, dict) else None
    return Rejection(
        rejection_rule=RejectionRule.MALFORMED_FINDING,
        criterion=criterion if isinstance(criterion, str) else None,
        detail="; ".join(problems),
        allowed_values=sorted(Finding.model_fields),
    )
