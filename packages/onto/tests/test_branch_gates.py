"""The gates over what a branch changed: ontology sources and generated files."""

from __future__ import annotations

import io
import json
import subprocess

import pytest
from onto import changes, gates, gen
from onto.cli import main
from onto.hooks import BLOCK
from onto.testing import scratch_repo

GLOSSARY = "ontology/domains/call-qa.yaml"
SHARED = "ontology/workflow.yaml"
GENERATED = "ontology/schemas/workflow.schema.json"
STOP = ("trace", "--gate", "stop", "--scope", "branch")


def git(repo, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(repo.root), *identity, *args], check=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A scratch repository with one commit: the base every test branches from."""
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("ONTO_TASK", raising=False)
    scratch.item("OCR-0001", status="done")  # an old request, settled before this branch
    git(scratch, "init", "-q", "-b", "main")
    git(scratch, "add", "-A")
    git(scratch, "commit", "-q", "-m", "base")
    return scratch


def touch(repo, rel):
    path = repo.root / rel
    path.write_text(path.read_text() + "\n# touched\n")


def unrequested(repo) -> list[str]:
    ws = repo.ws()
    found = changes.branch_problems(ws)
    assert {p.rule for p in found} <= {changes.REQUESTED}
    return [p.file for p in found]


def run(*argv, monkeypatch, capsys, stdin: dict | None = None):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin) if stdin is not None else ""))
    code = main(list(argv))
    return code, capsys.readouterr()


def test_an_untouched_ontology_needs_no_request(repo):
    repo.item("REQ-0001")
    assert unrequested(repo) == []


def test_a_changed_ontology_source_needs_a_request_on_the_same_branch(repo):
    touch(repo, GLOSSARY)
    # OCR-0001 is done, but this branch did not touch it: it asked for something else.
    assert unrequested(repo) == [GLOSSARY]

    repo.item("OCR-0002", status="draft")
    assert unrequested(repo) == [GLOSSARY]
    repo.item("OCR-0002", status="in_progress")
    assert unrequested(repo) == []
    repo.item("OCR-0002", status="done")
    assert unrequested(repo) == []


def test_a_committed_change_is_seen_as_well_as_an_uncommitted_one(repo):
    git(repo, "checkout", "-q", "-b", "feature")
    touch(repo, GLOSSARY)
    git(repo, "commit", "-q", "-am", "edit the glossary")
    assert unrequested(repo) == [GLOSSARY]


def test_a_request_covers_its_own_context_and_the_shared_files(repo):
    touch(repo, GLOSSARY)
    touch(repo, SHARED)
    touch(repo, "ontology/shapes/gates.shacl.ttl")
    repo.item("OCR-0002", status="in_progress", bounded_context="billing")
    assert unrequested(repo) == [GLOSSARY]
    (problem,) = changes.branch_problems(repo.ws())
    assert "--context call-qa" in problem.fix


def test_a_deleted_or_moved_ontology_source_is_a_change(repo):
    git(repo, "mv", GLOSSARY, "ontology/domains/renamed.yaml")
    assert unrequested(repo) == [GLOSSARY, "ontology/domains/renamed.yaml"]


def test_trace_fails_on_a_branch_whose_only_change_is_the_ontology(repo, monkeypatch, capsys):
    touch(repo, SHARED)

    code, out = run("trace", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 1 and f"{SHARED}: error[{changes.REQUESTED}]" in out.out

    code, out = run("trace", "--scope", "branch", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 1 and changes.REQUESTED in out.out

    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert code == BLOCK and out.out == ""
    assert changes.REQUESTED in out.err and "onto ocr new" in out.err
    assert "take back the claim" not in out.err  # that advice is for a failed requirement

    repo.item("OCR-0002", status="in_progress")
    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert (code, out.out, out.err) == (0, "", "")
    code, out = run("trace", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 0


def test_trace_fails_when_there_is_no_base_to_compare_the_branch_with(repo, monkeypatch, capsys):
    git(repo, "checkout", "-q", "-b", "feature")
    touch(repo, SHARED)
    git(repo, "commit", "-q", "-am", "edit the workflow ontology")
    code, out = run("trace", monkeypatch=monkeypatch, capsys=capsys)
    assert code == 1 and changes.REQUESTED in out.out

    # A CI checkout that did not fetch the base, or a default branch onto.toml does not name.
    git(repo, "branch", "-q", "-D", "main")
    for scope in ("all", "branch"):
        code, out = run("trace", "--scope", scope, monkeypatch=monkeypatch, capsys=capsys)
        assert code == 1 and f"error[{changes.BASE}]" in out.out
        assert "origin/main" in out.out and "base_ref" in out.out and "fetch-depth" in out.out

    # Nothing the agent can put right, so it does not hold the session.
    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert (code, out.err) == (0, "")


def test_a_repository_without_commits_has_no_base_to_miss(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    git(scratch, "init", "-q", "-b", "trunk")
    # Nothing is committed, so every file counts as changed and none is hidden.
    assert GLOSSARY in gates.changed_files(scratch.ws().cfg)
    assert changes.base_is_known(scratch.ws().cfg) == []


def test_the_branch_that_brings_the_ontology_layer_in_needs_no_request(tmp_path, monkeypatch):
    """As `onto init` leaves a repository: the ontology is new, not changed."""
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    git(scratch, "init", "-q", "-b", "main")
    assert unrequested(scratch) == []  # before the first commit

    config = (scratch.root / "onto.toml").read_text()
    (scratch.root / "onto.toml").unlink()
    scratch.write("README.md", "A repository with a history and no ontology layer.\n")
    git(scratch, "add", "README.md")
    git(scratch, "commit", "-q", "-m", "before the layer")
    scratch.write("onto.toml", config)
    git(scratch, "checkout", "-q", "-b", "adopt")
    assert unrequested(scratch) == []
    git(scratch, "add", "-A")
    git(scratch, "commit", "-q", "-m", "adopt the ontology layer")
    assert unrequested(scratch) == []

    # Once the base carries the layer, a change to it is a change.
    git(scratch, "checkout", "-q", "main")
    git(scratch, "merge", "-q", "--ff-only", "adopt")
    touch(scratch, GLOSSARY)
    assert unrequested(scratch) == [GLOSSARY]


def test_the_stop_gate_catches_a_generated_file_changed_by_any_tool(repo, monkeypatch, capsys):
    pytest.importorskip("linkml")
    target = repo.root / GENERATED
    target.write_text(target.read_text().replace('"superseded"', '"retired"'))

    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert code == BLOCK
    assert f"{GENERATED}: error[{changes.GENERATED}]" in out.err and "onto gen" in out.err

    git(repo, "checkout", "-q", "--", GENERATED)
    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert (code, out.err) == (0, "")


def test_the_stop_gate_catches_a_source_that_was_not_compiled(repo, monkeypatch, capsys):
    pytest.importorskip("linkml")
    source = repo.root / GLOSSARY
    source.write_text(
        source.read_text().replace(
            "    minimum_value: 1\n    required: true",
            "    minimum_value: 2\n    required: true",
            1,
        )
    )
    repo.item("OCR-0002", status="in_progress")

    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert code == BLOCK and changes.GENERATED in out.err and "generated.py" in out.err


def test_the_stop_gate_says_which_glossary_a_shell_command_left_unparsable(
    repo, monkeypatch, capsys
):
    path = repo.root / GLOSSARY
    path.write_text(path.read_text() + "x: y: z\n")

    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)

    # Exit 1 would not hold the session, and a traceback tells the agent nothing it can act on.
    assert code == BLOCK and "Traceback" not in out.err
    assert f"{GLOSSARY}: error[{changes.GENERATED}]" in out.err and "cannot be read" in out.err
    assert f"{GLOSSARY}: error[{changes.REQUESTED}]" in out.err

    # Everywhere else it is one line that names the file, and never exit 2.
    for command in (["trace"], ["gen", "--check"], ["validate"], ["rules"]):
        code, out = run(*command, monkeypatch=monkeypatch, capsys=capsys)
        assert code == 1, command
        assert "call-qa.yaml cannot be read as YAML (line " in out.err, command


def test_a_missing_generator_does_not_block_the_session(repo, monkeypatch, capsys):
    def unavailable():
        raise gen.GeneratorUnavailable("linkml is not installed")

    monkeypatch.setattr(gen, "_require_linkml", unavailable)
    touch(repo, GENERATED)
    code, out = run(*STOP, stdin={"hook_event_name": "Stop"}, monkeypatch=monkeypatch, capsys=capsys)
    assert (code, out.err) == (0, "")


def test_outside_a_git_repository_there_is_no_branch_to_judge(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    touch(scratch, GLOSSARY)
    assert changes.branch_problems(scratch.ws(), stop=True) == []
