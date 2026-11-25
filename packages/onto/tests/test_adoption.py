"""Another repository adopts the framework: `onto init`, then every gate, from the outside.

Each command runs as a subprocess in a temporary git repository, the way an
adopting team runs it. Nothing here reads this repository's ontology/ or work/.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from onto import scaffold
from onto.cli import main
from onto.testing import scratch_repo

# What the scaffolded hooks, Makefile and CI workflow run: the onto of this test run.
ONTO_CMD = f"{shlex.quote(sys.executable)} -m onto"
BASE_URI = "https://library.example"
SENTINEL = "kept-as-it-was"
THEIR_SETTINGS = {
    "model": SENTINEL,
    "permissions": {"allow": ["Bash(ls *)"], "deny": ["Bash(rm *)"]},
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": SENTINEL}]}]
    },
}


def environment(repo: Path) -> dict[str, str]:
    """An environment in which onto can only find `repo`, whatever this test run was started in."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ONTO_", "GITHUB_"))}
    return {**env, "ONTO_ROOT": str(repo), "CLAUDE_PROJECT_DIR": str(repo)}


def run(repo: Path, *command: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=repo,
        env=environment(repo),
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def onto(repo: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return run(repo, sys.executable, "-m", "onto", *args, stdin=stdin)


def init(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    return onto(
        repo,
        "init",
        "--context",
        "loans",
        "--domain-path",
        "src/loans/domain/**",
        "--base-uri",
        BASE_URI,
        "--onto-cmd",
        ONTO_CMD,
        *extra,
    )


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    done = run(path, "git", "init", "--quiet", "--initial-branch", "main")
    assert done.returncode == 0, done.stderr
    return path


def snapshot(repo: Path) -> dict[str, bytes]:
    return {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in sorted(repo.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    }


@pytest.fixture(scope="module")
def scaffolded(tmp_path_factory) -> tuple[Path, subprocess.CompletedProcess]:
    """A repository that had files of its own, after `onto init`. Do not change it: copy it."""
    repo = git_repo(tmp_path_factory.mktemp("adopter") / "repo")
    (repo / ".gitignore").write_text(f"{SENTINEL}/", encoding="utf-8")  # no final newline
    (repo / "Makefile").write_text(f"test:\n\t@echo {SENTINEL}\n", encoding="utf-8")
    (repo / "README.md").write_text(SENTINEL, encoding="utf-8")
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.json").write_text(json.dumps(THEIR_SETTINGS), encoding="utf-8")
    return repo, init(repo)


@pytest.fixture
def adopter(scaffolded, tmp_path) -> Path:
    """A copy of the scaffolded repository that a test may change."""
    source, _ = scaffolded
    return Path(shutil.copytree(source, tmp_path / "repo"))


# --- the scaffold ------------------------------------------------------------------


def test_init_leaves_a_repository_in_which_every_gate_runs_clean(scaffolded):
    repo, done = scaffolded
    assert done.returncode == 0, done.stdout + done.stderr

    for gate in (
        ["gen", "--check"],
        ["validate"],
        ["check-terms"],
        ["trace"],
        ["rules"],
        ["guard", "--check-settings"],
        ["cq", "--check"],
    ):
        result = onto(repo, *gate)
        assert result.returncode == 0, f"onto {' '.join(gate)}\n{result.stdout}{result.stderr}"
    assert "CQ-01" in onto(repo, "cq").stdout
    assert "Owner" in onto(repo, "overview").stdout


def test_what_init_writes_speaks_of_the_adopting_repository_only(scaffolded):
    repo, _ = scaffolded
    files = snapshot(repo)
    pinned = ".claude/pstack/upstream/"

    for rel, data in files.items():
        if rel.startswith(pinned):
            continue
        text = data.decode()
        assert not re.search(r"\{\{[a-z_]+\}\}", text), f"{rel} has a placeholder left in it"
        assert "bank.example" not in text, f"{rel} names the namespace of the onto repository"
        assert "bin/onto" not in text, f"{rel} runs onto through a wrapper that is not here"
        assert "${CLAUDE_PROJECT_DIR}" not in text, f"{rel} looks for onto in the project folder"
    assert f"wf: {BASE_URI}/ontology/workflow/" in files["ontology/workflow.yaml"].decode()
    assert ONTO_CMD in files[".github/workflows/ontology-gates.yml"].decode()
    assert f"`{ONTO_CMD} resolve <name>`" in files[".claude/skills/ostack-mode/SKILL.md"].decode()
    assert f"\n!`{ONTO_CMD} overview`\n" in files[".claude/skills/term-gap/SKILL.md"].decode()


def test_the_skills_adapted_from_pstack_arrive_with_their_licence_and_attribution(scaffolded):
    repo, _ = scaffolded

    assert "MIT License" in (repo / ".claude/pstack/LICENSE").read_text(encoding="utf-8")
    assert "Adapted from pstack" in (repo / ".claude/skills/ostack-mode/SKILL.md").read_text(
        encoding="utf-8"
    )
    for agent in ("domain-analyst", "implementer", "ontology-steward", "reviewer"):
        assert (repo / f".claude/agents/{agent}.md").is_file()
    # The pinned upstream copies are intact and every adapted skill they name is there.
    checked = run(repo, sys.executable, "tools/check_vendored.py")
    assert checked.returncode == 0, checked.stdout


def test_init_adds_to_the_files_a_repository_already_had(scaffolded):
    repo, done = scaffolded

    ignored = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"{SENTINEL}/" in ignored
    assert "work/evidence/" in ignored

    assert (repo / "README.md").read_text(encoding="utf-8") == SENTINEL
    assert run(repo, "make", "test").stdout.strip() == SENTINEL
    planned = run(repo, "make", "--dry-run", "onto-check")
    assert planned.returncode == 0, planned.stderr
    assert f"{ONTO_CMD} trace --collect" in planned.stdout

    settings = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["model"] == SENTINEL
    assert settings["permissions"]["deny"][0] == "Bash(rm *)"
    assert settings["permissions"]["allow"] == ["Bash(ls *)", f"Bash({ONTO_CMD} *)"]
    before_edit = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert before_edit == [SENTINEL, f'cd "$CLAUDE_PROJECT_DIR" && {ONTO_CMD} guard']
    assert {"PostToolUse", "SubagentStart", "Stop"} <= settings["hooks"].keys()

    for merged in (".gitignore", "Makefile", ".claude/settings.json"):
        assert re.search(rf"^merged\s+{re.escape(merged)}", done.stdout, re.M), done.stdout


def test_init_a_second_time_changes_nothing_and_says_what_it_kept(adopter):
    before = snapshot(adopter)

    again = init(adopter, "--base-uri", "https://changed.example")

    assert again.returncode == 0, again.stdout + again.stderr
    assert snapshot(adopter) == before
    assert re.search(r"^exists\s+onto\.toml$", again.stdout, re.M)
    assert re.search(r"^unchanged\s+\.claude/settings\.json$", again.stdout, re.M)
    assert not re.search(
        r"^(written|merged)\s+(?!ontology/schemas|ontology/shapes|src/)", again.stdout, re.M
    )


def test_init_refuses_to_generate_over_a_file_it_did_not_write(tmp_path):
    repo = git_repo(tmp_path / "repo")
    mine = repo / "src/loans/generated.py"
    mine.parent.mkdir(parents=True)
    mine.write_text(SENTINEL, encoding="utf-8")

    done = init(repo)

    assert done.returncode == 1
    assert "src/loans/generated.py" in done.stdout
    assert mine.read_text(encoding="utf-8") == SENTINEL


def test_init_outside_a_git_repository_says_so(tmp_path):
    done = onto(tmp_path, "init")

    assert done.returncode == 1
    assert "git init" in done.stderr
    assert not (tmp_path / "onto.toml").exists()


def options(root: Path, **changes) -> scaffold.Options:
    return scaffold.Options(root=root, context="loans", onto_cmd=ONTO_CMD, **changes)


def test_the_claude_and_ci_parts_can_be_left_out(tmp_path):
    scaffold.scaffold(options(tmp_path, claude=False, ci=False))

    assert (tmp_path / "ontology/shapes/gates.shacl.ttl").is_file()
    assert (tmp_path / "ontology/domains/loans.yaml").is_file()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".github").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "tools").exists()


@pytest.mark.parametrize(
    "theirs",
    ['// a comment\n{"model": "x"}', '{"hooks": []}', '{"permissions": {"allow": "Bash(ls *)"}}'],
)
def test_settings_that_cannot_be_added_to_safely_get_a_file_beside_them(tmp_path, theirs):
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(theirs, encoding="utf-8")

    steps = scaffold.scaffold(options(tmp_path))

    assert settings.read_text(encoding="utf-8") == theirs
    beside = json.loads((tmp_path / ".claude/settings.onto.json").read_text(encoding="utf-8"))
    assert f"Bash({ONTO_CMD} *)" in beside["permissions"]["allow"]
    (told,) = [step for step in steps if step.status == scaffold.BESIDE]
    assert ".claude/settings.json" in told.note


def test_an_existing_claude_md_is_kept_and_the_section_is_written_beside_it(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(SENTINEL, encoding="utf-8")

    scaffold.scaffold(options(tmp_path))

    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == SENTINEL
    assert "/ostack-mode" in (tmp_path / "CLAUDE.onto.md").read_text(encoding="utf-8")


def test_the_files_nobody_edits_are_denied_as_the_adopting_repository_names_them(
    tmp_path, monkeypatch
):
    packaged = scaffold.templates

    def denying(folder: str) -> dict[str, bytes]:
        tree = dict(packaged(folder))
        if folder == "synced":
            settings = json.loads(tree[scaffold.SETTINGS])
            settings["permissions"]["deny"] = [f"Edit({scaffold.GENERATED})"]
            tree[scaffold.SETTINGS] = json.dumps(settings).encode()
        return tree

    monkeypatch.setattr(scaffold, "templates", denying)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text(json.dumps(THEIR_SETTINGS), encoding="utf-8")

    scaffold.scaffold(options(tmp_path))

    settings = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["model"] == SENTINEL
    assert settings["permissions"]["deny"] == [
        "Bash(rm *)",
        "Edit(/ontology/schemas/workflow.schema.json)",
        "Edit(/ontology/shapes/workflow.shacl.ttl)",
        "Edit(/src/loans/generated.py)",
        "Edit(/src/loans/schemas/loans.glossary.json)",
        "Edit(/src/loans/schemas/loans.schema.json)",
        "Edit(/work/evidence/**)",
    ]


def test_a_file_already_beside_the_one_that_could_not_be_merged_is_kept_too(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text("// comments\n{}", encoding="utf-8")
    (tmp_path / ".claude/settings.onto.json").write_text(SENTINEL, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(SENTINEL, encoding="utf-8")
    (tmp_path / "CLAUDE.onto.md").write_text(SENTINEL, encoding="utf-8")

    steps = {step.path: step for step in scaffold.scaffold(options(tmp_path))}

    for rel in (".claude/settings.onto.json", "CLAUDE.onto.md"):
        assert (tmp_path / rel).read_text(encoding="utf-8") == SENTINEL
        assert steps[rel].status == scaffold.EXISTS
        assert "not written" in steps[rel].note


def test_a_context_the_existing_onto_toml_does_not_have_gets_no_glossary(tmp_path):
    scaffold.scaffold(options(tmp_path))

    steps = scaffold.scaffold(scaffold.Options(root=tmp_path, context="billing"))

    assert not (tmp_path / "ontology/domains/billing.yaml").exists()
    (skipped,) = [step for step in steps if step.status == scaffold.SKIPPED]
    assert "[contexts.billing]" in skipped.note


@pytest.mark.parametrize(
    "bad",
    [
        {"context": "Loans"},
        {"domain_path": "domain/**"},
        {"domain_path": "../x/domain/**"},
        {"base_uri": "library"},
        {"base_uri": "https://library.example/a b"},
        {"base_uri": 'https://library.example/a>b"c'},
        {"context": "linkml"},
        {"context": "link-ml"},
    ],
)
def test_options_that_would_scaffold_something_broken_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        scaffold.Options(root=tmp_path, **bad)
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize(
    "given", ["src/loans/domain", "./src/loans/domain/**", "src/loans/domain/"]
)
def test_a_domain_path_written_loosely_still_puts_the_layer_under_the_vocabulary_gate(
    tmp_path, given
):
    repo = git_repo(tmp_path / "repo")
    scaffold.scaffold(options(repo, domain_path=given, claude=False, ci=False))
    domain = repo / "src/loans/domain"
    domain.mkdir(parents=True)
    (domain / "bad.py").write_text("class Holder:\n    pass\n", encoding="utf-8")

    checked = onto(repo, "check-terms")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert "error[denied-term]" in checked.stdout


# --- the gates, in the adopting repository -----------------------------------------


def test_a_domain_layer_pattern_that_matches_no_file_is_not_passed_in_silence(adopter):
    domain = adopter / "src/loans/domain"
    domain.mkdir(parents=True)
    (domain / "bad.py").write_text("class Holder:\n    pass\n", encoding="utf-8")
    assert "unchecked-layer" not in onto(adopter, "check-terms").stdout

    toml = adopter / "onto.toml"
    text = toml.read_text(encoding="utf-8")
    assert '"src/loans/domain/**"' in text
    toml.write_text(text.replace('"src/loans/domain/**"', '"src/loans/domain"'), encoding="utf-8")

    checked = onto(adopter, "check-terms")

    assert "warning[unchecked-layer]" in checked.stdout
    assert "src/loans/domain" in checked.stdout


def test_a_denied_synonym_in_the_domain_layer_blocks_and_the_term_does_not(adopter):
    domain = adopter / "src/loans/domain"
    domain.mkdir(parents=True)
    (domain / "bad.py").write_text("def holder_of(item):\n    return item\n", encoding="utf-8")
    (domain / "good.py").write_text("def owner_of(item):\n    return item\n", encoding="utf-8")

    bad = onto(adopter, "check-terms", "src/loans/domain/bad.py")
    good = onto(adopter, "check-terms", "src/loans/domain/good.py")

    assert bad.returncode == 1
    assert "error[denied-term]" in bad.stdout
    assert "Owner" in bad.stdout
    assert good.returncode == 0, good.stdout

    refused = onto(adopter, "resolve", "Holder")
    assert refused.returncode == 1
    assert "Owner" in refused.stdout


def test_a_requirement_goes_from_written_to_verified(adopter):
    requirement = onto(
        adopter,
        "new",
        "Requirement",
        "title=Every item has an owner",
        "bounded_context=loans",
        "ears_text=The system shall record one `Owner` for each `Item`.",
        "uses_terms=Owner,Item",
        "status=done",
    )
    # A Test item is refused until the test it points at exists.
    (adopter / "tests").mkdir()
    (adopter / "tests/test_owner.py").write_text(
        "def test_an_item_has_its_owner():\n    assert {'item': 'owner'}['item'] == 'owner'\n",
        encoding="utf-8",
    )
    task = onto(
        adopter, "new", "Task", "title=Record the owner", "bounded_context=loans",
        "implements=REQ-0001", "status=done",
    )  # fmt: skip
    test = onto(
        adopter, "new", "Test", "title=An item has its owner", "bounded_context=loans",
        "verifies=REQ-0001", "path=tests/test_owner.py::test_an_item_has_its_owner", "status=done",
    )  # fmt: skip
    for created, rel in ((requirement, "REQ-0001"), (task, "TASK-0001"), (test, "TST-0001")):
        assert created.returncode == 0, created.stdout + created.stderr
        assert created.stdout.strip() == f"work/{rel}.md"
    assert onto(adopter, "validate").returncode == 0

    refused = onto(
        adopter, "new", "Requirement", "title=Holders", "bounded_context=loans",
        "ears_text=The system shall list each `Holder`.", "uses_terms=Holder",
    )  # fmt: skip
    assert refused.returncode == 1
    assert "nothing was written" in refused.stderr
    assert not (adopter / "work/REQ-0002.md").exists()

    claimed = onto(adopter, "trace")
    assert claimed.returncode == 1
    assert "gate:" in claimed.stdout
    assert "no passing Evidence" in claimed.stdout

    tested = run(
        adopter, sys.executable, "-m", "pytest", "--onto-evidence", "--rootdir", ".",
        "-p", "no:cacheprovider", "tests",
    )  # fmt: skip
    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert "recorded evidence for 1 test item(s)" in tested.stdout
    assert (adopter / "work/evidence/EVD-0001.md").is_file()

    proven = onto(adopter, "trace")
    assert proven.returncode == 0, proven.stdout
    assert re.search(r"^REQ-0001\s+done\s.*TST-0001:pass\s+verified$", proven.stdout, re.M)

    ignored = run(adopter, "git", "status", "--porcelain", "--untracked-files=all")
    assert "work/REQ-0001.md" in ignored.stdout
    assert "work/evidence" not in ignored.stdout


# --- after ship --------------------------------------------------------------------


def set_status(repo: Path, identifier: str, status: str) -> None:
    path = repo / f"work/{identifier}.md"
    text, count = re.subn(r"(?m)^status: .*$", f"status: {status}", path.read_text("utf-8"))
    assert count == 1, identifier
    path.write_text(text, encoding="utf-8")


def new(repo: Path, cls: str, *fields: str) -> str:
    created = onto(repo, "new", cls, "bounded_context=loans", *fields)
    assert created.returncode == 0, created.stdout + created.stderr
    return created.stdout.strip().removeprefix("work/").removesuffix(".md")


def collect(repo: Path) -> None:
    tested = run(
        repo, sys.executable, "-m", "pytest", "--onto-evidence", "--rootdir", ".",
        "-p", "no:cacheprovider", "tests",
    )  # fmt: skip
    assert tested.returncode == 0, tested.stdout + tested.stderr


def owner_test(repo: Path) -> None:
    (repo / "tests").mkdir()
    (repo / "tests/test_owner.py").write_text(
        "def test_an_item_has_its_owner():\n    assert {'item': 'owner'}['item'] == 'owner'\n",
        encoding="utf-8",
    )


OWNER_TEST = "path=tests/test_owner.py::test_an_item_has_its_owner"


def test_an_incident_is_closed_only_by_a_verified_requirement(adopter):
    incident = new(
        adopter, "Incident", "title=An item was shown with no owner",
        "observed_on=2026-03-02", "status=in_progress",
    )  # fmt: skip
    assert incident == "INC-0001"
    requirement = new(
        adopter, "Requirement", "title=Every item has an owner",
        "ears_text=The system shall record one `Owner` for each `Item`.",
        "uses_terms=Owner,Item", "status=in_progress", f"raised_from={incident}",
    )  # fmt: skip
    assert onto(adopter, "validate").returncode == 0

    waiting = onto(adopter, "cq", "CQ-08")
    assert re.search(rf"^{incident}\s+in_progress\s+{requirement}\s+in_progress$", waiting.stdout, re.M)
    assert f"{incident} [in_progress] An item was shown with no owner: waiting on {requirement}" in (
        onto(adopter, "view").stdout
    )

    # Closed by saying so: the gate refuses.
    set_status(adopter, incident, "done")
    early = onto(adopter, "trace")
    assert early.returncode == 1
    assert "gate:ClosedIncidentIsFixed" in early.stdout and requirement in early.stdout
    set_status(adopter, incident, "in_progress")

    owner_test(adopter)
    new(adopter, "Task", "title=Record the owner", f"implements={requirement}", "status=done")
    new(adopter, "Test", "title=An item has its owner", f"verifies={requirement}", OWNER_TEST,
        "status=done")  # fmt: skip
    collect(adopter)
    set_status(adopter, requirement, "done")
    set_status(adopter, incident, "done")

    closed = onto(adopter, "trace")
    assert closed.returncode == 0, closed.stdout
    assert "(no rows)" in onto(adopter, "cq", "CQ-08").stdout
    assert f"{incident} [" not in onto(adopter, "view").stdout  # no longer among the open ones


def test_a_rule_changes_by_a_requirement_that_replaces_the_old_one(adopter):
    """The Rule change playbook, as the scaffolded gates take it."""
    owner_test(adopter)
    old = new(
        adopter, "Requirement", "title=Every item has an owner",
        "ears_text=The system shall record one `Owner` for each `Item`.",
        "uses_terms=Owner,Item", "status=done",
    )  # fmt: skip
    old_task = new(adopter, "Task", "title=Record the owner", f"implements={old}", "status=done")
    test = new(adopter, "Test", "title=An item has its owner", f"verifies={old}", OWNER_TEST,
               "status=done")  # fmt: skip
    old_decision = new(adopter, "Decision", "title=One owner", "rationale=Simplest.",
                       "uses_terms=Owner", "status=done")  # fmt: skip
    collect(adopter)
    assert onto(adopter, "trace").returncode == 0

    replacement = new(
        adopter, "Requirement", "title=Every item has an owner or a label",
        "ears_text=The system shall record one `Owner` or one `Label` for each `Item`.",
        "uses_terms=Owner,Label,Item", "status=done", f"replaces={old}",
    )  # fmt: skip
    new(adopter, "Task", "title=Allow a label", f"implements={replacement}", "status=done")
    (adopter / "src/loans/domain").mkdir(parents=True, exist_ok=True)
    (adopter / "src/loans/domain/owner.py").write_text("owner = None\n", encoding="utf-8")
    decision = new(
        adopter, "Decision", "title=An owner or a label", "rationale=Shared items have no owner.",
        "uses_terms=Owner", "status=done", f"supersedes={old_decision}",
        "affects=src/loans/domain/*.py",
    )  # fmt: skip
    path = adopter / f"work/{test}.md"
    path.write_text(
        path.read_text("utf-8").replace(f"verifies: [{old}]", f"verifies: [{replacement}]"), "utf-8"
    )

    unmarked = onto(adopter, "trace")
    assert unmarked.returncode == 1
    assert "gate:ReplacedRequirementIsMarked" in unmarked.stdout
    assert "gate:SupersededDecisionIsMarked" in unmarked.stdout

    set_status(adopter, old, "superseded")
    set_status(adopter, old_decision, "superseded")
    set_status(adopter, old_task, "superseded")
    collect(adopter)
    for gate in (["validate"], ["trace"], ["rules"]):
        held = onto(adopter, *gate)
        assert held.returncode == 0, f"onto {' '.join(gate)}\n{held.stdout}{held.stderr}"

    forward = onto(adopter, "cq", "CQ-09", "--bind", f"requirement={old}")
    assert re.search(rf"^{old}\s+{replacement}\s+done\s", forward.stdout, re.M)
    on_path = onto(adopter, "cq", "CQ-10", "--bind", "path=src/loans/domain/owner.py")
    assert decision in on_path.stdout and old_decision not in on_path.stdout
    sliced = onto(adopter, "slice", "--term", "Item", "--file", "src/loans/domain/owner.py")
    assert f"{decision} An owner or a label" in sliced.stdout
    assert old not in sliced.stdout.split("already established")[1]

    # The file the Decision constrains is moved away: the constraint is reported as stale.
    (adopter / "src/loans/domain/owner.py").unlink()
    stale = onto(adopter, "validate")
    assert stale.returncode == 0
    assert "warning[stale-affects]" in stale.stdout and "src/loans/domain/*.py" in stale.stdout


def test_the_scaffolded_guard_hook_blocks_the_files_nobody_edits_by_hand(adopter):
    settings = json.loads((adopter / ".claude/settings.json").read_text(encoding="utf-8"))
    (command,) = [
        hook["command"]
        for group in settings["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if hook["command"].endswith(" guard")
    ]

    def edit(rel: str) -> subprocess.CompletedProcess:
        event = {"tool_name": "Edit", "tool_input": {"file_path": str(adopter / rel)}}
        return run(adopter, "sh", "-c", command, stdin=json.dumps(event))

    for protected in (
        "ontology/domains/loans.yaml",
        "src/loans/generated.py",
        "work/evidence/EVD-0001.md",
    ):
        blocked = edit(protected)
        assert blocked.returncode == 2, f"{protected}: {blocked.stdout}{blocked.stderr}"
        assert protected in blocked.stderr
    allowed = edit("src/loans/domain/loan.py")
    assert allowed.returncode == 0, allowed.stderr


def test_the_scaffolded_stop_hook_blocks_a_claim_that_has_no_evidence(adopter):
    settings = json.loads((adopter / ".claude/settings.json").read_text(encoding="utf-8"))
    (command,) = [h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"]]
    assert onto(adopter, "new", "Requirement", "title=Every item has an owner",
                "bounded_context=loans", "ears_text=The system shall record one `Owner`.",
                "uses_terms=Owner", "status=done").returncode == 0  # fmt: skip

    stopped = run(adopter, "sh", "-c", command, stdin=json.dumps({"hook_event_name": "Stop"}))

    assert stopped.returncode == 2
    assert "REQ-0001" in stopped.stderr


def test_trace_fails_in_an_adopting_repository_whose_gates_use_another_namespace(adopter):
    gates = adopter / "ontology/shapes/gates.shacl.ttl"
    text = gates.read_text(encoding="utf-8")
    assert BASE_URI in text
    gates.write_text(text.replace(BASE_URI, "https://bank.example"), encoding="utf-8")

    done = onto(adopter, "trace")

    assert done.returncode == 1
    assert "error[namespace]" in done.stdout


def test_the_test_helpers_work_on_an_adopting_repository(scaffolded, tmp_path, monkeypatch, capsys):
    source, _ = scaffolded

    repo = scratch_repo(tmp_path, source)
    repo.item("REQ-0001")
    repo.item("TASK-0001")

    assert (repo.bounded_context, repo.term) == ("loans", "Item")
    monkeypatch.setenv("ONTO_ROOT", str(repo.root))
    assert main(["validate"]) == 0, capsys.readouterr().out
