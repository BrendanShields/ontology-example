"""Validate work items one file at a time: shape, references, vocabulary.

These checks need no graph, so they are fast enough to run after every edit.
The cross-artefact rules (does every finished requirement have passing
evidence?) live in the SHACL gates and run on the graph: see gates.py.
"""

from __future__ import annotations

import difflib
import os
import re
import subprocess

from . import ears
from .config import Config, matches
from .glossary import Glossary, Resolution
from .report import ERROR, WARNING, Violation
from .textscan import DeniedMatcher
from .workspace import WorkItem, Workspace

# Classes whose prose is scanned for denied synonyms. Decisions and change
# requests are left out on purpose: they have to be able to name a retired term.
PROSE_CHECKED = {"Requirement": ("title", "ears_text"), "Task": ("title",), "Test": ("title",)}


def validate(ws: Workspace, only: set[str] | None = None) -> list[Violation]:
    """All problems in the work items, or just in the files named by `only` (repo-relative)."""
    wanted = (lambda rel: True) if only is None else (lambda rel: rel in only)
    problems = [p for p in ws.load_problems if wanted(p.file or "")]

    seen: dict[str, WorkItem] = {}
    for item in ws.items:
        first = seen.setdefault(item.id, item)
        if first is not item and wanted(item.rel):
            problems.append(
                Violation(
                    "duplicate-id",
                    ERROR,
                    f"id {item.id} is already used by {first.rel}",
                    file=item.rel,
                    line=item.line_of("id"),
                    subject=item.id,
                )
            )
        if wanted(item.rel):
            problems.extend(validate_item(ws, item))
    return problems


def validate_item(ws: Workspace, item: WorkItem) -> list[Violation]:
    if item.cls is None:
        patterns = tuple(p.pattern for p in ws.schema.record_classes.values())
        return [
            Violation(
                "unknown-id",
                ERROR,
                f"id '{item.id}' has the shape of no class in the workflow ontology",
                file=item.rel,
                line=item.line_of("id"),
                subject=item.id,
                found=item.id,
                allowed=patterns,
            )
        ]

    problems: list[Violation] = []

    def problem(rule: str, message: str, key: str | None = None, severity: str = ERROR, **extra):
        problems.append(
            Violation(
                rule,
                severity,
                message,
                file=item.rel,
                line=item.line_of(key) if key else None,
                subject=item.id,
                **extra,
            )
        )

    if item.path.stem != item.id:
        problem("filename", f"the file must be named {item.id}.md, after its id", "id")

    problems.extend(_schema_problems(ws, item))

    glossary = ws.glossary(item.context)
    if item.context and glossary is None:
        problem(
            "unknown-context",
            f"bounded_context '{item.context}' is not configured in onto.toml",
            "bounded_context",
            found=item.context,
            allowed=tuple(ws.cfg.contexts),
        )

    for slot in ws.schema.slots(item.cls):
        if slot.kind == "record":
            for value in item.values(slot.name):
                target = ws.by_id.get(value)
                if target is None:
                    problem(
                        "dangling-reference",
                        f"{slot.name} points at {value}, which does not exist under work/",
                        slot.name,
                        found=value,
                    )
                elif target.cls != slot.range:
                    problem(
                        "dangling-reference",
                        f"{slot.name} must point at a {slot.range}, but {value} is a {target.cls}",
                        slot.name,
                        found=value,
                    )
        elif slot.kind == "term" and glossary is not None:
            for value in item.values(slot.name):
                issue = _term_problem(glossary, value)
                if issue:
                    problem(*issue[:2], slot.name, found=value, **issue[2])

    if item.cls == "Requirement":
        problems.extend(_requirement_problems(item, glossary))
        if item.id in _earlier_versions(ws, item):
            problem(
                "replaces-cycle",
                "replaces leads back to this Requirement: a Requirement replaces an earlier one",
                "replaces",
            )
        successors = [r for r in ws.of_class("Requirement") if item.id in r.values("replaces")]
        settled = any(r.status in ("done", "superseded") for r in successors)
        if item.status == "superseded" and successors and not settled:
            waiting = ", ".join(f"{r.id} ({r.status})" for r in successors)
            problem(
                "withdrawn-early",
                f"status is superseded, but what replaces it is not done yet: {waiting}. "
                "Until then no Requirement is in force in its place",
                "status",
                severity=WARNING,
                fix="keep the earlier status until the Requirement that replaces it is done",
            )
    if item.cls == "Incident":
        if item.status == "superseded":
            problem(
                "incident-superseded",
                "status is superseded, which would close the Incident with no Requirement: "
                "an Incident is closed as done, by the Requirements that fix it",
                "status",
                found=item.status,
                fix="set it done once each Requirement it breaks or that was raised from it "
                "is done; delete an Incident that was recorded by mistake",
            )
        if not item.meta.get("observed_on"):
            problem(
                "incident-undated",
                "observed_on is missing: an Incident says when it was observed",
                severity=WARNING,
            )
    if item.cls == "Test":
        for value in item.values("path"):
            file_part = value.split("::", 1)[0]
            if not (ws.cfg.root / file_part).is_file():
                problem(
                    "missing-test",
                    f"path points at {file_part}, which does not exist",
                    "path",
                    found=value,
                )

    if item.cls == "Decision" and item.status != "superseded":
        files = repository_files(ws.cfg) if item.values("affects") else []
        for glob in item.values("affects"):
            if not any(matches(rel, (glob,)) for rel in files):
                problem(
                    "stale-affects",
                    f"affects names '{glob}', which matches no file in the repository",
                    "affects",
                    severity=WARNING,
                    found=glob,
                    fix="write the glob from the repository root, or take it out if the "
                    "files it named are gone",
                )

    if glossary is not None:
        problems.extend(_denied_in_prose(item, glossary))
    return problems


def _earlier_versions(ws: Workspace, item: WorkItem) -> set[str]:
    """Every Requirement reached from this one by following `replaces`."""
    reached: set[str] = set()
    ahead = item.values("replaces")
    while ahead:
        earlier = ahead.pop()
        if earlier not in reached:
            reached.add(earlier)
            if earlier in ws.by_id:
                ahead.extend(ws.by_id[earlier].values("replaces"))
    return reached


SKIPPED_FOLDERS = ("node_modules", "__pycache__")


def repository_files(cfg: Config) -> list[str]:
    """Every file of the repository, relative to its root: what git tracks or would track.

    Outside a git repository the folders are walked instead, leaving out hidden
    ones and those no one writes by hand.
    """
    listed = subprocess.run(
        ["git", "-C", str(cfg.root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode == 0:
        return [rel for rel in listed.stdout.splitlines() if (cfg.root / rel).is_file()]
    found: list[str] = []
    for folder, folders, names in os.walk(cfg.root):
        folders[:] = [f for f in folders if not f.startswith(".") and f not in SKIPPED_FOLDERS]
        found.extend(cfg.rel(os.path.join(folder, name)) for name in names)
    return found


# --- shape -----------------------------------------------------------------------


def _schema_problems(ws: Workspace, item: WorkItem) -> list[Violation]:
    """JSON Schema errors, reworded so they say what was found and what is allowed."""
    problems: list[Violation] = []
    properties = ws.schema.json_schema["$defs"][item.cls]["properties"]
    validator = ws.schema.validator(item.cls)
    for error in sorted(validator.iter_errors(item.meta), key=lambda e: list(e.absolute_path)):
        key = str(error.absolute_path[0]) if error.absolute_path else None
        value = error.instance
        extra: dict = {}
        if error.validator == "required":
            missing = re.match(r"'([^']+)'", error.message)
            key = missing.group(1) if missing else None
            message = f"{item.cls} needs the field '{key}'"
        elif error.validator == "additionalProperties":
            unknown = sorted(set(item.meta) - set(properties))
            key = unknown[0] if unknown else None
            message = f"{item.cls} has no field '{key}'"
            extra["found"] = key
            extra["suggestions"] = tuple(difflib.get_close_matches(key or "", properties, n=3))
            extra["allowed"] = tuple(sorted(properties))
        elif _enum_of(error) is not None:
            message = f"{key} is '{value}', which is not one of its permitted values"
            extra["found"] = str(value)
            extra["allowed"] = tuple(_enum_of(error))
        elif error.validator == "pattern":
            message = f"{key} is '{value}', which does not match {error.validator_value}"
            extra["found"] = str(value)
        elif error.validator == "type":
            message = f"{key} must be of type {error.validator_value}"
        elif error.validator == "format":
            message = f"{key} is '{value}', which is not a valid {error.validator_value}"
            extra["found"] = str(value)
        elif error.validator == "minItems":
            message = f"{key} needs at least {error.validator_value} value(s)"
        else:
            message = f"{key}: {error.message}" if key else error.message
        problems.append(
            Violation(
                "schema",
                ERROR,
                message,
                file=item.rel,
                line=item.line_of(key) if key else None,
                subject=item.id,
                **extra,
            )
        )
    return problems


def _enum_of(error) -> list[str] | None:
    """The permitted values if the error is about an enum, including nullable enums."""
    if error.validator == "enum":
        return list(error.validator_value)
    if error.validator == "anyOf":
        for sub in error.context or ():
            if sub.validator == "enum":
                return list(sub.validator_value)
    return None


# --- vocabulary ------------------------------------------------------------------


def _term_problem(glossary: Glossary, name: str) -> tuple[str, str, dict] | None:
    """(rule, message, extra) if `name` is not the canonical name of a glossary term."""
    resolution = glossary.resolve(name)
    return None if resolution.status == "exact" else explain(glossary, resolution)


def explain(glossary: Glossary, resolution: Resolution) -> tuple[str, str, dict]:
    """Why a name was not accepted, and what to write or do instead."""
    name, context = resolution.query, glossary.name
    if resolution.status in ("alias", "normalized"):
        canonical = tuple(t.short_name for t in resolution.terms)
        return (
            "term-not-canonical",
            f"'{name}' is not a canonical term name in the {context} glossary",
            {"suggestions": canonical, "fix": f"write {' or '.join(canonical)}"},
        )
    if resolution.status == "denied":
        term = resolution.terms[0]
        return (
            "denied-term",
            f"'{name}' is a denied synonym in the {context} glossary",
            {"suggestions": (term.name,), "fix": f"write {term.name}"},
        )
    return (
        "unknown-term",
        f"'{name}' is not a term of the {context} glossary",
        {
            "suggestions": resolution.suggestions,
            "fix": (
                "use an existing term, or if this is a new concept raise an "
                f"OntologyChangeRequest: onto ocr new --context {context} --term {name} "
                '--justification "..."'
            ),
        },
    )


def _requirement_problems(item: WorkItem, glossary: Glossary | None) -> list[Violation]:
    problems: list[Violation] = []
    text = item.meta.get("ears_text")
    if not isinstance(text, str):
        return problems
    line = item.line_of("ears_text")

    def problem(rule: str, message: str, severity: str = ERROR, **extra):
        problems.append(
            Violation(rule, severity, message, file=item.rel, line=line, subject=item.id, **extra)
        )

    if ears.classify(text) is None:
        problem("ears", "ears_text follows none of the EARS patterns", allowed=ears.TEMPLATES)
    if glossary is None:
        return problems

    listed = {t.name for name in item.values("uses_terms") if (t := glossary.get(name))}
    mentioned: set[str] = set()
    for name in ears.bound_terms(text):
        resolution = glossary.resolve(name)
        if resolution.status != "exact":
            rule, message, extra = explain(glossary, resolution)
            problem(rule, f"ears_text: {message}", found=name, **extra)
            continue
        term = resolution.terms[0]
        mentioned.add(term.name)
        if term.name not in listed:
            problem(
                "unbound-term",
                f"`{name}` is written in ears_text but is missing from uses_terms",
                found=name,
                fix=f"add {name} to uses_terms",
            )
    for name in sorted(listed - mentioned):
        short = glossary.terms[name].short_name
        problem(
            "unmentioned-term",
            f"uses_terms lists {short}, which ears_text never writes in backticks",
            severity=WARNING,
            found=short,
        )
    return problems


def _denied_in_prose(item: WorkItem, glossary: Glossary) -> list[Violation]:
    """Denied synonyms in plain prose only warn: prose is not an identifier."""
    problems: list[Violation] = []
    matcher = DeniedMatcher(glossary.denied_entries())
    for key in PROSE_CHECKED.get(item.cls or "", ()):
        text = item.meta.get(key)
        if not isinstance(text, str):
            continue
        plain = re.sub(
            r"`[^`]*`", lambda m: " " * len(m.group(0)), text
        )  # backticks: handled above
        for hit in matcher.find(plain):
            problems.append(
                Violation(
                    "denied-term",
                    WARNING,
                    f"{key} says '{hit.text}', a denied synonym in the {glossary.name} glossary",
                    file=item.rel,
                    line=item.line_of(key),
                    subject=item.id,
                    found=hit.text,
                    suggestions=(hit.term.name,),
                    fix=f"write `{hit.term.name}`",
                )
            )
    return problems
