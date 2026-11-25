"""A scratch copy of the ontology layer, for testing a gate against work items you make up.

    def test_my_gate(tmp_path):
        repo = scratch_repo(tmp_path)
        repo.item("REQ-0001", status="done")
        problems = run_shacl(repo.ws(), build_graph(repo.ws()))

The scratch repository has the onto.toml and ontology/ of the repository the tests
run in and an empty work/.
`item` fills in every required field of the class with something valid, so a
test states only what it is about.

A glossary that binds rules makes `onto rules` and `onto verify` ask for a done
Requirement that proves each one, and a scratch repository starts with none.
A test that is not about those rules starts from a copy that binds nothing:

    repo = scratch_repo(tmp_path, bind_rules=False)
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter
from .config import find_root
from .glossary import DEFAULT_CLASSIFICATION
from .rules import scanned_files
from .workspace import Workspace

TEST_PATH = "tests/test_example.py::test_example"
BINDING_KEYS = ("binding", "precondition_of")  # the annotations that bind a term to code


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
        "INC": {
            "title": "An incident",
            "status": "in_progress",
            "bounded_context": context,
            "observed_on": "2026-01-15",
        },
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
    bounded_context: str  # the one the default items belong to
    term: str  # the glossary term the default Requirement is about

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def item(self, identifier: str, body: str = "", **fields) -> Path:
        """Write a work item. Fields override the defaults; a field set to None is left out."""
        prefix = identifier.split("-", 1)[0]
        defaults = _defaults(self.bounded_context, self.term).get(prefix, {})
        meta = {"id": identifier, **defaults, **fields}
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


def scratch_repo(
    tmp_path: Path,
    source: Path | None = None,
    *,
    context: str | None = None,
    term: str | None = None,
    bind_rules: bool = True,
) -> Scratch:
    """Copy the ontology layer of a repository into tmp_path.

    `source` is the repository to copy: by default the one the tests run in.
    The default items belong to `context` (by default the first in onto.toml)
    and are about `term` (by default its first class that is not classified).
    With `bind_rules=False` the copied glossaries keep every term and bind none
    of them, and the generated files are written again to match. That takes
    `onto gen`, so make such a copy once and pass it as `source` to the rest.
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
    # A bindings manifest is compiled from code as well: bring the files it was read from.
    for context in workspace.cfg.contexts.values():
        if context.bindings_json is not None and context.bindings_json.is_file():
            for rel in scanned_files(workspace.cfg, context):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source / rel, root / rel)
    (root / "work").mkdir(exist_ok=True)
    scratch.write(TEST_PATH.split("::")[0], "def test_example():\n    assert True\n")
    if not bind_rules:
        _withdraw_bindings(root)
    return scratch


def _withdraw_bindings(root: Path) -> None:
    """Rewrite each glossary under root with no term bound, and regenerate from it."""
    import yaml

    from . import gen
    from .config import load_config

    def strip(node) -> None:
        if isinstance(node, dict):
            annotations = node.get("annotations")
            if isinstance(annotations, dict):
                for key in BINDING_KEYS:
                    annotations.pop(key, None)
                if not annotations:
                    del node["annotations"]
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for value in node:
                strip(value)

    cfg = load_config(root)
    for context in cfg.contexts.values():
        glossary = yaml.safe_load(context.schema.read_text(encoding="utf-8"))
        strip(glossary)
        context.schema.write_text(yaml.safe_dump(glossary, sort_keys=False), encoding="utf-8")
        if context.bindings_json is not None:
            context.bindings_json.unlink(missing_ok=True)
    gen.generate(cfg)


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
