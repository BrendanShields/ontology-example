"""A scratch copy of the ontology layer, for testing a gate against work items you make up.

    def test_my_gate(tmp_path):
        repo = scratch_repo(tmp_path)
        repo.item("REQ-0001", status="done")
        problems = run_shacl(repo.ws(), build_graph(repo.ws()))

The scratch repository has the onto.toml and ontology/ of the repository the tests
run in and an empty work/.
`item` fills in every required field of the class with something valid, so a
test states only what it is about.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter
from .config import find_root
from .glossary import DEFAULT_CLASSIFICATION
from .workspace import Workspace

TEST_PATH = "tests/test_example.py::test_example"


def _defaults(context: str, term: str) -> dict[str, dict]:
    return {
        "REQ": {
            "title": "A requirement",
            "status": "ready",
            "bounded_context": context,
            "ears_text": f"The system shall record a `{term}`.",
            "uses_terms": [term],
        },
        "TASK": {
            "title": "A task",
            "status": "ready",
            "bounded_context": context,
            "implements": ["REQ-0001"],
        },
        "DEC": {
            "title": "A decision",
            "status": "done",
            "bounded_context": context,
            "rationale": "Because it is simpler.",
        },
        "CHG": {
            "title": "A change",
            "status": "in_progress",
            "bounded_context": context,
            "resolves": ["TASK-0001"],
        },
        "TST": {
            "title": "A test",
            "status": "done",
            "bounded_context": context,
            "verifies": ["REQ-0001"],
            "path": TEST_PATH,
        },
        "EVD": {"of_test": "TST-0001", "result": "pass"},
        "OCR": {
            "title": "A request",
            "status": "draft",
            "bounded_context": context,
            "proposed_term": "Calibration",
            "justification": "A requirement needs it.",
        },
    }


@dataclass
class Scratch:
    root: Path
    context: str  # the bounded context the default items belong to
    term: str  # the glossary term the default Requirement is about

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def item(self, identifier: str, body: str = "", **fields) -> Path:
        """Write a work item. Fields override the defaults; a field set to None is left out."""
        prefix = identifier.split("-", 1)[0]
        defaults = _defaults(self.context, self.term).get(prefix, {})
        meta = {"id": identifier, **defaults, **fields}
        meta = {key: value for key, value in meta.items() if value is not None}
        folder = "work/evidence" if prefix == "EVD" else "work"
        return self.write(f"{folder}/{identifier}.md", frontmatter.render(meta, body))

    def ws(self) -> Workspace:
        return Workspace.at(self.root)


def scratch_repo(
    tmp_path: Path,
    source: Path | None = None,
    *,
    context: str | None = None,
    term: str | None = None,
) -> Scratch:
    """Copy the ontology layer of a repository into tmp_path.

    `source` is the repository to copy: by default the one the tests run in.
    The default items belong to `context` (by default the first in onto.toml)
    and are about `term` (by default its first class that is not classified).
    """
    source = source or find_root()
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(source / "onto.toml", root / "onto.toml")
    shutil.copytree(
        source / "ontology",
        root / "ontology",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test_*.py"),
    )
    workspace = Workspace.at(source)
    context = context or next(iter(workspace.cfg.contexts), None)
    if context not in workspace.cfg.contexts:
        raise ValueError(f"{source / 'onto.toml'} configures no bounded context '{context}'")
    scratch = Scratch(root, context, term or _plain_term(workspace, context))
    # Generated artefacts of each context, so `onto gen --check` has something to compare.
    for target, _ in workspace.cfg.generated_files().items():
        if (source / target).is_file() and not (root / target).exists():
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source / target, root / target)
    (root / "work").mkdir(exist_ok=True)
    scratch.write(TEST_PATH.split("::")[0], "def test_example():\n    assert True\n")
    return scratch


def _plain_term(workspace: Workspace, context: str) -> str:
    """A class any Requirement may use: a classified one would bring its own gates into play."""
    for candidate in workspace.glossaries[context].terms.values():
        if (
            candidate.kind == "class"
            and not candidate.abstract
            and candidate.classification == DEFAULT_CLASSIFICATION
        ):
            return candidate.name
    raise ValueError(f"the {context} glossary has no unclassified class: pass term=")
