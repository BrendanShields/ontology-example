"""Faults planted in a copy of the package, each of which a named property must report.

A check that has never been seen to fail shows nothing. Each Mutant swaps one
exact piece of source text in a temporary copy of `call_qa_agent` and names the
explorer and the property that must report it. The text must occur exactly
once: when the guarded line is edited the mutant stops applying, and the test
fails until someone confirms the check still describes the code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
PACKAGE = APP / "src" / "call_qa_agent"

RUNNER = """
import sys
import call_qa_agent
print("PACKAGE", call_qa_agent.__file__)
from tests.bounded import explore, statechart
sys.exit({"explore": explore, "statechart": statechart}[sys.argv[1]].main(sys.argv[2:]))
"""


@dataclass(frozen=True)
class Mutant:
    name: str
    file: str
    old: str
    new: str
    check: str  # the explorer to run: a key of explore.CHECKS
    reported_by: str  # the property that must report it: a key of explore.PROPERTIES


_SCORING = "domain/scoring.py"
_GUARDRAILS = "domain/guardrails.py"
_APPLIES = "if f.finding_outcome != FindingOutcome.NOT_APPLICABLE"
_NEEDS_REVIEW = "needs_review = critical_failed or applied == 0"
_ANSWERED = '        messages.append({"role": "user", "content": results})\n'
_OUT_OF_TURNS = '    raise EvaluationIncomplete(\n        f"the model did not'

_EVALUATION_RETURNED = _ANSWERED + "        if session.evaluation is not None:\n            return session.evaluation"
_CONCLUDED = "self.evaluation = scoring.conclude(self.call, self.scorecard, self.findings)"
_UNCITED = "[f.model_copy(update={'cited_utterances': None}) for f in findings],"
_RECITED = "model_copy(update={'cited_utterances': [2]})"
_IF_ACCEPTED = "        if not rejections:\n            self.findings.append(finding)"
_OUTSTANDING = "        rejections = self.outstanding()\n"
_RECORDED_UNCITED = "self.findings.append(finding.model_copy(update={'cited_utterances': []}))"
_PUBLICATION = "domain/publication.py"
_LEDGER = "ledger.py"
_UNLESS_FINAL = "if Disposition(disposition) is not Disposition.FINAL and not confirmed:"
_SAME_EVALUATION = "found.sha256 == digest(evaluation)"
_REVIEW_ASKED = "            record = publication.review(made, found.disposition, found.records)\n"
_REVIEW_KEPT_ANYWAY = (
    "            try:\n    " + _REVIEW_ASKED + "            except publication.Refused:\n"
    '                _append(ledger, {"review": _plain(made)})\n                raise\n'
)
_PUBLISHED_ALREADY = "            if found.publication_state is PublicationState.PUBLISHED:\n                return False"

MUTANTS = [
    Mutant("evaluation-loses-its-score", _SCORING, "score=points,", "score=0,", "scoring", "S1"),
    Mutant("critical-failure-can-pass", _SCORING, "passed = not critical_failed and points", "passed = points", "scoring", "S2"),
    Mutant("no-review-after-critical-failure", _SCORING, _NEEDS_REVIEW, "needs_review = applied == 0", "scoring", "S2"),
    Mutant("pass-mark-strict", _SCORING, "points >= scorecard.pass_mark", "points > scorecard.pass_mark", "scoring", "S3"),
    Mutant("no-review-when-nothing-applied", _SCORING, _NEEDS_REVIEW, "needs_review = critical_failed", "scoring", "S4"),
    Mutant("not-applicable-counts-against", _SCORING, _APPLIES, "if True", "scoring", "S4"),
    Mutant("findings-reordered", _SCORING, "findings=findings,", "findings=findings[::-1],", "scoring", "S5"),
    Mutant("evaluation-loses-its-citations", _SCORING, "findings=findings,", "findings=" + _UNCITED, "scoring", "S5"),
    Mutant("only-not-met-applies", _SCORING, _APPLIES, "if f.finding_outcome == FindingOutcome.NOT_MET", "scoring", "S6"),
    Mutant("score-rounds-up", _SCORING, "met * 100 // applied if applied else 0", "-(-met * 100 // applied) if applied else 0", "scoring", "S6"),
    Mutant("score-ignores-weight", _SCORING, "criterion.criterion_id: criterion.weight for", "criterion.criterion_id: 1 for", "scoring", "S6"),
    Mutant("evaluation-from-any-findings", _SCORING, "    if judged != sorted(criterion.criterion_id for criterion in scorecard.criteria):", "    if False:", "scoring", "S7"),
    Mutant("duplicate-findings-concluded", _SCORING, "    judged = sorted(finding.criterion for finding in findings)", "    judged = sorted({finding.criterion for finding in findings})", "scoring", "S7"),
    Mutant("rejected-finding-recorded", "session.py", "        if not rejections:\n            self.findings.append(finding)", "        self.findings.append(finding)", "session", "G1"),
    Mutant("rejected-proposal-changes-a-citation", "session.py", _IF_ACCEPTED, "        if rejections and self.findings:\n            self.findings[0] = self.findings[0]." + _RECITED + "\n" + _IF_ACCEPTED, "session", "G1"),
    Mutant("finding-recorded-first", "session.py", "self.findings.append(finding)", "self.findings.insert(0, finding)", "session", "G2"),
    Mutant("finding-recorded-without-citations", "session.py", "self.findings.append(finding)", _RECORDED_UNCITED, "session", "G2"),
    Mutant("duplicate-finding-recorded", _GUARDRAILS, "elif any(existing.criterion == finding.criterion for existing in recorded):", "elif False:", "session", "G3"),
    Mutant("uncited-judgement-recorded", _GUARDRAILS, "if finding.finding_outcome in JUDGED and not cited:", "if False:", "session", "G3"),
    Mutant("unknown-utterance-recorded", _GUARDRAILS, "    if unknown:", "    if False:", "session", "G3"),
    Mutant("unknown-criterion-recorded", _GUARDRAILS, "if finding.criterion not in criteria:", "if False:", "session", "G3"),
    Mutant("wrong-rule-named", _GUARDRAILS, "rejection_rule=RejectionRule.UNKNOWN_UTTERANCE", "rejection_rule=RejectionRule.MISSING_CITATION", "session", "G3"),
    Mutant("rejection-names-another-criterion", _GUARDRAILS, "rejection_rule=RejectionRule.DUPLICATE_FINDING,\n                criterion=finding.criterion,", "rejection_rule=RejectionRule.DUPLICATE_FINDING,\n                criterion='zz',", "session", "G3"),
    Mutant("malformed-proposal-misnamed", "session.py", "rejection_rule=RejectionRule.MALFORMED_FINDING", "rejection_rule=RejectionRule.MISSING_CITATION", "session", "G3"),
    Mutant("finish-ignores-missing", _GUARDRAILS, "if criterion.criterion_id not in judged", "if False", "session", "G4"),
    Mutant("evaluation-without-all-findings", "session.py", "if not rejections and self.evaluation is None:", "if self.evaluation is None:", "session", "G4"),
    Mutant("finish-changes-the-citations", "session.py", _OUTSTANDING, _OUTSTANDING + "        self.findings[:] = [f." + _RECITED + " for f in self.findings]\n", "session", "G4"),
    Mutant("missing-finding-misnamed", _GUARDRAILS, "rejection_rule=RejectionRule.MISSING_FINDING", "rejection_rule=RejectionRule.MISSING_CITATION", "session", "G5"),
    Mutant("evaluation-loses-a-finding", "session.py", _CONCLUDED, _CONCLUDED + "\n            self.evaluation = self.evaluation.model_copy(update={'findings': self.findings[1:]})", "session", "G6"),
    Mutant("concluded-evaluation-loses-citations", _SCORING, "findings=findings,", "findings=" + _UNCITED, "session", "G6"),
    Mutant("record-after-completion", "session.py", "        if self.evaluation is not None:\n            raise RuntimeError", "        if False:\n            raise RuntimeError", "session", "G7"),
    Mutant("one-turn-too-many", "agent.py", "for _ in range(settings.max_turns):", "for _ in range(settings.max_turns + 1):", "loop", "L1"),
    Mutant("keeps-asking-after-evaluation", "agent.py", _ANSWERED + "        if session.evaluation is not None:", _ANSWERED + "        if False:", "loop", "L2"),
    Mutant("refusal-ignored", "agent.py", 'if response.stop_reason == "refusal":', "if False:", "loop", "L2"),
    Mutant("cut-off-ignored", "agent.py", 'if response.stop_reason == "max_tokens":', "if False:", "loop", "L2"),
    Mutant("tool-run-after-completion", "agent.py", "            if session.evaluation is not None:\n                text, rejected", "            if False:\n                text, rejected", "loop", "L2"),
    Mutant("stop-without-tool-never-finishes", "agent.py", "            missing = session.finish()\n", "            missing = session.outstanding()\n", "loop", "L2"),
    Mutant("turn-limit-returns-partial", "agent.py", _OUT_OF_TURNS, "    from .domain import scoring as _s\n    return _s.conclude(call, scorecard, session.findings)\n" + _OUT_OF_TURNS, "loop", "L2"),
    Mutant("returned-evaluation-loses-a-finding", "agent.py", _EVALUATION_RETURNED, _EVALUATION_RETURNED + ".model_copy(update={'findings': session.findings[1:]})", "loop", "L3"),
    Mutant("returned-evaluation-loses-citations", "session.py", "self.findings.append(finding)", _RECORDED_UNCITED, "loop", "L3"),
    Mutant("outstanding-rejections-dropped", "agent.py", "        session.outstanding(),\n    )", "        [],\n    )", "loop", "L4"),
    Mutant("tool-result-dropped", "agent.py", "            results.append(\n", "            results.clear()\n            results.append(\n", "loop", "L5"),
    Mutant("returned-evaluation-rescored", "agent.py", _EVALUATION_RETURNED, _EVALUATION_RETURNED + ".model_copy(update={'score': 0})", "loop", "L6"),
    Mutant("staged-as-published", _PUBLICATION, "        PublicationState.STAGED,\n        records,", "        PublicationState.PUBLISHED,\n        records,", "ledger", "P1"),
    Mutant("same-disposition-taken-for-the-same-evaluation", _LEDGER, _SAME_EVALUATION, "found.disposition.value == evaluation.disposition", "ledger", "P2"),
    Mutant("published-without-a-review", _PUBLICATION, _UNLESS_FINAL, "if False:", "ledger", "P3"),
    Mutant("review-required-misnamed", _PUBLICATION, "rejection_rule=RejectionRule.REVIEW_REQUIRED", "rejection_rule=RejectionRule.MISSING_FINDING", "ledger", "P4"),
    Mutant("refusal-of-a-review-names-a-rule", _PUBLICATION, "it stands without a Review\"\n        )", "it stands without a Review\",\n            [Rejection(rejection_rule=RejectionRule.MISSING_FINDING, detail='d')],\n        )", "ledger", "P4"),
    Mutant("withheld-asked-for-a-review-it-cannot-use", _PUBLICATION, "PublicationState.WITHHELD: (),", "PublicationState.WITHHELD: (PublicationState.PUBLISHED,),", "ledger", "P4"),
    Mutant("withheld-can-be-withheld-again", _PUBLICATION, "PublicationState.WITHHELD: (),", "PublicationState.WITHHELD: (PublicationState.WITHHELD,),", "ledger", "P5"),
    Mutant("published-can-be-withheld", _PUBLICATION, "PublicationState.PUBLISHED: (),", "PublicationState.PUBLISHED: (PublicationState.WITHHELD,),", "ledger", "P5"),
    Mutant("overturned-leaves-it-staged", _PUBLICATION, "case ReviewOutcome.CONFIRMED:", "case ReviewOutcome.CONFIRMED | ReviewOutcome.OVERTURNED:", "ledger", "P6"),
    Mutant("review-forgotten-on-reading", _LEDGER, "reviews=(*found.reviews, made)", "reviews=found.reviews", "ledger", "P6"),
    Mutant("final-evaluation-reviewed", _PUBLICATION, "    if Disposition(disposition) is Disposition.FINAL:", "    if False:", "ledger", "P7"),
    Mutant("final-evaluation-needs-a-review", _PUBLICATION, _UNLESS_FINAL, "if not confirmed:", "ledger", "P8"),
    Mutant("withheld-in-the-name-of-the-call", _PUBLICATION, "actor=made.reviewer,", "actor=made.call,", "ledger", "P9"),
    Mutant("confirmed-review-gets-an-audit-record", _LEDGER, "            if record is not None:\n                line[\"audit_record\"] = _plain(record)", "            line[\"audit_record\"] = _plain(AuditRecord(call=call, scorecard=scorecard, publication_state=found.publication_state, actor=reviewer, recorded_at=made.reviewed_at))", "ledger", "P13"),
    Mutant("score-on-the-ledger", _LEDGER, '"sha256": digest(evaluation),\n                }', '"sha256": digest(evaluation),\n                    "score": evaluation.score,\n                }', "ledger", "P10"),
    Mutant("rationale-beside-a-review", _LEDGER, 'line = {"review": _plain(made)}', 'line = {"review": {**_plain(made), "rationale": "r"}}', "ledger", "P10"),
    Mutant("refused-review-kept", _LEDGER, _REVIEW_ASKED, _REVIEW_KEPT_ANYWAY, "ledger", "P11"),
    Mutant("review-recorded-twice", _LEDGER, "(made.reviewer, made.review_outcome) == (reviewer, outcome.value)", "False", "ledger", "P12"),
    Mutant("published-twice-is-refused", _LEDGER, _PUBLISHED_ALREADY, "            if False:\n                return False", "ledger", "P12"),
    Mutant("another-evaluation-staged-over-the-first", _LEDGER, "evaluation, found.records if found else (), actor=SYSTEM", "evaluation, (), actor=SYSTEM", "ledger", "P13"),
]


def copy_package(target: Path) -> Path:
    """A copy of the real package under `target`, to be put first on the import path."""
    copied = target / PACKAGE.name
    shutil.copytree(PACKAGE, copied, ignore=shutil.ignore_patterns("__pycache__"))
    return copied


def plant(mutant: Mutant, copied: Path) -> None:
    path = copied / mutant.file
    text = path.read_text(encoding="utf-8")
    found = text.count(mutant.old)
    if found != 1:
        raise LookupError(
            f"{mutant.name}: the text to swap occurs {found} times in {mutant.file}, not once. "
            "The guarded line changed: confirm the check still describes the code, then update "
            "the mutant."
        )
    path.write_text(text.replace(mutant.old, mutant.new), encoding="utf-8")


@dataclass
class Explored:
    package: Path  # the file the explored call_qa_agent was imported from
    violated: str | None  # the property reported, or None when every check held
    returncode: int
    output: str


def explore_copy(root: Path, *arguments: str, module: str = "explore") -> Explored:
    """Run `module` in a fresh interpreter against the package copied under `root`."""
    env = {**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-c", RUNNER, module, *arguments],
        cwd=APP,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = done.stdout.splitlines()
    package = next((line.split(" ", 1)[1] for line in lines if line.startswith("PACKAGE ")), "")
    violated = next((line.split()[1] for line in lines if line.startswith("VIOLATED ")), None)
    return Explored(Path(package), violated, done.returncode, done.stdout + done.stderr)
