"""One JSON document for user interfaces: where each task stands, the ontology, the plan.

`onto view` exists so that a display never has to work anything out. The
Claude mods under mods/ draw this document as it is; all the judgement about
which stage a task is at lives here, where it is tested.

A task moves through seven stages. Each stage is guarded by one command, and
its state is read from the repository, never from what anyone says:

    intake      the Task implements Requirements that are agreed        onto new
    vocabulary  its work items validate against the glossary             onto validate
    design      a Decision is in force on the terms, or one was logged   onto slice
    implement   the domain layer uses only glossary vocabulary           onto check-terms
    verify      every Requirement has a Test with passing Evidence       onto evidence collect
    trace       the Task and its Requirements are done and gates hold    onto trace
    ship        a Change resolves the Task                               onto prov emit

What happens after ship has no stage of its own. An Incident comes back in at
intake, as a Requirement it breaks or one raised from it, and a changed rule
comes back as a Requirement that replaces the old one. The plan lists both.
"""

from __future__ import annotations

from . import gates, prov, terms
from .graph import build_graph
from .report import Violation, errors
from .slicing import current_task, decisions_in_force
from .workitems import validate
from .workspace import WorkItem, Workspace

STAGES = (
    ("intake", "Intake", "onto new"),
    ("vocabulary", "Vocabulary", "onto validate"),
    ("design", "Design", "onto slice"),
    ("implement", "Implement", "onto check-terms"),
    ("verify", "Verify", "onto evidence collect"),
    ("trace", "Trace", "onto trace"),
    ("ship", "Ship", "onto prov emit"),
)
DONE, CURRENT, BLOCKED, TODO = "done", "current", "blocked", "todo"
SETTLED = ("done", "superseded")  # the statuses of a work item nobody is still to act on


def build(ws: Workspace) -> dict:
    graph = build_graph(ws)
    file_problems = validate(ws)
    gate_problems = gates.run_shacl(ws, graph)
    rows = {row.requirement: row for row in gates.traceability(graph)}
    term_problems = _term_problems(ws)
    in_force = decisions_in_force(ws)
    task_in_hand = current_task(ws)

    tasks = [
        _task(ws, task, rows, file_problems, gate_problems, term_problems, in_force)
        for task in ws.of_class("Task")
    ]
    replaced_by: dict[str, list[str]] = {}
    for requirement in ws.of_class("Requirement"):
        for earlier in requirement.values("replaces"):
            replaced_by.setdefault(earlier, []).append(requirement.id)
    return {
        "task_in_hand": task_in_hand.id if task_in_hand else None,
        "stages": [{"key": key, "label": label, "gate": gate} for key, label, gate in STAGES],
        "tasks": tasks,
        "trace": {
            "coverage": gates.coverage(list(rows.values())),
            "requirements": [
                {
                    "id": row.requirement,
                    "title": row.title,
                    "status": row.status,
                    "risk_tier": row.risk,
                    "context": row.context,
                    "tasks": sorted(row.tasks),
                    "tests": row.tests,
                    "verdict": row.verdict,
                    "replaces": _one(ws, row.requirement, "replaces"),
                    "replaced_by": replaced_by.get(row.requirement, []),
                    "raised_from": _one(ws, row.requirement, "raised_from"),
                }
                for row in rows.values()
            ],
            "violations": [p.to_dict() for p in (*file_problems, *gate_problems) if p.blocking],
        },
        "ontology": _ontology(ws),
        "plan": _plan(ws, tasks, in_force, replaced_by),
    }


def _one(ws: Workspace, identifier: str, slot: str) -> str | None:
    return next(iter(ws.by_id[identifier].values(slot)), None)


# --- stages ------------------------------------------------------------------------


def _term_problems(ws: Workspace) -> dict[str, list[Violation]]:
    """Blocking vocabulary problems in each context's domain layer."""
    from .cli import _domain_files  # the one place that knows how to list them

    found: dict[str, list[Violation]] = {name: [] for name in ws.cfg.contexts}
    for rel in _domain_files(ws):
        context = ws.cfg.domain_context_of(rel)
        try:
            text = (ws.cfg.root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if context is not None:
            found[context.name].extend(errors(terms.check_file(ws, rel, text)))
    return found


def _task(ws, task: WorkItem, rows, file_problems, gate_problems, term_problems, in_force) -> dict:
    glossary = ws.glossary(task.context)
    requirements = [ws.by_id[r] for r in task.values("implements") if r in ws.by_id]
    own = {task.id, *(r.id for r in requirements)}
    tests = {t.id for t in ws.of_class("Test") if set(t.values("verifies")) & own}
    changes = [c.id for c in ws.of_class("Change") if task.id in c.values("resolves")]
    logged = _logged_phases(ws, task.id)

    def terms_of(item: WorkItem) -> set[str]:
        return {t.name for n in item.values("uses_terms") if glossary and (t := glossary.get(n))}

    used = set().union(*(terms_of(r) for r in requirements)) if requirements else set()
    decisions = [d.id for d in in_force if d.context == task.context and terms_of(d) & used]

    file_errors = [p for p in file_problems if p.blocking and p.subject in own]
    vocabulary_errors = term_problems.get(task.context, [])
    gate_errors = [p for p in gate_problems if p.blocking and p.subject in own | tests]
    # A superseded Requirement is no longer a claim, so nothing is left to verify on it.
    live = [r for r in requirements if r.status != "superseded"]
    trace_rows = [rows[r.id] for r in live if r.id in rows]
    unverified = [row for row in trace_rows if row.verdict != "verified"]
    failing = [row.requirement for row in trace_rows if row.verdict == "failing"]
    untested = [row.requirement for row in trace_rows if not row.tests]
    open_claims = [i.id for i in (task, *requirements) if i.status not in SETTLED]

    def first(problems: list[Violation]) -> str:
        return f"{len(problems)} problem(s): {problems[0].message}" if problems else ""

    # (is the stage complete, is it blocked by its gate, what to say about it)
    checks = {
        "intake": (
            bool(requirements) and all(r.status != "draft" for r in requirements),
            False,
            f"implements {', '.join(r.id for r in requirements)}"
            if requirements
            else "implements no Requirement yet",
        ),
        "vocabulary": (
            not file_errors,
            bool(file_errors),
            first(file_errors) or "work items validate against the glossary",
        ),
        "design": (
            bool(decisions) or "design" in logged or task.status in SETTLED,
            False,
            f"in force: {', '.join(decisions)}" if decisions else "no Decision on these terms yet",
        ),
        "implement": (
            not vocabulary_errors and (not untested or "implement" in logged),
            bool(vocabulary_errors),
            first(vocabulary_errors)
            or (
                "domain layer uses glossary vocabulary"
                if not untested
                else f"no Test yet for {', '.join(untested)}"
            ),
        ),
        "verify": (
            (bool(trace_rows) or bool(requirements) and not live) and not unverified,
            bool(failing),
            f"failing: {', '.join(failing)}"
            if failing
            else f"{len(trace_rows) - len(unverified)} of {len(trace_rows)} verified"
            if live
            else "every Requirement it implements is superseded",
        ),
        "trace": (
            not open_claims and not gate_errors,
            bool(gate_errors),
            first(gate_errors)
            or (f"not yet done: {', '.join(open_claims)}" if open_claims else "the gate holds"),
        ),
        "ship": (
            bool(changes),
            False,
            f"resolved by {', '.join(changes)}" if changes else "no Change record yet",
        ),
    }

    stages, reached = [], True
    for key, label, gate in STAGES:
        complete, blocked, detail = checks[key]
        if reached and complete:
            state = DONE
        elif reached:
            state, reached = (BLOCKED if blocked else CURRENT), False
        else:
            state = TODO
        stages.append({"key": key, "label": label, "gate": gate, "state": state, "detail": detail})

    at = next((s for s in stages if s["state"] in (CURRENT, BLOCKED)), None)
    return {
        "id": task.id,
        "title": str(task.meta.get("title", "")),
        "status": task.status,
        "context": task.context,
        "implements": [r.id for r in requirements],
        "blocked_by": task.values("blocked_by"),
        "stage": at["key"] if at else "complete",
        "blocked": bool(at and at["state"] == BLOCKED),
        "stages": stages,
    }


def _logged_phases(ws: Workspace, subject: str) -> set[str]:
    path = prov.log_path(ws.cfg, subject)
    return {row.get("phase", "") for row in prov.read_log(path)} if path.is_file() else set()


# --- ontology ------------------------------------------------------------------------


def _ontology(ws: Workspace) -> dict:
    view = ws.schema.view
    workflow = []
    for name, cls in view.all_classes(imports=False).items():
        if cls.mixin:
            continue
        links = [
            {"slot": slot.name, "to": slot.range, "many": slot.multivalued}
            for slot in ws.schema.slots(name)
            if slot.kind in ("record", "term") and slot.name != "id"
        ]
        workflow.append(
            {
                "name": name,
                "abstract": bool(cls.abstract),
                "parent": cls.is_a,
                "definition": " ".join((cls.description or "").split()),
                "links": links,
            }
        )

    contexts = []
    for glossary in ws.glossaries.values():
        all_terms = list(glossary.terms.values())
        contexts.append(
            {
                "name": glossary.name,
                "title": str(glossary.view.schema.title or glossary.name),
                "source": ws.cfg.rel(glossary.context.schema),
                "governs": list(glossary.context.paths),
                "classes": [
                    {
                        "name": t.name,
                        "definition": t.definition,
                        "classification": t.classification,
                        "abstract": t.abstract,
                        "parent": t.parent,
                        "attributes": [
                            {
                                "name": a.name,
                                "range": a.range,
                                "required": a.required,
                                "many": a.multivalued,
                                "constraints": list(a.constraints),
                            }
                            for a in t.attributes
                        ],
                        "aliases": list(t.aliases),
                        "denied_synonyms": list(t.denied_synonyms),
                    }
                    for t in all_terms
                    if t.kind == "class"
                ],
                "enums": [
                    {
                        "name": t.name,
                        "definition": t.definition,
                        "values": [
                            {"name": v, "definition": glossary.terms[f"{t.name}.{v}"].definition}
                            for v in t.values
                        ],
                    }
                    for t in all_terms
                    if t.kind == "enum"
                ],
                "denied": [{"synonym": s, "use": t.name} for s, t in glossary.denied_entries()],
                "terms": len(all_terms),
            }
        )
    return {"workflow": workflow, "contexts": contexts}


# --- plan ----------------------------------------------------------------------------


def _plan(
    ws: Workspace, tasks: list[dict], in_force: list[WorkItem], replaced_by: dict[str, list[str]]
) -> dict:
    superseded_by = {
        target: d.id
        for d in ws.of_class("Decision")
        if d.status in ("done", "superseded")
        for target in d.values("supersedes")
    }
    requirements = ws.of_class("Requirement")
    return {
        "order": _order(tasks),
        "requirements_by_status": {
            status: [r.id for r in ws.of_class("Requirement") if r.status == status]
            for status in ws.schema.enum_values("StatusEnum")
        },
        "decisions_in_force": [
            {"id": d.id, "title": str(d.meta.get("title", "")), "terms": d.values("uses_terms")}
            for d in in_force
        ],
        "superseded_decisions": [
            {
                "id": d.id,
                "title": str(d.meta.get("title", "")),
                "superseded_by": superseded_by.get(d.id),
            }
            for d in ws.of_class("Decision")
            if d.status == "superseded"
        ],
        "open_change_requests": [
            {
                "id": o.id,
                "status": o.status,
                "term": str(o.meta.get("proposed_term", "")),
                "title": str(o.meta.get("title", "")),
            }
            for o in ws.of_class("OntologyChangeRequest")
            if o.status != "done"
        ],
        "superseded_requirements": [
            {
                "id": r.id,
                "title": str(r.meta.get("title", "")),
                "replaced_by": replaced_by.get(r.id, []),
            }
            for r in requirements
            if r.status == "superseded"
        ],
        "open_incidents": [_incident(ws, i, requirements) for i in _open_incidents(ws)],
    }


def _open_incidents(ws: Workspace) -> list[WorkItem]:
    # Only `done` closes an Incident, since only then does the gate ask what fixed it.
    return [i for i in ws.of_class("Incident") if i.status != "done"]


def _incident(ws: Workspace, incident: WorkItem, requirements: list[WorkItem]) -> dict:
    """An Incident with the Requirements that close it, as gate:ClosedIncidentIsFixed reads them."""
    breaks = incident.values("breaks")
    raised = [r.id for r in requirements if incident.id in r.values("raised_from")]
    return {
        "id": incident.id,
        "title": str(incident.meta.get("title", "")),
        "status": incident.status,
        "context": incident.context,
        "observed_on": str(incident.meta.get("observed_on", "")),
        "breaks": breaks,
        "raised": raised,
        "waiting_on": [
            r for r in (*breaks, *raised) if r in ws.by_id and ws.by_id[r].status not in SETTLED
        ],
    }


def _order(tasks: list[dict]) -> list[str]:
    """Open tasks in an order that respects blocked_by: what can start now comes first."""
    remaining = {t["id"]: set(t["blocked_by"]) for t in tasks if t["status"] not in SETTLED}
    done = {t["id"] for t in tasks if t["status"] in SETTLED}
    order: list[str] = []
    while remaining:
        ready = sorted(t for t, blockers in remaining.items() if blockers <= done | set(order))
        if not ready:  # a cycle, or a blocker that does not exist: list the rest as they are
            order.extend(sorted(remaining))
            break
        order.extend(ready)
        for task in ready:
            del remaining[task]
    return order


# --- text ----------------------------------------------------------------------------

MARK = {DONE: "[x]", CURRENT: "[>]", BLOCKED: "[!]", TODO: "[ ]"}


def render_text(view: dict) -> str:
    lines = []
    for task in view["tasks"]:
        hand = "  <- in hand" if task["id"] == view["task_in_hand"] else ""
        lines.append(f"{task['id']} [{task['status']}] {task['title']}{hand}")
        lines.append("  " + "  ".join(f"{MARK[s['state']]} {s['key']}" for s in task["stages"]))
        for stage in task["stages"]:
            if stage["state"] in (CURRENT, BLOCKED):
                lines.append(f"      {stage['key']}: {stage['detail']}  (gate: {stage['gate']})")
        lines.append("")
    for requirement in view["trace"]["requirements"]:
        links = [
            f"replaces {requirement['replaces']}" if requirement["replaces"] else "",
            f"raised from {requirement['raised_from']}" if requirement["raised_from"] else "",
        ]
        if any(links):
            lines.append(
                f"{requirement['id']} [{requirement['status']}] {', '.join(filter(None, links))}"
            )
    for incident in view["plan"]["open_incidents"]:
        named = [*incident["breaks"], *incident["raised"]]
        waits = (
            f"waiting on {', '.join(incident['waiting_on'])}"
            if incident["waiting_on"]
            else f"names {', '.join(named)}, none of them still open"
            if named
            else "names no Requirement yet"
        )
        lines.append(f"{incident['id']} [{incident['status']}] {incident['title']}: {waits}")
    if lines and lines[-1]:
        lines.append("")
    cover = view["trace"]["coverage"]
    lines.append(
        f"{cover['verified']} of {cover['requirements']} agreed requirement(s) verified, "
        f"{len(view['trace']['violations'])} gate error(s)"
    )
    return "\n".join(lines) + "\n"
