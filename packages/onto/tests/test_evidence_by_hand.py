"""Evidence is what a test run recorded, where it recorded it, and nothing else is."""

from __future__ import annotations

import io
import json
import subprocess

import pytest
from onto import evidence, frontmatter, gates, guard
from onto.cli import main
from onto.graph import build_graph
from onto.hooks import BLOCK
from onto.testing import scratch_repo
from onto.workitems import validate
from onto.workspace import EVIDENCE_RULE
from rdflib import Literal, URIRef

FORGED = {"id": "EVD-9001", "of_test": "TST-0001", "result": "pass"}


def git(repo, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(repo.root), *identity, *args], check=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A done Requirement whose only Test failed in the last run."""
    scratch = scratch_repo(tmp_path, term="Finding")
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("ONTO_TASK", raising=False)
    scratch.item("REQ-0001", status="done")
    scratch.item("TST-0001")
    scratch.item("EVD-0001", result="fail")
    git(scratch, "init", "-q", "-b", "main")
    git(scratch, "add", "-A")
    git(scratch, "commit", "-q", "-m", "base")
    return scratch


def trace(capsys) -> tuple[int, str]:
    code = main(["trace"])
    return code, capsys.readouterr().out


def refused(repo) -> list[str]:
    return [p.file for p in validate(repo.ws()) if p.rule == EVIDENCE_RULE]


def test_the_failing_requirement_fails_the_trace(repo, capsys):
    code, out = trace(capsys)

    assert code == 1 and "gate:CompleteRequirementIsVerified" in out


@pytest.mark.parametrize(
    "where",
    ["work/EVD-9001.md", "work/notes/EVD-9001.md", "work/evidence/EVD-9001.md"],
)
def test_a_pass_written_by_hand_is_refused_and_proves_nothing(repo, capsys, where):
    repo.write(where, frontmatter.render(FORGED, "written by hand"))

    assert refused(repo) == [where]
    assert "EVD-9001" not in repo.ws().by_id
    code, out = trace(capsys)
    assert code == 1 and "TST-0001:fail" in out


def test_evidence_that_was_committed_is_refused(repo, capsys):
    (repo.root / "work/evidence/EVD-0001.md").write_text(
        frontmatter.render({"id": "EVD-0001", "of_test": "TST-0001", "result": "pass"}, "")
    )
    assert refused(repo) == [] and trace(capsys)[0] == 0  # a run could have recorded this

    git(repo, "add", "-f", "work/evidence/EVD-0001.md")

    assert refused(repo) == ["work/evidence/EVD-0001.md"]
    assert trace(capsys)[0] == 1


def test_committed_evidence_is_refused_where_the_layer_lies_below_the_checkout(
    tmp_path, monkeypatch
):
    outer = tmp_path / "checkout"
    (outer / "services").mkdir(parents=True)
    scratch = scratch_repo(outer / "services", term="Finding")
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    scratch.item("REQ-0001", status="done")
    scratch.item("TST-0001")
    scratch.item("EVD-0001", result="pass")
    subprocess.run(["git", "-C", str(outer), "init", "-q", "-b", "main"], check=True)
    assert refused(scratch) == []

    subprocess.run(["git", "-C", str(outer), "add", "-f", "."], check=True)

    assert refused(scratch) == ["work/evidence/EVD-0001.md"]


def test_another_file_in_the_evidence_folder_is_refused(repo):
    repo.write("work/evidence/REQ-0002.md", frontmatter.render({"id": "REQ-0002"}, ""))

    assert refused(repo) == ["work/evidence/REQ-0002.md"]


def test_a_row_the_matrix_calls_failing_is_an_error_whatever_the_graph_gate_says(repo):
    """Two Evidence items of one Test cannot be loaded any more, so the graph is given them."""
    ws = repo.ws()
    graph = build_graph(ws)
    recorded, forged = graph.node("EVD-0001"), URIRef("urn:forged")
    for _, predicate, value in list(graph.rdf.triples((recorded, None, None))):
        said = Literal("pass", datatype=value.datatype) if str(value) == "fail" else value
        graph.rdf.add((forged, predicate, said))
    problems = gates.run_shacl(ws, graph)
    assert not [p for p in problems if p.rule == gates.VERIFIED]  # the pass satisfies the shape

    rows = gates.traceability(graph)
    (found,) = gates.unverified(ws, rows, problems)

    assert (found.subject, found.rule, found.blocking) == ("REQ-0001", gates.VERIFIED, True)
    assert "failing" in found.message and "TST-0001 (fail)" in found.message


@pytest.mark.parametrize(
    ("tool_input", "decision"),
    [
        ({"file_path": "work/EVD-9001.md", "content": "x"}, guard.DENY),
        ({"file_path": "work/notes.md", "content": "---\nid: EVD-9001\n---\n"}, guard.DENY),
        (
            {
                "file_path": "work/TST-0001.md",
                "old_string": "id: TST-0001",
                "new_string": "id: EVD-0001",
            },
            guard.DENY,
        ),
        ({"file_path": "work/notes.md", "content": "---\nid: REQ-0009\n---\n"}, guard.ALLOW),
    ],
)
def test_the_guard_denies_evidence_wherever_it_is_written(repo, tool_input, decision):
    assert guard.decide(repo.ws(), tool_input["file_path"], tool_input)[0] == decision


def test_the_guard_hook_blocks_a_write_of_evidence_outside_the_folder(repo, monkeypatch, capsys):
    event = {"tool_input": {"file_path": "work/EVD-9001.md", "content": "x"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert main(["guard"]) == BLOCK
    assert "only a test run may write" in capsys.readouterr().err


# --- a run that did not happen -------------------------------------------------------


def test_without_pytest_nothing_ran_and_old_evidence_does_not_stand_in(repo, monkeypatch, capsys):
    (repo.root / "work/evidence/EVD-0001.md").write_text(
        frontmatter.render({"id": "EVD-0001", "of_test": "TST-0001", "result": "pass"}, "")
    )
    monkeypatch.setattr(evidence, "_pytest_installed", lambda: False)

    run = evidence.collect(repo.ws(), evidence.tests_for(repo.ws(), None))
    assert not run.ok and "pytest is not installed" in run.output

    assert main(["evidence", "collect"]) == 1
    said = capsys.readouterr()
    assert "ran 1 test item(s)" not in said.out and "could not complete" in said.err
    assert main(["trace", "--collect"]) == 1
    assert "pytest is not installed" in capsys.readouterr().err


def test_a_pytest_that_stopped_before_the_recorder_spoke_is_not_a_run(repo, monkeypatch):
    done = subprocess.CompletedProcess([], 1, stdout="", stderr="No module named pytest")
    monkeypatch.setattr(evidence.subprocess, "run", lambda *a, **k: done)

    assert not evidence.collect(repo.ws(), evidence.tests_for(repo.ws(), None)).ok


def test_collecting_drops_the_evidence_of_a_test_that_is_gone(repo, capsys):
    repo.item("EVD-0002", of_test="TST-0002")  # left behind by another branch
    (stale,) = validate(repo.ws())
    assert stale.rule == "dangling-reference" and "onto evidence collect" in stale.fix

    assert evidence.prune(repo.ws()) == ["EVD-0002"]

    assert not (repo.root / "work/evidence/EVD-0002.md").exists()
    assert (repo.root / "work/evidence/EVD-0001.md").exists()
    assert validate(repo.ws()) == []


# --- a folder of work items that cannot be read -------------------------------------


def test_what_cannot_be_read_under_work_is_a_violation_and_stops_no_gate(repo, capsys):
    (repo.root / "work/notes.md").mkdir()  # a folder named like a work item
    (repo.root / "work/notes.md/.DS_Store").write_text("x")
    (repo.root / "work/REQ-0009.md").write_bytes(b"\xff\xfe not text\n")

    problems = validate(repo.ws())

    assert [(p.rule, p.file) for p in problems] == [("frontmatter", "work/REQ-0009.md")]
    assert guard.decide(repo.ws(), "ontology/workflow.yaml")[0] == guard.DENY
    assert main(["trace"]) == 1 and "IsADirectoryError" not in capsys.readouterr().out


def test_a_guard_that_cannot_decide_asks_a_person(repo, monkeypatch, capsys):
    def broken(*args, **kwargs):
        raise IsADirectoryError(21, "Is a directory", "work/notes.md")

    monkeypatch.setattr(guard, "decide", broken)
    event = {"tool_input": {"file_path": "ontology/workflow.yaml", "content": "x"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert main(["guard"]) == 0
    answer = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert (
        answer["permissionDecision"] == "ask"
        and "IsADirectoryError" in (answer["permissionDecisionReason"])
    )
