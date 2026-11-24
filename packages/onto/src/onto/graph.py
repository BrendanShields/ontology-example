"""The traceability graph: work items and glossary terms as RDF.

Nothing here is authored. The graph is rebuilt from the files on every run and
is small enough that there is no cache to go stale:

    work/*.md frontmatter            -> one node per work item, typed by workflow.yaml
    ontology/domains/<ctx>.yaml      -> one wf:Term node per glossary term

rdflib builds the graph and feeds pySHACL; Oxigraph answers the SPARQL.
"""

from __future__ import annotations

import io
from functools import cached_property
from pathlib import Path
from urllib.parse import quote

from rdflib import RDF, Graph, Literal, URIRef

from .schema import TERM_CLASS
from .workspace import Workspace

PROV = "http://www.w3.org/ns/prov#"
SKOS = "http://www.w3.org/2004/02/skos/core#"


class WorkGraph:
    def __init__(self, ws: Workspace, graph: Graph):
        self.ws = ws
        self.rdf = graph

    @cached_property
    def prefixes(self) -> dict[str, str]:
        """Prefix -> namespace for everything the graph uses. Longest namespace first."""
        found = {
            "wf": self.ws.schema.wf_ns,
            "work": self.ws.schema.work_ns,
            "prov": PROV,
            "skos": SKOS,
        }
        for glossary in self.ws.glossaries.values():
            found[glossary.prefix] = glossary.namespace
        return dict(sorted(found.items(), key=lambda item: -len(item[1])))

    def short(self, value: str) -> str:
        """Readable form of an IRI: a bare id for work items, a CURIE where a prefix is known."""
        work = self.ws.schema.work_ns
        if value.startswith(work):
            return value[len(work) :]
        for prefix, namespace in self.prefixes.items():
            if value.startswith(namespace):
                return f"{prefix}:{value[len(namespace) :]}"
        return value

    def node(self, name: str) -> URIRef:
        """The IRI a short name stands for: a work item id, a term name or a CURIE."""
        if name.startswith(("http://", "https://", "urn:")):
            return URIRef(name)
        if self.ws.schema.class_for_id(name):
            return URIRef(self.ws.schema.work_ns + name)
        prefix, _, local = name.partition(":")
        if local and prefix in self.prefixes:
            return URIRef(self.prefixes[prefix] + local)
        for glossary in self.ws.glossaries.values():
            term = glossary.get(name)
            if term:
                return URIRef(term.iri)
        raise KeyError(f"'{name}' is not a work item id, a glossary term or a known CURIE")

    @cached_property
    def _store(self):
        import pyoxigraph

        store = pyoxigraph.Store()
        store.load(
            io.BytesIO(self.rdf.serialize(format="nt", encoding="utf-8")),
            format=pyoxigraph.RdfFormat.N_TRIPLES,
        )
        return store

    def select(self, sparql: str, **bindings: str) -> list[dict[str, str]]:
        """Run a SELECT query. Rows are plain dicts of shortened strings.

        Keyword arguments pre-bind variables of the SELECT clause, given as work
        item ids, term names, CURIEs or IRIs: `graph.select(q, term="Scorecard")`.
        """
        import pyoxigraph

        substitutions = {
            pyoxigraph.Variable(name): pyoxigraph.NamedNode(str(self.node(value)))
            for name, value in bindings.items()
        }
        results = self._store.query(sparql, substitutions=substitutions or None)
        if isinstance(results, pyoxigraph.QueryBoolean):
            return [{"ask": str(bool(results)).lower()}]
        variables = [variable.value for variable in results.variables]
        rows = []
        for solution in results:
            row = {}
            for name in variables:
                value = solution[name]
                if value is not None:
                    row[name] = self.short(value.value)
            rows.append(row)
        return rows

    def serialize(self, fmt: str = "turtle") -> str:
        return self.rdf.serialize(format=fmt)


def build_graph(ws: Workspace) -> WorkGraph:
    graph = Graph()
    work_graph = WorkGraph(ws, graph)
    for prefix, namespace in work_graph.prefixes.items():
        graph.bind(prefix, namespace)
    _add_terms(ws, graph)
    _add_work_items(ws, graph)
    return work_graph


def load_graph(root: Path | None = None) -> WorkGraph:
    """Build the graph of the monorepo at `root` (default: found from the working directory)."""
    return build_graph(Workspace.at(root))


def _add_terms(ws: Workspace, graph: Graph) -> None:
    """One wf:Term per glossary term, using only predicates declared on Term in workflow.yaml."""
    schema = ws.schema
    term_types = [URIRef(iri) for iri in schema.class_iris(TERM_CLASS)]
    predicate = {slot.name: URIRef(slot.iri) for slot in schema.slots(TERM_CLASS)}
    for glossary in ws.glossaries.values():
        for term in glossary.terms.values():
            node = URIRef(term.iri)
            for term_type in term_types:
                graph.add((node, RDF.type, term_type))
            graph.add((node, predicate["id"], Literal(term.name)))
            graph.add((node, predicate["term_kind"], Literal(term.kind)))
            graph.add((node, predicate["bounded_context"], Literal(term.context)))
            graph.add((node, predicate["classification"], Literal(term.classification)))
            if term.definition:
                graph.add((node, predicate["definition"], Literal(term.definition)))
            for alias in term.aliases:
                graph.add((node, predicate["aliases"], Literal(alias)))
            for synonym in term.denied_synonyms:
                graph.add((node, predicate["denied_synonyms"], Literal(synonym)))
            for mapping in term.exact_mappings:
                graph.add((node, predicate["exact_mappings"], URIRef(mapping)))
            for mapping in term.close_mappings:
                graph.add((node, predicate["close_mappings"], URIRef(mapping)))


def _add_work_items(ws: Workspace, graph: Graph) -> None:
    schema = ws.schema
    work = schema.work_ns
    for item in ws.items:
        if item.cls is None:
            continue  # `onto validate` reports it
        node = URIRef(work + item.id)
        # Typing with every ancestor is the only inference the graph needs:
        # it makes a Requirement a wf:WorkItem and a prov:Entity for queries.
        for class_iri in schema.class_iris(item.cls):
            graph.add((node, RDF.type, URIRef(class_iri)))
        glossary = ws.glossary(item.context)
        for slot in schema.slots(item.cls):
            for value in item.values(slot.name):
                graph.add((node, URIRef(slot.iri), _object(slot, value, work, glossary)))


def _object(slot, value: str, work: str, glossary):
    if slot.kind == "record":
        return URIRef(work + value)
    if slot.kind == "term":
        term = glossary.get(value) if glossary else None
        if term:
            return URIRef(term.iri)
        # Not a term: point at a node that is typed as nothing, so the SHACL
        # shape for the slot (sh:class wf:Term) reports it.
        base = glossary.namespace if glossary else work
        return URIRef(base + "unknown-term/" + quote(value, safe=""))
    if slot.kind == "iri":
        return URIRef(value)
    if slot.datatype:
        return Literal(value, datatype=URIRef(slot.datatype))
    return Literal(value)
