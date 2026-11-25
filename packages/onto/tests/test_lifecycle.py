"""The lifecycle past ship: Incidents, Requirements that replace one another, Decisions on paths.

Each gate constraint is shown to fail and to pass on a scratch repository, and
each command that reads the new links is checked on the work items that carry them.
"""

from __future__ import annotations

import json
import subprocess

import pytest
from onto import create, gates, prov, slicing, view, workitems
from onto.cli import main
from onto.graph import build_graph
from onto.report import errors
from onto.testing import scratch_repo
from rdflib import RDF, Literal, Namespace, URIRef

PROV = Namespace("http://www.w3.org/ns/prov#")
DATE = URIRef("http://www.w3.org/2001/XMLSchema#date")
REPLACED = "gate:ReplacedRequirementIsMarked"
CLOSED = "gate:ClosedIncidentIsFixed"
SUPERSEDED_DECISION = "gate:SupersededDecisionIsMarked"
UNVERIFIED = "gate:CompleteRequirementIsVerified"
APP_FILE = "apps/call-qa-agent/src/call_qa_agent/agent.py"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path, term="Finding")
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


def verified(repo, requirement: str, **fields):
    """A Requirement with a Test and passing Evidence, numbered after it."""
    number = requirement.split("-")[1]
    repo.item(requirement, **fields)
    repo.item(f"TST-{number}", verifies=[requirement])
    repo.item(f"EVD-{number}", of_test=f"TST-{number}")


def git(repo, *args: str) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(repo.root), *identity, *args], check=True)


def committed(repo) -> None:
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")


# --- writing and the graph ---------------------------------------------------------


def test_onto_new_writes_an_incident_that_validates_and_links(repo, capsys):
    repo.item("REQ-0001")

    code = main(
        ["new", "Incident", "title=Scores went out early", "bounded_context=call-qa"]
        + ["observed_on=2026-02-03", "breaks=REQ-0001", "status=in_progress"]
    )

    assert code == 0 and "work/INC-0001.md" in capsys.readouterr().out
    ws = repo.ws()
    assert ws.by_id["INC-0001"].cls == "Incident"
    assert workitems.validate(ws) == []  # as read back from the file, date and all
    assert create.next_id(ws, "Incident") == "INC-0002"


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        ({"breaks": ["REQ-0404"]}, "dangling-reference"),
        ({"breaks": ["TASK-0001"]}, "dangling-reference"),
        ({"observed_on": "last Tuesday"}, "schema"),
    ],
)
def test_an_incident_that_breaks_a_rule_is_refused_and_nothing_is_written(repo, fields, rule):
    repo.item("REQ-0001")
    repo.item("TASK-0001")
    given = {"title": "T", "bounded_context": "call-qa", "observed_on": "2026-02-03", **fields}

    path, problems = create.create(repo.ws(), "Incident", given)

    assert path is None and rule in [p.rule for p in problems]
    assert not (repo.root / "work/INC-0001.md").exists()


def test_the_graph_carries_the_new_links(repo):
    repo.item("REQ-0001", status="superseded")
    repo.item("INC-0001", breaks=["REQ-0001"])
    repo.item("REQ-0002", replaces="REQ-0001", raised_from="INC-0001")
    repo.item("DEC-0001", affects=["apps/**/*.py", "docs/*.md"])
    ws = repo.ws()
    rdf = build_graph(ws).rdf
    wf, work = Namespace(ws.schema.wf_ns), Namespace(ws.schema.work_ns)

    assert (work["REQ-0002"], PROV.wasRevisionOf, work["REQ-0001"]) in rdf
    assert (work["REQ-0002"], wf.raised_from, work["INC-0001"]) in rdf
    assert (work["INC-0001"], wf.breaks, work["REQ-0001"]) in rdf
    assert (work["INC-0001"], wf.observed_on, Literal("2026-01-15", datatype=DATE)) in rdf
    assert set(rdf.objects(work["DEC-0001"], wf.affects)) == {
        Literal("apps/**/*.py"),
        Literal("docs/*.md"),
    }
    assert {wf.Incident, wf.WorkItem, PROV.Entity} <= set(rdf.objects(work["INC-0001"], RDF.type))


# --- gate: a replaced Requirement is marked ----------------------------------------


def test_a_done_requirement_marks_the_one_it_replaces(repo):
    verified(repo, "REQ-0001", status="done")
    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    assert gate(repo) == {"REQ-0001": [REPLACED]}

    repo.item("REQ-0001", status="superseded")
    assert gate(repo) == {}


def test_a_requirement_that_is_not_done_replaces_nothing_yet(repo):
    verified(repo, "REQ-0001", status="done")
    for status in ("draft", "ready", "in_progress"):
        repo.item("REQ-0002", status=status, replaces="REQ-0001")
        assert gate(repo) == {}, status


def test_a_superseded_requirement_names_its_successor(repo):
    repo.item("REQ-0001", status="superseded")
    assert gate(repo) == {"REQ-0001": [REPLACED]}

    repo.item("REQ-0002", replaces="REQ-0001")
    assert gate(repo) == {}


# --- gate: a closed Incident is fixed ----------------------------------------------


def test_an_incident_is_not_closed_while_a_requirement_it_breaks_is_open(repo):
    verified(repo, "REQ-0001", status="in_progress")
    repo.item("INC-0001", status="done", breaks=["REQ-0001"])
    assert gate(repo) == {"INC-0001": [CLOSED]}

    repo.item("REQ-0001", status="done")
    assert gate(repo) == {}


def test_an_incident_is_not_closed_while_a_requirement_raised_from_it_is_open(repo):
    repo.item("INC-0001", status="done")
    verified(repo, "REQ-0001", status="ready", raised_from="INC-0001")
    assert gate(repo) == {"INC-0001": [CLOSED]}

    repo.item("REQ-0001", status="done", raised_from="INC-0001")
    assert gate(repo) == {}


def test_every_requirement_of_an_incident_counts_not_only_one(repo):
    verified(repo, "REQ-0001", status="done")
    verified(repo, "REQ-0002", status="in_progress", raised_from="INC-0001")
    repo.item("INC-0001", status="done", breaks=["REQ-0001"])
    assert gate(repo) == {"INC-0001": [CLOSED]}


def test_an_incident_is_not_closed_by_saying_so(repo):
    repo.item("INC-0001", status="done")
    assert gate(repo) == {"INC-0001": [CLOSED]}

    repo.item("INC-0001", status="in_progress")
    assert gate(repo) == {}  # open, with nothing named yet: that is intake


def test_a_closed_incident_rests_on_passing_evidence(repo):
    # The Incident gate reads statuses. The traceability gate is what makes done mean verified.
    repo.item("REQ-0001", status="done")
    repo.item("INC-0001", status="done", breaks=["REQ-0001"])
    assert gate(repo) == {"REQ-0001": [UNVERIFIED]}


def test_a_requirement_replaced_after_the_incident_still_closes_it(repo):
    repo.item("REQ-0001", status="superseded")
    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    repo.item("INC-0001", status="done", breaks=["REQ-0001"])
    assert gate(repo) == {}


# --- the two uses of prov:wasRevisionOf --------------------------------------------


def test_a_chain_of_requirements_does_not_touch_the_decision_gate(repo):
    repo.item("REQ-0001", status="superseded")
    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    repo.item("DEC-0001", status="done")
    assert gate(repo) == {}

    # A Requirement that replaces another is no successor for a Decision.
    repo.item("DEC-0001", status="superseded")
    assert gate(repo) == {"DEC-0001": [SUPERSEDED_DECISION]}


def test_a_chain_of_decisions_does_not_touch_the_requirement_gate(repo):
    repo.item("DEC-0001", status="done")
    repo.item("DEC-0002", supersedes="DEC-0001")
    verified(repo, "REQ-0001", status="done")
    assert gate(repo) == {"DEC-0001": [SUPERSEDED_DECISION]}

    # A Decision that supersedes another is no successor for a Requirement.
    repo.item("DEC-0001", status="superseded")
    repo.item("REQ-0001", status="superseded")
    assert gate(repo) == {"REQ-0001": [REPLACED]}


def test_a_revision_across_the_two_classes_is_refused_under_its_own_slot_name(repo):
    """What keeps the gates apart: neither link can reach the other class."""
    repo.item("REQ-0001")
    repo.item("DEC-0001")
    repo.item("REQ-0002", replaces="DEC-0001")
    repo.item("DEC-0002", supersedes="REQ-0001")
    ws = repo.ws()

    by_file = {p.subject: p.message for p in errors(workitems.validate(ws))}
    assert "replaces must point at a Requirement" in by_file["REQ-0002"]
    assert "supersedes must point at a Decision" in by_file["DEC-0002"]

    shapes = {
        p.subject: p for p in errors(gates.run_shacl(ws, build_graph(ws))) if p.rule == "shape"
    }
    # Both slots are prov:wasRevisionOf: each is reported as the slot of its own class,
    # on the line of the file where it is written.
    assert shapes["REQ-0002"].message.startswith("replaces points at DEC-0001")
    assert shapes["DEC-0002"].message.startswith("supersedes points at REQ-0001")
    assert shapes["REQ-0002"].line == ws.by_id["REQ-0002"].line_of("replaces")
    assert shapes["DEC-0002"].line == ws.by_id["DEC-0002"].line_of("supersedes")


def test_on_a_refused_link_the_decision_gate_takes_a_requirement_for_a_reviser(repo):
    """A limit of gate:SupersededDecisionIsMarked as written, pinned so that it is known.

    The gate does not ask what class the reviser is. The link is refused before
    that matters, by `onto validate` and by the generated shape (the test above),
    so the only effect is one more message on data that is already in error.
    When the gate asks for a Decision, this test fails and can go.
    """
    repo.item("DEC-0001")
    repo.item("REQ-0001", status="done", replaces="DEC-0001")

    found = gate(repo)

    assert found["DEC-0001"] == [SUPERSEDED_DECISION]
    assert "shape" in found["REQ-0001"]


# --- a rule change, start to finish ------------------------------------------------


def shipped_rule(repo) -> None:
    verified(repo, "REQ-0001", status="done")
    repo.item("TASK-0001", status="done", implements=["REQ-0001"])
    repo.item("CHG-0001", status="done", resolves=["TASK-0001"])


def test_a_rule_changes_by_a_requirement_that_replaces_the_old_one(repo):
    shipped_rule(repo)
    assert gate(repo) == {}

    # The new rule is written, built and verified. The Test that pinned the old
    # rule now pins the new one.
    repo.item("REQ-0002", status="in_progress", replaces="REQ-0001")
    repo.item("TASK-0002", status="in_progress", implements=["REQ-0002"])
    repo.item("TST-0001", verifies=["REQ-0002"])
    repo.item("REQ-0002", status="done", replaces="REQ-0001")
    repo.item("TASK-0002", status="done", implements=["REQ-0002"])
    assert REPLACED in gate(repo)["REQ-0001"]

    # The old Requirement and the work that delivered it leave the record of what is in force.
    repo.item("REQ-0001", status="superseded")
    repo.item("TASK-0001", status="superseded", implements=["REQ-0001"])
    repo.item("CHG-0001", status="superseded", resolves=["TASK-0001"])
    assert gate(repo) == {}


def test_a_superseded_requirement_whose_task_is_still_done_is_still_held_to_a_test(repo):
    """A limit of the gates as they stand, which the rule-change playbook works to.

    gate:CompleteRequirementIsVerified reads "all its Tasks are done" as a claim
    whatever the Requirement's own status, so the Task that delivered a replaced
    rule cannot stay done once no Test verifies that rule. When the gate learns
    to leave a superseded Requirement alone, this test fails and the playbook's
    step for the old Task and Change can go.
    """
    shipped_rule(repo)
    repo.item("REQ-0002", status="done", replaces="REQ-0001")
    repo.item("TST-0001", verifies=["REQ-0002"])
    repo.item("REQ-0001", status="superseded")
    assert gate(repo) == {"REQ-0001": [UNVERIFIED]}

    repo.item("TASK-0001", status="superseded", implements=["REQ-0001"])
    assert gate(repo) == {"CHG-0001": ["gate:DoneChangeResolvesDoneTasks"]}


# --- what a branch answers for -----------------------------------------------------


def test_a_branch_that_replaces_a_requirement_answers_for_the_old_one(repo):
    verified(repo, "REQ-0001", status="done")
    committed(repo)

    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    ws = repo.ws()
    scope = gates.branch_scope(ws)

    assert "REQ-0001" in scope  # reached through `replaces`: its file was not touched
    found = gates.in_scope(errors(gates.run_shacl(ws, build_graph(ws))), scope)
    assert [(p.subject, p.rule) for p in found] == [("REQ-0001", REPLACED)]


def test_a_branch_that_reopens_a_requirement_answers_for_the_incident_it_closed(repo):
    verified(repo, "REQ-0001", status="done")
    verified(repo, "REQ-0002", status="done", raised_from="INC-0001")
    repo.item("INC-0001", status="done", breaks=["REQ-0001"])
    committed(repo)
    assert gates.branch_scope(repo.ws()) == set()

    for reopened, fields in (("REQ-0001", {}), ("REQ-0002", {"raised_from": "INC-0001"})):
        repo.item(reopened, status="in_progress", **fields)
        ws = repo.ws()
        found = gates.in_scope(errors(gates.run_shacl(ws, build_graph(ws))), gates.branch_scope(ws))
        assert [(p.subject, p.rule) for p in found] == [("INC-0001", CLOSED)], reopened
        git(repo, "checkout", "-q", "--", ".")


def test_a_branch_that_supersedes_a_task_answers_for_the_change_that_resolved_it(
    repo, monkeypatch, capsys
):
    shipped_rule(repo)
    repo.item("TASK-0009", status="done", implements=["REQ-0001"])
    repo.item("CHG-0009", status="done", resolves=["TASK-0009"])  # another Change, left alone
    committed(repo)
    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    repo.item("TST-0001", verifies=["REQ-0002"])
    repo.item("REQ-0001", status="superseded")
    repo.item("TASK-0001", status="superseded", implements=["REQ-0001"])
    repo.item("TASK-0009", status="superseded", implements=["REQ-0001"])
    repo.item("CHG-0009", status="superseded", resolves=["TASK-0009"])

    # The Change is not drawn into the scope, and the gate on it is still heard.
    assert "CHG-0001" not in gates.branch_scope(repo.ws())
    assert main(["trace", "--scope", "branch"]) == 1
    out = capsys.readouterr().out
    assert "CHG-0001" in out and "gate:DoneChangeResolvesDoneTasks" in out

    repo.item("CHG-0001", status="superseded", resolves=["TASK-0001"])
    assert main(["trace", "--scope", "branch"]) == 0, capsys.readouterr().out


def _drops_replaces(repo):
    verified(repo, "REQ-0001", status="superseded")
    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    yield
    repo.item("REQ-0002", status="done")


def _deletes_the_successor(repo):
    verified(repo, "REQ-0001", status="superseded")
    repo.item("REQ-0002", status="draft", replaces="REQ-0001")
    yield
    (repo.root / "work/REQ-0002.md").unlink()


def _drops_raised_from(repo):
    repo.item("INC-0001", status="done")
    verified(repo, "REQ-0001", status="done", raised_from="INC-0001")
    yield
    repo.item("REQ-0001", status="done")


def _points_the_test_elsewhere(repo):
    verified(repo, "REQ-0001", status="done")
    repo.item("REQ-0002")
    yield
    repo.item("TST-0001", verifies=["REQ-0002"])


@pytest.mark.parametrize(
    ("change", "subject", "rule"),
    [
        (_drops_replaces, "REQ-0001", REPLACED),
        (_deletes_the_successor, "REQ-0001", REPLACED),
        (_drops_raised_from, "INC-0001", CLOSED),
        (_points_the_test_elsewhere, "REQ-0001", UNVERIFIED),
    ],
)
@pytest.mark.parametrize("commit", [False, True], ids=["uncommitted", "committed"])
def test_a_branch_that_takes_a_link_away_answers_for_what_the_link_held(
    repo, monkeypatch, capsys, change, subject, rule, commit
):
    import io

    from onto.hooks import BLOCK

    steps = change(repo)
    next(steps)
    committed(repo)
    assert main(["trace"]) == 0, capsys.readouterr().out
    git(repo, "checkout", "-q", "-b", "work")
    next(steps, None)
    if commit:
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "take the link away")
    capsys.readouterr()

    assert main(["trace"]) == 1
    assert subject in gates.branch_scope(repo.ws())  # its own file was not touched
    assert main(["trace", "--scope", "branch"]) == 1
    out = capsys.readouterr().out
    assert subject in out and rule in out

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "Stop"})))
    assert main(["trace", "--gate", "stop", "--scope", "branch"]) == BLOCK
    assert subject in capsys.readouterr().err


def test_a_base_file_that_cannot_be_read_adds_nothing_to_the_scope(repo):
    repo.write("work/REQ-0002.md", "no frontmatter here\n")
    committed(repo)
    verified(repo, "REQ-0002", status="done")

    assert gates.branch_scope(repo.ws()) == {"REQ-0002", "TST-0002", "EVD-0002"}


def test_the_stop_gate_holds_an_incident_closed_too_early(repo, monkeypatch, capsys):
    import io

    from onto.hooks import BLOCK

    verified(repo, "REQ-0001", status="in_progress")
    repo.item("INC-0001", breaks=["REQ-0001"])
    committed(repo)
    repo.item("INC-0001", status="done", breaks=["REQ-0001"])

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "Stop"})))
    code = main(["trace", "--gate", "stop", "--scope", "branch"])

    assert code == BLOCK
    assert "INC-0001" in capsys.readouterr().err


# --- slices ------------------------------------------------------------------------


def in_hand(repo) -> None:
    repo.item("REQ-0001", status="in_progress")
    repo.item("TASK-0001", status="in_progress")


def test_a_decision_joins_the_slice_of_work_that_touches_a_file_it_affects(repo):
    in_hand(repo)
    repo.item("DEC-0001", uses_terms=["Scorecard"], affects=["apps/**/agent.py"])
    repo.item("DEC-0002", uses_terms=["Scorecard"], affects=["docs/**"])
    repo.item("DEC-0003", uses_terms=["Scorecard"])  # about another term, on no path
    committed(repo)
    ws = repo.ws()
    assert slicing.build(ws, task="TASK-0001").decisions == []  # the branch changed nothing

    repo.write(APP_FILE, "x = 1\n")
    built, text = slicing.build_within_budget(ws, task="TASK-0001")

    assert [d.id for d in built.decisions] == ["DEC-0001"]
    assert built.affecting == {"DEC-0001": [APP_FILE]}
    assert f"Affects {APP_FILE}." in text
    (given,) = json.loads(slicing.render_json(ws, built))["decisions_in_force"]
    assert given["affects"] == ["apps/**/agent.py"] and given["affected_files"] == [APP_FILE]


def test_a_file_can_be_named_for_work_that_is_not_in_hand(repo, capsys):
    in_hand(repo)
    repo.item("REQ-0002")
    repo.item("TASK-0002", status="ready", implements=["REQ-0002"])
    repo.item("DEC-0001", uses_terms=["Scorecard"], affects=["docs/*.md"])
    repo.item("DEC-0002", uses_terms=["Scorecard"], affects=["apps/**"])
    committed(repo)
    repo.write(APP_FILE, "x = 1\n")
    ws = repo.ws()

    # TASK-0002 is not the task in hand, so the branch's changes are not taken to be its own.
    assert [d.id for d in slicing.build(ws, task="TASK-0001").decisions] == ["DEC-0002"]
    assert slicing.build(ws, task="TASK-0002").decisions == []
    named = slicing.build(ws, task="TASK-0002", files=["docs/guide.md"])
    assert named.affecting == {"DEC-0001": ["docs/guide.md"]}
    assert slicing.build(ws, task="TASK-0002", files=["docs/deep/guide.md"]).decisions == []

    assert main(["slice", "--term", "Finding", "--file", "docs/guide.md"]) == 0
    assert "DEC-0001" in capsys.readouterr().out


def test_only_a_decision_in_force_constrains_a_path(repo):
    in_hand(repo)
    repo.item("DEC-0001", status="superseded", uses_terms=["Scorecard"], affects=["docs/**"])
    repo.item("DEC-0002", supersedes="DEC-0001", uses_terms=["Scorecard"], affects=["docs/**"])
    repo.item("DEC-0003", status="draft", uses_terms=["Scorecard"], affects=["docs/**"])

    built = slicing.build(repo.ws(), task="TASK-0001", files=["docs/guide.md"])

    assert [d.id for d in built.decisions] == ["DEC-0002"]


def test_when_the_files_of_the_work_are_unknown_every_path_decision_is_given(repo):
    in_hand(repo)  # no git repository here: what the branch changed cannot be known
    repo.item("DEC-0001", uses_terms=["Scorecard"], affects=["docs/**", "tools/*.py"])

    built, text = slicing.build_within_budget(repo.ws(), task="TASK-0001")

    assert built.affecting == {"DEC-0001": []}
    assert "Affects docs/**, tools/*.py." in text


def test_a_requirement_being_replaced_is_not_presented_as_established(repo):
    repo.item("REQ-0001", status="done")  # the rule as it stands today
    repo.item("REQ-0002", status="in_progress", replaces="REQ-0001")
    repo.item("REQ-0003", status="done")  # another rule on the same term, still in force
    repo.item("REQ-0004", status="superseded")
    repo.item("REQ-0005", status="done", replaces="REQ-0004")
    repo.item("TASK-0001", status="in_progress", implements=["REQ-0002"])
    ws = repo.ws()

    built, text = slicing.build_within_budget(ws, task="TASK-0001", files=[])

    assert [r.id for r in built.established] == ["REQ-0003", "REQ-0005"]
    assert [r.id for r in built.replaced] == ["REQ-0001"]
    kept = text.split("already established")[1].split("## Types")[0]
    assert "REQ-0001" not in kept and "REQ-0004" not in kept
    assert "replaces REQ-0001, which is no longer to be kept true" in text
    data = json.loads(slicing.render_json(ws, built))
    assert data["requirements"][0]["replaces"] == "REQ-0001"
    assert [r["id"] for r in data["replaced_requirements"]] == ["REQ-0001"]

    # Without the link the old Requirement is established like any other.
    repo.item("REQ-0002", status="in_progress")
    assert "REQ-0001" in [r.id for r in slicing.build(repo.ws(), task="TASK-0001").established]


def test_the_slice_names_the_open_incident_the_work_answers(repo):
    repo.item("REQ-0001", status="in_progress")
    repo.item("REQ-0002", status="in_progress", raised_from="INC-0002")
    repo.item("TASK-0001", status="in_progress", implements=["REQ-0001", "REQ-0002"])
    repo.item("INC-0001", breaks=["REQ-0001"])
    repo.item("INC-0002")
    repo.item("INC-0003", status="done", breaks=["REQ-0001"])  # closed before: not this work's
    repo.item("INC-0004", breaks=["REQ-0404"])

    built, text = slicing.build_within_budget(repo.ws(), task="TASK-0001", files=[])

    assert [i.id for i in built.incidents] == ["INC-0001", "INC-0002"]
    assert "- INC-0001 [in_progress] An incident (breaks REQ-0001)" in text
    assert "raised from INC-0002" in text


# --- the view ----------------------------------------------------------------------


def test_the_plan_lists_open_incidents_with_what_they_wait_on(repo):
    verified(repo, "REQ-0001", status="done")
    repo.item("REQ-0002", status="in_progress", raised_from="INC-0001")
    repo.item("INC-0001", breaks=["REQ-0001"], title="Scores went out early")
    repo.item("INC-0002")
    repo.item("INC-0003", status="done", breaks=["REQ-0001"])
    built = view.build(repo.ws())

    first, second = built["plan"]["open_incidents"]
    assert first == {
        "id": "INC-0001",
        "title": "Scores went out early",
        "status": "in_progress",
        "context": "call-qa",
        "observed_on": "2026-01-15",
        "breaks": ["REQ-0001"],
        "raised": ["REQ-0002"],
        "waiting_on": ["REQ-0002"],
    }
    assert (second["id"], second["breaks"], second["raised"]) == ("INC-0002", [], [])
    text = view.render_text(built)
    assert "INC-0001 [in_progress] Scores went out early: waiting on REQ-0002" in text
    assert "INC-0002 [in_progress] An incident: names no Requirement yet" in text
    assert "INC-0003" not in text
    json.dumps(built)

    repo.item("REQ-0002", status="done", raised_from="INC-0001")
    assert "INC-0001 [in_progress] Scores went out early: ready to close" in view.render_text(
        view.build(repo.ws())
    )


def test_a_requirement_shows_what_it_replaces_and_what_it_was_raised_from(repo):
    repo.item("REQ-0001", status="superseded", title="The old rule")
    repo.item("INC-0001")
    repo.item("REQ-0002", status="done", replaces="REQ-0001", raised_from="INC-0001")
    repo.item("REQ-0003")
    built = view.build(repo.ws())
    rows = {row["id"]: row for row in built["trace"]["requirements"]}

    assert (rows["REQ-0002"]["replaces"], rows["REQ-0002"]["raised_from"]) == (
        "REQ-0001",
        "INC-0001",
    )
    assert rows["REQ-0001"]["replaced_by"] == ["REQ-0002"]
    assert (rows["REQ-0003"]["replaces"], rows["REQ-0003"]["replaced_by"]) == (None, [])
    assert built["plan"]["superseded_requirements"] == [
        {"id": "REQ-0001", "title": "The old rule", "replaced_by": "REQ-0002"}
    ]
    assert "REQ-0002 [done] replaces REQ-0001, raised from INC-0001" in view.render_text(built)


def test_the_view_keeps_every_key_the_mods_draw(repo):
    """The three mods read these keys of `onto view --format json`. New keys are added beside them."""
    repo.item("REQ-0001")
    repo.item("TASK-0001")
    built = view.build(repo.ws())

    assert {"task_in_hand", "stages", "tasks", "trace", "ontology", "plan"} <= set(built)
    assert {
        "order",
        "requirements_by_status",
        "decisions_in_force",
        "superseded_decisions",
        "open_change_requests",
    } <= set(built["plan"])
    assert {"id", "title", "status", "risk_tier", "context", "tasks", "tests", "verdict"} <= set(
        built["trace"]["requirements"][0]
    )


def test_work_that_was_superseded_is_not_shown_as_waiting(repo):
    repo.item("REQ-0001", status="superseded")
    verified(repo, "REQ-0002", status="done", replaces="REQ-0001")
    repo.item("TASK-0001", status="superseded", implements=["REQ-0001"])
    repo.item("TASK-0002", status="done", implements=["REQ-0002"])
    repo.item("TASK-0003", status="ready", implements=["REQ-0002"], blocked_by=["TASK-0001"])
    repo.item("CHG-0001", status="superseded", resolves=["TASK-0001"])
    built = view.build(repo.ws())
    tasks = {t["id"]: t for t in built["tasks"]}

    assert tasks["TASK-0001"]["stage"] == "complete"
    assert built["plan"]["order"] == ["TASK-0003"]  # a superseded Task blocks nothing


# --- provenance --------------------------------------------------------------------


def test_a_bundle_carries_where_its_requirements_came_from(repo):
    repo.item("REQ-0001", status="superseded")
    repo.item("REQ-0002", status="superseded", replaces="REQ-0001")
    repo.item("INC-0001", status="done", breaks=["REQ-0002"])
    repo.item("INC-0002", status="done")
    repo.item("INC-0003")  # about nothing this Change serves
    verified(repo, "REQ-0003", status="done", replaces="REQ-0002", raised_from="INC-0002")
    repo.item("TASK-0001", status="done", implements=["REQ-0003"])
    repo.item("CHG-0001", status="done")
    ws = repo.ws()
    work = Namespace(ws.schema.work_ns)
    wf = Namespace(ws.schema.wf_ns)

    bundle = prov.bundle(ws, build_graph(ws), ws.by_id["CHG-0001"])

    assert (work["REQ-0003"], PROV.wasRevisionOf, work["REQ-0002"]) in bundle
    assert (work["REQ-0002"], PROV.wasRevisionOf, work["REQ-0001"]) in bundle
    assert (work["REQ-0001"], wf.status, Literal("superseded")) in bundle
    assert (work["INC-0002"], wf.observed_on, None) in bundle
    assert (work["INC-0003"], None, None) not in bundle
    # The Change used the rule it delivered, not the ones that rule replaced.
    assert set(bundle.objects(work["CHG-0001"], PROV.used)) == {work["REQ-0003"]}

    import pyshacl

    conforms, _, text = pyshacl.validate(bundle, shacl_graph=gates.shapes_graph(ws.cfg))
    assert conforms, text


# --- a stale constraint ------------------------------------------------------------


def stale(repo) -> list[tuple[str, str, str | None]]:
    return [
        (p.subject, p.severity, p.found)
        for p in workitems.validate(repo.ws())
        if p.rule == "stale-affects"
    ]


def test_an_affects_glob_that_matches_no_file_is_a_warning(repo, capsys):
    repo.write(APP_FILE, "x = 1\n")
    repo.item("DEC-0001", affects=["apps/**/agent.py", "apps/**/gone.py", "/apps/**"])
    assert stale(repo) == [
        ("DEC-0001", "warning", "apps/**/gone.py"),
        ("DEC-0001", "warning", "/apps/**"),
    ]

    # It is said, with the glob, and it does not fail the run.
    assert main(["validate"]) == 0
    out = capsys.readouterr().out
    assert "stale-affects" in out and "apps/**/gone.py" in out and "1 work item(s)" in out

    repo.write("apps/call-qa-agent/gone.py", "")
    repo.item("DEC-0001", affects=["apps/**/agent.py", "apps/**/gone.py"])
    assert stale(repo) == []


def test_a_superseded_decision_may_name_files_that_are_gone(repo):
    repo.item("DEC-0001", status="superseded", affects=["apps/**/gone.py"])
    repo.item("DEC-0002", supersedes="DEC-0001")
    assert stale(repo) == []


def test_a_decision_can_be_written_before_the_file_it_will_constrain(repo):
    path, problems = create.create(
        repo.ws(),
        "Decision",
        {
            "title": "T",
            "bounded_context": "call-qa",
            "rationale": "R",
            "affects": ["apps/**/later.py"],
        },
    )
    assert path is not None and [p.rule for p in problems] == ["stale-affects"]


def test_in_a_git_repository_an_ignored_file_does_not_keep_a_glob_alive(repo):
    repo.write(".gitignore", "build/\n")
    repo.write("build/out.py", "")
    repo.write("src/kept.py", "")
    repo.item("DEC-0001", affects=["build/*.py", "src/*.py"])
    assert stale(repo) == []  # no git here: every file on disk counts

    git(repo, "init", "-q", "-b", "main")
    assert stale(repo) == [("DEC-0001", "warning", "build/*.py")]
