"""Competency questions as tests.

Each question is a SPARQL file in this folder. The first group of tests pins
its answer on this repository's own work items, so a change to the ontology
that breaks a question fails the build. The second group checks that the
questions that guard a rule do find a violation when there is one.
"""

from __future__ import annotations

import pytest
from onto import cq, gates
from onto.graph import build_graph, load_graph
from onto.slicing import decisions_affecting, decisions_in_force
from onto.testing import scratch_repo
from onto.workspace import Workspace


@pytest.fixture(scope="module")
def graph():
    return load_graph()


@pytest.fixture(scope="module")
def questions(graph):
    return cq.load(graph.ws.cfg)


def ask(graph, questions, identifier, **bindings):
    return cq.run(graph, questions[identifier], **bindings)


def column(rows, name):
    return [row[name] for row in rows]


def test_every_question_parses_and_runs(graph, questions):
    assert len(questions) == 10
    for question in questions.values():
        if not question.binds:
            cq.run(graph, question)


def test_cq01_a_change_is_traced_to_the_requirements_it_serves(graph, questions):
    rows = ask(graph, questions, "CQ-01", change="CHG-0001")
    assert column(rows, "requirement") == [f"REQ-000{n}" for n in range(1, 8)]
    assert {row["task"] for row in rows} == {"TASK-0001", "TASK-0002", "TASK-0003"}


def test_cq02_finds_what_is_absent(graph, questions):
    # REQ-0008 is agreed and has no Test. REQ-0009 has none either but is a draft.
    assert column(ask(graph, questions, "CQ-02"), "requirement") == ["REQ-0008"]


def test_cq03_leaves_out_superseded_decisions(graph, questions):
    # Four Decisions are about `score`. Two were superseded along the way.
    assert column(ask(graph, questions, "CQ-03", term="score"), "decision") == [
        "DEC-0005",
        "DEC-0006",
    ]
    assert column(ask(graph, questions, "CQ-03", term="Scorecard"), "decision") == ["DEC-0002"]


def test_cq03_agrees_with_the_slicer(graph, questions):
    """Slices compute "in force" in Python. The two definitions must not drift apart."""
    ws = graph.ws
    glossary = ws.glossary("call-qa")
    for term in ("score", "Scorecard", "Criterion", "Finding", "Representative", "weight"):
        from_slicer = sorted(
            d.id
            for d in decisions_in_force(ws, "call-qa")
            if glossary.get(term).name in {glossary.get(n).name for n in d.values("uses_terms")}
        )
        assert column(ask(graph, questions, "CQ-03", term=term), "decision") == from_slicer


def test_cq04_walks_the_whole_chain(graph, questions):
    assert column(ask(graph, questions, "CQ-04", decision="DEC-0005"), "earlier") == [
        "DEC-0004",
        "DEC-0003",
    ]
    assert ask(graph, questions, "CQ-04", decision="DEC-0006") == []


def test_cq05_returns_the_complete_set(graph, questions):
    rows = ask(graph, questions, "CQ-05")
    assert sorted({row["requirement"] for row in rows}) == ["REQ-0002", "REQ-0008", "REQ-0009"]
    assert {row["risk"] for row in rows} == {"high"}


def test_cq06_gives_the_impact_of_changing_a_term(graph, questions):
    rows = ask(graph, questions, "CQ-06", term="Finding")
    assert sorted({row["requirement"] for row in rows}) == [
        *(f"REQ-000{n}" for n in range(1, 6)),
        "REQ-0010",
    ]
    assert {"TST-0001", "TST-0004"} <= {row.get("test") for row in rows}


def test_cq07_no_change_to_personal_information_is_under_tiered(graph, questions):
    assert ask(graph, questions, "CQ-07") == []


def test_cq07_finds_an_under_tiered_change(tmp_path):
    repo = scratch_repo(tmp_path)
    repo.item(
        "REQ-0001",
        ears_text="The system shall store each `Utterance`.",
        uses_terms=["Utterance"],
        risk_tier="medium",
    )
    repo.item("TASK-0001")
    repo.item("CHG-0001")
    ws = Workspace.at(repo.root)

    rows = cq.run(build_graph(ws), cq.load(ws.cfg)["CQ-07"])

    assert rows == [{"change": "CHG-0001", "requirement": "REQ-0001", "term": "qa:Utterance"}]


# CQ-08 to CQ-10 are about what happens after ship. This repository has no
# Incident, no replaced Requirement and no Decision on a path, so its own answer
# to each is pinned as empty and the full answer is pinned on a scratch repository.


def scratch(tmp_path):
    repo = scratch_repo(tmp_path)
    return repo, lambda identifier, **bindings: cq.run(
        build_graph(repo.ws()), cq.load(repo.ws().cfg)[identifier], **bindings
    )


def test_cq08_the_repository_has_no_incident_waiting(graph, questions):
    assert ask(graph, questions, "CQ-08") == []


def test_cq08_lists_each_incident_with_what_its_fix_waits_on(tmp_path):
    repo, answer = scratch(tmp_path)
    repo.item("REQ-0001", status="done")
    repo.item("REQ-0002", status="in_progress", raised_from="INC-0002")
    repo.item("REQ-0003", status="ready", raised_from="INC-0002")
    repo.item("REQ-0004", status="superseded")
    repo.item("INC-0001", status="done", breaks=["REQ-0001", "REQ-0004"])  # fixed
    repo.item("INC-0002", breaks=["REQ-0001"])
    repo.item("INC-0003", status="done")  # closed by saying so
    repo.item("INC-0004")

    assert answer("CQ-08") == [
        {
            "incident": "INC-0002",
            "status": "in_progress",
            "requirement": "REQ-0002",
            "requirement_status": "in_progress",
        },
        {
            "incident": "INC-0002",
            "status": "in_progress",
            "requirement": "REQ-0003",
            "requirement_status": "ready",
        },
        {"incident": "INC-0003", "status": "done"},
        {"incident": "INC-0004", "status": "in_progress"},
    ]


def test_cq08_agrees_with_the_gate_on_closed_incidents(tmp_path):
    """The question lists open Incidents too. On the closed ones it and the gate must not differ."""
    repo, answer = scratch(tmp_path)
    for number, status in enumerate(("draft", "ready", "in_progress", "done", "superseded"), 1):
        repo.item(f"REQ-000{number}", status=status)
        repo.item(f"INC-000{number}", status="done", breaks=[f"REQ-000{number}"])
        repo.item(f"REQ-001{number}", status=status, raised_from=f"INC-001{number}")
        repo.item(f"INC-001{number}", status="done")
    repo.item("INC-0020", status="done")
    ws = repo.ws()

    by_gate = {
        problem.subject
        for problem in gates.run_shacl(ws, build_graph(ws))
        if problem.rule == "gate:ClosedIncidentIsFixed"
    }

    assert column(answer("CQ-08"), "incident") == sorted(by_gate)
    assert len(by_gate) == 7


def test_cq09_no_requirement_of_the_repository_has_been_replaced(graph, questions):
    for requirement in graph.ws.of_class("Requirement"):
        assert ask(graph, questions, "CQ-09", requirement=requirement.id) == []


def test_cq09_walks_the_whole_chain_forward(tmp_path):
    repo, answer = scratch(tmp_path)
    repo.item("REQ-0001", status="superseded")
    repo.item("REQ-0002", status="superseded", replaces="REQ-0001", title="Second")
    repo.item("REQ-0003", status="done", replaces="REQ-0002", title="Third")
    repo.item("REQ-0004", status="draft", replaces="REQ-0003", title="Fourth")
    repo.item("REQ-0005", status="done")

    assert answer("CQ-09", requirement="REQ-0001") == [
        {"requirement": "REQ-0001", "later": "REQ-0002", "status": "superseded", "title": "Second"},
        {"requirement": "REQ-0001", "later": "REQ-0003", "status": "done", "title": "Third"},
        {"requirement": "REQ-0001", "later": "REQ-0004", "status": "draft", "title": "Fourth"},
    ]
    assert column(answer("CQ-09", requirement="REQ-0003"), "later") == ["REQ-0004"]
    assert answer("CQ-09", requirement="REQ-0005") == []


def test_cq09_and_cq04_each_keep_to_their_own_class(tmp_path):
    """Decisions and Requirements share prov:wasRevisionOf. Neither question strays."""
    repo, answer = scratch(tmp_path)
    repo.item("DEC-0001", status="superseded")
    repo.item("DEC-0002", supersedes="DEC-0001")
    repo.item("REQ-0001", status="superseded")
    repo.item("REQ-0002", status="done", replaces="REQ-0001")

    assert answer("CQ-09", requirement="DEC-0001") == []
    # A link across the two classes is refused by `onto validate`. Were one written
    # all the same, the question would still not call a Decision a replaced Requirement.
    repo.item("REQ-0003", replaces="DEC-0001")
    assert answer("CQ-09", requirement="DEC-0001") == []
    assert column(answer("CQ-09", requirement="REQ-0001"), "later") == ["REQ-0002"]
    assert column(answer("CQ-04", decision="DEC-0002"), "earlier") == ["DEC-0001"]
    assert column(answer("CQ-03", term=repo.term), "decision") == []


def test_cq10_no_decision_of_the_repository_names_a_path(graph, questions):
    for path in ("onto.toml", "apps/call-qa-agent/src/call_qa_agent/domain/scoring.py"):
        assert ask(graph, questions, "CQ-10", path=path) == []


def test_cq10_gives_the_decisions_in_force_on_a_path(tmp_path):
    repo, answer = scratch(tmp_path)
    repo.item("DEC-0001", title="Old", status="superseded", affects=["apps/**"])
    repo.item("DEC-0002", title="Domain", supersedes="DEC-0001", affects=["apps/**/domain/*.py"])
    repo.item("DEC-0003", title="Draft", status="draft", affects=["apps/**"])
    repo.item("DEC-0004", title="Docs", affects=["docs/*.md", "apps/**/README.md"])
    repo.item("DEC-0005", title="On a term")
    # Superseded by a decided Decision and not yet marked: out of force all the same.
    repo.item("DEC-0006", title="Unmarked", affects=["apps/**"])
    repo.item("DEC-0007", title="Its successor", supersedes="DEC-0006")

    assert answer("CQ-10", path="apps/billing/src/domain/rules.py") == [
        {
            "path": "apps/billing/src/domain/rules.py",
            "decision": "DEC-0002",
            "glob": "apps/**/domain/*.py",
            "title": "Domain",
        }
    ]
    assert column(answer("CQ-10", path="apps/billing/README.md"), "decision") == ["DEC-0004"]
    assert answer("CQ-10", path="apps/billing/src/app.py") == []


GLOBS = (
    "apps/**",
    "apps/**/domain/*.py",
    "**/*.toml",
    "docs/a?.md",
    "docs/*.md",
    "*.md",
    "tools/**/x.py",
    "src/v1.2/(new)/a+b.py",
    "pages/[id]/{x}|y^z$.tsx",
    "back\\slash.py",
    "angle/<any>",
    "<dirs>angle.py",
)
PATHS = (
    "apps/a.py",
    "apps/x/domain/m.py",
    "apps/x/y/domain/m.py",
    "apps/domain/m.py",
    "apps/x/domain/sub/m.py",
    "appsx/a.py",
    "onto.toml",
    "x/y/onto.toml",
    "ontoXtoml",
    "docs/ab.md",
    "docs/abc.md",
    "docs/a/b.md",
    "README.md",
    "tools/x.py",
    "tools/a/b/x.py",
    "tools/ax.py",
    "src/v1.2/(new)/a+b.py",
    "src/v1x2/(new)/a+b.py",
    "src/v1.2/new/a+b.py",
    "src/v1.2/(new)/aab.py",
    "pages/[id]/{x}|y^z$.tsx",
    "pages/i/{x}|y^z$.tsx",
    "pages/[id]/{x}",
    "back\\slash.py",
    "backslash.py",
    "angle/<any>",
    "angle/b.py",
    "<dirs>angle.py",
    "q/angle.py",
)


def test_cq10_reads_a_glob_as_the_slicer_does(tmp_path):
    """The question turns a glob into a regular expression in SPARQL, the slicer in Python."""
    repo, answer = scratch(tmp_path)
    for number, glob in enumerate(GLOBS, 1):
        repo.item(f"DEC-{number:04d}", affects=[glob])
    ws = repo.ws()

    matched = 0
    for path in PATHS:
        from_slicer = sorted(decisions_affecting(ws, {path}))
        assert column(answer("CQ-10", path=path), "decision") == from_slicer, path
        matched += len(from_slicer)
    assert matched >= len(GLOBS)  # every glob is exercised by a path it matches


def test_a_path_is_bound_as_text_from_the_command_line(tmp_path, monkeypatch, capsys):
    from onto.cli import main

    repo, _ = scratch(tmp_path)
    repo.item("DEC-0001", title="Docs", affects=["docs/*.md"])
    monkeypatch.setenv("ONTO_ROOT", str(repo.root))

    assert main(["cq", "CQ-10", "--bind", "path=docs/guide.md"]) == 0
    out = capsys.readouterr().out
    assert "DEC-0001" in out and "docs/guide.md" in out
    assert main(["cq"]) == 0
    assert "CQ-10  Which Decisions in force affect a path?  [--bind path=...]" in (
        capsys.readouterr().out
    )


def test_a_question_that_needs_a_binding_says_so(graph, questions):
    with pytest.raises(ValueError, match="needs a value for: term"):
        ask(graph, questions, "CQ-03")
