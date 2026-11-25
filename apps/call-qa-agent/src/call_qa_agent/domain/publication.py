"""The way an Evaluation reaches the Representative: a state machine over its PublicationState.

The model proposes, a person permits, the system commits (DEC-0010):

    nothing   -> STAGED     a complete Evaluation is staged
    STAGED    -> PUBLISHED  its disposition is FINAL, or a Review has CONFIRMED it
    STAGED    -> WITHHELD   a Review has OVERTURNED it
    PUBLISHED, WITHHELD     lead nowhere

Each function here answers one request for a change. It returns the AuditRecord
of the change it permits and raises `Refused` otherwise. `CHANGES` is the only
place that says which changes exist, and `_enter` is the only place an
AuditRecord is made, so a change that is not in the table cannot be made and
is never passed over in silence. What is known of an Evaluation is its
disposition, the Reviews made of it and its AuditRecords, oldest first: its
PublicationState is the one its last AuditRecord entered.

Nothing here reads a clock or a file. Whoever calls says who the actor is and
what time it is, and keeps what comes back: see `ledger.py`.

This module is part of the domain layer. Its vocabulary is the call-qa glossary
(ontology/domains/call-qa.yaml) and its types are generated from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ..generated import (
    AuditRecord,
    Disposition,
    Evaluation,
    PublicationState,
    Rejection,
    RejectionRule,
    Review,
    ReviewOutcome,
)

# Every change of PublicationState there is. None stands for an Evaluation that is not staged.
CHANGES: dict[PublicationState | None, tuple[PublicationState, ...]] = {
    None: (PublicationState.STAGED,),
    PublicationState.STAGED: (PublicationState.PUBLISHED, PublicationState.WITHHELD),
    PublicationState.PUBLISHED: (),
    PublicationState.WITHHELD: (),
}


class Refused(ValueError):
    """A change of PublicationState, or a Review, that is not permitted.

    `rejections` names the rule that was broken where the glossary has one.
    Only REVIEW_REQUIRED is such a rule. The other refusals have no
    RejectionRule, so they carry a reason and no Rejection.
    """

    def __init__(self, reason: str, rejections: Sequence[Rejection] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rejections = list(rejections)


def publication_state(records: Sequence[AuditRecord]) -> PublicationState | None:
    """Where an Evaluation stands, given its AuditRecords oldest first. None: it is not staged."""
    return PublicationState(records[-1].publication_state) if records else None


def stage(
    evaluation: Evaluation, records: Sequence[AuditRecord], *, actor: str, recorded_at: datetime
) -> AuditRecord:
    """Stage a complete Evaluation. Refused if one of its Call and Scorecard already has a state."""
    return _enter(
        PublicationState.STAGED,
        records,
        call=evaluation.call,
        scorecard=evaluation.scorecard,
        actor=actor,
        recorded_at=recorded_at,
    )


def review(
    made: Review, disposition: Disposition, records: Sequence[AuditRecord]
) -> AuditRecord | None:
    """Take a Review of a STAGED Evaluation whose disposition is not FINAL.

    A CONFIRMED Review changes no state, so there is no AuditRecord: it is what
    `publish` looks for. An OVERTURNED one gives the AuditRecord of WITHHELD,
    with the reviewer as its actor. Any other Review is refused.
    """
    # A Review is taken while it could still withhold the Evaluation, and not after.
    _permitted(PublicationState.WITHHELD, records, made.call, made.scorecard, "be reviewed")
    if Disposition(disposition) is Disposition.FINAL:
        raise Refused(
            f"the Evaluation of {made.call} against {made.scorecard} has the disposition "
            f"{Disposition.FINAL.value}: it stands without a Review"
        )
    match ReviewOutcome(made.review_outcome):
        case ReviewOutcome.CONFIRMED:
            return None
        case ReviewOutcome.OVERTURNED:
            return _enter(
                PublicationState.WITHHELD,
                records,
                call=made.call,
                scorecard=made.scorecard,
                actor=made.reviewer,
                recorded_at=made.reviewed_at,
            )


def publish(
    call: str,
    scorecard: str,
    disposition: Disposition,
    reviews: Sequence[Review],
    records: Sequence[AuditRecord],
    *,
    actor: str,
    recorded_at: datetime,
) -> AuditRecord:
    """Publish the STAGED Evaluation of a Call against a Scorecard.

    Refused with a REVIEW_REQUIRED Rejection unless the disposition is FINAL or
    one of the Reviews is of this Call and Scorecard and CONFIRMED it. The guard
    is on the disposition, whatever caused it (DEC-0010).
    """
    _permitted(PublicationState.PUBLISHED, records, call, scorecard, "be published")
    confirmed = any(
        ReviewOutcome(made.review_outcome) is ReviewOutcome.CONFIRMED
        and (made.call, made.scorecard) == (call, scorecard)
        for made in reviews
    )
    if Disposition(disposition) is not Disposition.FINAL and not confirmed:
        reason = (
            f"the Evaluation of {call} against {scorecard} has the disposition "
            f"{Disposition(disposition).value} and no Review has confirmed it"
        )
        raise Refused(
            reason,
            [
                Rejection(
                    rejection_rule=RejectionRule.REVIEW_REQUIRED,
                    detail=f"{reason[0].upper()}{reason[1:]}. A Review must confirm it first.",
                    allowed_values=[ReviewOutcome.CONFIRMED.value],
                )
            ],
        )
    return _enter(
        PublicationState.PUBLISHED,
        records,
        call=call,
        scorecard=scorecard,
        actor=actor,
        recorded_at=recorded_at,
    )


def _enter(
    state: PublicationState,
    records: Sequence[AuditRecord],
    *,
    call: str,
    scorecard: str,
    actor: str,
    recorded_at: datetime,
) -> AuditRecord:
    """The one place an AuditRecord is made: one for a change `CHANGES` has, and none otherwise."""
    _permitted(state, records, call, scorecard, f"become {state.value}")
    return AuditRecord(
        call=call,
        scorecard=scorecard,
        publication_state=state,
        actor=actor,
        recorded_at=recorded_at,
    )


def _permitted(
    state: PublicationState, records: Sequence[AuditRecord], call: str, scorecard: str, what: str
) -> None:
    """Refuse unless the Evaluation stands where `CHANGES` lets it enter `state`."""
    current = publication_state(records)
    if state in CHANGES[current]:
        return
    if current is None:
        raise Refused(f"no Evaluation of {call} against {scorecard} is staged, so none can {what}")
    raise Refused(
        f"the Evaluation of {call} against {scorecard} is {current.value}, so it cannot {what}"
    )
