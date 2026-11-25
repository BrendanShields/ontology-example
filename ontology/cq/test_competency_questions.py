"""Competency questions as tests.

Each question is a SPARQL file in this folder. The first group of tests pins
its answer on this repository's own work items, so a change to the ontology
that breaks a question fails the build. The second group checks that the
questions that guard a rule do find a violation when there is one.
"""

from __future__ import annotations

import pytest
from onto import cq
from onto.graph import build_graph, load_graph
from onto.slicing import decisions_in_force
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
    assert len(questions) == 7
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


def test_a_question_that_needs_a_binding_says_so(graph, questions):
    with pytest.raises(ValueError, match="needs a value for: term"):
        ask(graph, questions, "CQ-03")
