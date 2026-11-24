"""One loaded view of the monorepo's ontology layer, shared by all commands."""

from __future__ import annotations

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
        for path in sorted(self.cfg.work_dir.rglob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            rel = self.cfg.rel(path)
            text = path.read_text(encoding="utf-8")
            try:
                meta, body = frontmatter.split(text)
            except frontmatter.FrontmatterError as exc:
                problems.append(Violation("frontmatter", ERROR, str(exc), file=rel, line=1))
                continue
            if not isinstance(meta.get("id"), str):
                problems.append(
                    Violation("frontmatter", ERROR, "frontmatter has no `id`", file=rel, line=1)
                )
                continue
            items.append(
                WorkItem(path, rel, meta, body, text, self.schema.class_for_id(meta["id"]))
            )
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
