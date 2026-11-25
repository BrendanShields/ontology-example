"""Read access to the workflow ontology (L1) and the artefacts generated from it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import cached_property
from urllib.parse import urlparse

import yaml

from .config import Config
from .failures import SourceUnreadable, missing

RECORD_ROOT = "Record"  # every class stored as a file under work/ descends from this
TERM_CLASS = "Term"  # the bridge to the domain ontologies
XSD = "http://www.w3.org/2001/XMLSchema#"


@dataclass(frozen=True)
class SlotInfo:
    """How one slot of a class is written into the graph."""

    name: str
    iri: str
    kind: str  # "record" | "term" | "enum" | "iri" | "literal"
    range: str
    datatype: str | None  # XSD IRI for typed literals, None for plain strings
    multivalued: bool
    required: bool


class WorkflowSchema:
    """The workflow ontology as the gates need it. Everything is derived from the LinkML source."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    @cached_property
    def view(self):
        from linkml_runtime.utils.schemaview import SchemaView

        if not self.cfg.workflow_schema.is_file():
            raise missing(
                "the workflow ontology every command reads",
                self.cfg.rel(self.cfg.workflow_schema),
                "run `onto init` to scaffold it",
            )
        try:
            return SchemaView(str(self.cfg.workflow_schema))
        except yaml.YAMLError as exc:
            raise SourceUnreadable(self.cfg.workflow_schema, exc) from exc

    # --- namespaces -----------------------------------------------------------

    @cached_property
    def namespaces(self) -> dict[str, str]:
        return {prefix: str(ns) for prefix, ns in self.view.namespaces().items()}

    @cached_property
    def work_ns(self) -> str:
        return self.namespaces["work"]

    @cached_property
    def wf_ns(self) -> str:
        return self.namespaces[self.view.schema.default_prefix]

    # --- classes --------------------------------------------------------------

    @cached_property
    def record_classes(self) -> dict[str, re.Pattern[str]]:
        """Concrete classes stored under work/, each with the pattern its ids follow."""
        out: dict[str, re.Pattern[str]] = {}
        for name in self.view.class_descendants(RECORD_ROOT):
            cls = self.view.get_class(name)
            if cls.abstract or cls.mixin:
                continue
            pattern = self.view.induced_slot("id", name).pattern
            if not pattern:
                raise ValueError(
                    f"class {name} declares no id pattern in {self.cfg.workflow_schema}"
                )
            out[name] = re.compile(pattern)
        return out

    def class_for_id(self, identifier: str) -> str | None:
        """The class an id belongs to, decided by the id patterns in the schema."""
        found = [
            name for name, pattern in self.record_classes.items() if pattern.search(identifier)
        ]
        return found[0] if len(found) == 1 else None

    def id_prefix(self, cls: str) -> str:
        """'REQ' for Requirement: the literal prefix of the class's id pattern."""
        match = re.match(r"\^?\(?([A-Z]+)", self.record_classes[cls].pattern)
        if not match:
            raise ValueError(f"cannot read an id prefix from the pattern of {cls}")
        return match.group(1)

    def class_iri(self, cls: str) -> str:
        return self.view.get_uri(self.view.get_class(cls), expand=True)

    def class_iris(self, cls: str) -> list[str]:
        """The class and every ancestor (is_a and mixins), as IRIs. Used to type instances."""
        return [self.class_iri(name) for name in self.view.class_ancestors(cls)]

    def is_record_class(self, name: str) -> bool:
        return name in self.view.class_descendants(RECORD_ROOT)

    # --- slots ----------------------------------------------------------------

    def slot_iri(self, name: str) -> str:
        return self.view.get_uri(self.view.get_slot(name), expand=True)

    def slots(self, cls: str) -> list[SlotInfo]:
        """Every slot of a class as the graph builder needs it. The id comes first."""
        infos: list[SlotInfo] = []
        for slot in self.view.class_induced_slots(cls):
            rng = slot.range or self.view.schema.default_range
            datatype: str | None = None
            if rng == TERM_CLASS:
                kind = "term"
            elif rng in self.view.all_classes():
                kind = "record"
            elif rng in self.view.all_enums():
                kind = "enum"
            else:
                uri = self._type_iri(rng)
                # LinkML's SHACL generator expects a `uri` value to be an IRI node.
                kind = "iri" if uri.endswith("#anyURI") else "literal"
                datatype = None if kind == "iri" or uri.endswith("#string") else uri
            infos.append(
                SlotInfo(
                    name=slot.name,
                    iri=self.view.get_uri(slot, expand=True),
                    kind=kind,
                    range=rng,
                    datatype=datatype,
                    multivalued=bool(slot.multivalued),
                    required=bool(slot.required),
                )
            )
        infos.sort(key=lambda s: s.name != "id")
        return infos

    def _type_iri(self, type_name: str) -> str:
        """The XSD datatype a LinkML type stands for, as a full IRI."""
        uri = str(self.view.get_type(type_name).uri)
        if uri.startswith("xsd:"):  # declared by linkml:types, not by this schema's prefixes
            return XSD + uri.removeprefix("xsd:")
        return self.view.expand_curie(uri)

    def enum_values(self, enum: str) -> list[str]:
        return list(self.view.get_enum(enum).permissible_values)

    # --- generated JSON Schema ------------------------------------------------

    @cached_property
    def json_schema(self) -> dict:
        path = self.cfg.workflow_json_schema
        if not path.is_file():
            raise FileNotFoundError(f"{self.cfg.rel(path)} is missing: run `onto gen`")
        return json.loads(path.read_text(encoding="utf-8"))

    def validator(self, cls: str):
        """A JSON Schema validator for one class of the generated schema."""
        from jsonschema.validators import validator_for

        schema = {
            "$schema": self.json_schema["$schema"],
            "$defs": self.json_schema["$defs"],
            "$ref": f"#/$defs/{cls}",
        }
        return validator_for(schema)(schema, format_checker=_format_checker())


def _format_checker():
    """Formats are checked with the standard library so the result never depends on extras."""
    from jsonschema import FormatChecker

    checker = FormatChecker(formats=())

    @checker.checks("date", raises=ValueError)
    def _is_date(value) -> bool:
        if isinstance(value, str):
            date.fromisoformat(value)
        return True

    @checker.checks("date-time", raises=ValueError)
    def _is_datetime(value) -> bool:
        if isinstance(value, str):
            if "T" not in value:
                raise ValueError("a date-time needs a time part")
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True

    @checker.checks("uri")
    def _is_uri(value) -> bool:
        if not isinstance(value, str):
            return True
        parsed = urlparse(value)
        return bool(parsed.scheme and (parsed.netloc or parsed.path))

    return checker
