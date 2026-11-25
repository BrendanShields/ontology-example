"""The graph gates, evidence, provenance, the view, and the hook modes of the CLI."""

from __future__ import annotations

import io
import json
import subprocess

import pytest
from onto import evidence, gates, guard, prov, view
from onto.cli import main
from onto.graph import build_graph
from onto.hooks import BLOCK
from onto.report import errors
from onto.testing import TEST_PATH, scratch_repo
from rdflib import RDF, Namespace, URIRef

PROV = Namespace("http://www.w3.org/ns/prov#")
DOMAIN = "apps/call-qa-agent/src/call_qa_agent/domain/example.py"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("ONTO_TASK", raising=False)
    return scratch


def gate(repo) -> dict[str, list[str]]:
    """Blocking gate results as {subject: [rule, ...]}."""
    ws = repo.ws()
    found: dict[str, list[str]] = {}
    for problem in errors(gates.run_shacl(ws, build_graph(ws))):
        found.setdefault(problem.subject, []).append(problem.rule)
    return found


def verified(repo, requirement="REQ-0001", test="TST-0001", result="pass", **fields):
    repo.item(requirement, **fields)
    repo.item(test, verifies=[requirement])
    repo.item("EVD-" + test.split("-")[1], of_test=test, result=result)


def run(*argv, stdin: dict | None = None, monkeypatch=None, capsys=None):
    if monkeypatch is not None:
        text = json.dumps(stdin) if stdin is not None else ""
        monkeypatch.setattr("sys.stdin", io.StringIO(text))
    code = main(list(argv))
    captured = capsys.readouterr() if capsys is not None else None
    return code, captured


# --- the gates ---------------------------------------------------------------------


def test_the_real_repository_structure_conforms_to_the_generated_shapes():
    from onto.workspace import Workspace

    ws = Workspace.at()
    problems = gates.run_shacl(ws, build_graph(ws))
    assert [p for p in problems if p.rule == "shape"] == []


def test_a_done_requirement_needs_a_test_with_passing_evidence(repo):
    repo.item("REQ-0001", status="done")
    assert gate(repo) == {"REQ-0001": ["gate:CompleteRequirementIsVerified"]}

    repo.item("TST-0001")  # a test, but no evidence yet
    ws = repo.ws()
    (problem,) = errors(gates.run_shacl(ws, build_graph(ws)))
    assert "TST-0001 has no passing Evidence" in problem.message

    repo.item("EVD-0001", result="fail")
    assert "REQ-0001" in gate(repo)
    repo.item("EVD-0001", result="pass")
    assert gate(repo) == {}


def test_a_requirement_that_is_not_claimed_complete_is_left_alone(repo):
    repo.item("REQ-0001", status="in_progress")
    repo.item("TASK-0001", status="in_progress")
    assert gate(repo) == {}


def test_all_tasks_done_is_a_claim_too(repo):
    # Nobody marked the Requirement done, but every Task that implements it is.
    repo.item("REQ-0001", status="in_progress")
    repo.item("TASK-0001", status="done")
    repo.item("TASK-0002", status="done")
    assert gate(repo) == {"REQ-0001": ["gate:CompleteRequirementIsVerified"]}
    repo.item("TASK-0002", status="in_progress")
    assert gate(repo) == {}


def test_a_done_change_resolves_only_done_tasks(repo):
    verified(repo)
    repo.item("TASK-0001", status="in_progress")
    repo.item("CHG-0001", status="done")
    assert gate(repo) == {"CHG-0001": ["gate:DoneChangeResolvesDoneTasks"]}


def test_personal_information_needs_a_high_risk_tier(repo):
    pii = {"ears_text": "The system shall store each `Utterance`.", "uses_terms": ["Utterance"]}
    repo.item("REQ-0001", **pii, risk_tier="medium")
    assert gate(repo) == {"REQ-0001": ["gate:PiiRequirementIsHighRisk"]}
    repo.item("REQ-0001", **pii, risk_tier=None)
    assert gate(repo) == {"REQ-0001": ["gate:PiiRequirementIsHighRisk"]}
    repo.item("REQ-0001", **pii, risk_tier="critical")
    assert gate(repo) == {}


def test_supersession_is_recorded_on_both_ends(repo):
    repo.item("DEC-0001", status="done")
    repo.item("DEC-0002", supersedes="DEC-0001")
    assert gate(repo) == {"DEC-0001": ["gate:SupersededDecisionIsMarked"]}
    repo.item("DEC-0001", status="superseded")
    assert gate(repo) == {}
    # Marked superseded with nothing superseding it:
    repo.item("DEC-0003", status="superseded")
    assert gate(repo) == {"DEC-0003": ["gate:SupersededDecisionIsMarked"]}


def test_a_draft_decision_supersedes_nothing_yet(repo):
    repo.item("DEC-0001", status="done")
    repo.item("DEC-0002", status="draft", supersedes="DEC-0001")
    assert gate(repo) == {}


def test_a_supersession_cycle_is_caught(repo):
    repo.item("DEC-0001", status="superseded", supersedes="DEC-0002")
    repo.item("DEC-0002", status="superseded", supersedes="DEC-0001")
    assert set(gate(repo)) == {"DEC-0001", "DEC-0002"}


def test_the_generated_shapes_catch_what_file_checks_would_also_catch(repo):
    repo.item("REQ-0001", uses_terms=["Calibration"])
    repo.item("TASK-0001", implements=["REQ-0404"])
    found = gate(repo)
    assert found["REQ-0001"] == ["shape"] and found["TASK-0001"] == ["shape"]


def test_traceability_matrix_and_coverage(repo):
    verified(repo, status="done")
    repo.item("REQ-0002", status="ready")
    repo.item("REQ-0003", status="draft")
    repo.item("TASK-0001", implements=["REQ-0001", "REQ-0002"])
    rows = {r.requirement: r for r in gates.traceability(build_graph(repo.ws()))}
    assert rows["REQ-0001"].verdict == "verified" and rows["REQ-0001"].tasks == {"TASK-0001"}
    assert rows["REQ-0002"].verdict == "untested"
    # A draft is not yet agreed, so it does not count against coverage.
    assert gates.coverage(list(rows.values())) == {"requirements": 2, "with_test": 1, "verified": 1}


def test_branch_scope_follows_the_trace_links(repo):
    git = [
        "git",
        "-C",
        str(repo.root),
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "-c",
        "commit.gpgsign=false",
    ]
    verified(repo, status="done")
    repo.item("REQ-0002", status="done")
    repo.item("TASK-0001")
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], check=True)
    assert gates.branch_scope(repo.ws()) == set()

    # Touch one work item: its requirement, and what verifies and implements it, come into scope.
    repo.item("TST-0001", title="Reworded")
    assert gates.branch_scope(repo.ws()) == {"TST-0001", "REQ-0001", "TASK-0001", "EVD-0001"}

    # Touch an app's code: every finished requirement of its context comes into scope.
    subprocess.run([*git, "checkout", "-q", "--", "."], check=True)
    repo.write("apps/call-qa-agent/src/call_qa_agent/agent.py", "x = 1\n")
    assert {"REQ-0001", "REQ-0002"} <= gates.branch_scope(repo.ws())


def test_a_branch_with_no_base_to_compare_with_is_answerable_for_everything(repo):
    git = ["git", "-C", str(repo.root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    git += ["-c", "commit.gpgsign=false"]
    repo.item("REQ-0001", status="done")
    subprocess.run([*git, "init", "-q", "-b", "work"], check=True)
    # Before the first commit, everything is new.
    assert "REQ-0001" in gates.branch_scope(repo.ws())

    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "claim"], check=True)
    # No origin/main, main or master: a committed claim must not drop out of scope.
    assert gates.branch_scope(repo.ws()) is None

    subprocess.run([*git, "branch", "main"], check=True)
    assert gates.branch_scope(repo.ws()) == set()


# --- evidence ----------------------------------------------------------------------


def test_evidence_is_recorded_only_for_tests_that_fully_ran(repo):
    repo.item("REQ-0001")
    repo.item("TST-0001", path="tests/test_a.py::TestThing")
    repo.item("TST-0002", path="tests/test_b.py")
    repo.item("TST-0003", path="tests/test_c.py::test_one")
    repo.item("TST-0004", path="tests/test_d.py::test_skipped")
    outcomes = {
        "tests/test_a.py::TestThing::test_x": "passed",
        "tests/test_a.py::TestThing::test_y[case1]": "passed",
        "tests/test_b.py::test_ok": "passed",
        "tests/test_b.py::test_broken": "failed",
        "tests/test_d.py::test_skipped": "skipped",
    }
    written = evidence.record(repo.ws(), outcomes)
    results = {e.id: e.meta["result"] for e in repo.ws().of_class("Evidence")}

    assert written == ["EVD-0001", "EVD-0002", "EVD-0004"]
    # A class passes when all its tests pass, a file fails when one test fails,
    # a skipped test proves nothing, and a test that did not run gets no evidence.
    assert results == {"EVD-0001": "pass", "EVD-0002": "fail", "EVD-0004": "fail"}


def test_a_partly_deselected_test_gets_no_evidence(repo):
    repo.item("REQ-0001")
    repo.item("TST-0001", path="tests/test_a.py")
    outcomes = {"tests/test_a.py::test_x": "passed"}
    assert evidence.record(repo.ws(), outcomes, {"tests/test_a.py::test_y"}) == []


def test_collecting_evidence_runs_the_real_tests(repo):
    repo.item("REQ-0001")
    repo.item("TST-0001")
    repo.write("tests/test_example.py", "def test_example():\n    assert 1 + 1 == 2\n")
    collected = evidence.collect(repo.ws(), evidence.tests_for(repo.ws(), None))
    assert collected.ok, collected.output
    (item,) = repo.ws().of_class("Evidence")
    assert (item.id, item.meta["of_test"], item.meta["result"]) == ("EVD-0001", "TST-0001", "pass")

    repo.write("tests/test_example.py", "def test_example():\n    assert 1 + 1 == 3\n")
    assert evidence.collect(repo.ws(), evidence.tests_for(repo.ws(), None)).ok
    assert repo.ws().by_id["EVD-0001"].meta["result"] == "fail"
    assert TEST_PATH in repo.ws().by_id["EVD-0001"].body


# --- the guard ---------------------------------------------------------------------


def test_the_guard(repo):
    ws = repo.ws()
    decide = lambda path: guard.decide(repo.ws(), str(repo.root / path))[0]  # noqa: E731

    assert decide("apps/call-qa-agent/src/call_qa_agent/domain/scoring.py") == guard.ALLOW
    assert decide("work/REQ-0001.md") == guard.ALLOW
    assert decide("ontology/cq/CQ-01-requirements-a-change-serves.rq") == guard.ALLOW
    # Generated files and evidence are never edited.
    assert decide("ontology/schemas/workflow.schema.json") == guard.DENY
    assert decide("apps/call-qa-agent/src/call_qa_agent/generated.py") == guard.DENY
    assert decide("work/evidence/EVD-0001.md") == guard.DENY
    # Ontology sources need a change request in progress, and then a person's yes.
    assert decide("ontology/domains/call-qa.yaml") == guard.DENY
    assert "onto ocr new" in guard.decide(ws, "ontology/workflow.yaml")[1]
    repo.item("OCR-0001", status="draft")
    assert decide("ontology/domains/call-qa.yaml") == guard.DENY
    repo.item("OCR-0001", status="in_progress")
    decision, reason = guard.decide(repo.ws(), "ontology/domains/call-qa.yaml")
    assert decision == guard.ASK and "OCR-0001" in reason


def test_the_guard_hook_blocks_asks_or_stays_silent(repo, monkeypatch, capsys):
    def edit(path):
        return {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(repo.root / path),
                "old_string": "a",
                "new_string": "b",
            },
        }

    code, out = run("guard", stdin=edit("README.md"), monkeypatch=monkeypatch, capsys=capsys)
    assert (code, out.out, out.err) == (0, "", "")

    code, out = run(
        "guard", stdin=edit("ontology/workflow.yaml"), monkeypatch=monkeypatch, capsys=capsys
    )
    assert code == BLOCK and "OntologyChangeRequest" in out.err

    repo.item("OCR-0001", status="in_progress")
    code, out = run(
        "guard", stdin=edit("ontology/workflow.yaml"), monkeypatch=monkeypatch, capsys=capsys
    )
    answer = json.loads(out.out)["hookSpecificOutput"]
    assert (
        code == 0
        and answer["permissionDecision"] == "ask"
        and "OCR-0001" in answer["permissionDecisionReason"]
    )


# --- the term check as a hook ------------------------------------------------------


def write_event(repo, path, content):
    repo.write(path, content)
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(repo.root / path), "content": content},
    }


def test_the_term_hook_blocks_a_denied_synonym_with_what_to_write(repo, monkeypatch, capsys):
    event = write_event(repo, DOMAIN, "def load_rubric():\n    return None\n")
    code, out = run(
        "check-terms", "--changed-from-stdin", stdin=event, monkeypatch=monkeypatch, capsys=capsys
    )
    assert code == BLOCK
    assert f"{DOMAIN}:1: error[denied-term]" in out.err and "did you mean: Scorecard" in out.err


def test_the_term_hook_only_warns_about_a_coined_class(repo, monkeypatch, capsys):
    event = write_event(repo, DOMAIN, "class Calibration:\n    pass\n")
    code, out = run(
        "check-terms", "--changed-from-stdin", stdin=event, monkeypatch=monkeypatch, capsys=capsys
    )
    context = json.loads(out.out)["hookSpecificOutput"]
    assert code == 0 and context["hookEventName"] == "PostToolUse"
    assert "warning[unknown-term]" in context["additionalContext"]


def test_the_term_hook_checks_only_what_an_edit_inserted(repo, monkeypatch, capsys):
    repo.write(DOMAIN, "rubric = 1\nscore = 2\n")
    event = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(repo.root / DOMAIN),
            "old_string": "score = 1",
            "new_string": "score = 2",
        },
    }
    code, out = run(
        "check-terms", "--changed-from-stdin", stdin=event, monkeypatch=monkeypatch, capsys=capsys
    )
    assert (code, out.out, out.err) == (0, "", "")


def test_the_term_hook_validates_an_edited_work_item_and_ignores_other_files(
    repo, monkeypatch, capsys
):
    path = repo.item("REQ-0001", uses_terms=["Rubric"])
    event = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": "x"}}
    code, out = run(
        "check-terms", "--changed-from-stdin", stdin=event, monkeypatch=monkeypatch, capsys=capsys
    )
    assert code == BLOCK and "error[denied-term]" in out.err

    event = write_event(repo, "apps/call-qa-agent/README.md", "The rubric is here.\n")
    code, out = run(
        "check-terms", "--changed-from-stdin", stdin=event, monkeypatch=monkeypatch, capsys=capsys
    )
    assert (code, out.out, out.err) == (0, "", "")


def test_a_hook_with_no_event_does_nothing(repo, monkeypatch, capsys):
    for argv in (("guard",), ("check-terms", "--changed-from-stdin")):
        code, out = run(*argv, stdin=None, monkeypatch=monkeypatch, capsys=capsys)
        assert (code, out.out) == (0, "")


# --- the stop gate -----------------------------------------------------------------


def test_the_stop_gate_blocks_once_then_hands_back(repo, monkeypatch, capsys):
    repo.item("REQ-0001", status="done")  # a claim with nothing behind it
    stop = ("trace", "--gate", "stop", "--scope", "all")

    code, out = run(
        *stop,
        stdin={"hook_event_name": "Stop", "stop_hook_active": False},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert code == BLOCK and out.out == ""
    assert "REQ-0001" in out.err and "in_progress, not done" in out.err

    # Claude was already sent back once: do not loop, leave it to the person and to CI.
    code, out = run(
        *stop,
        stdin={"hook_event_name": "Stop", "stop_hook_active": True},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert code == 1 and "REQ-0001" in out.err


def test_the_stop_gate_is_silent_when_the_gate_holds(repo, monkeypatch, capsys):
    verified(repo, status="done")
    code, out = run(
        "trace",
        "--gate",
        "stop",
        "--scope",
        "all",
        stdin={},
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert (code, out.out, out.err) == (0, "", "")


def test_trace_in_ci_prints_the_matrix_and_fails_on_a_gate_error(repo, monkeypatch, capsys):
    repo.item("REQ-0001", status="done")
    code, out = run("trace", monkeypatch=monkeypatch, capsys=capsys)
    assert (
        code == 1
        and "untested" in out.out
        and "error[gate:CompleteRequirementIsVerified]" in out.out
    )


# --- provenance --------------------------------------------------------------------


def test_a_provenance_bundle_says_what_a_change_rested_on(repo):
    verified(repo, status="done", uses_terms=["Finding"])
    repo.item("TASK-0001", status="done")
    repo.item("DEC-0001", uses_terms=["Finding"])
    repo.item("DEC-0002", uses_terms=["Scorecard"])  # about another term: not used
    repo.item("CHG-0001", status="done", generated_by_agent="claude-code")
    prov.append_decision(
        repo.ws().cfg,
        "TASK-0001",
        phase="design",
        decision="reject\tin the tool",
        why="grounding",
        evidence="DEC-0001",
        result="tests green",
    )
    ws = repo.ws()

    bundle = prov.bundle(ws, build_graph(ws), ws.by_id["CHG-0001"], ws.cfg.audit_dir)
    work = Namespace(ws.schema.work_ns)
    change = work["CHG-0001"]

    assert (change, RDF.type, PROV.Activity) in bundle
    assert set(bundle.objects(change, PROV.used)) == {work["REQ-0001"], work["DEC-0001"]}
    (agent,) = bundle.objects(change, PROV.wasAssociatedWith)
    assert (agent, RDF.type, PROV.SoftwareAgent) in bundle
    assert (work["EVD-0001"], PROV.wasDerivedFrom, work["TST-0001"]) in bundle
    # The decision log row is in the bundle, typed by the workflow ontology.
    (logged,) = bundle.subjects(RDF.type, URIRef(ws.schema.wf_ns + "LoggedDecision"))
    assert str(bundle.value(logged, PROV.value)) == "reject in the tool"  # the tab was flattened
    assert bundle.value(logged, URIRef(ws.schema.wf_ns + "concerns")) == work["TASK-0001"]

    # What the bundle adds still conforms to the generated shapes.
    import pyshacl

    conforms, _, text = pyshacl.validate(bundle, shacl_graph=gates.shapes_graph(ws.cfg))
    assert conforms, text


def test_prov_emit_writes_one_file_per_change(repo, monkeypatch, capsys):
    verified(repo, status="done")
    repo.item("TASK-0001", status="done")
    repo.item("CHG-0001", status="done")
    code, out = run("prov", "emit", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0 and out.out.strip() == "prov/CHG-0001.ttl"
    assert "prov:Activity" in (repo.root / "prov/CHG-0001.ttl").read_text()


# --- the view ----------------------------------------------------------------------


def stage_of(repo, task="TASK-0001"):
    (found,) = [t for t in view.build(repo.ws())["tasks"] if t["id"] == task]
    return found["stage"], found["blocked"]


def test_a_task_moves_through_the_stages_as_the_repository_changes(repo):
    repo.item("REQ-0001", status="draft")
    repo.item("TASK-0001", status="in_progress")
    assert stage_of(repo) == ("intake", False)  # the Requirement is not agreed

    repo.item("REQ-0001", status="in_progress", uses_terms=["Rubric"])
    assert stage_of(repo) == ("vocabulary", True)  # blocked by the glossary

    repo.item("REQ-0001", status="in_progress")
    assert stage_of(repo) == ("design", False)  # no Decision on these terms

    repo.item("DEC-0001", uses_terms=["Finding"])
    assert stage_of(repo) == ("implement", False)  # no Test yet

    repo.write(DOMAIN, "rubric = 1\n")
    assert stage_of(repo) == ("implement", True)  # a denied synonym in the domain layer
    repo.write(DOMAIN, "score = 1\n")

    repo.item("TST-0001")
    assert stage_of(repo) == ("verify", False)  # a Test, no Evidence
    repo.item("EVD-0001", result="fail")
    assert stage_of(repo) == ("verify", True)
    repo.item("EVD-0001", result="pass")
    assert stage_of(repo) == ("trace", False)  # verified, but not yet claimed

    repo.item("REQ-0001", status="done")
    repo.item("TASK-0001", status="done")
    assert stage_of(repo) == ("ship", False)  # no Change record

    repo.item("CHG-0001", status="done")
    assert stage_of(repo) == ("complete", False)


def test_the_view_holds_the_ontology_and_the_plan(repo):
    repo.item("REQ-0001")
    repo.item("TASK-0001", status="in_progress")
    repo.item("TASK-0002", status="ready", blocked_by=["TASK-0001"])
    repo.item("DEC-0001", status="superseded")
    repo.item("DEC-0002", supersedes="DEC-0001")
    repo.item("OCR-0001")
    built = view.build(repo.ws())

    assert built["plan"]["order"] == ["TASK-0001", "TASK-0002"]
    assert [d["id"] for d in built["plan"]["decisions_in_force"]] == ["DEC-0002"]
    assert built["plan"]["superseded_decisions"][0]["superseded_by"] == "DEC-0002"
    assert built["plan"]["open_change_requests"][0]["term"] == "Calibration"
    (context,) = built["ontology"]["contexts"]
    assert "Scorecard" in [c["name"] for c in context["classes"]]
    assert {"slot": "implements", "to": "Requirement", "many": True} in next(
        w["links"] for w in built["ontology"]["workflow"] if w["name"] == "Task"
    )
    assert "[>]" in view.render_text(built)
    json.dumps(built)  # the whole document is plain JSON


def test_the_view_of_the_real_repository():
    from onto.workspace import Workspace

    built = view.build(Workspace.at())
    stages = {t["id"]: t["stage"] for t in built["tasks"]}
    assert stages["TASK-0004"] == "design"
    # TASK-0001 is implemented and tested. Whether it shows as verified depends on
    # Evidence, which only a test run writes, so a clean checkout has it at verify.
    assert stages["TASK-0001"] in ("verify", "complete")
    unrelated_to_evidence = [
        v for v in built["trace"]["violations"] if v["rule"] != "gate:CompleteRequirementIsVerified"
    ]
    assert unrelated_to_evidence == []


# --- generation --------------------------------------------------------------------


def test_gen_check_notices_a_hand_edited_generated_file(repo, monkeypatch, capsys):
    pytest.importorskip("linkml")
    code, out = run("gen", "--check", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0, out.out

    target = repo.root / "ontology/schemas/workflow.schema.json"
    target.write_text(target.read_text().replace('"superseded"', '"retired"'))
    code, out = run("gen", "--check", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 1 and "drift" in out.out and '-        "retired"' in out.out


def test_gen_check_notices_an_ontology_change_that_was_not_compiled(repo, monkeypatch, capsys):
    pytest.importorskip("linkml")
    source = repo.root / "ontology/domains/call-qa.yaml"
    source.write_text(
        source.read_text().replace(
            "    minimum_value: 1\n    required: true",
            "    minimum_value: 2\n    required: true",
            1,
        )
    )
    code, out = run("gen", "--check", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 1 and "generated.py" in out.out


def test_a_tool_that_cannot_run_never_blocks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ONTO_ROOT", str(tmp_path))  # no onto.toml there
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    code, out = run(
        "guard", stdin={"tool_input": {"file_path": "x"}}, monkeypatch=monkeypatch, capsys=capsys
    )
    assert code == 1 and "no onto.toml" in out.err  # 1 is a non-blocking error for a hook
