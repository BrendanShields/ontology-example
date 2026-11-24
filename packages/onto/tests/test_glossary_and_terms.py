"""The glossary, the denied-synonym matcher and the domain-layer vocabulary check."""

from __future__ import annotations

import pytest
from onto import terms
from onto.testing import scratch_repo
from onto.textscan import DeniedMatcher, split_words
from onto.workspace import Workspace

DOMAIN = "apps/call-qa-agent/src/call_qa_agent/domain/example.py"


@pytest.fixture(scope="module")
def ws():
    return Workspace.at()


@pytest.fixture(scope="module")
def glossary(ws):
    return ws.glossary("call-qa")


@pytest.mark.parametrize(
    ("name", "status", "term"),
    [
        ("Scorecard", "exact", "Scorecard"),
        ("pass_mark", "exact", "pass_mark"),
        ("NEEDS_REVIEW", "exact", "Disposition.NEEDS_REVIEW"),
        ("Disposition.NEEDS_REVIEW", "exact", "Disposition.NEEDS_REVIEW"),
        ("pass mark", "alias", "pass_mark"),
        ("scorecard question", "alias", "Criterion"),
        ("needs review", "normalized", "Disposition.NEEDS_REVIEW"),
        ("cited utterance", "normalized", "cited_utterances"),
        ("Rubric", "denied", "Scorecard"),
        ("rubrics", "denied", "Scorecard"),
        ("Agent", "denied", "Representative"),
        ("evidence", "denied", "cited_utterances"),
    ],
)
def test_resolve(glossary, name, status, term):
    resolution = glossary.resolve(name)
    assert resolution.status == status
    assert resolution.terms[0].name == term


def test_an_unknown_name_stays_unknown_and_gets_suggestions(glossary):
    resolution = glossary.resolve("Scorcard")
    assert resolution.status == "unknown" and not resolution.found
    assert "Scorecard" in resolution.suggestions
    assert glossary.resolve("Calibration").suggestions == ()


def test_only_an_exact_name_is_a_term(glossary):
    assert glossary.get("Scorecard").kind == "class"
    assert glossary.get("scorecard").kind == "slot"  # a different term, not a spelling
    assert glossary.get("Rubric") is None and glossary.get("pass mark") is None


def test_terms_carry_what_the_ontology_declares(glossary):
    call = glossary.get("Call")
    assert call.classification == "PII"
    assert call.close_mappings == ("https://schema.org/Conversation",)
    assert glossary.get("Criterion").classification == "internal"  # the default
    assert glossary.get("pass_mark").constraints == (">= 0", "<= 100")
    assert glossary.get("MET").iri.endswith("/FindingOutcome#MET")
    assert "FindingOutcome" in glossary.related("Finding")


def test_the_glossary_passes_its_own_lint(ws, glossary):
    allowed = ws.schema.enum_values("ClassificationEnum")
    assert glossary.lint(allowed, "ontology/domains/call-qa.yaml") == []
    assert [p.found for p in glossary.lint(["public"], "x")][:1] == ["PII"]


def test_split_words():
    assert split_words("EvaluationForm") == ("evaluation", "form")
    assert split_words("cited_utterances") == ("cited", "utterances")
    assert split_words("QAForm2") == ("qa", "form", "2")


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("rubric_id = 1", ["rubric"]),
        ("class ScorecardRubric: ...", ["Rubric"]),
        ("load_rubrics()", ["rubrics"]),
        ("the Rubric is", ["Rubric"]),
        ("evaluation_form = None", ["evaluation_form"]),
        ("an evaluation form", ["evaluation form"]),
        ("EvaluationForms", ["EvaluationForms"]),
        ("rubricate the page", []),  # a longer word, not the synonym
        ("the call-qa-agent shall", []),  # part of a hyphenated name
        ("agent_id", ["agent"]),  # but an identifier part counts
        ("user-agent header", []),
        ("evaluation of the form", []),  # the words are not adjacent
    ],
)
def test_denied_matcher(glossary, text, found):
    hits = DeniedMatcher(glossary.denied_entries()).find(text)
    assert [hit.text for hit in hits] == found


def test_a_hit_reports_where_it_is_and_what_to_write(glossary):
    (hit,) = DeniedMatcher(glossary.denied_entries()).find("a = 1\n  x = load_rubric(a)\n")
    assert (hit.line, hit.column, hit.term.name, hit.synonym) == (2, 12, "Scorecard", "Rubric")


def test_denied_synonym_in_domain_code_is_an_error(ws):
    (problem,) = terms.check_file(ws, DOMAIN, "def score_rubric(rubric):\n    return 1\n")[:1]
    assert problem.rule == "denied-term" and problem.blocking and problem.line == 1
    assert problem.suggestions == ("Scorecard",)
    assert "onto ocr new --context call-qa" in problem.fix


def test_nothing_is_checked_outside_a_domain_layer(ws):
    assert terms.check_file(ws, "apps/call-qa-agent/src/call_qa_agent/agent.py", "rubric = 1") == []
    assert terms.check_file(ws, "packages/onto/src/onto/cli.py", "class Rubric: ...") == []


def test_the_allow_pragma_accepts_a_denied_synonym_and_is_counted(ws):
    text = 'FIELD = "agentId"  # onto: allow-term (the telephony API calls it this)\n'
    assert terms.check_file(ws, DOMAIN, text) == []
    assert terms.suppressed(ws, DOMAIN, text) == 1


def test_a_coined_class_or_field_is_a_warning_not_an_error(ws):
    code = (
        "class Calibration:\n"
        "    agreement_rate: float\n"
        "    score: int\n"
        "class _Helper: ...\n"
        "class ScoringError(Exception): ...\n"
        "class Finding: ...\n"
    )
    problems = terms.check_file(ws, DOMAIN, code)
    assert [(p.rule, p.severity, p.found) for p in problems] == [
        ("unknown-term", "warning", "Calibration"),
        ("unknown-term", "warning", "agreement_rate"),
    ]


def test_only_the_changed_lines_are_reported(ws):
    text = "rubric = 1\nfine = 2\nverdict = 3\n"
    assert len(terms.check_file(ws, DOMAIN, text)) == 2
    lines = terms.changed_lines(text, "verdict = 3")
    assert lines == {3}
    assert [p.found for p in terms.check_file(ws, DOMAIN, text, lines)] == ["verdict"]
    assert terms.changed_lines(text, None) is None  # a whole-file write
    assert terms.changed_lines(text, "") == set()  # a pure deletion
    assert terms.changed_lines(text, "not there") is None


def test_the_repository_s_own_domain_layer_is_clean(ws):
    from onto.cli import _domain_files

    files = _domain_files(ws)
    assert "apps/call-qa-agent/src/call_qa_agent/domain/scoring.py" in files
    for rel in files:
        assert terms.check_file(ws, rel, (ws.cfg.root / rel).read_text()) == [], rel


def test_a_scratch_repo_has_the_real_glossary(tmp_path):
    assert scratch_repo(tmp_path).ws().glossary("call-qa").get("Scorecard") is not None
