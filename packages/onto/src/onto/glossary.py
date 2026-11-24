"""The glossary of one bounded context, read from its domain ontology (L2).

Every class, slot, enum and permissible value of the LinkML schema is a term.
This module answers the two questions the gates ask: "does this name exist?"
and "what should have been written instead?".
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import cached_property

from .config import Context
from .report import ERROR, Violation

DEFAULT_CLASSIFICATION = "internal"
KIND_ORDER = {"class": 0, "enum": 1, "slot": 2, "value": 3}


def norm(text: str) -> str:
    """Comparison key that ignores case and separators: 'Pass mark' -> 'passmark'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass(frozen=True)
class Attribute:
    """A slot as it appears on one class."""

    name: str
    range: str
    required: bool
    multivalued: bool
    constraints: tuple[str, ...]


@dataclass(frozen=True)
class Term:
    name: str  # canonical name; for a value this is "Enum.VALUE"
    kind: str  # class | slot | enum | value
    context: str
    iri: str
    definition: str
    classification: str
    aliases: tuple[str, ...] = ()
    denied_synonyms: tuple[str, ...] = ()
    exact_mappings: tuple[str, ...] = ()
    close_mappings: tuple[str, ...] = ()
    parent: str | None = None  # the superclass of a class, the enum of a value
    abstract: bool = False
    attributes: tuple[Attribute, ...] = ()  # classes
    range: str | None = None  # slots
    constraints: tuple[str, ...] = ()  # slots
    used_by: tuple[str, ...] = ()  # slots: the classes that carry it
    values: tuple[str, ...] = ()  # enums: bare value names

    @property
    def short_name(self) -> str:
        """'NEEDS_REVIEW' for the value term 'Disposition.NEEDS_REVIEW'."""
        return self.name.split(".", 1)[1] if self.kind == "value" else self.name


@dataclass(frozen=True)
class Resolution:
    """The answer to "what is this name?"."""

    query: str
    status: str  # exact | alias | normalized | denied | unknown
    terms: tuple[Term, ...] = ()
    suggestions: tuple[str, ...] = ()
    denied_synonym: str | None = None

    @property
    def found(self) -> bool:
        return self.status in ("exact", "alias", "normalized")


class Glossary:
    def __init__(self, context: Context):
        self.context = context
        self.name = context.name

    @cached_property
    def view(self):
        from linkml_runtime.utils.schemaview import SchemaView

        return SchemaView(str(self.context.schema))

    @cached_property
    def namespace(self) -> str:
        return str(self.view.namespaces()[self.view.schema.default_prefix])

    @cached_property
    def prefix(self) -> str:
        return str(self.view.schema.default_prefix)

    # --- building -------------------------------------------------------------

    @cached_property
    def terms(self) -> dict[str, Term]:
        view = self.view
        terms: dict[str, Term] = {}

        users: dict[str, list[str]] = {}
        for cls_name in view.all_classes(imports=False):
            for slot_name in view.class_slots(cls_name):
                users.setdefault(slot_name, []).append(cls_name)

        for cls_name, cls in view.all_classes(imports=False).items():
            attributes = tuple(
                Attribute(
                    name=slot.name,
                    range=slot.range or view.schema.default_range,
                    required=bool(slot.required or slot.identifier),
                    multivalued=bool(slot.multivalued),
                    constraints=_constraints(slot),
                )
                for slot in view.class_induced_slots(cls_name)
            )
            terms[cls_name] = self._term(
                cls, "class", parent=cls.is_a, abstract=bool(cls.abstract), attributes=attributes
            )

        for slot_name, slot in view.all_slots(imports=False).items():
            terms[slot_name] = self._term(
                slot,
                "slot",
                range=slot.range or view.schema.default_range,
                constraints=_constraints(slot),
                used_by=tuple(users.get(slot_name, ())),
            )

        for enum_name, enum in view.all_enums(imports=False).items():
            values = tuple(enum.permissible_values)
            terms[enum_name] = self._term(enum, "enum", values=values)
            enum_iri = view.get_uri(enum, expand=True)
            for value_name, value in enum.permissible_values.items():
                terms[f"{enum_name}.{value_name}"] = Term(
                    name=f"{enum_name}.{value_name}",
                    kind="value",
                    context=self.name,
                    iri=f"{enum_iri}#{value_name}",
                    definition=_clean(value.description),
                    classification=DEFAULT_CLASSIFICATION,
                    parent=enum_name,
                )
        return terms

    def _term(self, element, kind: str, **extra) -> Term:
        annotations = _annotations(element)
        return Term(
            name=element.name,
            kind=kind,
            context=self.name,
            iri=self.view.get_uri(element, expand=True),
            definition=_clean(element.description),
            classification=str(annotations.get("classification", DEFAULT_CLASSIFICATION)),
            aliases=tuple(element.aliases or ()),
            denied_synonyms=tuple(_as_list(annotations.get("denied_synonyms"))),
            exact_mappings=tuple(self.view.expand_curie(m) for m in element.exact_mappings or ()),
            close_mappings=tuple(self.view.expand_curie(m) for m in element.close_mappings or ()),
            **extra,
        )

    # --- lookup ---------------------------------------------------------------

    @cached_property
    def _bare_values(self) -> dict[str, Term]:
        """Value terms reachable by their bare name ('MET'), where that is unambiguous."""
        by_short: dict[str, list[Term]] = {}
        for term in self.terms.values():
            if term.kind == "value":
                by_short.setdefault(term.short_name, []).append(term)
        return {
            short: found[0]
            for short, found in by_short.items()
            if len(found) == 1 and short not in self.terms
        }

    @cached_property
    def _by_norm(self) -> dict[str, list[Term]]:
        index: dict[str, list[Term]] = {}
        for term in self.terms.values():
            for key in {norm(term.name), norm(term.short_name)}:
                index.setdefault(key, []).append(term)
        return index

    @cached_property
    def _by_alias(self) -> dict[str, list[Term]]:
        index: dict[str, list[Term]] = {}
        for term in self.terms.values():
            for alias in term.aliases:
                index.setdefault(norm(alias), []).append(term)
        return index

    @cached_property
    def _by_denied(self) -> dict[str, tuple[str, Term]]:
        index: dict[str, tuple[str, Term]] = {}
        for term in self.terms.values():
            for synonym in term.denied_synonyms:
                index.setdefault(norm(synonym), (synonym, term))
        return index

    def get(self, name: str) -> Term | None:
        """The term with exactly this canonical name. Values may be named bare when unique."""
        return self.terms.get(name) or self._bare_values.get(name)

    def resolve(self, text: str) -> Resolution:
        """Find the term a piece of text names. Never guesses: an unknown name stays unknown."""
        text = text.strip()
        exact = self.get(text)
        if exact:
            return Resolution(text, "exact", (exact,))

        key = norm(text)
        # Also try the singular and the plural: "Findings" and "cited utterance"
        # are spellings of terms, not new names.
        singular = key[:-1] if key.endswith("s") and len(key) > 3 else key
        candidates = tuple(dict.fromkeys((key, singular, key + "s")))

        for candidate in candidates:
            if candidate in self._by_alias:
                return Resolution(text, "alias", _ordered(self._by_alias[candidate]))

        found: list[Term] = []
        for candidate in candidates:
            found.extend(t for t in self._by_norm.get(candidate, ()) if t not in found)
        if found:
            return Resolution(text, "normalized", _ordered(found))

        for candidate in candidates:
            if candidate in self._by_denied:
                synonym, term = self._by_denied[candidate]
                return Resolution(text, "denied", (term,), denied_synonym=synonym)

        return Resolution(text, "unknown", suggestions=self.suggest(text))

    def suggest(self, text: str, limit: int = 3) -> tuple[str, ...]:
        """The nearest existing term names, for an unknown name."""
        keys: dict[str, str] = {}
        for term in self.terms.values():
            keys.setdefault(norm(term.name), term.name)
            keys.setdefault(norm(term.short_name), term.name)
            for alias in term.aliases:
                keys.setdefault(norm(alias), term.name)
        close = difflib.get_close_matches(norm(text), list(keys), n=limit * 2, cutoff=0.72)
        return tuple(dict.fromkeys(keys[k] for k in close))[:limit]

    def denied_entries(self) -> list[tuple[str, Term]]:
        """Every (denied synonym, term to use instead) pair of the context."""
        return [(s, term) for term in self.terms.values() for s in term.denied_synonyms]

    def related(self, name: str) -> list[str]:
        """Terms one step away: what a slice at depth 1 adds to a focus term."""
        term = self.get(name)
        if term is None:
            return []
        out: list[str] = []
        if term.kind == "class":
            if term.parent:
                out.append(term.parent)
            for attribute in term.attributes:
                out.append(attribute.name)
                if attribute.range in self.terms:
                    out.append(attribute.range)
        elif term.kind == "slot":
            if term.range in self.terms:
                out.append(term.range)
            out.extend(term.used_by)
        elif term.kind == "value" and term.parent:
            out.append(term.parent)
        return [n for n in dict.fromkeys(out) if n != term.name]

    # --- self-check -----------------------------------------------------------

    def lint(self, allowed_classifications: list[str], file: str) -> list[Violation]:
        """Problems in the glossary itself. One that fails this cannot be trusted as a gate."""
        problems: list[Violation] = []

        def problem(term: Term, message: str, **extra) -> None:
            problems.append(
                Violation(
                    rule="glossary",
                    severity=ERROR,
                    message=message,
                    file=file,
                    subject=term.name,
                    **extra,
                )
            )

        names = {norm(t.name): t for t in self.terms.values() if t.kind != "value"}
        aliases: dict[str, Term] = {}
        for term in self.terms.values():
            if not term.definition:
                problem(term, f"term '{term.name}' has no description: a term needs a definition")
            if term.classification not in allowed_classifications:
                problem(
                    term,
                    f"term '{term.name}' has classification '{term.classification}'",
                    found=term.classification,
                    allowed=tuple(allowed_classifications),
                )
            for mapping in (*term.exact_mappings, *term.close_mappings):
                if not re.match(r"^(https?://|urn:)", mapping):
                    problem(term, f"mapping '{mapping}' of '{term.name}' uses an undeclared prefix")
            for alias in term.aliases:
                key = norm(alias)
                other = aliases.get(key) or (names.get(key) if names.get(key) != term else None)
                if other and other != term:
                    problem(term, f"alias '{alias}' of '{term.name}' also names '{other.name}'")
                aliases[key] = term
        for synonym, term in self.denied_entries():
            key = norm(synonym)
            clash = names.get(key) or aliases.get(key)
            if clash:
                problem(
                    term,
                    f"'{synonym}' is denied in favour of '{term.name}' but is itself "
                    f"a name or alias of '{clash.name}'",
                )
        return problems


def _ordered(terms: list[Term]) -> tuple[Term, ...]:
    return tuple(sorted(terms, key=lambda t: (KIND_ORDER[t.kind], t.name)))


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _annotations(element) -> dict[str, object]:
    """LinkML annotations as a plain dict, whichever container the runtime used."""
    raw = element.annotations
    if not raw:
        return {}
    keys = raw.keys() if isinstance(raw, dict) else [k for k in vars(raw) if not k.startswith("_")]
    return {key: getattr(raw[key], "value", raw[key]) for key in keys}


def _constraints(slot) -> tuple[str, ...]:
    """The machine-checked constraints of a slot, in words."""
    out: list[str] = []
    if slot.identifier:
        out.append("identifier")
    if slot.minimum_value is not None:
        out.append(f">= {slot.minimum_value}")
    if slot.maximum_value is not None:
        out.append(f"<= {slot.maximum_value}")
    if slot.pattern:
        out.append(f"matches {slot.pattern}")
    if slot.minimum_cardinality:
        out.append(f"at least {slot.minimum_cardinality}")
    return tuple(out)
