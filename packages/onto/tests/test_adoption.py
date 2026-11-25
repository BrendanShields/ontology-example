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

    for gate in (["gen", "--check"], ["validate"], ["check-terms"], ["trace"], ["cq", "--check"]):
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
    assert settings["permissions"]["deny"] == ["Bash(rm *)"]
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
    ],
)
def test_options_that_would_scaffold_something_broken_are_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        scaffold.Options(root=tmp_path, **bad)
    assert not any(tmp_path.iterdir())


# --- the gates, in the adopting repository -----------------------------------------


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

    assert (repo.context, repo.term) == ("loans", "Item")
    monkeypatch.setenv("ONTO_ROOT", str(repo.root))
    assert main(["validate"]) == 0, capsys.readouterr().out
