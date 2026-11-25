"""A gate that was configured away is reported, not passed in silence."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from onto import gateconfig, scaffold
from onto.cli import main
from onto.config import find_root
from onto.testing import scratch_repo

SETTINGS = ".claude/settings.json"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path, term="Finding")
    (scratch.root / ".claude").mkdir()
    shutil.copy(find_root() / SETTINGS, scratch.root / SETTINGS)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("ONTO_TASK", raising=False)
    subprocess.run(["git", "-C", str(scratch.root), "init", "-q", "-b", "main"], check=True)
    return scratch


def configure(repo, old: str, new: str) -> None:
    path = repo.root / "onto.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def said(repo) -> list[str]:
    return [p.found for p in gateconfig.problems(repo.ws().cfg)]


def test_the_configuration_as_it_is_switches_every_gate_on(repo, capsys):
    assert said(repo) == []
    assert gateconfig.hooks_missing(repo.ws().cfg) == []
    assert main(["validate"]) == 0 and main(["guard", "--check-settings"]) == 0


def test_no_graph_gates_is_an_error_in_validate_and_in_trace(repo, capsys):
    repo.item("REQ-0001", status="done")  # no Test: the graph gate would say so
    assert main(["trace"]) == 1
    configure(repo, 'gates = ["ontology/shapes/gates.shacl.ttl"]', "gates = []")

    assert said(repo) == ["gates = []"]
    capsys.readouterr()
    assert main(["validate"]) == 1 and "error[gate-config]" in capsys.readouterr().out
    assert main(["trace"]) == 1 and "error[gate-config]" in capsys.readouterr().out
    assert main(["trace", "--gate", "stop", "--scope", "branch"]) == 2


def test_an_ontology_source_that_is_not_protected_is_an_error(repo, capsys):
    configure(repo, '    "ontology/domains/**",\n', "")

    assert said(repo) == ["ontology/domains/call-qa.yaml"]
    assert main(["validate"]) == 1


@pytest.mark.parametrize("ref", ["HEAD", "@", "HEAD~1", "HEAD^"])
def test_a_branch_compared_with_itself_is_an_error(repo, ref):
    configure(repo, 'base_ref = "origin/main"', f'base_ref = "{ref}"')

    assert said(repo) == [ref]


@pytest.mark.parametrize(
    ("change", "missing"),
    [
        (lambda s: {}, ["PreToolUse", "PostToolUse", "Stop"]),
        (lambda s: {**s, "hooks": {**s["hooks"], "Stop": []}}, ["Stop"]),
        (
            lambda s: {
                **s,
                "hooks": {
                    **s["hooks"],
                    "PreToolUse": [{**s["hooks"]["PreToolUse"][0], "matcher": "NotebookEdit"}],
                },
            },
            ["PreToolUse"],
        ),
        (
            lambda s: {
                **s,
                "hooks": {
                    **s["hooks"],
                    "PostToolUse": [{"hooks": [{"type": "command", "command": "true"}]}],
                },
            },
            ["PostToolUse"],
        ),
    ],
)
def test_settings_without_a_hook_of_the_gates_fail_the_settings_check(
    repo, capsys, change, missing
):
    path = repo.root / SETTINGS
    path.write_text(json.dumps(change(json.loads(path.read_text()))))

    assert [p.found for p in gateconfig.hooks_missing(repo.ws().cfg)] == missing
    assert main(["guard", "--check-settings"]) == 1
    assert "error[hook]" in capsys.readouterr().out


def options(root, **changes) -> scaffold.Options:
    return scaffold.Options(root=root, context="loans", onto_cmd="uv run onto", **changes)


def test_the_scaffolded_ci_checks_the_settings_when_there_are_settings(tmp_path):
    scaffold.scaffold(options(tmp_path))
    workflow = (tmp_path / ".github/workflows/ontology-gates.yml").read_text()
    targets = (tmp_path / "onto.mk").read_text()

    assert "run: $ONTO guard --check-settings" in workflow
    assert "\t$(ONTO) guard --check-settings\n" in targets
    assert gateconfig.hooks_missing(scaffold.load_config(tmp_path)) == []
    assert "prov/verify.json" in (tmp_path / ".gitignore").read_text().splitlines()


def test_without_the_claude_layer_no_step_checks_settings_that_are_not_there(tmp_path):
    scaffold.scaffold(options(tmp_path, claude=False))
    workflow = (tmp_path / ".github/workflows/ontology-gates.yml").read_text()
    targets = (tmp_path / "onto.mk").read_text()

    assert "check-settings" not in workflow and "check-settings" not in targets
    assert "run: $ONTO check-terms\n\n      - name: Tests of the Test items" in workflow
    assert "\t$(ONTO) check-terms\n\t$(ONTO) trace --collect\n" in targets


def test_a_path_that_was_never_checked_is_not_reported_clean(repo, capsys):
    repo.item("REQ-0001")
    assert main(["validate", str(repo.root / "work/REQ-0001.md")]) == 0
    capsys.readouterr()

    assert main(["validate", str(repo.root / "work/REQ-0009.md")]) == 1
    assert main(["validate", "/etc/passwd"]) == 1
    assert main(["check-terms", str(repo.root / "nope.py")]) == 1
    said = capsys.readouterr()
    assert "0 error(s)" not in said.out and "work/REQ-0009.md is not a work item" in said.err
