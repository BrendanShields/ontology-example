"""What a command says when the ontology layer is incomplete or disagrees with itself."""

from __future__ import annotations

import pytest
from onto.cli import main
from onto.testing import scratch_repo

GATES = "ontology/shapes/gates.shacl.ttl"
QUESTION = "ontology/cq/CQ-05-requirements-on-personal-information.rq"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return scratch


def rewrite(repo, rel: str, old: str, new: str) -> None:
    path = repo.root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_a_missing_workflow_ontology_is_named_with_the_way_to_get_it(repo, capsys):
    (repo.root / "ontology/workflow.yaml").unlink()

    assert main(["validate"]) == 1
    said = capsys.readouterr().err
    assert "ontology/workflow.yaml is missing" in said
    assert "onto init" in said


def test_a_repository_without_the_ontology_layer_is_pointed_at_init(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for variable in ("ONTO_ROOT", "CLAUDE_PROJECT_DIR"):
        monkeypatch.delenv(variable, raising=False)

    assert main(["validate"]) == 1
    said = capsys.readouterr().err
    assert "no onto.toml" in said
    assert "onto init" in said


def test_a_missing_gates_file_is_not_blamed_on_the_generator(repo, capsys):
    (repo.root / GATES).unlink()

    assert main(["trace"]) == 1
    said = capsys.readouterr().err
    assert f"{GATES} is missing" in said
    assert "`onto gen` does not produce" in said
    assert "onto init" in said


def test_a_missing_glossary_is_named(repo, capsys):
    (repo.root / "ontology/domains" / f"{repo.context}.yaml").unlink()

    assert main(["validate"]) == 1
    said = capsys.readouterr().err
    assert f"{repo.context}.yaml is missing" in said
    assert f"[contexts.{repo.context}]" in said


@pytest.mark.parametrize(
    ("file", "declaration"),
    [
        (GATES, "@prefix wf:   <{ns}> ."),
        (GATES, 'sh:prefix "wf" ;   sh:namespace "{ns}"^^xsd:anyURI'),
        (QUESTION, "PREFIX wf: <{ns}>"),
    ],
)
def test_trace_fails_when_a_gate_or_question_is_written_for_another_namespace(
    repo, capsys, file, declaration
):
    namespace = repo.ws().schema.wf_ns
    assert main(["trace"]) == 0
    capsys.readouterr()

    rewrite(
        repo,
        file,
        declaration.format(ns=namespace),
        declaration.format(ns="https://elsewhere.example/workflow/"),
    )

    assert main(["trace"]) == 1
    said = capsys.readouterr().out
    assert "error[namespace]" in said
    assert file in said
    assert namespace in said


def test_a_namespace_mismatch_stops_the_branch_gate_too(repo, capsys):
    rewrite(repo, GATES, repo.ws().schema.wf_ns, "https://elsewhere.example/workflow/")
    repo.item("REQ-0001")

    assert main(["trace", "--scope", "branch"]) == 1
    assert "error[namespace]" in capsys.readouterr().out


def test_a_prefix_in_a_comment_is_not_a_declaration(repo, capsys):
    path = repo.root / QUESTION
    path.write_text(
        "# PREFIX wf: <https://elsewhere.example/>\n" + path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    assert main(["trace"]) == 0
