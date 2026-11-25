"""Graph-level gates: SHACL over the traceability graph.

Two sets of shapes run together:

* the shapes generated from workflow.yaml, which check every node against its
  class (required links, link targets of the right class, permitted values);
* the hand-written shapes in ontology/shapes/gates.shacl.ttl, which express the
  rules that span artefacts, such as "a finished requirement has a test with
  passing evidence".
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from rdflib import RDF, Graph, Namespace

from . import namespaces
from .config import Config
from .failures import missing
from .graph import WorkGraph
from .report import ERROR, WARNING, Violation
from .workspace import Workspace

SH = Namespace("http://www.w3.org/ns/shacl#")
_IRI = re.compile(r"(?:https?://|urn:)[^\s,;\"'<>()]*[^\s,;\"'<>().]")


def shapes_graph(cfg: Config) -> Graph:
    shapes = Graph()
    if not cfg.workflow_shacl.is_file():
        raise FileNotFoundError(f"{cfg.rel(cfg.workflow_shacl)} is missing: run `onto gen`")
    for path in cfg.gate_shapes:
        if not path.is_file():
            raise missing(
                "the hand-written graph gates, which `onto gen` does not produce",
                cfg.rel(path),
                "run `onto init` to scaffold it, or take it out of `gates` in onto.toml",
            )
    for path in (cfg.workflow_shacl, *cfg.gate_shapes):
        shapes.parse(path, format="turtle")
    return shapes


def run_shacl(ws: Workspace, graph: WorkGraph) -> list[Violation]:
    """Validate the graph. Each result becomes one violation on the work item it concerns.

    A gate file or competency question written against another namespace than
    the workflow ontology's is reported first: its rules would pass in silence.
    """
    import pyshacl

    shapes = shapes_graph(ws.cfg)
    _, report, _ = pyshacl.validate(graph.rdf, shacl_graph=shapes, inference=None)

    slot_names = _slot_names(ws)
    seen: set[tuple] = set()
    problems: list[Violation] = namespaces.problems(ws)
    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = report.value(result, SH.focusNode)
        path = report.value(result, SH.resultPath)
        value = report.value(result, SH.value)
        component = report.value(result, SH.sourceConstraintComponent)
        key = (focus, path, component, value)
        if key in seen:  # the same slot is checked by the shape of every superclass
            continue
        seen.add(key)

        subject = graph.short(str(focus))
        item = ws.by_id.get(subject)
        slot = slot_names.get(str(path)) if path is not None else None
        source_shape = report.value(result, SH.sourceShape)
        sparql = component == SH.SPARQLConstraintComponent
        severity = report.value(result, SH.resultSeverity)
        problems.append(
            Violation(
                rule=f"gate:{_local(source_shape)}" if sparql else "shape",
                severity=ERROR if severity == SH.Violation else WARNING,
                message=_message(graph, report, result, slot, value, component),
                file=item.rel if item else None,
                line=item.line_of(slot) if item and slot else None,
                subject=subject,
                found=graph.short(str(value)) if value is not None and not sparql else None,
            )
        )
    return problems


def _local(iri) -> str:
    return str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _slot_names(ws: Workspace) -> dict[str, str]:
    """Slot IRI -> slot name, for pointing a result at the frontmatter key it is about."""
    names: dict[str, str] = {}
    for cls in ws.schema.view.all_classes():
        for slot in ws.schema.slots(cls):
            names[slot.iri] = slot.name
    return names


def _message(graph: WorkGraph, report: Graph, result, slot, value, component) -> str:
    written = graph.short(str(value)) if value is not None else None
    local = str(component).rsplit("#", 1)[-1]
    if local == "SPARQLConstraintComponent":
        message = str(report.value(result, SH.resultMessage) or "gate failed")
        return _IRI.sub(lambda m: graph.short(m.group(0)), message)
    if local == "ClassConstraintComponent":
        return f"{slot} points at {written}, which is not what {slot} may link to"
    if local == "MinCountConstraintComponent":
        return f"{slot} is required"
    if local == "MaxCountConstraintComponent":
        return f"{slot} may have only one value"
    if local == "InConstraintComponent":
        return f"{slot} is '{written}', which is not one of its permitted values"
    if local == "PatternConstraintComponent":
        return f"{slot} is '{written}', which does not have the required form"
    return f"{slot or 'node'}: {report.value(result, SH.resultMessage) or local}"


# --- traceability matrix ---------------------------------------------------------

TRACE_QUERY = """
PREFIX wf: <{wf}>
SELECT ?req ?title ?status ?risk ?context ?task ?test ?result WHERE {{
  ?req a wf:Requirement ; wf:title ?title ; wf:status ?status ; wf:bounded_context ?context .
  OPTIONAL {{ ?req wf:risk_tier ?risk }}
  OPTIONAL {{ ?task wf:implements ?req }}
  OPTIONAL {{
    ?test wf:verifies ?req .
    OPTIONAL {{ ?evidence wf:of_test ?test ; wf:result ?result }}
  }}
}}
"""

AGREED = ("ready", "in_progress", "done")  # the statuses coverage is measured over


@dataclass
class TraceRow:
    requirement: str
    title: str
    status: str
    context: str
    risk: str | None = None
    tasks: set[str] = field(default_factory=set)
    tests: dict[str, str | None] = field(default_factory=dict)  # test -> pass | fail | None

    @property
    def verdict(self) -> str:
        if not self.tests:
            return "untested"
        results = set(self.tests.values())
        if "fail" in results:
            return "failing"
        if None in results:
            return "no evidence"
        return "verified"


def traceability(graph: WorkGraph) -> list[TraceRow]:
    """One row per requirement: who implements it, what verifies it, what the evidence says."""
    rows: dict[str, TraceRow] = {}
    for found in graph.select(TRACE_QUERY.format(wf=graph.ws.schema.wf_ns)):
        row = rows.setdefault(
            found["req"],
            TraceRow(
                found["req"], found["title"], found["status"], found["context"], found.get("risk")
            ),
        )
        if "task" in found:
            row.tasks.add(found["task"])
        if "test" in found:
            previous = row.tests.get(found["test"])
            result = found.get("result")
            row.tests[found["test"]] = (
                "fail" if "fail" in (previous, result) else result or previous
            )
    return sorted(rows.values(), key=lambda r: r.requirement)


def coverage(rows: list[TraceRow]) -> dict[str, int]:
    agreed = [r for r in rows if r.status in AGREED]
    return {
        "requirements": len(agreed),
        "with_test": sum(1 for r in agreed if r.tests),
        "verified": sum(1 for r in agreed if r.verdict == "verified"),
    }


# --- scope -----------------------------------------------------------------------


def changed_files(cfg: Config) -> set[str] | None:
    """Files that differ from the base branch, plus untracked ones. None outside a git repo."""

    def git(*args: str) -> str | None:
        done = subprocess.run(
            ["git", "-C", str(cfg.root), *args], capture_output=True, text=True, check=False
        )
        return done.stdout if done.returncode == 0 else None

    if git("rev-parse", "--is-inside-work-tree") is None:
        return None
    base = "HEAD"
    for ref in dict.fromkeys((cfg.base_ref, "main", "master")):
        merge_base = git("merge-base", "HEAD", ref)
        if merge_base:
            base = merge_base.strip()
            break
    changed = git("diff", "--name-only", "--relative", base)
    untracked = git("ls-files", "--others", "--exclude-standard")
    if changed is None:  # a repository without commits yet: everything is new
        changed = git("ls-files", "--cached") or ""
    return {line for line in (changed + (untracked or "")).splitlines() if line}


def branch_scope(ws: Workspace) -> set[str] | None:
    """The work items the current branch touches, with what they trace to. None means all.

    A branch is answerable for the items it changed and, when it changed an
    app's code, for every finished requirement of that app's bounded context:
    they have to hold after the change as they did before it.
    """
    changed = changed_files(ws.cfg)
    if changed is None:
        return None
    ids: set[str] = set()
    work_prefix = ws.cfg.rel(ws.cfg.work_dir) + "/"
    tests_by_file: dict[str, list[str]] = {}
    for test in ws.of_class("Test"):
        for path in test.values("path"):
            tests_by_file.setdefault(path.split("::", 1)[0], []).append(test.id)

    for rel in changed:
        stem = rel.rsplit("/", 1)[-1].removesuffix(".md")
        if rel.startswith(work_prefix) and stem in ws.by_id:
            ids.add(stem)
        ids.update(tests_by_file.get(rel, ()))
        context = ws.cfg.context_of(rel)
        if context is not None:
            ids.update(
                item.id
                for item in ws.of_class("Requirement")
                if item.context == context.name and item.status == "done"
            )
    return _closure(ws, ids)


def _closure(ws: Workspace, ids: set[str]) -> set[str]:
    """Follow the trace links both ways until nothing new is reached."""
    links = {"Task": "implements", "Test": "verifies", "Change": "resolves", "Evidence": "of_test"}
    scope = set(ids)
    while True:
        grown = set(scope)
        for item in ws.items:
            slot = links.get(item.cls or "")
            if slot is None:
                continue
            targets = set(item.values(slot))
            if item.id in scope:
                grown |= targets
            elif item.cls != "Change" and targets & scope:
                grown.add(item.id)
        if grown == scope:
            return scope
        scope = grown


def in_scope(problems: list[Violation], scope: set[str] | None) -> list[Violation]:
    """The problems a scope answers for. One that is about no work item concerns every scope."""
    if scope is None:
        return problems
    return [p for p in problems if p.subject is None or p.subject in scope]
