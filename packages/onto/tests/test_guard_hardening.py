"""The ways round the guard that were found and closed, and the rules derived for settings.json."""

from __future__ import annotations

import io
import json
import re

import pytest
from onto import denyrules, guard, paths
from onto.cli import main
from onto.hooks import BLOCK
from onto.testing import scratch_repo

GLOSSARY = "ontology/domains/call-qa.yaml"
GENERATED = "apps/call-qa-agent/src/call_qa_agent/generated.py"
DOMAIN = "apps/call-qa-agent/src/call_qa_agent/domain/example.py"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("ONTO_TASK", raising=False)
    return scratch


@pytest.fixture
def volume_ignores_case(monkeypatch):
    """Decide as on macOS or Windows, whatever volume the tests run on."""
    monkeypatch.setattr(paths, "ignores_case", lambda root: True)


def decide(repo, path, **tool_input):
    return guard.decide(repo.ws(), str(path), tool_input or None)[0]


def hook(*argv, stdin, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin)))
    code = main(list(argv))
    return code, capsys.readouterr()


# --- paths -------------------------------------------------------------------------


def test_a_notebook_edit_is_guarded_like_any_other_edit(repo, monkeypatch, capsys):
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "NotebookEdit",
        "tool_input": {
            "notebook_path": str(repo.root / "work/evidence/notes.ipynb"),
            "new_source": "x = 1",
            "edit_mode": "insert",
        },
    }
    code, out = hook("guard", stdin=event, monkeypatch=monkeypatch, capsys=capsys)
    assert code == BLOCK and "evidence" in out.err


def test_a_symlink_to_a_guarded_file_is_guarded(repo, tmp_path):
    file_link = tmp_path / "notes.yaml"
    file_link.symlink_to(repo.root / GLOSSARY)
    folder_link = repo.root / "scratch"
    folder_link.symlink_to(repo.root / "ontology", target_is_directory=True)

    assert decide(repo, file_link) == guard.DENY
    assert decide(repo, folder_link / "schemas/workflow.schema.json") == guard.DENY
    assert decide(repo, folder_link / "domains/call-qa.yaml") == guard.DENY


def test_letter_case_does_not_dodge_the_guard_where_the_volume_ignores_it(
    repo, volume_ignores_case
):
    assert decide(repo, repo.root / "ONTOLOGY/Workflow.yaml") == guard.DENY
    assert decide(repo, repo.root / GENERATED.replace("generated", "Generated")) == guard.DENY
    assert decide(repo, repo.root / "ONTO.toml") == guard.ASK
    # A file that does not exist yet, in a folder that does not exist yet.
    assert not (repo.root / "work/evidence").exists()
    assert decide(repo, repo.root / "work/Evidence/EVD-0001.md") == guard.DENY
    # The repository itself, spelled differently.
    assert decide(repo, str(repo.root).upper() + "/" + GLOSSARY) == guard.DENY
    reason = guard.decide(repo.ws(), str(repo.root / "ONTOLOGY/Schemas/workflow.schema.json"))[1]
    assert "ontology/schemas/workflow.schema.json is generated" in reason


def test_letter_case_is_judged_as_the_volume_judges_it(repo):
    # No fixture here: on a case-sensitive volume the capitalised path is another file.
    same_file = (repo.root / "ONTO.TOML").exists()
    assert paths.ignores_case(repo.root) == same_file
    assert decide(repo, repo.root / "ONTOLOGY/workflow.yaml") == (
        guard.DENY if same_file else guard.ALLOW
    )


def test_the_term_hook_checks_a_domain_file_named_in_another_case(repo, monkeypatch, capsys):
    repo.write(DOMAIN, "rubric = 1\n")
    shouted = repo.root / DOMAIN.replace("domain", "DOMAIN")
    if not shouted.exists():
        pytest.skip("this volume tells DOMAIN from domain: the path names no file")
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(shouted), "content": "rubric = 1\n"},
    }
    code, out = hook(
        "check-terms", "--changed-from-stdin", stdin=event, monkeypatch=monkeypatch, capsys=capsys
    )
    assert code == BLOCK and "Scorecard" in out.err


# --- the files that configure the gates --------------------------------------------


def test_an_edit_to_the_gates_own_configuration_is_put_to_a_person(repo, monkeypatch, capsys):
    for path in (
        "onto.toml",
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".github/CODEOWNERS",
        ".github/workflows/ontology-gates.yml",
    ):
        assert decide(repo, repo.root / path) == guard.ASK, path
    # The tooling is edited all day: prompting there would teach people to switch the guard off.
    assert decide(repo, repo.root / "packages/onto/src/onto/guard.py") == guard.ALLOW
    assert decide(repo, repo.root / "apps/call-qa-agent/onto.toml") == guard.ALLOW

    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(repo.root / "onto.toml"),
            "old_string": 'on_open_ocr = "ask"',
            "new_string": 'on_open_ocr = "allow"',
        },
    }
    code, out = hook("guard", stdin=event, monkeypatch=monkeypatch, capsys=capsys)
    answer = json.loads(out.out)["hookSpecificOutput"]
    assert code == 0 and answer["permissionDecision"] == "ask"
    assert "configures the gates" in answer["permissionDecisionReason"]


def test_the_optional_list_is_set_in_onto_toml_but_the_core_three_are_not(repo):
    config = repo.root / "onto.toml"
    listed = re.compile(r"^gate_files = .*$", re.MULTILINE)
    assert listed.search(config.read_text())
    config.write_text(listed.sub('gate_files = ["Makefile"]', config.read_text()))
    assert decide(repo, repo.root / "Makefile") == guard.ASK
    assert decide(repo, repo.root / ".github/CODEOWNERS") == guard.ALLOW
    assert decide(repo, repo.root / "onto.toml") == guard.ASK
    assert decide(repo, repo.root / ".claude/settings.json") == guard.ASK

    config.write_text(listed.sub("", config.read_text()))  # not set: the default list
    assert decide(repo, repo.root / ".github/CODEOWNERS") == guard.ASK
    assert decide(repo, repo.root / ".github/workflows/release.yml") == guard.ASK


# --- approving a request -----------------------------------------------------------


def test_marking_a_request_approved_is_put_to_a_person(repo, monkeypatch, capsys):
    request = repo.item("OCR-0001", "Notes.", status="draft")
    replace = {"old_string": "status: draft", "new_string": "status: in_progress"}
    text = request.read_text()

    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(request), **replace},
    }
    code, out = hook("guard", stdin=event, monkeypatch=monkeypatch, capsys=capsys)
    answer = json.loads(out.out)["hookSpecificOutput"]
    assert code == 0 and answer["permissionDecision"] == "ask"
    assert "A person approves" in answer["permissionDecisionReason"]

    assert decide(repo, request, **replace) == guard.ASK
    assert decide(repo, request, old_string="draft", new_string="done") == guard.ASK
    assert decide(repo, request, edits=[replace]) == guard.ASK
    assert decide(repo, request, content=text.replace("draft", "in_progress")) == guard.ASK
    decision, reason = guard.decide(repo.ws(), str(request), replace)
    assert "OCR-0001" in reason and "in_progress" in reason

    # Everything else about a request is the agent's to write.
    assert decide(repo, request, old_string="Notes.", new_string="More notes.") == guard.ALLOW
    assert decide(repo, request, old_string="status: draft", new_string="status: ready") == (
        guard.ALLOW
    )
    assert decide(repo, request, content=text) == guard.ALLOW
    assert decide(repo, request, old_string="not in the file", new_string="status: done") == (
        guard.ALLOW
    )


def test_the_edit_is_judged_by_the_file_it_leaves_behind(repo):
    request = repo.item("OCR-0001", title="A draft of a request", status="draft")
    word = {"old_string": "draft", "new_string": "done"}
    assert decide(repo, request, **word) == guard.ALLOW  # only the title changes
    assert decide(repo, request, **word, replace_all=True) == guard.ASK
    assert decide(repo, request, edits=[word, word]) == guard.ASK


def test_a_request_written_already_approved_is_put_to_a_person(repo):
    request = repo.item("OCR-0001", status="in_progress")
    text = request.read_text()
    request.unlink()
    assert decide(repo, request, content=text) == guard.ASK
    # The id decides what a work item is, not the name of its file.
    assert decide(repo, repo.root / "work/notes.md", content=text) == guard.ASK


def test_only_a_request_is_approved_this_way(repo):
    request = repo.item("OCR-0001", status="in_progress")
    assert decide(repo, request, old_string="A request", new_string="Reworded") == guard.ALLOW
    assert decide(repo, request, old_string="in_progress", new_string="done") == guard.ASK

    requirement = repo.item("REQ-0001", status="in_progress")
    assert decide(repo, requirement, old_string="in_progress", new_string="done") == guard.ALLOW


def apply(path, old_string, new_string):
    """What the Edit tool does once the guard has let the edit through."""
    path.write_text(path.read_text().replace(old_string, new_string, 1))


@pytest.mark.parametrize(
    ("disguise", "restore"),
    [
        (("id: OCR-0001", "id: DEC-9999"), ("id: DEC-9999", "id: OCR-0001")),
        (("---\nid:", "----\nid:"), ("----\nid:", "---\nid:")),
    ],
    ids=["another class's id", "unreadable frontmatter"],
)
def test_approval_cannot_be_split_into_edits_that_each_look_harmless(repo, disguise, restore):
    request = repo.item("OCR-0001", status="draft")
    approve = ("status: draft", "status: in_progress")
    asked = []
    for old, new in (disguise, approve, restore):
        asked.append(decide(repo, request, old_string=old, new_string=new))
        apply(request, old, new)

    (item,) = repo.ws().of_class("OntologyChangeRequest")
    assert (item.id, item.status) == ("OCR-0001", "in_progress")
    assert guard.ASK in asked  # a person was asked before the request stood approved
    assert asked[-1] == guard.ASK


def test_an_approval_does_not_move_to_another_request_unasked(repo):
    request = repo.item("OCR-0001", status="in_progress")
    assert decide(repo, request, old_string="OCR-0001", new_string="OCR-0002") == guard.ASK


def test_an_edit_the_guard_cannot_read_is_put_to_a_person(repo, monkeypatch, capsys):
    request = repo.item("OCR-0001", status="draft")
    approve = {"old_string": "status: draft", "new_string": "status: in_progress"}
    # Not a payload the tool should send. What a tool would write from it is unknown,
    # so the answer is neither a crash (exit 1 lets the edit through) nor allow.
    for edits in (["status: in_progress"], [None, approve], "status: in_progress", {"0": approve}):
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {"file_path": str(request), "edits": edits},
        }
        code, out = hook("guard", stdin=event, monkeypatch=monkeypatch, capsys=capsys)
        assert code == 0 and "Traceback" not in out.err
        answer = json.loads(out.out)["hookSpecificOutput"]
        assert answer["permissionDecision"] == "ask"
        assert "cannot read" in answer["permissionDecisionReason"]

    assert decide(repo, repo.root / "README.md", edits=["x"]) == guard.ALLOW
    assert decide(repo, repo.root / GENERATED, edits=["x"]) == guard.DENY


def test_onto_new_does_not_approve_the_request_it_creates(repo, capsys):
    request = [
        "new",
        "OntologyChangeRequest",
        "title=Add Calibration",
        "bounded_context=call-qa",
        "proposed_term=Calibration",
        "justification=A requirement needs it.",
    ]
    for status in guard.APPROVED:
        assert main([*request, f"status={status}"]) == 1
        assert "a person approves" in capsys.readouterr().err
    assert repo.ws().items == []
    # With no request in progress the ontology stays shut.
    assert decide(repo, repo.root / GLOSSARY) == guard.DENY

    assert main([*request, "status=ready"]) == 0
    assert main(request) == 0
    assert [item.status for item in repo.ws().items] == ["ready", "draft"]
    assert decide(repo, repo.root / GLOSSARY) == guard.DENY


# --- deny rules --------------------------------------------------------------------


def test_the_deny_rules_follow_onto_toml(repo, monkeypatch, capsys):
    assert main(["guard", "--deny-rules"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == [
        "Edit(/apps/call-qa-agent/src/call_qa_agent/generated.py)",
        "Edit(/apps/call-qa-agent/src/call_qa_agent/schemas/call-qa.bindings.json)",
        "Edit(/apps/call-qa-agent/src/call_qa_agent/schemas/call-qa.glossary.json)",
        "Edit(/apps/call-qa-agent/src/call_qa_agent/schemas/call-qa.schema.json)",
        "Edit(/docs/generated/call-qa.md)",
        "Edit(/docs/generated/workflow.md)",
        "Edit(/ontology/schemas/workflow.schema.json)",
        "Edit(/ontology/shapes/workflow.shacl.ttl)",
        "Edit(/work/evidence/**)",
    ]

    config = repo.root / "onto.toml"
    config.write_text(config.read_text().replace("call_qa_agent/generated.py", "types.py"))
    assert "Edit(/apps/call-qa-agent/src/types.py)" in denyrules.rules(repo.ws().cfg)


def test_settings_that_lack_a_derived_rule_fail_the_check(repo, capsys):
    check = ["guard", "--check-settings"]
    assert main(check) == 1  # no settings file at all
    assert "Edit(/work/evidence/**)" in capsys.readouterr().out

    wanted = denyrules.rules(repo.ws().cfg)
    settings = {"permissions": {"deny": [*wanted, "Read(./.env)"]}}
    repo.write(".claude/settings.json", json.dumps(settings))
    assert main(check) == 0
    capsys.readouterr()

    settings["permissions"]["deny"].remove("Edit(/ontology/shapes/workflow.shacl.ttl)")
    repo.write(".claude/settings.json", json.dumps(settings))
    assert main(check) == 1
    out = capsys.readouterr().out
    assert "Edit(/ontology/shapes/workflow.shacl.ttl)" in out and "onto guard --deny-rules" in out

