#!/usr/bin/env python3
"""Regenerate the templates `onto init` scaffolds from this repository's own files.

    python tools/sync_templates.py            rewrite packages/onto/src/onto/templates/synced/
    python tools/sync_templates.py --check    fail if that folder is out of date

The workflow ontology, the graph gates, the competency questions and the Claude
Code layer exist once, here, where they are used and tested. An adopting
repository gets a copy with two things replaced by placeholders: the namespace
the ontologies are published under, and the command that runs onto. Nobody
edits the copy: change the source and run this.

Everything under .claude/ is taken except the names in EXCLUDE, so a new skill,
agent or command is picked up without a change here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from onto import scaffold
from onto.config import load_config

ROOT = Path(__file__).resolve().parents[1]
SYNCED = ROOT / "packages/onto/src/onto/templates/synced"

# Sources, relative to the repository root. A folder is walked.
SOURCES = (
    "ontology/workflow.yaml",
    "ontology/shapes/gates.shacl.ttl",
    "ontology/cq",
    ".claude",
    "tools/check_vendored.py",
)
# Left out of a walk: a path, or a name anywhere in a path.
EXCLUDE = (
    ".claude/settings.local.json",  # a person's own settings
    ".claude/worktrees",
    "test_competency_questions.py",  # pins the answers on this repository's work items
    "__pycache__",
    ".DS_Store",
)
# Copied byte for byte: the pinned upstream files, whose hashes are on record,
# and the tool that checks them.
VERBATIM = (
    ".claude/pstack/upstream/",
    ".claude/pstack/provenance.json",
    ".claude/pstack/LICENSE",
    "tools/check_vendored.py",
)
SETTINGS = ".claude/settings.json"
ONTO_HERE = "bin/onto"  # how this repository runs onto
# A hook cannot rely on its working directory, so it names the project folder.
HOOK_HERE = f'"$CLAUDE_PROJECT_DIR"/{ONTO_HERE}'
HOOK_THERE = f'cd "$CLAUDE_PROJECT_DIR" && {scaffold.ONTO_CMD}'


def base_uri() -> str:
    """The namespace this repository publishes under, read from the workflow ontology."""
    source = (ROOT / "ontology/workflow.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(source)["id"].removesuffix("/ontology/workflow")


def sources() -> list[str]:
    found: list[str] = []
    for source in SOURCES:
        path = ROOT / source
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        for file in files:
            rel = file.relative_to(ROOT).as_posix()
            if not any(rel.startswith(name) or name in rel.split("/") for name in EXCLUDE):
                found.append(rel)
    return found


def template_path(rel: str) -> str:
    for plain, hidden in scaffold.HIDDEN.items():
        if rel.startswith(hidden + "/"):
            return plain + rel.removeprefix(hidden)
    return rel


def settings_template(text: str) -> bytes:
    """The hooks and permissions, with every way this repository spells onto replaced."""

    def generalise(value):
        if isinstance(value, str):
            value = value.replace(HOOK_HERE, HOOK_THERE)
            return value.replace(f"./{ONTO_HERE}", scaffold.ONTO_CMD).replace(
                ONTO_HERE, scaffold.ONTO_CMD
            )
        if isinstance(value, list):
            items = [generalise(entry) for entry in value]
            # `bin/onto` and `./bin/onto` become the same permission.
            return list(dict.fromkeys(items)) if all(isinstance(i, str) for i in items) else items
        if isinstance(value, dict):
            return {key: generalise(entry) for key, entry in value.items()}
        return value

    return (json.dumps(generalise(json.loads(text)), indent=2) + "\n").encode()


def local_words() -> list[str]:
    """Names that mean something only here: the bounded contexts and the code they govern."""
    words: set[str] = set()
    for context in load_config(ROOT).contexts.values():
        words.add(context.name)
        words.update(pattern.split("*", 1)[0].rstrip("/") for pattern in context.paths)
    return sorted(word for word in words if word)


def build() -> tuple[dict[str, bytes], list[str]]:
    """The template tree as {path under synced/: content}, and what is wrong with the sources."""
    base = base_uri()
    local = local_words()
    tree: dict[str, bytes] = {}
    problems: list[str] = []
    for rel in sources():
        data = (ROOT / rel).read_bytes()
        if rel == SETTINGS:
            data = settings_template(data.decode())
        elif not rel.startswith(VERBATIM):
            text = data.decode()
            problems += [
                f"{rel}: contains the placeholder {token}"
                for token in (scaffold.ONTO_CMD, scaffold.BASE_URI)
                if token in text
            ]
            problems += [
                f"{rel}: names '{word}', which an adopting repository does not have. "
                "Generalise the source, or add the file to EXCLUDE in tools/sync_templates.py."
                for word in local
                if word in text
            ]
            text = text.replace(base, scaffold.BASE_URI).replace(ONTO_HERE, scaffold.ONTO_CMD)
            data = text.encode()
        tree[template_path(rel)] = data

    hooks = json.loads(tree[template_path(SETTINGS)]).get("hooks", {})
    for groups in hooks.values():
        for command in sorted(scaffold.hook_commands(groups)):
            if scaffold.ONTO_CMD not in command and "/.claude/" not in command:
                problems.append(
                    f"{SETTINGS}: the hook `{command}` runs something `onto init` does not scaffold"
                )
    return tree, problems


def restore(tree: dict[str, bytes]) -> dict[str, bytes]:
    """The templates rendered with this repository's own values, as `onto init` renders them."""
    values = {scaffold.ONTO_CMD: ONTO_HERE, scaffold.BASE_URI: base_uri()}
    return {rel: scaffold.render(data, values) for rel, data in tree.items()}


def differences(tree: dict[str, bytes]) -> list[str]:
    on_disk = {
        path.relative_to(SYNCED).as_posix(): path.read_bytes()
        for path in SYNCED.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    both = sorted(tree.keys() & on_disk.keys())
    return (
        [f"missing   {rel}" for rel in sorted(tree.keys() - on_disk.keys())]
        + [f"stale     {rel}" for rel in sorted(on_disk.keys() - tree.keys())]
        + [f"differs   {rel}" for rel in both if tree[rel] != on_disk[rel]]
    )


def write(tree: dict[str, bytes]) -> None:
    for path in sorted(SYNCED.rglob("*"), reverse=True) if SYNCED.is_dir() else []:
        if path.is_file() and path.relative_to(SYNCED).as_posix() not in tree:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    for rel, data in tree.items():
        target = SYNCED / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)


def main(argv: list[str]) -> int:
    tree, problems = build()
    for problem in problems:
        print(problem)
    if "--check" in argv:
        changed = differences(tree)
        for line in changed:
            print(line)
        if changed:
            print(
                "The templates of `onto init` are out of date: "
                "run `python tools/sync_templates.py` and commit the result."
            )
        return 1 if changed or problems else 0
    if problems:
        return 1
    write(tree)
    print(f"{len(tree)} template file(s) in {SYNCED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
