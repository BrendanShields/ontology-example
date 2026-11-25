"""The hand-written gates and questions must speak the workflow ontology's namespaces.

The gate shapes and the competency questions repeat the namespaces of
workflow.yaml as literal text. If one of them differs, its rules match nothing
in the graph and report no violation, so a gate that looks green checks
nothing. This module compares every prefix such a file declares with the
prefix of the same name in the workflow ontology.
"""

from __future__ import annotations

import re
from pathlib import Path

from .report import ERROR, Violation
from .workspace import Workspace

# `@prefix wf: <...>` in Turtle and `PREFIX wf: <...>` in SPARQL, and the
# `sh:declare` entries that give the SPARQL constraints of a shapes file their prefixes.
_PREFIX = re.compile(r"^[ \t]*@?prefix[ \t]+([\w.-]*):[ \t]*<([^>]*)>", re.I | re.M)
_DECLARE = re.compile(r'sh:prefix\s+"([^"]+)"\s*;\s*sh:namespace\s+"([^"]+)"')
_NOT_OURS = ("linkml",)


def declared(text: str) -> list[tuple[str, str, int]]:
    """(prefix, namespace, line) for each prefix a Turtle or SPARQL text declares."""
    found = []
    for pattern in (_PREFIX, _DECLARE):
        for match in pattern.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            if text[start : match.start()].lstrip().startswith("#"):
                continue
            found.append((match.group(1), match.group(2), text.count("\n", 0, match.start()) + 1))
    return sorted(found, key=lambda entry: entry[2])


def files(ws: Workspace) -> list[Path]:
    gates = [path for path in ws.cfg.gate_shapes if path.is_file()]
    return [*gates, *sorted(ws.cfg.cq_dir.glob("*.rq"))]


def problems(ws: Workspace) -> list[Violation]:
    """One error for each prefix that names a different namespace than the workflow ontology."""
    schema = ws.cfg.rel(ws.cfg.workflow_schema)
    expected = {
        name: str(prefix.prefix_reference)
        for name, prefix in ws.schema.view.schema.prefixes.items()
        if name not in _NOT_OURS
    }
    found: list[Violation] = []
    for path in files(ws):
        for name, namespace, line in declared(path.read_text(encoding="utf-8")):
            if name in expected and namespace != expected[name]:
                found.append(
                    Violation(
                        rule="namespace",
                        severity=ERROR,
                        message=(
                            f"prefix {name}: is <{namespace}> here and <{expected[name]}> in "
                            f"{schema}, so what is written with it matches nothing in the graph"
                        ),
                        file=ws.cfg.rel(path),
                        line=line,
                        found=namespace,
                        allowed=(expected[name],),
                        fix=f"declare {name}: as <{expected[name]}>",
                    )
                )
    return found
