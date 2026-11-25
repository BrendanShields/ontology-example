"""Provenance: a PROV-O bundle per Change, and the decision log it draws on.

A bundle answers "what did this change rest on?" in a form an auditor's tools
can read: the Change (a prov:Activity), the agent that made it, the
requirements and decisions it used, the tests that verify those requirements
and the evidence of their last run. Where a requirement came from is in it too:
the earlier Requirements it replaces, back to the first, and the Incidents it
answers. Those are carried as they stand, and the Change is not said to have
used them.

Most of it is a plain extract of the traceability graph, which already carries
PROV types and properties through workflow.yaml. Three statements are added
here because PROV wants them said in its own words:

    Change    prov:used               each Requirement it serves, and each Decision in force
                                      on the terms of those Requirements
    Change    prov:wasAssociatedWith  the agent named in generated_by_agent
    Evidence  prov:wasDerivedFrom     the Test it is evidence of

A bundle also carries the glossary terms its members use, so that it can be read
years later without the repository: the definition and the classification of
each term are the ones that were in force when the bundle was written.
"""

from __future__ import annotations

import csv
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

from .config import Config
from .graph import PROV as PROV_NS
from .graph import WorkGraph
from .schema import TERM_CLASS
from .slicing import decisions_in_force
from .workspace import WorkItem, Workspace

PROV = Namespace(PROV_NS)
LOG_COLUMNS = ("ts", "phase", "decision", "why", "evidence", "result")  # pstack's decision log
LOG_CLASS = "LoggedDecision"


# --- decision log ------------------------------------------------------------------


def log_path(cfg: Config, subject: str) -> Path:
    return cfg.audit_dir / f"{subject}.tsv"


def append_decision(
    cfg: Config,
    subject: str,
    *,
    phase: str,
    decision: str,
    why: str,
    evidence: str = "",
    result: str = "",
) -> Path:
    """Add one row to .audit/<subject>.tsv. Tabs and newlines in values become spaces."""
    path = log_path(cfg, subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    row = [now, phase, decision, why, evidence, result]
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(
            handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, escapechar="\\"
        )
        if new:
            writer.writerow(LOG_COLUMNS)
        writer.writerow([re.sub(r"[\t\r\n]+", " ", str(value)).strip() for value in row])
    return path


def read_log(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        return [dict(row) for row in reader if row.get("decision")]


# --- bundles -----------------------------------------------------------------------


def served(ws: Workspace, change: WorkItem) -> list[WorkItem]:
    """The Requirements a Change serves: those its Tasks implement."""
    tasks = [ws.by_id[t] for t in change.values("resolves") if t in ws.by_id]
    ids = {r for task in tasks for r in task.values("implements") if r in ws.by_id}
    return [ws.by_id[r] for r in sorted(ids)]


def origins(ws: Workspace, requirements: list[WorkItem]) -> list[WorkItem]:
    """Where Requirements came from: what each replaces, all the way back, and its Incidents."""
    earlier: dict[str, WorkItem] = {}
    queue = list(requirements)
    while queue:
        for target in queue.pop().values("replaces"):
            item = ws.by_id.get(target)
            if item is not None and item.cls == "Requirement" and target not in earlier:
                earlier[target] = item
                queue.append(item)
    ids = {r.id for r in requirements}
    raised_from = {target for r in requirements for target in r.values("raised_from")}
    incidents = [
        i for i in ws.of_class("Incident") if i.id in raised_from or set(i.values("breaks")) & ids
    ]
    return [*(earlier[key] for key in sorted(earlier) if key not in ids), *incidents]


def change_closure(ws: Workspace, change: WorkItem) -> list[WorkItem]:
    """Everything a Change traces to: tasks, requirements, tests, evidence, decisions, origins."""
    glossary = ws.glossary(change.context)
    tasks = [ws.by_id[t] for t in change.values("resolves") if t in ws.by_id]
    requirements = served(ws, change)
    requirement_ids = {r.id for r in requirements}
    tests = [t for t in ws.of_class("Test") if set(t.values("verifies")) & requirement_ids]
    test_ids = {t.id for t in tests}
    evidence = [e for e in ws.of_class("Evidence") if set(e.values("of_test")) & test_ids]

    def terms(item: WorkItem) -> set[str]:
        return {t.name for n in item.values("uses_terms") if glossary and (t := glossary.get(n))}

    used = set().union(*(terms(r) for r in requirements)) if requirements else set()
    decisions = [d for d in decisions_in_force(ws, change.context) if terms(d) & used]
    return [
        change,
        *tasks,
        *requirements,
        *tests,
        *evidence,
        *decisions,
        *origins(ws, requirements),
    ]


def bundle(ws: Workspace, graph: WorkGraph, change: WorkItem, log_dir: Path | None = None) -> Graph:
    out = Graph()
    for prefix, namespace in graph.prefixes.items():
        out.bind(prefix, namespace)
    out.bind("prov", PROV)

    work = ws.schema.work_ns
    node = URIRef(work + change.id)
    members = change_closure(ws, change)
    term_type = URIRef(ws.schema.class_iri(TERM_CLASS))
    for item in members:
        for triple in graph.rdf.triples((URIRef(work + item.id), None, None)):
            out.add(triple)
            # A bundle stands on its own: it carries each glossary term its
            # members use, with the definition and classification then in force.
            if (triple[2], RDF.type, term_type) in graph.rdf:
                for term_triple in graph.rdf.triples((triple[2], None, None)):
                    out.add(term_triple)

    used = {r.id for r in served(ws, change)}
    for item in members:
        if item.cls == "Decision" or item.id in used:
            out.add((node, PROV.used, URIRef(work + item.id)))
        elif item.cls == "Evidence":
            for test in item.values("of_test"):
                out.add((URIRef(work + item.id), PROV.wasDerivedFrom, URIRef(work + test)))

    agent_name = change.meta.get("generated_by_agent")
    if agent_name:
        agent = URIRef(work + "agent/" + quote(str(agent_name), safe=""))
        out.add((agent, RDF.type, PROV.SoftwareAgent))
        out.add((agent, RDFS.label, Literal(str(agent_name))))
        out.add((node, PROV.wasAssociatedWith, agent))

    if log_dir is not None and log_dir.is_dir():
        subjects = [change.id, *change.values("resolves")]
        for subject in subjects:
            path = log_dir / f"{subject}.tsv"
            if path.is_file():
                _add_log(ws, out, subject, read_log(path))
    return out


def _add_log(ws: Workspace, out: Graph, subject: str, rows: list[dict[str, str]]) -> None:
    """Each log row becomes a wf:LoggedDecision, using the slots workflow.yaml declares for it."""
    schema = ws.schema
    work = schema.work_ns
    predicate = {slot.name: URIRef(slot.iri) for slot in schema.slots(LOG_CLASS)}
    column_to_slot = {
        "phase": "phase",
        "decision": "decision",
        "why": "rationale",
        "evidence": "basis",
        "result": "outcome",
    }
    for number, row in enumerate(rows, start=1):
        node = URIRef(f"{work}log/{quote(subject, safe='')}/{number}")
        for class_iri in schema.class_iris(LOG_CLASS):
            out.add((node, RDF.type, URIRef(class_iri)))
        if subject in ws.by_id:
            out.add((node, predicate["concerns"], URIRef(work + subject)))
        if row.get("ts"):
            out.add((node, predicate["recorded_at"], Literal(row["ts"], datatype=XSD.dateTime)))
        for column, slot in column_to_slot.items():
            if row.get(column):
                out.add((node, predicate[slot], Literal(row[column])))


def emit(
    ws: Workspace,
    graph: WorkGraph,
    out_dir: Path,
    *,
    changes: list[WorkItem],
    log_dir: Path | None = None,
) -> list[Path]:
    """Write prov/<CHG-id>.ttl for each Change. Returns the files written."""
    written: list[Path] = []
    for change in changes:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{change.id}.ttl"
        header = f"# PROV-O bundle of {change.id}, generated by `onto prov emit`. Do not edit.\n"
        target.write_text(
            header + bundle(ws, graph, change, log_dir).serialize(format="turtle"), encoding="utf-8"
        )
        written.append(target)
    return written
