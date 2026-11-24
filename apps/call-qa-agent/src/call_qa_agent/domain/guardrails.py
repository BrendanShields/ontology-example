"""The rules a proposed Finding has to satisfy before it is recorded.

Each function returns Rejections rather than raising: a Rejection names the rule
that was broken and what would have been accepted, so whoever proposed the
Finding can correct it. An empty list means the proposal is acceptable.

This module is part of the domain layer. Its vocabulary is the call-qa glossary
(ontology/domains/call-qa.yaml) and its types are generated from it.
"""

from __future__ import annotations

from ..generated import Call, Finding, FindingOutcome, Rejection, RejectionRule, Scorecard

JUDGED = (FindingOutcome.MET, FindingOutcome.NOT_MET)


def check_finding(
    finding: Finding, call: Call, scorecard: Scorecard, recorded: list[Finding]
) -> list[Rejection]:
    """Every rule the Finding breaks, given the Call, the Scorecard and what is already recorded."""
    rejections: list[Rejection] = []
    criteria = [criterion.criterion_id for criterion in scorecard.criteria]

    if finding.criterion not in criteria:
        rejections.append(
            Rejection(
                rejection_rule=RejectionRule.UNKNOWN_CRITERION,
                criterion=finding.criterion,
                detail=(
                    f"'{finding.criterion}' is not a Criterion of Scorecard "
                    f"{scorecard.scorecard_id}."
                ),
                allowed_values=criteria,
            )
        )
    elif any(existing.criterion == finding.criterion for existing in recorded):
        rejections.append(
            Rejection(
                rejection_rule=RejectionRule.DUPLICATE_FINDING,
                criterion=finding.criterion,
                detail=f"A Finding for '{finding.criterion}' is already recorded.",
            )
        )

    cited = finding.cited_utterances or []
    spoken = {utterance.sequence for utterance in call.utterances}
    unknown = sorted(set(cited) - spoken)
    if unknown:
        rejections.append(
            Rejection(
                rejection_rule=RejectionRule.UNKNOWN_UTTERANCE,
                criterion=finding.criterion,
                detail=(
                    f"Call {call.call_id} has no Utterance numbered "
                    f"{', '.join(str(number) for number in unknown)}. "
                    f"Its Utterances are numbered {min(spoken)} to {max(spoken)}."
                ),
            )
        )

    if finding.finding_outcome in JUDGED and not cited:
        rejections.append(
            Rejection(
                rejection_rule=RejectionRule.MISSING_CITATION,
                criterion=finding.criterion,
                detail=(
                    f"A Finding that is {finding.finding_outcome} must cite at least one "
                    "Utterance that shows it."
                ),
            )
        )
    return rejections


def check_complete(scorecard: Scorecard, recorded: list[Finding]) -> list[Rejection]:
    """One MISSING_FINDING Rejection for every Criterion that has no Finding yet."""
    judged = {finding.criterion for finding in recorded}
    return [
        Rejection(
            rejection_rule=RejectionRule.MISSING_FINDING,
            criterion=criterion.criterion_id,
            detail=f"Criterion '{criterion.criterion_id}' has no Finding.",
        )
        for criterion in scorecard.criteria
        if criterion.criterion_id not in judged
    ]
