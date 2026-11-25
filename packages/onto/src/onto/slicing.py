"""Slices: the part of the ontology one piece of work needs, and no more.

An agent is never handed the whole glossary. It gets an overview to orient
itself (`onto overview`), resolves names one at a time (`onto resolve`), and
receives a slice for the task in hand (`onto slice`): the terms its
requirements use, their direct neighbours, the decisions still in force about
them and the requirements already established on them.

A Decision can also constrain files instead of terms, through the globs in its
`affects`. It joins the slice of work that touches a matching file: a file
named with `--file`, or for a Task a file the branch changed.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field

from .config import matches
from .glossary import Glossary, Term
from .workitems import repository_files
from .workspace import WorkItem, Workspace

DEFAULT_BUDGET = 3000  # tokens. The spike's exit criterion for a slice.


class SliceError(ValueError):
    pass


@dataclass
class Slice:
    context: str
    title: str
    task: WorkItem | None = None
    requirements: list[WorkItem] = field(default_factory=list)
    focus: list[Term] = field(default_factory=list)  # named by the work itself
    neighbours: list[Term] = field(default_factory=list)  # one step away
    decisions: list[WorkItem] = field(default_factory=list)
    # Decision id -> the files of this work its `affects` globs match. A Decision
    # listed with no file is here because which files the work touches is unknown.
    affecting: dict[str, list[str]] = field(default_factory=dict)
    established: list[WorkItem] = field(default_factory=list)
    replaced: list[WorkItem] = field(default_factory=list)  # by the work's own Requirements
    incidents: list[WorkItem] = field(default_factory=list)  # open, and answered by this work
    types_file: str | None = None
    depth: int = 1


def estimate_tokens(text: str) -> int:
    """A rough token count (about four characters per token). An estimate, not a measurement."""
    return math.ceil(len(text) / 4)


# --- what is being worked on -------------------------------------------------------


def current_task(ws: Workspace) -> WorkItem | None:
    """The task in hand: $ONTO_TASK, else the branch name, else the only task in progress."""
    named = os.environ.get("ONTO_TASK")
    if not named:
        done = subprocess.run(
            ["git", "-C", str(ws.cfg.root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        )
        match = re.search(r"TASK-\d{4}", done.stdout) if done.returncode == 0 else None
        named = match.group(0) if match else None
    if named:
        item = ws.by_id.get(named)
        return item if item is not None and item.cls == "Task" else None
    active = [t for t in ws.of_class("Task") if t.status == "in_progress"]
    return active[0] if len(active) == 1 else None


def decisions_in_force(ws: Workspace, context: str | None = None) -> list[WorkItem]:
    """Decisions that are decided and that no later decided Decision supersedes.

    A Decision is decided once it is done, and it stays decided after it has
    itself been superseded: a draft that names a predecessor replaces nothing yet.
    """
    decisions = ws.of_class("Decision")
    superseded = {
        target
        for d in decisions
        if d.status in ("done", "superseded")
        for target in d.values("supersedes")
    }
    return [
        d
        for d in decisions
        if d.status == "done"
        and d.id not in superseded
        and (context is None or d.context == context)
    ]


def decisions_affecting(ws: Workspace, files: set[str] | None) -> dict[str, list[str]]:
    """Decisions in force whose `affects` globs match one of the files: id -> the files matched.

    `files` is None when what the work touches is unknown. Every Decision in
    force that constrains files is then given, each with no file: a constraint
    shown without need costs a line, one withheld costs the constraint.
    """
    found: dict[str, list[str]] = {}
    for decision in decisions_in_force(ws):
        globs = decision.values("affects")
        if not globs:
            continue
        matched = sorted(f for f in files or () if matches(f, globs))
        if matched or files is None:
            found[decision.id] = matched
    return found


def touched_files(ws: Workspace, task: WorkItem | None, named: list[str] | None) -> set[str] | None:
    """The files the sliced work touches: those named, and for a Task those the branch changed.

    Which Task of several a changed file belongs to is not recorded, so each
    Task sliced on the branch is given them all. A folder is named for the
    files in it.
    """
    files: set[str] = set()
    for name in named or ():
        rel = ws.cfg.rel(name)
        if (ws.cfg.root / rel).is_dir():
            inside = "" if rel == "." else rel + "/"
            files.update(f for f in repository_files(ws.cfg) if f.startswith(inside))
        else:
            files.add(rel)
    if task is None:
        return files
    from .gates import changed_files  # gates needs the graph; a term slice does not

    changed = changed_files(ws.cfg)
    return None if changed is None else files | changed


# --- building ------------------------------------------------------------------------


def build(
    ws: Workspace,
    *,
    task: str | None = None,
    terms: list[str] | None = None,
    context: str | None = None,
    depth: int = 1,
    files: list[str] | None = None,
) -> Slice:
    task_item: WorkItem | None = None
    requirements: list[WorkItem] = []
    if task:
        task_item = ws.by_id.get(task)
        if task_item is None or task_item.cls != "Task":
            raise SliceError(f"{task} is not a Task under work/")
        context = task_item.context
        requirements = [ws.by_id[r] for r in task_item.values("implements") if r in ws.by_id]
        names = [name for req in requirements for name in req.values("uses_terms")]
        title = f"{task_item.id} {task_item.meta.get('title', '')}".strip()
    elif terms:
        context = context or _context_of_terms(ws, terms)
        names = list(terms)
        title = ", ".join(terms)
    else:
        raise SliceError("a slice needs a task or at least one term")

    glossary = ws.glossary(context or "")
    if glossary is None:
        raise SliceError(f"'{context}' is not a bounded context in onto.toml")

    focus: list[Term] = []
    for name in dict.fromkeys(names):
        term = glossary.get(name)
        if term is None:
            if terms:  # asked for by name: an unknown name is the caller's mistake
                hint = ", ".join(glossary.suggest(name)) or "none close"
                raise SliceError(f"'{name}' is not a term of the {context} glossary ({hint})")
            continue  # a work item with a bad term: `onto validate` reports it
        focus.append(term)

    focus_names = {t.name for t in focus}
    neighbours: list[Term] = []
    if depth >= 1:
        for term in focus:
            for name in glossary.related(term.name):
                other = glossary.get(name)
                # Slots of a focus class are already listed inside the class.
                if (
                    other
                    and other.name not in focus_names
                    and other.kind != "slot"
                    and other not in neighbours
                ):
                    neighbours.append(other)

    relevant = focus_names | {t.parent for t in focus if t.kind == "value" and t.parent}
    current = {r.id for r in requirements}

    def about(item: WorkItem) -> bool:
        used = {t.name for n in item.values("uses_terms") if (t := glossary.get(n))}
        return bool(used & relevant)

    replaced = [
        ws.by_id[old]
        for req in requirements
        for old in req.values("replaces")
        if old in ws.by_id and old not in current
    ]
    # What this work replaces is on its way out, whatever its status says today.
    outgoing = current | {r.id for r in replaced}
    raised_from = {incident for req in requirements for incident in req.values("raised_from")}
    affecting = decisions_affecting(ws, touched_files(ws, task_item, files))
    decisions = [d for d in decisions_in_force(ws, glossary.name) if about(d)]
    decisions += [ws.by_id[d] for d in affecting if ws.by_id[d] not in decisions]

    return Slice(
        context=glossary.name,
        title=title,
        task=task_item,
        requirements=requirements,
        focus=focus,
        neighbours=neighbours,
        decisions=decisions,
        affecting=affecting,
        established=[
            r
            for r in ws.of_class("Requirement")
            if r.status == "done"
            and r.context == glossary.name
            and r.id not in outgoing
            and about(r)
        ],
        replaced=replaced,
        incidents=[
            i
            for i in ws.of_class("Incident")
            if i.status not in ("done", "superseded")
            and (i.id in raised_from or set(i.values("breaks")) & current)
        ],
        types_file=ws.cfg.rel(glossary.context.pydantic) if glossary.context.pydantic else None,
        depth=depth,
    )


def build_within_budget(ws: Workspace, budget: int = DEFAULT_BUDGET, **kwargs) -> tuple[Slice, str]:
    """Build a slice and render it, dropping the neighbours if it would not fit the budget."""
    built = build(ws, **kwargs)
    text = render_markdown(ws, built)
    if estimate_tokens(text) > budget and built.depth > 0:
        built = build(ws, **{**kwargs, "depth": 0})
        text = render_markdown(ws, built)
    return built, text


def _context_of_terms(ws: Workspace, terms: list[str]) -> str:
    holding = [name for name, g in ws.glossaries.items() if all(g.get(t) for t in terms)]
    if len(holding) == 1:
        return holding[0]
    if len(ws.glossaries) == 1:
        return next(iter(ws.glossaries))
    raise SliceError("say which bounded context the terms belong to with --context")


# --- rendering -----------------------------------------------------------------------


def _tags(term: Term) -> str:
    tags = [term.kind]
    if term.kind == "slot" and term.used_by:
        tags = [f"slot of {', '.join(term.used_by)}"]
    if term.abstract:
        tags.append("abstract")
    if term.classification != "internal":
        tags.append(term.classification)
    return ", ".join(tags)


def _attribute_line(attribute) -> str:
    parts = [attribute.range]
    if attribute.multivalued:
        parts.append("list")
    parts.append("required" if attribute.required else "optional")
    parts.extend(attribute.constraints)
    return f"- {attribute.name}: {', '.join(parts)}"


def _term_block(glossary: Glossary, term: Term) -> list[str]:
    if term.kind == "value":
        return [f"### {term.short_name} ({term.parent} value)", term.definition]
    lines = [f"### {term.name} ({_tags(term)})", term.definition]
    if term.kind == "class":
        lines += [_attribute_line(a) for a in term.attributes]
    elif term.kind == "slot":
        parts = [term.range or "string", *term.constraints]
        lines.append(f"- value: {', '.join(parts)}")
    elif term.kind == "enum":
        for value in term.values:
            lines.append(f"- {value}: {glossary.terms[f'{term.name}.{value}'].definition}")
    if term.denied_synonyms:
        lines.append(f"Never write: {', '.join(term.denied_synonyms)}")
    return lines


def _first_sentence(text: str) -> str:
    flat = " ".join(str(text).split())
    match = re.match(r"(.+?[.!?])(\s|$)", flat)
    return match.group(1) if match else flat


def _ears(requirement: WorkItem) -> str:
    return " ".join(str(requirement.meta.get("ears_text", "")).split())


def render_markdown(ws: Workspace, built: Slice) -> str:
    glossary = ws.glossaries[built.context]
    out = [
        f"# Ontology slice: {built.title} ({built.context})",
        "",
        "Use these terms, spelled exactly as written. If a concept you need is missing,",
        "stop and say so: never coin a name. `onto resolve <name>` looks one up.",
    ]
    if built.task or built.requirements:
        out += ["", "## Work"]
        if built.task:
            out.append(
                f"- {built.task.id} [{built.task.status}] {built.task.meta.get('title', '')}"
            )
        for req in built.requirements:
            risk = f", risk {req.meta['risk_tier']}" if req.meta.get("risk_tier") else ""
            out.append(f"- {req.id} [{req.status}{risk}] {_ears(req)}")
            for old in req.values("replaces"):
                earlier = ws.by_id.get(old)
                was = f": {_ears(earlier)}" if earlier else ""
                out.append(f"  - replaces {old}, which is no longer to be kept true{was}")
            for incident in req.values("raised_from"):
                out.append(f"  - raised from {incident}")
        for incident in built.incidents:
            broken = ", ".join(incident.values("breaks"))
            out.append(
                f"- {incident.id} [{incident.status}] {incident.meta.get('title', '')}"
                + (f" (breaks {broken})" if broken else "")
            )
    out += ["", "## Terms"]
    for term in built.focus:
        out += _term_block(glossary, term) + [""]
    if built.neighbours:
        out += ["## Related terms"]
        for term in built.neighbours:
            out += _term_block(glossary, term) + [""]
    if built.decisions:
        out += ["## Decisions in force"]
        for decision in built.decisions:
            rationale = _first_sentence(decision.meta.get("rationale", ""))
            line = f"- {decision.id} {decision.meta.get('title', '')}. {rationale}"
            if decision.id in built.affecting:
                on = built.affecting[decision.id] or decision.values("affects")
                line += f" Affects {', '.join(on)}."
            out.append(line)
        out.append("")
    if built.established:
        out += ["## Requirements already established on these terms (keep them true)"]
        for req in built.established:
            out.append(f"- {req.id} {_ears(req)}")
        out.append("")
    if built.types_file:
        types = [t.name for t in (*built.focus, *built.neighbours) if t.kind in ("class", "enum")]
        if types:
            out += [
                "## Types",
                f"Import {', '.join(dict.fromkeys(types))} from `{built.types_file}`.",
                "They are generated from the ontology: never redefine or edit them.",
                "",
            ]
    return "\n".join(out).rstrip() + "\n"


def render_json(ws: Workspace, built: Slice) -> str:
    def term(t: Term) -> dict:
        data = {
            "name": t.short_name,
            "kind": t.kind,
            "definition": t.definition,
            "classification": t.classification,
            "iri": t.iri,
        }
        if t.attributes:
            data["attributes"] = [
                {
                    "name": a.name,
                    "range": a.range,
                    "required": a.required,
                    "multivalued": a.multivalued,
                    "constraints": list(a.constraints),
                }
                for a in t.attributes
            ]
        if t.kind == "slot":
            data["range"] = t.range
            data["constraints"] = list(t.constraints)
        if t.values:
            data["values"] = list(t.values)
        if t.denied_synonyms:
            data["denied_synonyms"] = list(t.denied_synonyms)
        return data

    def item(i: WorkItem, *keys: str) -> dict:
        return {"id": i.id, "status": i.status, **{k: i.meta[k] for k in keys if k in i.meta}}

    return json.dumps(
        {
            "context": built.context,
            "task": item(built.task, "title") if built.task else None,
            "requirements": [
                item(r, "ears_text", "risk_tier", "replaces", "raised_from")
                for r in built.requirements
            ],
            "replaced_requirements": [item(r, "ears_text") for r in built.replaced],
            "incidents": [item(i, "title", "observed_on", "breaks") for i in built.incidents],
            "terms": [term(t) for t in built.focus],
            "related_terms": [term(t) for t in built.neighbours],
            "decisions_in_force": [
                item(d, "title", "rationale", "affects")
                | ({"affected_files": built.affecting[d.id]} if d.id in built.affecting else {})
                for d in built.decisions
            ],
            "established_requirements": [item(r, "ears_text") for r in built.established],
            "types_file": built.types_file,
        },
        indent=2,
    )


def render_overview(ws: Workspace, context: str | None = None) -> str:
    """The table of contents: what exists, in a few lines per context, and where to go next."""
    names = [context] if context else list(ws.glossaries)
    out = ["# Ontology overview", ""]
    for name in names:
        glossary = ws.glossary(name)
        if glossary is None:
            raise SliceError(f"'{name}' is not a bounded context in onto.toml")
        terms = list(glossary.terms.values())
        counts = {k: sum(1 for t in terms if t.kind == k) for k in ("class", "slot", "enum")}
        out += [
            f"## {name}: {glossary.view.schema.title or name}",
            f"Source: {ws.cfg.rel(glossary.context.schema)} "
            f"({counts['class']} classes, {counts['slot']} slots, {counts['enum']} enums)",
            f"Governs: {', '.join(glossary.context.paths) or '-'}",
            "",
        ]
        for term in terms:
            if term.kind == "class":
                out.append(f"- {term.name}: {_first_sentence(term.definition)}")
        enums = [f"{t.name} ({' | '.join(t.values)})" for t in terms if t.kind == "enum"]
        if enums:
            out += ["", "Enums: " + "; ".join(enums)]
        denied = [f"{s} -> {t.name}" for s, t in glossary.denied_entries()]
        if denied:
            out += ["Never write: " + "; ".join(denied)]
        out.append("")
    statuses: dict[str, int] = {}
    for item in ws.items:
        if item.cls:
            statuses[item.cls] = statuses.get(item.cls, 0) + 1
    out += [
        "## Work items",
        ", ".join(f"{count} {cls}" for cls, count in sorted(statuses.items())) or "none",
    ]
    requests = [r for r in ws.of_class("OntologyChangeRequest") if r.status != "done"]
    if requests:
        out.append(
            "Open ontology change requests: "
            + "; ".join(f"{r.id} [{r.status}] {r.meta.get('proposed_term', '')}" for r in requests)
        )
    out += [
        "",
        "Next: `onto resolve <name>` to look a name up, `onto slice --term <Term>` for a",
        "term and its neighbours, `onto slice --task <TASK-id>` for everything a task needs.",
    ]
    return "\n".join(out) + "\n"
