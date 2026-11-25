"""A scratch copy of the ontology layer, for testing a gate against work items you make up.

    def test_my_gate(tmp_path):
        repo = scratch_repo(tmp_path)
        repo.item("REQ-0001", status="done")
        problems = run_shacl(repo.ws(), build_graph(repo.ws()))

The scratch repository has the real onto.toml and ontology/ and an empty work/.
`item` fills in every required field of the class with something valid, so a
test states only what it is about.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter
from .config import find_root
from .workspace import Workspace

CONTEXT = "call-qa"
TEST_PATH = "tests/test_example.py::test_example"

_DEFAULTS: dict[str, dict] = {
    "REQ": {
        "title": "A requirement",
        "status": "ready",
        "bounded_context": CONTEXT,
        "ears_text": "The system shall record a `Finding`.",
        "uses_terms": ["Finding"],
    },
    "TASK": {
        "title": "A task",
        "status": "ready",
        "bounded_context": CONTEXT,
        "implements": ["REQ-0001"],
    },
    "DEC": {
        "title": "A decision",
        "status": "done",
        "bounded_context": CONTEXT,
        "rationale": "Because it is simpler.",
    },
    "CHG": {
        "title": "A change",
        "status": "in_progress",
        "bounded_context": CONTEXT,
        "resolves": ["TASK-0001"],
    },
    "TST": {
        "title": "A test",
        "status": "done",
        "bounded_context": CONTEXT,
        "verifies": ["REQ-0001"],
        "path": TEST_PATH,
    },
    "EVD": {"of_test": "TST-0001", "result": "pass"},
    "OCR": {
        "title": "A request",
        "status": "draft",
        "bounded_context": CONTEXT,
        "proposed_term": "Calibration",
        "justification": "A requirement needs it.",
    },
}


@dataclass
class Scratch:
    root: Path

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def item(self, identifier: str, body: str = "", **fields) -> Path:
        """Write a work item. Fields override the defaults; a field set to None is left out."""
        prefix = identifier.split("-", 1)[0]
        meta = {"id": identifier, **_DEFAULTS.get(prefix, {}), **fields}
        meta = {key: value for key, value in meta.items() if value is not None}
        folder = "work/evidence" if prefix == "EVD" else "work"
        return self.write(f"{folder}/{identifier}.md", frontmatter.render(meta, body))

    def context(self, name: str, schema: str, **table: str | list[str]) -> None:
        """Add a bounded context of your own: its glossary and its table in onto.toml."""
        self.write(f"ontology/domains/{name}.yaml", schema)
        lines = [f"\n[contexts.{name}]", f'schema = "ontology/domains/{name}.yaml"']
        lines += [f"{key} = {json.dumps(value)}" for key, value in table.items()]
        with (self.root / "onto.toml").open("a", encoding="utf-8") as config:
            config.write("\n".join(lines) + "\n")

    def ws(self) -> Workspace:
        return Workspace.at(self.root)


def scratch_repo(tmp_path: Path, source: Path | None = None) -> Scratch:
    """Copy the ontology layer of the real repository (found from this file) into tmp_path."""
    source = source or find_root(Path(__file__).resolve())
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(source / "onto.toml", root / "onto.toml")
    shutil.copytree(
        source / "ontology",
        root / "ontology",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test_*.py"),
    )
    scratch = Scratch(root)
    # Generated artefacts of each context, so `onto gen --check` has something to compare.
    workspace = Workspace.at(source)
    for target, _ in workspace.cfg.generated_files().items():
        if (source / target).is_file() and not (root / target).exists():
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source / target, root / target)
    (root / "work").mkdir(exist_ok=True)
    scratch.write(TEST_PATH.split("::")[0], "def test_example():\n    assert True\n")
    return scratch
