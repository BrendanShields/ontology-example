"""Where the ontology layer lives: reads onto.toml at the monorepo root."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_FILE = "onto.toml"


class ConfigError(Exception):
    """onto.toml is missing or does not make sense."""


@dataclass(frozen=True)
class Context:
    """One bounded context: a domain ontology and the code it governs."""

    name: str
    schema: Path
    paths: tuple[str, ...]  # everything that belongs to the context (the app)
    domain_paths: tuple[str, ...]  # the domain layer: vocabulary is enforced here
    pydantic: Path | None  # generated types
    json_schema: Path | None  # generated JSON Schema
    glossary_json: Path | None  # generated definitions, for apps that quote them at runtime
    docs: Path | None = None  # generated page: diagram, terms, enums, mappings


@dataclass(frozen=True)
class Config:
    root: Path
    workflow_schema: Path
    workflow_json_schema: Path  # generated
    workflow_shacl: Path  # generated
    gate_shapes: tuple[Path, ...]  # hand-written
    cq_dir: Path
    work_dir: Path
    evidence_dir: Path
    audit_dir: Path
    prov_dir: Path
    base_ref: str
    protected: tuple[str, ...]
    on_open_ocr: str  # "ask" | "allow"
    contexts: dict[str, Context]
    workflow_docs: Path | None = None  # generated page of the workflow ontology

    def rel(self, path: Path | str) -> str:
        """Repository-relative, forward-slashed form of a path (for messages and globs)."""
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        try:
            return p.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return p.as_posix()

    def generated_files(self) -> dict[str, str]:
        """Generated file (repo-relative) -> the source it is generated from."""
        out = {
            self.rel(self.workflow_json_schema): self.rel(self.workflow_schema),
            self.rel(self.workflow_shacl): self.rel(self.workflow_schema),
        }
        if self.workflow_docs is not None:
            out[self.rel(self.workflow_docs)] = self.rel(self.workflow_schema)
        for ctx in self.contexts.values():
            for target in (ctx.pydantic, ctx.json_schema, ctx.glossary_json, ctx.docs):
                if target is not None:
                    out[self.rel(target)] = self.rel(ctx.schema)
        return out

    def context_of(self, path: Path | str) -> Context | None:
        """The bounded context a file belongs to, if any."""
        rel = self.rel(path)
        for ctx in self.contexts.values():
            if matches(rel, ctx.paths):
                return ctx
        return None

    def domain_context_of(self, path: Path | str) -> Context | None:
        """The bounded context whose *domain layer* contains the file, if any."""
        rel = self.rel(path)
        for ctx in self.contexts.values():
            if matches(rel, ctx.domain_paths):
                return ctx
        return None


def find_root(start: Path | None = None) -> Path:
    """Locate the monorepo root: $ONTO_ROOT, then $CLAUDE_PROJECT_DIR, then walk up."""
    for var in ("ONTO_ROOT", "CLAUDE_PROJECT_DIR"):
        value = os.environ.get(var)
        if value and (Path(value) / CONFIG_FILE).is_file():
            return Path(value).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_FILE).is_file():
            return candidate
    raise ConfigError(f"no {CONFIG_FILE} found in {here} or any parent directory")


def load_config(root: Path | None = None) -> Config:
    root = (root or find_root()).resolve()
    path = root / CONFIG_FILE
    if not path.is_file():
        raise ConfigError(f"{path} does not exist")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    workflow = raw.get("workflow", {})
    guard = raw.get("guard", {})
    work_dir = root / workflow.get("work", "work")

    contexts: dict[str, Context] = {}
    for name, body in raw.get("contexts", {}).items():
        if "schema" not in body:
            raise ConfigError(f"{path}: [contexts.{name}] needs a `schema`")
        contexts[name] = Context(
            name=name,
            schema=root / body["schema"],
            paths=tuple(body.get("paths", ())),
            domain_paths=tuple(body.get("domain_paths", ())),
            pydantic=root / body["pydantic"] if "pydantic" in body else None,
            json_schema=root / body["json_schema"] if "json_schema" in body else None,
            glossary_json=root / body["glossary_json"] if "glossary_json" in body else None,
            docs=root / body["docs"] if "docs" in body else None,
        )

    on_open_ocr = guard.get("on_open_ocr", "ask")
    if on_open_ocr not in ("ask", "allow"):
        raise ConfigError(f"{path}: [guard] on_open_ocr must be 'ask' or 'allow'")

    return Config(
        root=root,
        workflow_schema=root / workflow.get("schema", "ontology/workflow.yaml"),
        workflow_json_schema=root
        / workflow.get("json_schema", "ontology/schemas/workflow.schema.json"),
        workflow_shacl=root / workflow.get("shacl", "ontology/shapes/workflow.shacl.ttl"),
        gate_shapes=tuple(root / p for p in workflow.get("gates", ())),
        cq_dir=root / workflow.get("competency_questions", "ontology/cq"),
        work_dir=work_dir,
        evidence_dir=work_dir / "evidence",
        audit_dir=root / workflow.get("decision_log", ".audit"),
        prov_dir=root / workflow.get("provenance", "prov"),
        base_ref=workflow.get("base_ref", "origin/main"),
        protected=tuple(guard.get("protected", ())),
        on_open_ocr=on_open_ocr,
        contexts=contexts,
        workflow_docs=root / workflow["docs"] if "docs" in workflow else None,
    )


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob into a regex. `**` crosses directories, `*` and `?` do not."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(rel_path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """True if the repository-relative path matches any of the globs."""
    return any(_glob_regex(p).match(rel_path) for p in patterns)
