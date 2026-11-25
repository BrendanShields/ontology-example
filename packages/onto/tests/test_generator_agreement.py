"""The Pydantic types and the SHACL shapes of a context give the same answer.

Both are compiled from the same LinkML schema by different generators: the
Pydantic types guard the app's write path, and SHACL is what a graph of the
same data would be checked with. For a table of made-up instances derived from
the schema (valid, a value outside an enum, a required slot left out, an
integer out of range, a required list left empty) the two must agree on
accept or reject. Where they do not, the disagreement is named in
KNOWN_DISAGREEMENTS, and the test fails once it is gone.

Every instance here is synthetic. No Call is loaded.
"""

from __future__ import annotations

import importlib.util
from functools import cache

import pyshacl
import pytest
from onto.workspace import Workspace
from pydantic import ValidationError
from rdflib import RDF, BNode, Graph, Literal, URIRef

CONTEXT = "call-qa"
INTEGER = URIRef("http://www.w3.org/2001/XMLSchema#integer")

# One valid instance of every concrete class. A slot whose range is a class
# with an identifier holds that identifier, as the Pydantic types expect.
SAMPLES: dict[str, dict] = {
    "Utterance": {"sequence": 1, "speaker": "CUSTOMER", "text": "A made-up line."},
    "Representative": {"representative_id": "REP-0001"},
    "Criterion": {"criterion_id": "greeting", "statement": "A made-up statement.", "weight": 5},
    "Finding": {
        "criterion": "greeting",
        "finding_outcome": "MET",
        "cited_utterances": [1],
        "rationale": "A made-up reason.",
    },
    "Rejection": {"rejection_rule": "MISSING_FINDING", "detail": "A made-up detail."},
}
SAMPLES["Call"] = {
    "call_id": "CALL-0001",
    "representative": "REP-0001",
    "utterances": [SAMPLES["Utterance"]],
}
SAMPLES["Scorecard"] = {
    "scorecard_id": "example-v1",
    "pass_mark": 80,
    "criteria": [SAMPLES["Criterion"]],
}
SAMPLES["Evaluation"] = {
    "call": "CALL-0001",
    "scorecard": "example-v1",
    "findings": [SAMPLES["Finding"]],
    "score": 100,
    "evaluation_outcome": "PASS",
    "disposition": "FINAL",
}

# case id -> why the two generators disagree on it today. Each entry is checked
# to still be a disagreement: when the schema or a generator changes so that the
# two agree, the case fails as an unexpected pass and the entry has to go.
KNOWN_DISAGREEMENTS = {
    "Evaluation: findings left empty": (
        "`findings` is required without a minimum_cardinality. gen-shacl turns required into "
        "sh:minCount 1, so SHACL rejects an Evaluation with no Findings. gen-pydantic turns it "
        "into a list that must be present and may be empty, so Pydantic accepts it. At runtime "
        "the MISSING_FINDING rule covers the gap."
    ),
}


@cache
def context():
    ws = Workspace.at()
    return ws.cfg.contexts[CONTEXT], ws.glossaries[CONTEXT].view


@cache
def pydantic_types():
    ctx, _ = context()
    spec = importlib.util.spec_from_file_location("generated_under_test", ctx.pydantic)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def shapes() -> Graph:
    """SHACL from the same schema, in memory, with the options `onto gen` uses."""
    from linkml.generators.shaclgen import ShaclGenerator

    ctx, _ = context()
    return Graph().parse(
        data=ShaclGenerator(str(ctx.schema), closed=False).serialize(), format="turtle"
    )


def cases() -> list[tuple[str, str, dict | None, bool]]:
    """(case id, class, instance, whether it is valid), derived from the schema."""
    _, view = context()
    found = []
    for cls, sample in SAMPLES.items():
        found.append((f"{cls}: valid", cls, sample, True))
        for slot in view.class_induced_slots(cls):
            name = slot.name
            if name not in sample:
                continue
            if slot.range in view.all_enums():
                found.append(
                    (f"{cls}: {name} outside its enum", cls, {**sample, name: "NO_SUCH"}, False)
                )
            # An identifier is the node itself in RDF, so "left out" has no graph form.
            if slot.required and not slot.identifier:
                without = {k: v for k, v in sample.items() if k != name}
                found.append((f"{cls}: {name} left out", cls, without, False))
            if slot.required and slot.multivalued:
                found.append((f"{cls}: {name} left empty", cls, {**sample, name: []}, False))
            if slot.minimum_value is not None and not slot.multivalued:
                below = {**sample, name: slot.minimum_value - 1}
                found.append((f"{cls}: {name} below its minimum", cls, below, False))
            if slot.maximum_value is not None and not slot.multivalued:
                above = {**sample, name: slot.maximum_value + 1}
                found.append((f"{cls}: {name} above its maximum", cls, above, False))
    return found


def pydantic_accepts(cls: str, instance: dict) -> bool:
    try:
        getattr(pydantic_types(), cls).model_validate(instance)
    except ValidationError:
        return False
    return True


def shacl_accepts(cls: str, instance: dict) -> bool:
    graph = Graph()
    _add(graph, cls, instance)
    conforms, _, _ = pyshacl.validate(graph, shacl_graph=shapes(), inference=None)
    return conforms


def _add(graph: Graph, cls: str, instance: dict, done: set | None = None):
    """Write an instance into the graph as LinkML would, and every node it refers to in full."""
    _, view = context()
    done = set() if done is None else done
    identifier = view.get_identifier_slot(cls)
    base = view.schema.id.rstrip("/") + "/data/"
    key = instance.get(identifier.name) if identifier else None
    node = URIRef(f"{base}{cls}/{key}") if key is not None else BNode()
    if node in done:
        return node
    done.add(node)
    graph.add((node, RDF.type, URIRef(view.get_uri(cls, expand=True))))
    for slot in view.class_induced_slots(cls):
        value = instance.get(slot.name)
        values = value if isinstance(value, list) else [] if value is None else [value]
        for item in values:
            predicate = URIRef(view.get_uri(slot, expand=True))
            graph.add((node, predicate, _object(graph, view, slot, item, done)))
    return node


def _object(graph: Graph, view, slot, value, done: set):
    if slot.range in view.all_classes():
        if isinstance(value, dict):
            return _add(graph, slot.range, value, done)
        # A reference by identifier: the node it names has to be in the graph to be a
        # node of the right class, so the sample of that class stands in for it.
        return _add(graph, slot.range, SAMPLES[slot.range], done)
    if slot.range in view.all_enums():
        return _enum_value(view, slot.range, value)
    if isinstance(value, bool):
        return Literal(value)
    if isinstance(value, int):
        return Literal(value, datatype=INTEGER)
    return Literal(str(value))


def _enum_value(view, enum: str, value: str):
    """A permissible value as the generated shapes list it in sh:in."""
    listed = _listed_values(enum)
    return listed.get(value, Literal(value) if _literals(listed) else URIRef(f"urn:none:{value}"))


def _literals(listed: dict) -> bool:
    return all(isinstance(term, Literal) for term in listed.values())


@cache
def _listed_values(enum: str) -> dict:
    """value name -> the RDF term the shapes accept for it, read from the shapes themselves."""
    from rdflib import Namespace
    from rdflib.collection import Collection

    sh = Namespace("http://www.w3.org/ns/shacl#")
    _, view = context()
    names = set(view.get_enum(enum).permissible_values)
    for head in shapes().objects(None, sh["in"]):
        terms = list(Collection(shapes(), head))
        by_name = {str(term).rsplit("#", 1)[-1].rsplit("/", 1)[-1]: term for term in terms}
        if set(by_name) == names:
            return by_name
    raise AssertionError(f"the generated shapes list no sh:in for the enum {enum}")


def _params(known: bool) -> list:
    return [
        pytest.param(cls, instance, valid, id=case)
        for case, cls, instance, valid in cases()
        if (case in KNOWN_DISAGREEMENTS) == known
    ]


# Both answers are reduced to yes or no before asserting, so that no value of an
# instance reaches a report.


@pytest.mark.parametrize(("cls", "instance", "valid"), _params(known=False))
def test_pydantic_and_shacl_agree(cls, instance, valid):
    by_pydantic, by_shacl = pydantic_accepts(cls, instance), shacl_accepts(cls, instance)
    assert by_pydantic == by_shacl, f"Pydantic accepts: {by_pydantic}, SHACL accepts: {by_shacl}"
    assert by_pydantic == valid, f"both {'accept' if by_pydantic else 'reject'} it"


@pytest.mark.parametrize(("cls", "instance", "valid"), _params(known=True))
def test_a_known_disagreement_is_still_one(cls, instance, valid):
    by_pydantic, by_shacl = pydantic_accepts(cls, instance), shacl_accepts(cls, instance)
    assert by_pydantic != by_shacl, (
        f"Pydantic and SHACL now agree on this case (both {'accept' if by_pydantic else 'reject'}"
        " it): take it out of KNOWN_DISAGREEMENTS, so that the agreement is held from now on"
    )


def test_the_table_covers_every_class_and_every_kind_of_fault():
    _, view = context()
    concrete = {name for name, cls in view.all_classes().items() if not cls.abstract}
    assert set(SAMPLES) == concrete
    ids = [case for case, *_ in cases()]
    for kind in ("valid", "outside its enum", "left out", "left empty", "below its minimum"):
        assert any(case.endswith(kind) for case in ids), kind
    assert set(KNOWN_DISAGREEMENTS) <= set(ids), "a known disagreement names no case of the table"
