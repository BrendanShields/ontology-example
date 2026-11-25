"""The hand-written gates and questions must speak the workflow ontology's namespaces.

The gate shapes and the competency questions repeat the namespaces of
workflow.yaml as literal text. If one of them differs, its rules match nothing
in the graph and report no violation, so a gate that looks green checks
nothing. This module reads what each file declares with the parser that will
run it, so the spelling of a declaration does not matter, and checks each kind
of declaration on its own: the `@prefix` lines of a shapes file give its shapes
their names, and its `sh:declare` entries give its SPARQL constraints theirs.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from rdflib import Graph
from rdflib.namespace import SH
from rdflib.plugins.sparql.parser import parseQuery

from .report import ERROR, Violation
from .workspace import Workspace

_NOT_OURS = ("linkml",)
BINDING, DECLARE, QUERY = "@prefix", "sh:declare", "PREFIX"

Declared = list[tuple[str, str]]  # (prefix, namespace)


def shapes_declarations(text: str) -> dict[str, Declared]:
    """What a Turtle shapes file declares, by kind. No `sh:declare` kind without SPARQL in it."""
    graph = Graph(bind_namespaces="none").parse(data=text, format="turtle")
    found = {BINDING: [(prefix, str(namespace)) for prefix, namespace in graph.namespaces()]}
    entries = [
        (str(graph.value(entry, SH.prefix) or ""), str(graph.value(entry, SH.namespace) or ""))
        for entry in set(graph.objects(None, SH.declare))
    ]
    if entries or (None, SH.select, None) in graph or (None, SH.ask, None) in graph:
        found[DECLARE] = sorted(entries)
    return found


def query_declarations(text: str) -> dict[str, Declared]:
    prologue = parseQuery(text)[0]
    return {QUERY: [(d.get("prefix") or "", str(d.iri)) for d in prologue if "iri" in d]}


def files(ws: Workspace) -> list[Path]:
    gates = [path for path in ws.cfg.gate_shapes if path.is_file()]
    return [*gates, *sorted(ws.cfg.cq_dir.glob("*.rq"))]


def _tail(namespace: str) -> tuple[str, str]:
    parts = urlsplit(namespace)
    return parts.path, parts.fragment


def _line(text: str, namespace: str, kind: str) -> int | None:
    """The first line of that kind of declaration that names the namespace."""
    mark = "sh:namespace" if kind == DECLARE else "prefix"
    for number, line in enumerate(text.splitlines(), start=1):
        if namespace in line and mark in line.lower() and not line.lstrip().startswith("#"):
            return number
    return None


def problems(ws: Workspace) -> list[Violation]:
    """What each file declares that keeps it from matching the graph.

    An error for a prefix of the workflow ontology bound to another namespace,
    for a namespace that is one of the ontology's on another base, and for a
    file that never declares the workflow namespace at all.
    """
    schema = ws.cfg.rel(ws.cfg.workflow_schema)
    expected = {
        name: str(prefix.prefix_reference)
        for name, prefix in ws.schema.view.schema.prefixes.items()
        if name not in _NOT_OURS
    }
    workflow = ws.schema.wf_ns
    by_tail = {_tail(namespace): namespace for namespace in expected.values()}
    found: list[Violation] = []

    def error(path: Path, message: str, **details) -> None:
        found.append(
            Violation(
                rule="namespace",
                severity=ERROR,
                message=message,
                file=ws.cfg.rel(path),
                **details,
            )
        )

    for path in files(ws):
        text = path.read_text(encoding="utf-8")
        read = query_declarations if path.suffix == ".rq" else shapes_declarations
        try:
            kinds = read(text)
        except Exception as exc:  # the parsers raise their own unrelated types
            reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            error(path, f"cannot be read, so its namespaces cannot be checked: {reason}")
            continue
        for kind, pairs in kinds.items():
            wrong = False
            for name, namespace in pairs:
                right = expected.get(name)
                if right is None and namespace not in expected.values():
                    right = by_tail.get(_tail(namespace))
                if right is None or namespace == right:
                    continue
                wrong = True
                error(
                    path,
                    f"{kind} {name}: is <{namespace}> here and the namespace is <{right}> in "
                    f"{schema}, so what is written with it matches nothing in the graph",
                    line=_line(text, namespace, kind),
                    found=namespace,
                    allowed=(right,),
                    fix=f"declare {name}: as <{right}>",
                )
            if not wrong and workflow not in {namespace for _, namespace in pairs}:
                error(
                    path,
                    f"no {kind} names <{workflow}>, the namespace of {schema}, so nothing "
                    "written here can match a work item",
                    allowed=(workflow,),
                    fix=f"declare a prefix for <{workflow}> and write the workflow terms with it",
                )
    return found
