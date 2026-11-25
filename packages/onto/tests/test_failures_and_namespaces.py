"""What a command says when the ontology layer is incomplete or disagrees with itself."""

from __future__ import annotations

import subprocess

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


def test_gen_names_a_missing_workflow_ontology_with_the_way_to_get_it(repo, capsys):
    (repo.root / "ontology/workflow.yaml").unlink()

    assert main(["gen", "--check"]) == 1
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
    (repo.root / "ontology/domains" / f"{repo.bounded_context}.yaml").unlink()

    assert main(["validate"]) == 1
    said = capsys.readouterr().err
    assert f"{repo.bounded_context}.yaml is missing" in said
    assert f"[contexts.{repo.bounded_context}]" in said


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


ELSEWHERE = "https://elsewhere.example/ontology/workflow/"


def reserialised(repo) -> str:
    """The gates file as rdflib writes it: other spacing, `sh:namespace` before `sh:prefix`."""
    from rdflib import Graph

    path = repo.root / GATES
    graph = Graph().parse(path, format="turtle")
    text = graph.serialize(format="turtle")
    path.write_text(text, encoding="utf-8")
    return text


def test_a_gates_file_written_another_way_still_passes(repo):
    reserialised(repo)

    assert main(["trace"]) == 0


def test_trace_fails_on_a_declaration_with_the_namespace_written_first(repo, capsys):
    namespace = repo.ws().schema.wf_ns
    rewrite(
        repo,
        GATES,
        f'sh:prefix "wf" ;   sh:namespace "{namespace}"^^xsd:anyURI',
        f'sh:namespace "{ELSEWHERE}"^^xsd:anyURI ; sh:prefix "wf"',
    )

    assert main(["trace"]) == 1
    said = capsys.readouterr().out
    assert "error[namespace]" in said
    assert GATES in said


def test_trace_fails_when_the_workflow_prefix_has_another_name_and_namespace(repo, capsys):
    namespace = repo.ws().schema.wf_ns
    path = repo.root / GATES
    text = path.read_text(encoding="utf-8")
    text = text.replace("wf:", "wfl:").replace('sh:prefix "wf"', 'sh:prefix "wfl"')
    path.write_text(text.replace(namespace, ELSEWHERE), encoding="utf-8")

    assert main(["trace"]) == 1
    assert "error[namespace]" in capsys.readouterr().out


def test_trace_fails_until_every_declaration_of_a_reserialised_gates_file_is_right(repo, capsys):
    namespace = repo.ws().schema.wf_ns
    path = repo.root / GATES
    stale = reserialised(repo).replace(namespace, ELSEWHERE)
    path.write_text(stale, encoding="utf-8")
    assert main(["trace"]) == 1

    lines = stale.splitlines(keepends=True)
    binding = next(i for i, line in enumerate(lines) if line.startswith("@prefix wf:"))
    lines[binding] = lines[binding].replace(ELSEWHERE, namespace)
    path.write_text("".join(lines), encoding="utf-8")
    capsys.readouterr()

    assert main(["trace"]) == 1
    said = capsys.readouterr().out
    assert "error[namespace]" in said
    assert "sh:declare" in said


def test_trace_fails_on_a_stale_namespace_beside_the_right_one(repo, capsys):
    path = repo.root / QUESTION
    path.write_text(
        f"PREFIX old: <{ELSEWHERE}>\n" + path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert main(["trace"]) == 1
    assert "error[namespace]" in capsys.readouterr().out


def test_a_question_that_never_names_the_workflow_namespace_fails(repo, capsys):
    path = repo.root / QUESTION
    text = path.read_text(encoding="utf-8").replace("wf:", "terms:")
    path.write_text(
        text.replace(repo.ws().schema.wf_ns, "https://other.example/terms#"), encoding="utf-8"
    )

    assert main(["trace"]) == 1
    said = capsys.readouterr().out
    assert "error[namespace]" in said
    assert "no PREFIX names" in said


def test_a_question_that_cannot_be_parsed_is_an_error_not_a_crash(repo, capsys):
    (repo.root / QUESTION).write_text("SELECT WHERE {", encoding="utf-8")

    assert main(["trace"]) == 1
    assert "cannot be read" in capsys.readouterr().out


def committed(repo) -> None:
    git = ["git", "-C", str(repo.root), "-c", "user.name=t", "-c", "user.email=t@example.org"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], check=True)


def test_a_namespace_mismatch_stops_a_branch_that_touched_no_work_item(repo, capsys):
    committed(repo)
    assert main(["trace", "--scope", "branch"]) == 0
    assert "nothing in scope" in capsys.readouterr().out

    rewrite(repo, GATES, repo.ws().schema.wf_ns, ELSEWHERE)

    assert main(["trace", "--scope", "branch"]) == 1
    assert "error[namespace]" in capsys.readouterr().out
