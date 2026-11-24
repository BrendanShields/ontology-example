"""The generated Pydantic types enforce what the generated JSON Schema declares.

Both are compiled from ontology/domains/call-qa.yaml by different LinkML
generators. Checking one against the other catches a generator that drops or
mangles a constraint, which is how the multivalued-minimum bug noted in the
ontology was found.
"""

from __future__ import annotations

import json
from importlib import resources

import pytest
from call_qa_agent import generated
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

SCHEMA = json.loads(
    resources.files("call_qa_agent").joinpath("schemas", "call-qa.schema.json").read_text("utf-8")
)["$defs"]

# One valid instance of every class.
SAMPLES = {
    "Utterance": {"sequence": 1, "speaker": "CUSTOMER", "text": "Hello."},
    "Representative": {"representative_id": "REP-0001"},
    "Criterion": {"criterion_id": "greeting", "statement": "Greets the customer.", "weight": 5},
    "Finding": {
        "criterion": "greeting",
        "finding_outcome": "MET",
        "cited_utterances": [1],
        "rationale": "Greets the customer.",
    },
    "Rejection": {"rejection_rule": "MISSING_FINDING", "detail": "No Finding."},
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


def accepts(cls: str, **changes) -> bool:
    try:
        getattr(generated, cls).model_validate({**SAMPLES[cls], **changes})
    except ValidationError:
        return False
    return True


def properties(keyword: str) -> list[tuple[str, str, dict]]:
    """(class, property, schema) for every property that declares the keyword."""
    return [
        (cls, name, spec)
        for cls, definition in SCHEMA.items()
        for name, spec in definition.get("properties", {}).items()
        if keyword in spec
    ]


def enum_properties() -> list[tuple[str, str, list[str]]]:
    found = []
    for cls, definition in SCHEMA.items():
        for name, spec in definition.get("properties", {}).items():
            ref = spec.get("$ref", "")
            if ref and "enum" in SCHEMA[ref.rsplit("/", 1)[-1]]:
                found.append((cls, name, SCHEMA[ref.rsplit("/", 1)[-1]]["enum"]))
    return found


def test_every_class_of_the_ontology_has_a_sample():
    classes = {name for name, definition in SCHEMA.items() if "properties" in definition}
    assert classes == set(SAMPLES)


@pytest.mark.parametrize("cls", sorted(SAMPLES))
def test_a_valid_instance_is_accepted(cls):
    assert accepts(cls)


@pytest.mark.parametrize("cls", sorted(SAMPLES))
def test_an_undeclared_field_is_rejected(cls):
    assert not accepts(cls, not_in_the_ontology=1)


@pytest.mark.parametrize(("cls", "name", "spec"), properties("minimum") + properties("maximum"))
@given(value=st.integers(min_value=-1000, max_value=1000))
def test_numeric_bounds_are_enforced(cls, name, spec, value):
    within = spec.get("minimum", value) <= value <= spec.get("maximum", value)
    assert accepts(cls, **{name: value}) == within


@pytest.mark.parametrize(("cls", "name", "spec"), properties("pattern"))
def test_patterns_are_enforced(cls, name, spec):
    assert accepts(cls)  # the sample matches
    assert not accepts(cls, **{name: "not a valid id!"})


@pytest.mark.parametrize(("cls", "name", "values"), enum_properties())
def test_enums_are_closed(cls, name, values):
    for value in values:
        assert accepts(cls, **{name: value})
    assert not accepts(cls, **{name: "SOMETHING_ELSE"})


@pytest.mark.parametrize("cls", sorted(SAMPLES))
def test_required_fields_are_required(cls):
    for name in SCHEMA[cls].get("required", []):
        sample = {key: value for key, value in SAMPLES[cls].items() if key != name}
        with pytest.raises(ValidationError):
            getattr(generated, cls).model_validate(sample)
