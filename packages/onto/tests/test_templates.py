"""The templates `onto init` scaffolds are a copy of this repository's files, and stay one."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
from onto import scaffold
from onto.config import find_root

ROOT = find_root(Path(__file__).resolve())


@pytest.fixture(scope="module")
def sync():
    spec = importlib.util.spec_from_file_location(
        "sync_templates", ROOT / "tools/sync_templates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_packaged_templates_are_what_the_sources_give_today(sync):
    tree, problems = sync.build()

    assert problems == []
    assert sync.differences(tree) == [], "run `python tools/sync_templates.py`"


def test_rendered_with_this_repositorys_values_a_template_is_its_source_again(sync):
    tree, _ = sync.build()
    restored = sync.restore(tree)

    for rel in sync.sources():
        if rel != sync.SETTINGS:  # hooks are rewritten on purpose: they cannot rely on bin/onto
            assert restored[sync.template_path(rel)] == (ROOT / rel).read_bytes(), rel


def test_every_skill_agent_and_question_of_this_repository_is_a_template(sync):
    tree, _ = sync.build()
    here = [
        path.relative_to(ROOT).as_posix()
        for folder in (".claude/skills", ".claude/agents", ".claude/pstack")
        for path in (ROOT / folder).rglob("*")
        if path.is_file()
    ] + [path.relative_to(ROOT).as_posix() for path in (ROOT / "ontology/cq").glob("*.rq")]

    assert here
    assert {sync.template_path(rel) for rel in here} <= tree.keys()
    assert not [rel for rel in tree if rel.endswith("test_competency_questions.py")]


def test_the_hooks_template_runs_onto_through_the_placeholder_only(sync):
    tree, _ = sync.build()
    settings = tree[scaffold.SETTINGS].decode()

    assert "bin/onto" not in settings
    assert f'cd \\"$CLAUDE_PROJECT_DIR\\" && {scaffold.ONTO_CMD} guard' in settings


def test_a_template_folder_that_fell_behind_is_reported_file_by_file(sync, tmp_path, monkeypatch):
    tree, _ = sync.build()
    behind = Path(shutil.copytree(sync.SYNCED, tmp_path / "synced"))
    (behind / "ontology/workflow.yaml").write_text("edited by hand", encoding="utf-8")
    (behind / "claude/agents/reviewer.md").unlink()
    (behind / "claude/agents/retired.md").write_text("gone from the sources", encoding="utf-8")
    monkeypatch.setattr(sync, "SYNCED", behind)

    assert sync.differences(tree) == [
        "missing   claude/agents/reviewer.md",
        "stale     claude/agents/retired.md",
        "differs   ontology/workflow.yaml",
    ]
    assert sync.main(["--check"]) == 1

    sync.write(tree)
    assert sync.differences(tree) == []


def test_a_skill_that_names_this_repositorys_app_is_not_shipped_in_silence(sync, monkeypatch):
    monkeypatch.setattr(sync, "local_words", lambda: ["ostack-mode"])

    _, problems = sync.build()

    assert any(
        p.startswith(".claude/skills/ostack-mode/SKILL.md: names 'ostack-mode'") for p in problems
    )
    assert sync.main(["--check"]) == 1


def test_this_repositorys_contexts_and_app_paths_are_the_local_words(sync):
    assert {"call-qa", "apps/call-qa-agent"} <= set(sync.local_words())
