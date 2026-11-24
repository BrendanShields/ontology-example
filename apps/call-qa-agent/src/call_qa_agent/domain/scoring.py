"""Turn accepted Findings into an Evaluation: score, outcome and disposition.

Nothing here is asked of the language model (DEC-0006). The model proposes
Findings; this module computes what follows from them, the same way every time.

This module is part of the domain layer. Its vocabulary is the call-qa glossary
(ontology/domains/call-qa.yaml) and its types are generated from it.
"""

from __future__ import annotations

from ..generated import (
    Call,
    Disposition,
    Evaluation,
    EvaluationOutcome,
    Finding,
    FindingOutcome,
    Scorecard,
)


def score(findings: list[Finding], scorecard: Scorecard) -> int:
    """The weight met as a whole-number percentage of the weight that applied (REQ-0004).

    A NOT_APPLICABLE Finding counts neither for nor against (DEC-0005). When
    nothing applied there is nothing to take a share of, and the score is 0.
    """
    met, applied = _weights(findings, scorecard)
    return met * 100 // applied if applied else 0


def conclude(call: Call, scorecard: Scorecard, findings: list[Finding]) -> Evaluation:
    """Build the Evaluation of a Call from one accepted Finding per Criterion.

    The caller is responsible for the Findings being complete and accepted:
    see `guardrails.check_finding` and `guardrails.check_complete`.
    """
    _, applied = _weights(findings, scorecard)
    critical_failed = _critical_failed(findings, scorecard)
    points = score(findings, scorecard)

    # REQ-0005: no score makes up for a failed critical Criterion (DEC-0007).
    # REQ-0006: otherwise the pass mark decides.
    passed = not critical_failed and points >= scorecard.pass_mark
    # A failed critical Criterion is confirmed by a person before it stands, and
    # so is an Evaluation in which no Criterion applied at all.
    needs_review = critical_failed or applied == 0

    return Evaluation(
        call=call.call_id,
        scorecard=scorecard.scorecard_id,
        findings=findings,
        score=points,
        evaluation_outcome=EvaluationOutcome.PASS if passed else EvaluationOutcome.FAIL,
        disposition=Disposition.NEEDS_REVIEW if needs_review else Disposition.FINAL,
    )


def _weights(findings: list[Finding], scorecard: Scorecard) -> tuple[int, int]:
    """(weight met, weight that applied) over the Findings."""
    weight = {criterion.criterion_id: criterion.weight for criterion in scorecard.criteria}
    met = sum(weight[f.criterion] for f in findings if f.finding_outcome == FindingOutcome.MET)
    applied = sum(
        weight[f.criterion] for f in findings if f.finding_outcome != FindingOutcome.NOT_APPLICABLE
    )
    return met, applied


def _critical_failed(findings: list[Finding], scorecard: Scorecard) -> bool:
    critical = {c.criterion_id for c in scorecard.criteria if c.critical}
    return any(
        f.criterion in critical and f.finding_outcome == FindingOutcome.NOT_MET for f in findings
    )
