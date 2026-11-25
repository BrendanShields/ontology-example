"""The generated ontology pages: what they hold, and that nobody edits them by hand."""

from __future__ import annotations

import re

import pytest
from onto import gen, guard
from onto.cli import main
from onto.testing import scratch_repo

CALL_QA = "docs/generated/call-qa.md"
WORKFLOW = "docs/generated/workflow.md"

NAME = r"[A-Za-z_][A-Za-z0-9_]*"
RELATION = re.compile(rf'({NAME}) (<\|--|<\|\.\.|-->|\.\.>) (?:"[0-9.*]+" )?({NAME})(?: : {NAME})?')
MEMBER = re.compile(rf"<<{NAME}>>|\+{NAME}(~{NAME}~)? {NAME}|{NAME}")


def mermaid_problems(diagram: str) -> list[str]:
    """Structural check of a classDiagram: mmdc is not a dependency, so this stands in for it.

    Every line must be a class, a member inside a class body, or a relation
    between two declared classes.
    """
    lines = diagram.splitlines()
    if not lines or lines[0] != "classDiagram":
        return ["does not start with classDiagram"]
    problems: list[str] = []
    declared: set[str] = set()
    related: set[str] = set()
    body = False
    for number, raw in enumerate(lines[1:], start=2):
        line = raw.strip()
        if body:
            if line == "}":
                body = False
            elif not MEMBER.fullmatch(line):
                problems.append(f"line {number}: not a class member")
        elif found := re.fullmatch(rf"class ({NAME})( \{{)?", line):
            if found.group(1) in declared:
                problems.append(f"line {number}: class declared twice")
            declared.add(found.group(1))
            body = bool(found.group(2))
        elif found := RELATION.fullmatch(line):
            related.update((found.group(1), found.group(3)))
        else:
            problems.append(f"line {number}: neither a class nor a relation")
    if body:
        problems.append("a class body is never closed")
    problems.extend(f"relation to undeclared class {name}" for name in sorted(related - declared))
    return problems


def diagram_of(page: str) -> str:
    (diagram,) = re.findall(r"```mermaid\n(.*?)\n```", page, flags=re.DOTALL)
    return diagram


@pytest.fixture
def repo(tmp_path, monkeypatch):
    pytest.importorskip("linkml")
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    return scratch


def gen_check(capsys) -> tuple[int, str]:
    code = main(["gen", "--check"])
    return code, capsys.readouterr().out


def test_a_context_page_holds_every_term_of_the_glossary(repo):
    page = (repo.root / CALL_QA).read_text()
    glossary = repo.ws().glossaries["call-qa"]

    for term in glossary.terms.values():
        assert (
            f"| `{term.name}` | {term.kind} | {term.definition} | {term.classification} |" in page
        )
    assert (
        "| `Representative` | class | The bank employee who handles a Call. | PII | rep | Agent, Advisor |"
        in page
    )
    assert "| `NEEDS_REVIEW` | A person must review the Evaluation before it is used. |" in page
    assert "| `Utterance` | close | https://schema.org/Message |" in page
    assert 'Call --> "1..*" Utterance : utterances' in diagram_of(page)
    assert "Finding ..> FindingOutcome : finding_outcome" in diagram_of(page)


def test_the_workflow_page_shows_inheritance_and_the_concepts_reused_by_reference(repo):
    page = (repo.root / WORKFLOW).read_text()

    assert "WorkItem <|-- Requirement" in diagram_of(page)
    assert "Entity <|.. Requirement" in diagram_of(page)
    assert 'Test --> "1..*" Requirement : verifies' in diagram_of(page)
    assert "| `Activity` | is | http://www.w3.org/ns/prov#Activity |" in page
    assert "| `done` |" in page


@pytest.mark.parametrize("page", [CALL_QA, WORKFLOW])
def test_the_class_diagram_is_well_formed_mermaid(repo, page):
    assert mermaid_problems(diagram_of((repo.root / page).read_text())) == []


@pytest.mark.parametrize(
    ("broken", "problem"),
    [
        ("classDiagram\n    class A {\n        +string name\n", "never closed"),
        ("classDiagram\n    class A\n    A --> B : b", "undeclared class B"),
        ("classDiagram\n    class A\n    A -> A", "neither a class nor a relation"),
        ("classDiagram\n    class A {\n        one or two sentences\n    }", "not a class member"),
        ("class A", "does not start with classDiagram"),
    ],
)
def test_the_mermaid_check_rejects_a_broken_diagram(broken, problem):
    assert any(problem in found for found in mermaid_problems(broken))


def test_a_page_depends_on_the_ontology_alone(repo, capsys):
    before = (repo.root / CALL_QA).read_text()
    repo.item("REQ-0001", title="Something new on the branch")
    repo.write("apps/call-qa-agent/data/calls/extra.yaml", "call_id: C-9\n")

    assert main(["gen"]) == 0
    assert "unchanged docs/generated/call-qa.md" in capsys.readouterr().out
    assert (repo.root / CALL_QA).read_text() == before


def test_gen_check_notices_a_hand_edited_page(repo, capsys):
    code, out = gen_check(capsys)
    assert code == 0, out

    target = repo.root / CALL_QA
    target.write_text(target.read_text().replace("The bank employee", "The person"))
    code, out = gen_check(capsys)
    assert (
        code == 1
        and f"drift     {CALL_QA}" in out
        and "-| `Representative` | class | The person" in out
    )


def test_gen_check_notices_a_definition_that_changed_without_regenerating(repo, capsys):
    source = repo.root / "ontology/domains/call-qa.yaml"
    source.write_text(source.read_text().replace("The bank employee who", "The employee who", 1))

    code, out = gen_check(capsys)
    assert code == 1 and f"drift     {CALL_QA}" in out
    assert f"unchanged {WORKFLOW}" in out


def test_the_guard_denies_an_edit_to_a_generated_page(repo):
    for page, source in (
        (CALL_QA, "ontology/domains/call-qa.yaml"),
        (WORKFLOW, "ontology/workflow.yaml"),
    ):
        decision, reason = guard.decide(repo.ws(), str(repo.root / page))
        assert decision == guard.DENY and source in reason and "onto gen" in reason
    assert guard.decide(repo.ws(), str(repo.root / "docs/guide.md"))[0] == guard.ALLOW


def test_everything_gen_writes_is_guarded(repo):
    cfg = repo.ws().cfg
    assert {cfg.rel(t.path) for t in gen.targets(cfg)} == set(cfg.generated_files())


def test_a_repository_that_names_no_page_gets_none(repo, capsys):
    toml = repo.root / "onto.toml"
    toml.write_text(
        "".join(
            line
            for line in toml.read_text().splitlines(keepends=True)
            if not line.startswith("docs =")
        )
    )

    code, out = gen_check(capsys)
    assert code == 0 and "docs/generated" not in out
    assert guard.decide(repo.ws(), str(repo.root / CALL_QA))[0] == guard.ALLOW
