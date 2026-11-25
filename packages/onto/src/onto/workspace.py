"""One loaded view of the monorepo's ontology layer, shared by all commands."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from . import frontmatter
from .config import Config, load_config
from .glossary import Glossary
from .report import ERROR, Violation
from .schema import WorkflowSchema


@dataclass
class WorkItem:
    """One file under work/: typed frontmatter plus free-form notes."""

    path: Path
    rel: str
    meta: dict
    body: str
    text: str
    cls: str | None  # decided by the shape of the id; None if it fits no class

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))

    @property
    def status(self) -> str:
        return str(self.meta.get("status", ""))

    @property
    def context(self) -> str:
        return str(self.meta.get("bounded_context", ""))

    def values(self, key: str) -> list[str]:
        """A slot's value as a list of strings, whether it holds one value or many."""
        value = self.meta.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]

    def line_of(self, key: str) -> int | None:
        """The line a frontmatter key is written on, for pointing at it in messages."""
        for number, line in enumerate(self.text.splitlines(), start=1):
            if line.startswith(f"{key}:"):
                return number
        return None


EVIDENCE_RULE = "evidence-by-hand"


def _tracked(cfg: Config) -> set[str]:
    """The files under the evidence folder that git tracks: a test run never commits one."""
    if not cfg.evidence_dir.is_dir():
        return set()
    done = subprocess.run(
        ["git", "-C", str(cfg.root), "ls-files", "--full-name", "--", str(cfg.evidence_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    return set(done.stdout.splitlines()) if done.returncode == 0 else set()


def _not_recorded(
    cfg: Config, path: Path, rel: str, meta: dict, cls: str | None, tracked: set[str]
) -> str | None:
    """Why a file is not Evidence a test run recorded. None if it is, or is not Evidence at all.

    A run writes one file per Test, named after it, into the evidence folder,
    which git ignores. Anything else that calls itself Evidence was written by
    hand: elsewhere under work/, committed, or beside the run's own file under
    another id, where its `pass` would stand next to the `fail` the run recorded.
    """
    inside = path.parent == cfg.evidence_dir
    if cls != "Evidence":
        if inside:
            return f"is in {cfg.rel(cfg.evidence_dir)}/, which holds only what a test run recorded"
        return None
    if not inside:
        return (
            f"is Evidence outside {cfg.rel(cfg.evidence_dir)}/: only a test run writes "
            "Evidence, and only there"
        )
    if rel in tracked:
        return "is Evidence committed to git: a test run records it and nobody commits it"
    of_test = meta.get("of_test")
    expected = "EVD-" + of_test.split("-", 1)[-1] if isinstance(of_test, str) else None
    if meta["id"] != expected or path.stem != expected:
        return (
            f"is not the Evidence a test run records for {of_test}: that is "
            f"{expected}, in a file of that name"
        )
    return None


@dataclass
class Workspace:
    cfg: Config = field(default_factory=load_config)

    @classmethod
    def at(cls, root: Path | None = None) -> Workspace:
        return cls(load_config(root))

    @cached_property
    def schema(self) -> WorkflowSchema:
        return WorkflowSchema(self.cfg)

    @cached_property
    def glossaries(self) -> dict[str, Glossary]:
        return {name: Glossary(ctx) for name, ctx in self.cfg.contexts.items()}

    def glossary(self, context: str) -> Glossary | None:
        return self.glossaries.get(context)

    # --- work items -----------------------------------------------------------

    @cached_property
    def _loaded(self) -> tuple[list[WorkItem], list[Violation]]:
        items: list[WorkItem] = []
        problems: list[Violation] = []
        if not self.cfg.work_dir.is_dir():
            return items, problems
        tracked = _tracked(self.cfg)
        for path in sorted(self.cfg.work_dir.rglob("*.md")):
            # A folder named like a work item holds none, and reading it would stop every gate.
            if path.name.lower() == "readme.md" or not path.is_file():
                continue
            rel = self.cfg.rel(path)

            def refuse(message: str, fix: str | None = None, rule: str = "frontmatter", rel=rel):
                problems.append(Violation(rule, ERROR, message, file=rel, line=1, fix=fix))

            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                refuse(f"cannot be read as UTF-8 text ({type(exc).__name__})")
                continue
            try:
                meta, body = frontmatter.split(text)
            except frontmatter.FrontmatterError as exc:
                refuse(str(exc))
                continue
            if not isinstance(meta.get("id"), str):
                refuse("frontmatter has no `id`")
                continue
            cls = self.schema.class_for_id(meta["id"])
            by_hand = _not_recorded(self.cfg, path, rel, meta, cls, tracked)
            if by_hand:
                # Not an item: evidence nobody observed must not reach a gate as a pass.
                refuse(by_hand, "delete it, and run `onto evidence collect`", EVIDENCE_RULE)
                continue
            items.append(WorkItem(path, rel, meta, body, text, cls))
        return items, problems

    @property
    def items(self) -> list[WorkItem]:
        return self._loaded[0]

    @property
    def load_problems(self) -> list[Violation]:
        return self._loaded[1]

    @cached_property
    def by_id(self) -> dict[str, WorkItem]:
        return {item.id: item for item in self.items}

    def of_class(self, cls: str) -> list[WorkItem]:
        return [item for item in self.items if item.cls == cls]

    def reload(self) -> None:
        """Forget the cached work items, after files under work/ were written."""
        for name in ("_loaded", "by_id"):
            self.__dict__.pop(name, None)
