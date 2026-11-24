"""Work-item validation, the typed write path, the graph and the slices."""

from __future__ import annotations

import pytest
from onto import create, slicing
from onto.graph import load_graph
from onto.report import errors, warnings
from onto.testing import scratch_repo
from onto.workitems import validate
from onto.workspace import Workspace
from rdflib import RDF, URIRef


@pytest.fixture
def repo(tmp_path):
    scratch = scratch_repo(tmp_path)
    scratch.item("REQ-0001")
    return scratch


def problems_of(repo):
    return validate(repo.ws())


def rules(problems):
    return [p.rule for p in problems]


def test_a_valid_item_has_no_problems(repo):
    assert problems_of(repo) == []


def test_the_real_work_items_are_clean():
    assert validate(Workspace.at()) == []


def test_an_enum_error_lists_what_is_permitted(repo):
    repo.item("REQ-0001", status="finished")
    (problem,) = problems_of(repo)
    assert problem.rule == "schema" and problem.found == "finished"
    assert problem.allowed == ("draft", "ready", "in_progress", "done", "superseded")
    assert problem.line == 4  # points at the `status:` line


def test_an_unknown_field_suggests_the_one_meant(repo):
    repo.item("REQ-0001", risk_teir="high")
    (problem,) = problems_of(repo)
    assert "has no field 'risk_teir'" in problem.message
    assert problem.suggestions == ("risk_tier",)


def test_missing_fields_and_bad_shapes(repo):
    repo.item("REQ-0001", title=None, jira_key="nope")
    repo.item("DEC-0001", decided_on="next Tuesday")
    messages = " | ".join(p.message for p in problems_of(repo))
    assert "needs the field 'title'" in messages
    assert "jira_key is 'nope'" in messages
    assert "not a valid date" in messages


def test_an_id_that_fits_no_class_and_a_misnamed_file(repo):
    repo.write("work/NOTE-1.md", "---\nid: NOTE-1\n---\n")
    repo.write(
        "work/requirement.md",
        (repo.root / "work/REQ-0001.md").read_text().replace("REQ-0001", "REQ-0002"),
    )
    assert sorted(rules(problems_of(repo))) == ["filename", "unknown-id"]


def test_duplicate_ids_and_files_without_frontmatter(repo):
    repo.write("work/copy/REQ-0001.md", (repo.root / "work/REQ-0001.md").read_text())
    repo.write("work/notes.md", "no frontmatter here\n")
    assert sorted(rules(problems_of(repo))) == ["duplicate-id", "frontmatter"]


def test_a_reference_must_exist_and_be_of_the_right_class(repo):
    repo.item("TASK-0001", implements=["REQ-0001", "REQ-0404"], blocked_by=["REQ-0001"])
    found = {p.found: p.message for p in problems_of(repo)}
    assert "does not exist" in found["REQ-0404"]
    assert "must point at a Task, but REQ-0001 is a Requirement" in found["REQ-0001"]


def test_an_unknown_context(repo):
    repo.item("REQ-0001", bounded_context="payments")
    (problem,) = problems_of(repo)
    assert problem.rule == "unknown-context" and problem.allowed == ("call-qa",)


@pytest.mark.parametrize(
    ("term", "rule", "suggestion"),
    [
        ("Calibration", "unknown-term", None),
        ("Rubric", "denied-term", "Scorecard"),
        ("pass mark", "term-not-canonical", "pass_mark"),
        ("Scorcard", "unknown-term", "Scorecard"),
    ],
)
def test_uses_terms_takes_only_canonical_terms(repo, term, rule, suggestion):
    repo.item("REQ-0001", uses_terms=["Finding", term])
    (problem,) = errors(problems_of(repo))
    assert problem.rule == rule and problem.found == term
    if suggestion:
        assert suggestion in problem.suggestions
    if rule == "unknown-term":
        assert f"onto ocr new --context call-qa --term {term}" in problem.fix


def test_the_requirement_text_is_bound_to_uses_terms(repo):
    repo.item(
        "REQ-0001",
        ears_text="The system shall score each `Evaluation` with a `Verdict`.",
        uses_terms=["Finding"],
    )
    by_rule = {p.rule: p for p in problems_of(repo)}
    assert by_rule["denied-term"].found == "Verdict"  # backticked and denied
    assert by_rule["unbound-term"].found == "Evaluation"  # backticked, not listed
    assert by_rule["unmentioned-term"].severity == "warning"  # listed, never written


def test_ears_patterns(repo):
    from onto import ears

    assert ears.classify("The system shall record a Finding.") == "ubiquitous"
    assert ears.classify("When a Call ends, the system shall score it.") == "event-driven"
    assert (
        ears.classify("While a review is open, the system shall hide the score.") == "state-driven"
    )
    assert ears.classify("If a citation is missing, then the system shall reject it.") == (
        "unwanted-behaviour"
    )
    assert (
        ears.classify("Where a pass mark is set, the system shall apply it.") == "optional-feature"
    )
    assert ears.classify("Scores should probably be computed.") is None

    repo.item("REQ-0001", ears_text="Record a `Finding` please.")
    (problem,) = problems_of(repo)
    assert problem.rule == "ears" and len(problem.allowed) == 5


def test_a_denied_synonym_in_plain_prose_only_warns(repo):
    repo.item("REQ-0001", title="Score against the rubric")
    (problem,) = problems_of(repo)
    assert (problem.rule, problem.severity, problem.found) == ("denied-term", "warning", "rubric")
    # A Decision has to be able to name what it retired.
    repo.item("REQ-0001")
    repo.item("DEC-0001", title="Call it a Scorecard, not a rubric")
    assert problems_of(repo) == []


def test_a_test_item_must_point_at_a_file_that_exists(repo):
    repo.item("TST-0001", path="tests/test_missing.py::test_it")
    (problem,) = problems_of(repo)
    assert problem.rule == "missing-test"


# --- the typed write path ----------------------------------------------------------


def test_onto_new_writes_a_valid_item_with_the_next_id(repo):
    ws = repo.ws()
    fields = create.parse_fields(
        ws,
        "Requirement",
        [
            "title=Scores are whole numbers",
            "bounded_context=call-qa",
            "ears_text=The system shall store each `score` as a whole number.",
            "uses_terms=score",
        ],
    )
    path, problems = create.create(ws, "Requirement", fields)
    assert path.name == "REQ-0002.md" and problems == []
    assert ws.by_id["REQ-0002"].status == "draft"
    assert validate(repo.ws()) == []


def test_onto_new_refuses_an_invalid_item_and_writes_nothing(repo):
    ws = repo.ws()
    fields = create.parse_fields(
        ws,
        "Task",
        [
            "title=Do it",
            "bounded_context=call-qa",
            "implements=REQ-0001,REQ-0777",
            "status=started",
        ],
    )
    path, problems = create.create(ws, "Task", fields)
    assert path is None
    assert {p.rule for p in problems} == {"schema", "dangling-reference"}
    assert not (repo.root / "work/TASK-0001.md").exists()
    # Evidence is never created by hand, and a class has to exist.
    assert create.create(ws, "Evidence", {})[1][0].rule == "derived"
    assert "Requirement" in create.create(ws, "Story", {})[1][0].allowed


# --- the graph ---------------------------------------------------------------------


def test_every_predicate_in_the_graph_is_declared_in_the_workflow_ontology():
    graph = load_graph()
    declared = {
        slot.iri
        for cls in graph.ws.schema.view.all_classes()
        for slot in graph.ws.schema.slots(cls)
    }
    used = {str(p) for p in graph.rdf.predicates()} - {str(RDF.type)}
    assert used <= declared, used - declared


def test_instances_are_typed_with_their_ancestors_and_prov_classes():
    graph = load_graph()
    types = {graph.short(str(o)) for o in graph.rdf.objects(graph.node("CHG-0001"), RDF.type)}
    assert types == {"wf:Change", "wf:WorkItem", "wf:Record", "prov:Activity"}
    assert URIRef("http://www.w3.org/ns/prov#Entity") in set(
        graph.rdf.objects(graph.node("REQ-0001"), RDF.type)
    )


def test_short_names_and_bindings():
    graph = load_graph()
    assert graph.short("https://bank.example/work/REQ-0001") == "REQ-0001"
    assert graph.short("https://bank.example/ontology/call-qa/Scorecard") == "qa:Scorecard"
    assert str(graph.node("Scorecard")).endswith("/call-qa/Scorecard")
    assert str(graph.node("prov:Entity")) == "http://www.w3.org/ns/prov#Entity"
    with pytest.raises(KeyError):
        graph.node("Calibration")
    rows = graph.select(
        "PREFIX wf: <https://bank.example/ontology/workflow/> "
        "SELECT ?task ?req WHERE { ?task wf:implements ?req } ORDER BY ?req",
        task="TASK-0003",
    )
    assert rows == [{"task": "TASK-0003", "req": "REQ-0007"}]


# --- slices ------------------------------------------------------------------------


def test_a_task_slice_holds_what_the_task_needs_and_fits_the_budget():
    ws = Workspace.at()
    built, text = slicing.build_within_budget(ws, task="TASK-0002")

    assert [r.id for r in built.requirements] == ["REQ-0004", "REQ-0005", "REQ-0006"]
    assert {"score", "weight", "Criterion", "Finding"} <= {t.name for t in built.focus}
    # In force only: the two superseded scoring decisions are left out.
    assert {"DEC-0005", "DEC-0006", "DEC-0007"} <= {d.id for d in built.decisions}
    assert not {"DEC-0003", "DEC-0004"} & {d.id for d in built.decisions}
    # Requirements on the same terms that are already established, not the task's own.
    assert "REQ-0001" in {r.id for r in built.established}
    assert "Never write: Verdict" in text and "generated.py" in text
    # The spike's exit criterion: a slice under 3,000 tokens (estimated).
    assert slicing.estimate_tokens(text) < slicing.DEFAULT_BUDGET


def test_every_task_s_slice_fits_the_budget():
    ws = Workspace.at()
    for task in ws.of_class("Task"):
        _, text = slicing.build_within_budget(ws, task=task.id)
        assert slicing.estimate_tokens(text) < slicing.DEFAULT_BUDGET, task.id


def test_a_slice_that_would_not_fit_drops_the_neighbours():
    ws = Workspace.at()
    wide, _ = slicing.build_within_budget(ws, task="TASK-0002")
    narrow, text = slicing.build_within_budget(ws, budget=600, task="TASK-0002")
    assert wide.depth == 1 and wide.neighbours
    assert narrow.depth == 0 and not narrow.neighbours


def test_a_term_slice_and_its_errors():
    ws = Workspace.at()
    built = slicing.build(ws, terms=["NEEDS_REVIEW"])
    assert [t.name for t in built.neighbours] == ["Disposition"]
    with pytest.raises(slicing.SliceError, match="not a term"):
        slicing.build(ws, terms=["Calibration"])
    with pytest.raises(slicing.SliceError, match="not a Task"):
        slicing.build(ws, task="REQ-0001")


def test_the_task_in_hand(monkeypatch, repo):
    repo.item("TASK-0001", status="in_progress")
    repo.item("TASK-0002", status="ready")
    monkeypatch.delenv("ONTO_TASK", raising=False)
    assert slicing.current_task(repo.ws()).id == "TASK-0001"  # the only one in progress
    monkeypatch.setenv("ONTO_TASK", "TASK-0002")
    assert slicing.current_task(repo.ws()).id == "TASK-0002"


def test_the_overview_is_a_table_of_contents():
    text = slicing.render_overview(Workspace.at())
    assert "- Scorecard:" in text and "Rubric -> Scorecard" in text
    assert "OCR-0002 [draft] Calibration" in text
    assert slicing.estimate_tokens(text) < 1000


def test_warnings_are_not_errors(repo):
    repo.item("REQ-0001", title="Score against the rubric")
    problems = problems_of(repo)
    assert warnings(problems) and not errors(problems)
