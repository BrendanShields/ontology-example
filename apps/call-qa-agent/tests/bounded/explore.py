"""Bounded exploration of the write path: every case within a stated bound, through the real code.

Nothing here re-models the code. Every Evaluation is built by the real
`scoring.conclude`, every state is a real `EvaluationSession`, every loop
run is the real `agent.evaluate` answered by a scripted client, and every
ledger is a real file written by the real `Ledger`. The only hand-written
logic is the oracle: the properties, written from the Requirement sentences in
work/ and the glossary, not from the code.

A check that returns has held for every case within its bound. That is not a
proof: a fault that needs a larger Scorecard, a longer script or an input
outside the alphabet below is not covered.

    cd apps/call-qa-agent && uv run python -m tests.bounded.explore [scoring|session|loop|ledger]

A violation names the property and the first case that breaks it. Cases are
visited smallest first, and a case is described by ids, outcomes, weights and
Utterance numbers only.
"""

from __future__ import annotations

import copy
import itertools
import json
import sys
import tempfile
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from call_qa_agent import agent as agent_module
from call_qa_agent import ledger as ledger_module
from call_qa_agent.domain import publication, scoring
from call_qa_agent.generated import (
    AuditRecord,
    Call,
    Criterion,
    Disposition,
    Evaluation,
    EvaluationOutcome,
    Finding,
    FindingOutcome,
    PublicationState,
    RejectionRule,
    Review,
    ReviewOutcome,
    Scorecard,
    Speaker,
)
from call_qa_agent.session import EvaluationSession
from call_qa_agent.tools import FINISH_EVALUATION, RECORD_FINDING

MET = FindingOutcome.MET.value
NOT_MET = FindingOutcome.NOT_MET.value
NOT_APPLICABLE = FindingOutcome.NOT_APPLICABLE.value
OUTCOMES = tuple(outcome.value for outcome in FindingOutcome)

# A synthetic Call. What its two Utterances say is a placeholder and is never read.
CALL = Call.model_validate(
    {
        "call_id": "CALL-9000",
        "representative": "REP-9000",
        "utterances": [
            {"sequence": 1, "speaker": Speaker.CUSTOMER.value, "text": "x"},
            {"sequence": 2, "speaker": Speaker.REPRESENTATIVE.value, "text": "y"},
        ],
    }
)
SPOKEN = {1, 2}

PROPERTIES = {
    # scoring: REQ-0004, REQ-0005, REQ-0006, REQ-0010
    "S1": "the score is between 0 and 100, and the Evaluation carries the score of its Findings",
    "S2": "a NOT_MET Finding for a critical Criterion gives FAIL and NEEDS_REVIEW",
    "S3": "PASS exactly when no critical Criterion is NOT_MET and the score is at least the pass mark",
    "S4": "FINAL exactly when no critical Criterion is NOT_MET and at least one Criterion applied",
    "S5": "the Evaluation carries exactly the Findings it was given, whole and in order",
    "S6": "the score is the met share of the weight that applied, rounded down, and 0 when nothing applied",
    "S7": "there is an Evaluation exactly when the Findings given are one for each Criterion",
    # session: REQ-0001, REQ-0002, REQ-0003
    "G1": "a rejected proposal is not recorded and changes nothing",
    "G2": "an accepted proposal is recorded once and whole, after the Findings already recorded",
    "G3": "the Rejections name exactly the rules the proposal breaks, for the Criterion proposed",
    "G4": "finish completes the Evaluation exactly when every Criterion has a Finding",
    "G5": "finish otherwise answers one MISSING_FINDING for each Criterion with no Finding",
    "G6": "a complete Evaluation holds the recorded Findings whole, exactly one per Criterion",
    "G7": "a complete Evaluation never changes",
    # loop: REQ-0007
    "L1": "the loop makes no more requests than the turn limit",
    "L2": "the loop returns an Evaluation exactly when the model completed one, otherwise reports none, and then makes no further request",
    "L3": "a returned Evaluation has the Findings that were accepted, whole, one per Criterion",
    "L4": "with no Evaluation, the outstanding Rejections are the Criteria with no Finding",
    "L5": "every tool call of a turn is answered once, in order, in the next request",
    "L6": "the Evaluation is the one the domain layer computes from the accepted Findings",
    # ledger: REQ-0016 to REQ-0025
    "P1": "staging an Evaluation of a Call and Scorecard that have none on the ledger gives STAGED",
    "P2": "another Evaluation of the same Call against the same Scorecard is refused and changes nothing",
    "P3": "an Evaluation whose disposition is not FINAL is PUBLISHED only after a Review CONFIRMED it",
    "P4": "publishing without the Review it needs is answered with REVIEW_REQUIRED alone, and no other refusal names a rule",
    "P5": "once an Evaluation is PUBLISHED or WITHHELD its state never changes and nothing more is recorded of it",
    "P6": "an OVERTURNED Review gives WITHHELD, a CONFIRMED one is recorded and leaves the Evaluation STAGED",
    "P7": "a Review is recorded only of a STAGED Evaluation whose disposition is not FINAL",
    "P8": "a STAGED Evaluation that is FINAL, or that a Review CONFIRMED, is PUBLISHED when asked",
    "P9": "a change of state adds exactly one AuditRecord, of the state entered, by its actor at its time, and nothing else adds one",
    "P10": "a line of the ledger holds identifiers, states, times and a digest under known names, and nothing else",
    "P11": "a refused command adds nothing to the ledger, and no command changes a line already there",
    "P12": "a command given again is answered as done already and adds nothing",
    "P13": "the ledger reads back without complaint as what the commands were answered",
}


class PropertyViolation(AssertionError):
    def __init__(self, prop: str, case: dict) -> None:
        shown = ", ".join(f"{name}={value!r}" for name, value in case.items())
        super().__init__(f"{prop} does not hold: {PROPERTIES[prop]}. Smallest case: {shown}")
        self.prop = prop


def require(condition: bool, prop: str, **case) -> None:
    if not condition:
        raise PropertyViolation(prop, case)


def criterion_ids(count: int) -> list[str]:
    return [f"c{index}" for index in range(count)]


def make_scorecard(
    weights: Iterable[int], critical: Iterable[bool], pass_mark: int = 50
) -> Scorecard:
    return Scorecard(
        scorecard_id="bounded-v1",
        pass_mark=pass_mark,
        criteria=[
            Criterion(criterion_id=f"c{index}", statement="s", weight=weight, critical=is_critical)
            for index, (weight, is_critical) in enumerate(zip(weights, critical, strict=True))
        ],
    )


# --------------------------------------------------------------------------- scoring


def check_scoring(max_criteria: int = 3, max_weight: int = 3) -> dict:
    """Every Scorecard within the bound, with every combination of outcomes and every pass mark.

    The bound: 1 to `max_criteria` Criteria, each with a weight of 1 to
    `max_weight` and critical or not, one Finding per Criterion with any
    outcome, and every pass mark from 0 to 100.

    S1 to S6 leave one score, outcome and disposition for each case, so what
    follows from them (raising a Finding never lowers the score, for one) is
    not checked again: no fault could be reported by it first.

    For S7 the Findings are any list of 0 to one more than the number of
    Criteria, over the Criteria and one unknown one.
    """
    findings = {
        (index, outcome): Finding(
            criterion=f"c{index}", finding_outcome=outcome, cited_utterances=[1], rationale="r"
        )
        for index in range(max_criteria)
        for outcome in OUTCOMES
    }
    evaluations = finding_lists = 0
    for count in range(1, max_criteria + 1):
        ids = criterion_ids(count)
        card = make_scorecard([1] * count, [False] * count)
        for length in range(0, count + 2):
            for criteria in itertools.product([*ids, "zz"], repeat=length):
                finding_lists += 1
                given = [
                    Finding(criterion=c, finding_outcome=MET, cited_utterances=[1], rationale="r")
                    for c in criteria
                ]
                try:
                    scoring.conclude(CALL, card, given)
                    answer = "an Evaluation"
                except ValueError:
                    answer = "no Evaluation"
                except Exception as error:
                    answer = f"raised {type(error).__name__}"
                want = "an Evaluation" if sorted(criteria) == ids else "no Evaluation"
                require(answer == want, "S7", criteria=ids, findings_for=criteria, got=answer)
        for weights in itertools.product(range(1, max_weight + 1), repeat=count):
            for critical in itertools.product((False, True), repeat=count):
                card = make_scorecard(weights, critical)
                for outcomes in itertools.product(OUTCOMES, repeat=count):
                    case = {"weights": weights, "critical": critical, "outcomes": outcomes}
                    given = [findings[(index, outcome)] for index, outcome in enumerate(outcomes)]
                    whole = _whole(given)
                    points = scoring.score(given, card)
                    require(0 <= points <= 100, "S1", **case, score=points)

                    # REQ-0004 as an inequality, so the oracle does not repeat the code's
                    # formula: points/100 <= met/applied < (points + 1)/100.
                    judged = list(zip(weights, outcomes, strict=True))
                    met = sum(weight for weight, outcome in judged if outcome == MET)
                    applied = sum(weight for weight, outcome in judged if outcome != NOT_APPLICABLE)
                    if applied:
                        floored = points * applied <= 100 * met < (points + 1) * applied
                        require(floored, "S6", **case, score=points)
                    else:
                        require(points == 0, "S6", **case, score=points)

                    critical_failure = any(
                        is_critical and outcome == NOT_MET
                        for is_critical, outcome in zip(critical, outcomes, strict=True)
                    )
                    for pass_mark in range(0, 101):
                        marked = card.model_copy(update={"pass_mark": pass_mark})
                        evaluation = scoring.conclude(CALL, marked, given)
                        evaluations += 1
                        case["pass_mark"] = pass_mark
                        passed = evaluation.evaluation_outcome == EvaluationOutcome.PASS
                        final = evaluation.disposition == Disposition.FINAL
                        require(evaluation.score == points, "S1", **case, score=evaluation.score)
                        require(not (critical_failure and (passed or final)), "S2", **case)
                        require(
                            passed == (not critical_failure and points >= pass_mark),
                            "S3",
                            **case,
                            score=points,
                        )
                        require(final == (not critical_failure and applied > 0), "S4", **case)
                        require(_whole(evaluation.findings) == whole, "S5", **case)
    return {"evaluations": evaluations, "finding_lists": finding_lists}


def _judgements(findings: Iterable[Finding]) -> list[tuple[str, str]]:
    return [(finding.criterion, _value(finding.finding_outcome)) for finding in findings]


def _whole(findings: Iterable[Finding]) -> list[tuple]:
    """Every field of each Finding. Compared and never shown: a rationale stays out of messages."""
    return [
        (f.criterion, _value(f.finding_outcome), f.cited_utterances, f.rationale) for f in findings
    ]


def _value(member) -> str:
    return getattr(member, "value", member)


# --------------------------------------------------------------------------- session


def proposals(count: int) -> list[tuple[str, object]]:
    """Every proposal of the bounded proposer for a Scorecard of `count` Criteria, with a label."""
    out: list[tuple[str, object]] = []
    for criterion in [*criterion_ids(count), "zz"]:
        for outcome in OUTCOMES:
            for cited in (None, [], [1], [2, 1], [9], [1, 9]):
                proposal = {"criterion": criterion, "finding_outcome": outcome, "rationale": "r"}
                if cited is not None:
                    proposal["cited_utterances"] = cited
                out.append((f"{criterion} {outcome} cites {cited}", proposal))
    well_formed = {
        "criterion": "c0",
        "finding_outcome": MET,
        "cited_utterances": [1],
        "rationale": "r",
    }
    out += [
        ("an empty object", {}),
        ("a string", "text"),
        ("nothing", None),
        ("an outcome outside the glossary", {**well_formed, "finding_outcome": "MAYBE"}),
        ("no rationale", {k: v for k, v in well_formed.items() if k != "rationale"}),
        ("a score added by the proposer", {**well_formed, "score": 100}),
        ("a number as the Criterion", {**well_formed, "criterion": 7}),
    ]
    return out


def broken_rules(proposal: object, count: int, recorded: tuple[str, ...]) -> set[str]:
    """The oracle: the rules of the glossary a proposal breaks. None broken means acceptable."""
    malformed = {RejectionRule.MALFORMED_FINDING.value}
    if not isinstance(proposal, dict):
        return malformed
    if set(proposal) - {"criterion", "finding_outcome", "cited_utterances", "rationale"}:
        return malformed
    if not {"criterion", "finding_outcome", "rationale"} <= set(proposal):
        return malformed
    criterion, outcome = proposal["criterion"], proposal["finding_outcome"]
    if not isinstance(criterion, str) or outcome not in OUTCOMES:
        return malformed
    cited = proposal.get("cited_utterances") or []
    broken = set()
    if criterion not in criterion_ids(count):
        broken.add(RejectionRule.UNKNOWN_CRITERION.value)  # REQ-0001
    elif criterion in recorded:
        broken.add(RejectionRule.DUPLICATE_FINDING.value)  # REQ-0001
    if set(cited) - SPOKEN:
        broken.add(RejectionRule.UNKNOWN_UTTERANCE.value)  # REQ-0002
    if outcome != NOT_APPLICABLE and not cited:
        broken.add(RejectionRule.MISSING_CITATION.value)  # REQ-0003
    return broken


def _state(session: EvaluationSession) -> tuple[tuple[tuple[str, str], ...], bool]:
    return tuple(_judgements(session.findings)), session.evaluation is not None


def check_session(max_criteria: int = 3) -> dict:
    """Every state a real EvaluationSession can reach, under every bounded proposal and finish.

    The bound: a Scorecard of 1 to `max_criteria` Criteria, a Call of two
    Utterances, and the proposals of `proposals`: every Criterion and one
    unknown one, every outcome, six ways of citing, and seven things that are
    not a Finding at all.

    Two states are the same when they hold the same Criteria and outcomes in the
    same order. What a recorded Finding cites does not make a new state, so each
    way of citing is tried from every state but not carried into every later one.
    The Findings are still compared whole at every step.
    """
    states = transitions = 0
    for count in range(1, max_criteria + 1):
        ids = criterion_ids(count)
        card = make_scorecard([1] * count, [index == 0 for index in range(count)])
        offered = proposals(count)
        start = EvaluationSession(CALL, card)
        seen = {_state(start)}
        frontier = deque([start])
        while frontier:
            current = frontier.popleft()  # breadth first: the fewest steps come first
            states += 1
            before = _state(current)
            held = _whole(current.findings)
            recorded = tuple(criterion for criterion, _ in before[0])
            case = {"criteria": ids, "recorded": before[0]}

            if before[1]:
                kept = current.evaluation
                require(_whole(kept.findings) == held, "G6", **case)
                require(sorted(recorded) == ids, "G6", **case)
                for label, proposal in offered:
                    probe = copy.deepcopy(current)
                    transitions += 1
                    try:
                        probe.record_finding(proposal)
                    except RuntimeError:
                        refused = True
                    else:
                        refused = False
                    require(refused and _state(probe) == before, "G7", **case, proposal=label)
                    require(probe.evaluation == kept, "G7", **case, proposal=label)
                transitions += 1
                require(current.finish() == [] and current.evaluation is kept, "G7", **case)
                continue

            for label, proposal in offered:
                after_proposal = copy.deepcopy(current)
                rejections = after_proposal.record_finding(proposal)
                transitions += 1
                after = _state(after_proposal)
                case["proposal"] = label
                named = {_value(rejection.rejection_rule) for rejection in rejections}
                broken = broken_rules(proposal, count, recorded)
                require(named == broken, "G3", **case, named=sorted(named), broken=sorted(broken))
                proposed = proposal.get("criterion") if isinstance(proposal, dict) else None
                about = {rejection.criterion for rejection in rejections}
                require(about <= {proposed if isinstance(proposed, str) else None}, "G3", **case)
                if rejections:
                    require(after == before, "G1", **case)
                    require(_whole(after_proposal.findings) == held, "G1", **case)
                else:
                    # Citing nothing and not citing are told apart: neither becomes the other.
                    proposed_whole = (
                        proposal["criterion"],
                        proposal["finding_outcome"],
                        proposal.get("cited_utterances"),
                        proposal["rationale"],
                    )
                    require(
                        _whole(after_proposal.findings) == [*held, proposed_whole], "G2", **case
                    )
                    require(after_proposal.evaluation is None, "G2", **case)
                if after not in seen:
                    seen.add(after)
                    frontier.append(after_proposal)

            del case["proposal"]
            finished = copy.deepcopy(current)
            try:
                rejections = finished.finish()
            except Exception as error:
                raise PropertyViolation("G4", {**case, "raised": type(error).__name__}) from None
            transitions += 1
            after = _state(finished)
            missing = [criterion for criterion in ids if criterion not in recorded]
            require(after == (before[0], not missing), "G4", **case)
            require(_whole(finished.findings) == held, "G4", **case)
            require((not rejections) == (not missing), "G4", **case)
            require(
                [(_value(r.rejection_rule), r.criterion) for r in rejections]
                == [(RejectionRule.MISSING_FINDING.value, criterion) for criterion in missing],
                "G5",
                **case,
            )
            if after not in seen:
                seen.add(after)
                frontier.append(finished)
    return {"states": states, "transitions": transitions}


# --------------------------------------------------------------------------- the loop


@dataclass
class ScriptedClient:
    """Stands in for the Claude API: it answers request k with turn k of the script.

    The replies are plain objects, not SDK responses, so the SDK's parsing and
    the fallback request path are outside what the loop check covers.
    """

    script: tuple
    requests: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        index = len(self.requests)
        self.requests.append(list(request["messages"]))
        if index >= len(self.script):
            raise PropertyViolation("L1", {"turn_limit": len(self.script), "requests": index + 1})
        stop_reason, calls = self.script[index]
        content = [
            SimpleNamespace(type="tool_use", id=f"t{index}_{position}", name=name, input=tool_input)
            for position, (name, tool_input) in enumerate(calls)
        ]
        return SimpleNamespace(stop_reason=stop_reason, content=content, model="scripted")


def _accepted(criterion: str) -> tuple[str, dict]:
    return (
        RECORD_FINDING,
        {"criterion": criterion, "finding_outcome": MET, "cited_utterances": [1], "rationale": "r"},
    )


_UNCITED = (
    RECORD_FINDING,
    {"criterion": "c0", "finding_outcome": MET, "cited_utterances": [], "rationale": "r"},
)
_FINISH = (FINISH_EVALUATION, {})

# The alphabet: every kind of turn the scripted model can take, for a Scorecard of two Criteria.
TURNS = {
    "declines": ("refusal", ()),
    "cut-off": ("max_tokens", ()),
    "no-tool": ("end_turn", ()),
    "c0": ("tool_use", (_accepted("c0"),)),
    "c1": ("tool_use", (_accepted("c1"),)),
    "uncited": ("tool_use", (_UNCITED,)),
    "finish": ("tool_use", (_FINISH,)),
    "unknown-tool": ("tool_use", (("no_such_tool", {}),)),
    "c0+c1": ("tool_use", (_accepted("c0"), _accepted("c1"))),
    "c1+finish": ("tool_use", (_accepted("c1"), _FINISH)),
    "finish+c0": ("tool_use", (_FINISH, _accepted("c0"))),
    "c0+c1+finish+c0": ("tool_use", (_accepted("c0"), _accepted("c1"), _FINISH, _accepted("c0"))),
    "c0+finish+c1": ("tool_use", (_accepted("c0"), _FINISH, _accepted("c1"))),
}
LOOP_CRITERIA = criterion_ids(2)

EVALUATED = "evaluated"
DECLINED = "declined"
CUT_OFF = "cut off"
OUT_OF_TURNS = "out of turns"


@dataclass
class Expected:
    """What REQ-0007, REQ-0001 and DEC-0006 say a script must lead to."""

    result: str
    requests: int
    accepted: list[dict]  # the tool inputs that were acceptable, in order

    @property
    def judged(self) -> list[str]:
        return [tool_input["criterion"] for tool_input in self.accepted]

    @property
    def missing(self) -> list[str]:
        return [criterion for criterion in LOOP_CRITERIA if criterion not in self.judged]


def expected(script: tuple[str, ...]) -> Expected:
    """The oracle for the loop, written from the Requirements and not from agent.py."""
    accepted: list[dict] = []
    judged: list[str] = []
    for turn, name in enumerate(script, start=1):
        stop_reason, calls = TURNS[name]
        if stop_reason == "refusal":
            return Expected(DECLINED, turn, accepted)
        if stop_reason == "max_tokens":
            return Expected(CUT_OFF, turn, accepted)
        complete = not calls and sorted(judged) == LOOP_CRITERIA
        for tool, tool_input in calls:
            if complete:
                break
            if tool == RECORD_FINDING:
                criterion = tool_input["criterion"]
                if tool_input["cited_utterances"] and criterion not in judged:
                    accepted.append(tool_input)
                    judged.append(criterion)
            elif tool == FINISH_EVALUATION:
                complete = sorted(judged) == LOOP_CRITERIA
        if complete:
            return Expected(EVALUATED, turn, accepted)
    return Expected(OUT_OF_TURNS, len(script), accepted)


@dataclass
class Run:
    """What one run of the real loop showed from the outside."""

    script: tuple[str, ...]
    result: str
    requests: list
    steps: list
    evaluation: Evaluation | None
    rejections: list


def run_loop(script: tuple[str, ...], card: Scorecard) -> Run:
    client = ScriptedClient(tuple(TURNS[name] for name in script))
    settings = agent_module.Settings(max_turns=len(script), refusal_fallback=False)
    trace = agent_module.Trace()
    evaluation, rejections = None, []
    try:
        evaluation = agent_module.evaluate(CALL, card, client, settings, trace)
        result = EVALUATED
    except agent_module.EvaluationIncomplete as stopped:
        rejections = stopped.rejections
        if "declined" in stopped.reason:
            result = DECLINED
        elif "cut off" in stopped.reason:
            result = CUT_OFF
        else:
            result = OUT_OF_TURNS
    except PropertyViolation:
        raise
    except Exception as error:
        result = f"raised {type(error).__name__}"
    return Run(script, result, client.requests, trace.steps, evaluation, rejections)


def check_loop(max_turns: int = 4, observe: Callable[[Run], None] | None = None) -> dict:
    """The real agent.evaluate under every script of up to `max_turns` turns.

    The bound: a Scorecard of two Criteria, a turn limit equal to the length of
    the script, and every sequence of the thirteen kinds of turn in TURNS.
    """
    card = make_scorecard([1, 3], [True, False])
    runs = 0
    for length in range(0, max_turns + 1):
        for script in itertools.product(TURNS, repeat=length):
            runs += 1
            run = run_loop(script, card)
            want = expected(script)
            case = {"script": script}
            require(len(run.requests) <= length, "L1", **case, requests=len(run.requests))
            require(run.result == want.result, "L2", **case, got=run.result, want=want.result)
            require(len(run.requests) == want.requests, "L2", **case, requests=len(run.requests))
            if run.evaluation is not None:
                found = [finding.criterion for finding in run.evaluation.findings]
                require(found == want.judged, "L3", **case, findings=found)
                given = [
                    (i["criterion"], i["finding_outcome"], i["cited_utterances"], i["rationale"])
                    for i in want.accepted
                ]
                require(_whole(run.evaluation.findings) == given, "L3", **case, findings=found)
                require(sorted(found) == LOOP_CRITERIA, "L3", **case, findings=found)
                recomputed = scoring.conclude(CALL, card, list(run.evaluation.findings))
                require(recomputed == run.evaluation, "L6", **case)
            else:
                require(
                    [(_value(r.rejection_rule), r.criterion) for r in run.rejections]
                    == [(RejectionRule.MISSING_FINDING.value, c) for c in want.missing],
                    "L4",
                    **case,
                )
            for index in range(1, len(run.requests)):
                asked = TURNS[script[index - 1]][1]
                answer = run.requests[index][-1]["content"]
                if asked:
                    answered = [block["tool_use_id"] for block in answer]
                    in_order = [f"t{index - 1}_{position}" for position in range(len(asked))]
                    require(answered == in_order, "L5", **case, turn=index)
            if observe is not None:
                observe(run)
    return {"runs": runs}


# --------------------------------------------------------------------------- the ledger

LEDGER_CARD = make_scorecard([1, 1], [True, False])


def _concluded(*outcomes: str, cited: int = 1) -> Evaluation:
    return scoring.conclude(
        CALL,
        LEDGER_CARD,
        [
            Finding(
                criterion=f"c{index}",
                finding_outcome=outcome,
                cited_utterances=[cited],
                rationale="r",
            )
            for index, outcome in enumerate(outcomes)
        ],
    )


# Four Evaluations of the one Call against the one Scorecard, two of each disposition.
# NEEDS_REVIEW has two causes and both are here: a failed critical Criterion, and nothing applied.
_OUTCOMES = {
    "stands": (MET, MET),
    "stands-too": (MET, NOT_MET),
    "critical-failure": (NOT_MET, MET),
    "nothing-applied": (NOT_APPLICABLE, NOT_APPLICABLE),
}
EVALUATIONS = {name: _concluded(*outcomes) for name, outcomes in _OUTCOMES.items()}
# For each, another Evaluation with the same outcome for every Criterion, the same score and
# the same disposition, whose Findings cite another Utterance. It is not a command of the
# alphabet: it is offered once after each staging, and has to be refused (DEC-0012).
TWINS = {name: _concluded(*outcomes, cited=2) for name, outcomes in _OUTCOMES.items()}
REVIEWERS = ("QA-1", "QA-2")
STAGE, REVIEW, PUBLISH = "stage", "review", "publish"
# The alphabet: every command there is, on the one Call and Scorecard.
COMMANDS = (
    *((STAGE, name) for name in EVALUATIONS),
    *((REVIEW, reviewer, outcome) for reviewer in REVIEWERS for outcome in ReviewOutcome),
    (PUBLISH,),
)
KEY = (CALL.call_id, LEDGER_CARD.scorecard_id)
TERMINAL = (PublicationState.PUBLISHED, PublicationState.WITHHELD)
LINE_NAMES = {
    "audit_record": set(AuditRecord.model_fields),
    "review": set(Review.model_fields),
    "disposition": None,
    "sha256": None,
}

RECORDED = "recorded"
DONE_ALREADY = "done already"
REFUSED = "refused"


@dataclass(frozen=True)
class Known:
    """What the Requirements say the ledger holds after the commands so far."""

    staged: str | None = None  # the name of the Evaluation on the ledger
    state: PublicationState | None = None
    reviews: tuple[tuple[str, ReviewOutcome], ...] = ()
    records: int = 0

    @property
    def disposition(self) -> Disposition | None:
        return Disposition(EVALUATIONS[self.staged].disposition) if self.staged else None

    @property
    def confirmed(self) -> bool:
        return any(outcome is ReviewOutcome.CONFIRMED for _, outcome in self.reviews)


def wanted(known: Known, command: tuple) -> tuple[str, bool, Known]:
    """The oracle for the ledger: (the answer, whether REVIEW_REQUIRED is why, what is then known).

    Written from REQ-0016 to REQ-0025 and DEC-0012, not from ledger.py.
    """
    refused = (REFUSED, False, known)
    done_already = (DONE_ALREADY, False, known)
    if command[0] == STAGE:
        if known.staged is None:  # REQ-0022
            return RECORDED, False, Known(command[1], PublicationState.STAGED, (), 1)
        return done_already if known.staged == command[1] else refused  # REQ-0024, REQ-0023
    if command[0] == REVIEW:
        made = (command[1], command[2])
        if known.staged is None:
            return refused
        if made in known.reviews:  # REQ-0024
            return done_already
        if known.state is not PublicationState.STAGED or known.disposition is Disposition.FINAL:
            return refused  # REQ-0018, REQ-0020
        withheld = command[2] is ReviewOutcome.OVERTURNED  # REQ-0019
        return (
            RECORDED,
            False,
            replace(
                known,
                state=PublicationState.WITHHELD if withheld else known.state,
                reviews=(*known.reviews, made),
                records=known.records + withheld,
            ),
        )
    if known.state is PublicationState.PUBLISHED:  # REQ-0024
        return done_already
    if known.state is not PublicationState.STAGED:  # REQ-0018, and nothing is staged
        return refused
    if known.disposition is not Disposition.FINAL and not known.confirmed:
        return REFUSED, True, known  # REQ-0016, REQ-0017
    published = replace(known, state=PublicationState.PUBLISHED, records=known.records + 1)
    return RECORDED, False, published  # REQ-0025


@dataclass
class Clock:
    """Stands in for the time of day: each reading is one second after the last."""

    at: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.at += timedelta(seconds=1)
        return self.at


@dataclass
class Answer:
    """What one command given to the real Ledger showed from the outside."""

    answer: str
    rules: list[str]
    lines: list[str]  # the lines it added to the file
    entry: ledger_module.Entry | None
    asked_at: datetime


def give(path: Path, clock: Clock, command: tuple, script: tuple = ()) -> Answer:
    """Give one command to the real Ledger over the file, and read the file before and after.

    `script` is the commands the file already holds the effect of: it is only shown.
    """
    case = {"commands": [_shown(c) for c in (*script, command)]}
    before = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    ledger = ledger_module.Ledger(path, clock)
    asked_at, rules = clock.at, []
    try:
        if command[0] == STAGE:
            recorded = ledger.stage(EVALUATIONS[command[1]])
        elif command[0] == REVIEW:
            recorded = ledger.review(*KEY, command[1], command[2])
        else:
            recorded = ledger.publish(*KEY)
        answer = RECORDED if recorded else DONE_ALREADY
    except publication.Refused as refused:
        answer = REFUSED
        rules = [_value(rejection.rejection_rule) for rejection in refused.rejections]
    after = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = after[len(before) :]
    # Both are read from the file as text, before anything tries to make sense of it.
    require(after[: len(before)] == before, "P11", **case)
    require(not (answer == REFUSED and lines), "P11", **case, lines=len(lines))
    for line in lines:
        held = json.loads(line)
        named = all(
            name in LINE_NAMES and (LINE_NAMES[name] is None or set(held[name]) <= LINE_NAMES[name])
            for name in held
        )
        require(named, "P10", **case, names=sorted(held))
    try:
        entry = ledger_module.Ledger(path, clock).entry(*KEY)
    except ledger_module.Corrupt:
        raise PropertyViolation("P13", {**case, "read": "Corrupt"}) from None
    return Answer(answer, rules, lines, entry, asked_at)


def _shown(command: tuple) -> str:
    return " ".join(_value(part) for part in command)


def _standing(entry: ledger_module.Entry | None) -> PublicationState | None:
    return entry.publication_state if entry else None


def check_ledger(max_commands: int = 4, observe: Callable | None = None) -> dict:
    """The real Ledger, on a real file, under every sequence of up to `max_commands` commands.

    The bound: one Call and one Scorecard, four Evaluations of them (two of
    each disposition, NEEDS_REVIEW by each of its two causes), two reviewers,
    and the nine commands of COMMANDS: stage each Evaluation, each reviewer's
    Review with each outcome, and publish. Every command is also given a
    second time straight after the first. After each staging, the twin of the
    Evaluation staged is offered as well: the same outcomes, score and
    disposition, with Findings that cite another Utterance.

    A sequence that starts like another shares its first commands with it:
    the file is put back as it was before each next command is tried.
    """
    dispositions = sorted(evaluation.disposition for evaluation in EVALUATIONS.values())
    assert dispositions == sorted(2 * [disposition.value for disposition in Disposition])
    sequences = commands = 0
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "ledger.jsonl"
        clock = Clock()
        frontier: deque[tuple[tuple, Known, str]] = deque([((), Known(), "")])
        while frontier:
            script, known, text = frontier.popleft()  # breadth first: the fewest commands first
            sequences += 1
            if len(script) == max_commands:
                continue
            for command in COMMANDS:
                path.write_text(text, encoding="utf-8")
                before = ledger_module.Ledger(path, clock).entry(*KEY)
                want, review_required, then = wanted(known, command)
                got = give(path, clock, command, script)
                commands += 1
                _check_answer(script, command, known, before, want, review_required, then, got)
                if command[0] == STAGE and got.answer == RECORDED:
                    _check_twin(path, clock, script, command)
                if observe is not None:
                    observe(before, command, got)
                after = path.read_text(encoding="utf-8")

                again = give(path, clock, command, (*script, command))
                case = {"commands": [_shown(c) for c in (*script, command)], "again": True}
                if got.answer == REFUSED:
                    require(again.answer == REFUSED and again.rules == got.rules, "P12", **case)
                else:
                    require(again.answer == DONE_ALREADY, "P12", **case, answer=again.answer)
                require(not again.lines and again.entry == got.entry, "P12", **case)

                frontier.append(((*script, command), then, after))
    return {"sequences": sequences, "commands": commands}


def _check_twin(path: Path, clock: Clock, script: tuple, command: tuple) -> None:
    """P2 for an Evaluation that differs from the one just staged in a Finding alone."""
    case = {"commands": [_shown(c) for c in (*script, command)], "twin": True}
    staged, twin = EVALUATIONS[command[1]], TWINS[command[1]]
    alike = ("call", "scorecard", "score", "evaluation_outcome", "disposition")
    assert all(getattr(staged, name) == getattr(twin, name) for name in alike) and staged != twin
    held = path.read_text(encoding="utf-8")
    try:
        ledger_module.Ledger(path, clock).stage(twin)
        answer = RECORDED
    except publication.Refused:
        answer = REFUSED
    try:  # as after every command: what was written has to read back
        ledger_module.Ledger(path, clock).entry(*KEY)
    except ledger_module.Corrupt:
        raise PropertyViolation("P13", {**case, "read": "Corrupt"}) from None
    require(answer == REFUSED and path.read_text(encoding="utf-8") == held, "P2", **case)


def _check_answer(
    script: tuple,
    command: tuple,
    known: Known,
    before: ledger_module.Entry | None,
    want: str,
    review_required: bool,
    then: Known,
    got: Answer,
) -> None:
    case = {
        "commands": [_shown(c) for c in (*script, command)],
        "answer": got.answer,
        "state": getattr(_standing(got.entry), "value", None),
    }
    state, was = _standing(got.entry), _standing(before)
    reviews = (
        [(r.reviewer, ReviewOutcome(r.review_outcome)) for r in got.entry.reviews]
        if got.entry
        else []
    )
    added = len(got.entry.records) - len(before.records if before else ()) if got.entry else 0

    require(not (was in TERMINAL and (got.entry != before or got.lines)), "P5", **case)
    if state is PublicationState.PUBLISHED and got.entry.disposition is not Disposition.FINAL:
        # Read from the ledger alone: the CONFIRMED Review comes before the AuditRecord of PUBLISHED.
        published_at = got.entry.records[-1].recorded_at
        confirmed = any(
            ReviewOutcome(r.review_outcome) is ReviewOutcome.CONFIRMED
            and r.reviewed_at <= published_at
            for r in got.entry.reviews
        )
        require(confirmed, "P3", **case)

    if command[0] == STAGE:
        if want == RECORDED:
            staged = (
                got.answer == RECORDED
                and state is PublicationState.STAGED
                and got.entry.disposition is Disposition(EVALUATIONS[command[1]].disposition)
            )
            require(staged, "P1", **case)
        elif want == REFUSED:
            require(got.answer == REFUSED and got.entry == before, "P2", **case)
    elif command[0] == REVIEW:
        if want == REFUSED:
            require(got.answer == REFUSED and got.entry == before, "P7", **case)
        elif want == RECORDED:
            taken = got.answer == RECORDED and reviews == list(then.reviews) and state is then.state
            require(taken, "P6", **case)
    elif review_required:
        require(got.answer == REFUSED and state is was, "P3", **case)
        require(got.rules == [RejectionRule.REVIEW_REQUIRED.value], "P4", **case, rules=got.rules)
    elif want == RECORDED:
        require(got.answer == RECORDED and state is PublicationState.PUBLISHED, "P8", **case)
    if got.answer == REFUSED and not review_required:
        require(got.rules == [], "P4", **case, rules=got.rules)
    if want == DONE_ALREADY:
        require(got.answer == DONE_ALREADY and not got.lines, "P12", **case)

    require(added == (state is not was), "P9", **case, audit_records=added)
    if added == 1:
        record = got.entry.records[-1]
        actor = command[1] if command[0] == REVIEW else ledger_module.SYSTEM
        whole = (
            (record.call, record.scorecard) == KEY
            and PublicationState(record.publication_state) is state
            and record.actor == actor
            and got.asked_at < record.recorded_at <= got.asked_at + timedelta(seconds=2)
        )
        require(whole, "P9", **case)
    held = (
        (then.staged and ledger_module.digest(EVALUATIONS[then.staged]))
        == (got.entry.sha256 if got.entry else None)
        and state is then.state
        and reviews == list(then.reviews)
        and (len(got.entry.records) if got.entry else 0) == then.records
        and got.answer == want
    )
    require(held, "P13", **case, want=want)


CHECKS = {
    "scoring": check_scoring,
    "session": check_session,
    "loop": check_loop,
    "ledger": check_ledger,
}


def main(argv: list[str]) -> int:
    for name in argv or list(CHECKS):
        try:
            counted = CHECKS[name]()
        except PropertyViolation as violation:
            print(f"{name}: {violation}")
            print(f"VIOLATED {violation.prop}")
            return 3
        print(f"{name}: held for every case within the bound {counted}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
