"""Hold declared rules to code and to proof: `onto rules`.

A glossary term annotated `binding: rule` (an enum, for each of its values, or
one value) or `binding: computed` (a slot) is a promise that the software
enforces or computes it. This gate checks both ends of the promise:

* code: a function in the context's domain layer or write path produces the
  term. A rule is produced where `<Enum>.<VALUE>` is written, other than as
  something to compare with. A computed slot is produced where `<slot>=` is
  passed to a generated class that carries it.
* proof: a done Requirement uses the term and a Test that verifies the
  Requirement has passing Evidence.

The code half reads source files only (`scan`), so `onto gen` can write it down
as the bindings manifest of the context. The proof half needs the evidence of a
test run, which is not committed, and so stays out of that file.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field

from . import report
from .config import Config, Context, matches
from .glossary import Glossary, Term
from .report import ERROR, WARNING, Violation

# Calls on a generated class that build an instance from data the scan cannot see into.
_FROM_DATA = ("model_validate", "model_validate_json", "model_validate_strings")


@dataclass(frozen=True)
class Binding:
    term: str  # canonical name: "Enum.VALUE" for a rule, the slot name for a computed slot
    kind: str  # rule | computed
    precondition_of: str | None = None
    functions: tuple[str, ...] = ()  # "path/to/file.py::Class.method", sorted


@dataclass(frozen=True)
class Proof:
    requirement: str
    tests: tuple[str, ...]  # the Tests with passing Evidence


@dataclass
class ContextRules:
    context: str
    bindings: list[Binding] = field(default_factory=list)
    proofs: dict[str, list[Proof]] = field(default_factory=dict)  # term -> what proves it

    def to_dict(self) -> dict:
        return {
            "context": self.context,
            "bindings": [
                {
                    "term": b.term,
                    "binding": b.kind,
                    **({"precondition_of": b.precondition_of} if b.precondition_of else {}),
                    "functions": list(b.functions),
                    "proven_by": [
                        {"requirement": p.requirement, "tests": list(p.tests)}
                        for p in self.proofs.get(b.term, ())
                    ],
                }
                for b in self.bindings
            ],
        }


# --- the code half ---------------------------------------------------------------


def scanned_files(cfg: Config, ctx: Context) -> list[str]:
    """The Python files of the domain layer and the write path, repository-relative."""
    found: set[str] = set()
    for pattern in (*ctx.domain_paths, *ctx.write_paths):
        base = cfg.root / pattern.split("*", 1)[0]
        base = base if base.is_dir() else base.parent
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            rel = cfg.rel(path)
            if path.is_file() and "__pycache__" not in rel and matches(rel, (pattern,)):
                found.add(rel)
    if ctx.pydantic is not None:
        found.discard(cfg.rel(ctx.pydantic))
    return sorted(found)


def scan(cfg: Config, ctx: Context, glossary: Glossary) -> tuple[list[Binding], list[Violation]]:
    """Every bound term of the context with the functions that produce it.

    The violations are the terms nothing produces, and a warning for each place
    where one of them may be produced out of the scan's sight.
    """
    bound = glossary.bound()
    schema = cfg.rel(ctx.schema)
    if not bound:
        return [], []

    problems: list[Violation] = []
    functions: dict[str, set[str]] = {}
    hidden: list[_Hidden] = []
    files = scanned_files(cfg, ctx)
    for rel in files:
        try:
            tree = ast.parse((cfg.root / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            problems.append(
                Violation(
                    "unreadable",
                    WARNING,
                    "this file could not be parsed, so no binding was looked for in it",
                    file=rel,
                )
            )
            continue
        visitor = _Producers(rel, glossary, bound, _local_names(tree))
        visitor.visit(tree)
        for term, where in visitor.found.items():
            functions.setdefault(term, set()).update(where)
        hidden.extend(visitor.hidden)

    bindings = [
        Binding(
            term.name,
            "rule" if term.kind == "value" else "computed",
            term.precondition_of,
            tuple(sorted(functions.get(term.name, ()))),
        )
        for term in bound
    ]
    unbound = {b.term for b in bindings if not b.functions}
    where = _layers(ctx, len(files))
    for term in bound:
        if term.name in unbound:
            problems.append(_unbound(ctx, schema, term, where, glossary))
    for site in hidden:
        out_of_sight = sorted(set(site.terms) & unbound)
        if out_of_sight:
            problems.append(
                Violation(
                    "hidden-binding",
                    WARNING,
                    f"`{site.code}` in {site.function} {site.why}, so the scan cannot see "
                    f"whether it produces {_listed(out_of_sight)}",
                    file=site.file,
                    line=site.line,
                    fix=site.fix,
                )
            )
    return bindings, problems


def manifest(ctx: Context, bindings: list[Binding]) -> dict:
    """What `onto gen` commits: which functions produce each bound term, and what guards a verb."""
    out: dict = {
        "context": ctx.name,
        "bindings": {
            b.term: {
                "binding": b.kind,
                **({"precondition_of": b.precondition_of} if b.precondition_of else {}),
                "functions": list(b.functions),
            }
            for b in bindings
        },
    }
    preconditions: dict[str, list[str]] = {}
    for b in bindings:
        if b.precondition_of:
            preconditions.setdefault(b.precondition_of, []).append(b.term)
    if preconditions:
        out["preconditions"] = dict(sorted(preconditions.items()))
    return out


@dataclass(frozen=True)
class _Hidden:
    """A place where bound terms may be produced without being written out."""

    file: str
    line: int
    function: str
    code: str
    why: str
    fix: str
    terms: tuple[str, ...]


def _local_names(tree: ast.Module) -> dict[str, str]:
    """Local name -> the name it was imported or assigned from: `import X as Y`, `Y = X`."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, (ast.Name, ast.Attribute))
        ):
            names[node.targets[0].id] = _named(node.value, names) or ""
    return names


def _named(node: ast.AST, names: dict[str, str]) -> str | None:
    """The glossary name an expression refers to: `Rule`, `generated.Rule`, or an alias of it."""
    if isinstance(node, ast.Name):
        return names.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class _Producers(ast.NodeVisitor):
    def __init__(self, rel: str, glossary: Glossary, bound: list[Term], names: dict[str, str]):
        self.rel = rel
        self.names = names
        self.rules = {t.parent: set() for t in bound if t.kind == "value"}
        for term in bound:
            if term.kind == "value":
                self.rules[term.parent].add(term.short_name)
        slots = {t.name for t in bound if t.kind == "slot"}
        # generated class -> the computed slots it carries
        self.computed = {
            t.name: carried
            for t in glossary.terms.values()
            if t.kind == "class" and (carried := slots & {a.name for a in t.attributes})
        }
        self.found: dict[str, set[str]] = {}
        self.hidden: list[_Hidden] = []
        self._scope: list[str] = []
        self._functions = 0
        self._compared: set[int] = set()

    # Only code inside a function binds: a module-level table produces nothing by itself.
    def _where(self) -> str | None:
        return f"{self.rel}::{'.'.join(self._scope)}" if self._functions else None

    def _enter(self, node, function: bool) -> None:
        self._scope.append(node.name)
        self._functions += function
        self.generic_visit(node)
        self._functions -= function
        self._scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node, False)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node, True)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node, True)

    def visit_Compare(self, node: ast.Compare) -> None:
        for operand in (node.left, *node.comparators):
            members = operand.elts if isinstance(operand, (ast.Tuple, ast.List, ast.Set)) else ()
            self._compared.update(id(n) for n in (operand, *members))
        self.generic_visit(node)

    def visit_match_case(self, node: ast.match_case) -> None:
        self._compared.update(id(n) for n in ast.walk(node.pattern))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        enum = _named(node.value, self.names)
        where = self._where()
        if where and id(node) not in self._compared and node.attr in self.rules.get(enum, ()):
            self.found.setdefault(f"{enum}.{node.attr}", set()).add(where)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        enum = _named(node.value, self.names)
        if enum in self.rules:
            self._looked_up(node, enum)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = _named(node.func, self.names)
        method = node.func.attr if isinstance(node.func, ast.Attribute) else None
        owner = _named(node.func.value, self.names) if method else None
        first = _named(node.args[0], self.names) if node.args else None
        if target in self.rules:
            self._looked_up(node, target)
        elif target == "getattr" and first in self.rules:
            self._looked_up(node, first)
        elif method in _FROM_DATA and owner in self.computed:
            self._built_from_data(node, owner, self.computed[owner])
        else:
            cls = owner if method == "model_construct" else target
            self._constructed(node, cls, self.computed.get(cls, set()))
        self.generic_visit(node)

    def _constructed(self, node: ast.Call, cls: str | None, computed: set[str]) -> None:
        passed = {kw.arg for kw in node.keywords}
        where = self._where()
        if where:
            for slot in computed & passed:
                self.found.setdefault(slot, set()).add(where)
        if None in passed and computed - passed:  # Cls(**data)
            self._built_from_data(node, cls, computed - passed)

    def _looked_up(self, node: ast.AST, enum: str) -> None:
        if not self._functions:
            return
        self.hidden.append(
            _Hidden(
                self.rel,
                node.lineno,
                ".".join(self._scope),
                ast.unparse(node),
                f"looks a {enum} up by a value known only when the code runs",
                f"write the rule out as {enum}.<VALUE> where it is enforced",
                tuple(f"{enum}.{value}" for value in self.rules[enum]),
            )
        )

    def _built_from_data(self, node: ast.AST, cls: str, slots: set[str]) -> None:
        if not self._functions:
            return
        self.hidden.append(
            _Hidden(
                self.rel,
                node.lineno,
                ".".join(self._scope),
                ast.unparse(node),
                f"builds {cls} from data instead of naming its slots",
                f"pass {_listed(sorted(slots), '=')} to {cls}(...) by name",
                tuple(slots),
            )
        )


def _listed(names: list[str], suffix: str = "") -> str:
    return ", ".join(f"{name}{suffix}" for name in names)


def _layers(ctx: Context, count: int) -> str:
    patterns = _listed([*ctx.domain_paths, *ctx.write_paths]) or "nothing"
    return f"{count} file(s) of {patterns}"


def _unbound(ctx: Context, schema: str, term: Term, where: str, glossary: Glossary) -> Violation:
    if term.kind == "value":
        found = f"{term.name} is declared `binding: rule`, but no function writes {term.name}"
        accepted = f"a function that enforces the rule and reports it as {term.name}"
    else:
        classes = " or ".join(f"{cls}(...)" for cls in term.used_by) or "a generated class"
        found = (
            f"{term.name} is declared `binding: computed`, but no function passes "
            f"{term.name}= to {classes}"
        )
        accepted = f"a function that computes it and passes {term.name}= to {classes} by name"
    return Violation(
        "unbound-rule",
        ERROR,
        f"{found}. Looked in {where}",
        file=schema,
        subject=term.name,
        fix=(
            f"write {accepted}, or name the file that already does in `write_paths` of "
            f"[contexts.{ctx.name}] in onto.toml. If the software no longer does this, withdraw "
            f"the binding: `onto ocr new --context {ctx.name} --term {term.name} "
            f'--title "Withdraw the binding on {term.name}" --justification "..."`'
        ),
    )


# --- the proof half --------------------------------------------------------------


def check(ws, context: str | None = None) -> tuple[list[ContextRules], list[Violation]]:
    """Both halves, for one context or all of them."""
    from .gates import traceability
    from .graph import build_graph

    if context is not None and context not in ws.cfg.contexts:
        raise ValueError(f"no bounded context '{context}' in onto.toml")
    selected = [c for c in ws.cfg.contexts.values() if context in (None, c.name)]
    declared = [c for c in selected if ws.glossaries[c.name].bound()]
    rows = {row.requirement: row for row in traceability(build_graph(ws))} if declared else {}

    results: list[ContextRules] = []
    problems: list[Violation] = []
    for ctx in declared:
        glossary = ws.glossaries[ctx.name]
        bindings, found = scan(ws.cfg, ctx, glossary)
        problems.extend(found)
        result = ContextRules(ctx.name, bindings)
        for binding in bindings:
            proofs, miss = _proof(ws, ctx, glossary, binding, rows)
            if proofs:
                result.proofs[binding.term] = proofs
            else:
                problems.append(miss)
        if ctx.bindings_json is None:
            problems.append(
                Violation(
                    "no-manifest",
                    WARNING,
                    f"[contexts.{ctx.name}] declares bindings but no `bindings_json`, so "
                    "`onto gen` writes no bindings manifest for it",
                    file="onto.toml",
                    fix=f'add bindings_json = "<path>.bindings.json" to [contexts.{ctx.name}]',
                )
            )
        results.append(result)
    return results, problems


def _proof(ws, ctx: Context, glossary: Glossary, binding: Binding, rows: dict):
    """(what proves the term, None) or ([], the violation that says what is missing)."""
    using = [
        item
        for item in ws.of_class("Requirement")
        if item.context == ctx.name
        and any(
            (term := glossary.get(name)) is not None and term.name == binding.term
            for name in item.values("uses_terms")
        )
    ]
    proofs = []
    for item in using:
        row = rows.get(item.id)
        tests = row.tests if row else {}
        passing = tuple(sorted(test for test, result in tests.items() if result == "pass"))
        if item.status == "done" and passing:
            proofs.append(Proof(item.id, passing))
    if proofs:
        return proofs, None

    name = binding.term
    accepted = (
        "Accepted: a Requirement with status done that lists it in uses_terms, verified by a "
        "Test with passing Evidence."
    )
    done = [item for item in using if item.status == "done"]
    tested = [item for item in done if rows.get(item.id) and rows[item.id].tests]
    if not using:
        found = f"no Requirement of {ctx.name} lists {name} in uses_terms"
        fix = (
            f"add {name} to uses_terms (and in backticks to ears_text) of the Requirement that "
            f"states it, or write one: `onto new Requirement bounded_context={ctx.name} "
            f'title="..." ears_text="..." uses_terms={name}`'
        )
    elif not done:
        states = _listed([f"{item.id} ({item.status})" for item in using])
        found = f"{name} is used by {states}, and none of them is done"
        fix = "finish the Requirement: it is done when `onto trace` holds for it"
    elif not tested:
        found = f"{name} is used by {_listed([i.id for i in done])}, which no Test verifies"
        fix = (
            f'`onto new Test bounded_context={ctx.name} title="..." verifies={done[0].id} '
            "path=<file>::<test>`, then `uv run pytest --onto-evidence`"
        )
    else:
        results = _listed(
            [
                f"{test} ({result or 'no evidence'})"
                for item in tested
                for test, result in sorted(rows[item.id].tests.items())
            ]
        )
        found = f"{name} is used by {_listed([i.id for i in tested])}, whose Tests are {results}"
        fix = "record what the tests show: `uv run pytest --onto-evidence`, and fix a failing one"
    return [], Violation(
        "unproven-rule",
        ERROR,
        f"{found}. {accepted}",
        file=ws.cfg.rel(ctx.schema),
        subject=name,
        fix=fix,
    )


# --- the command -----------------------------------------------------------------


def run(ws, fmt: str = "text", context: str | None = None) -> int:
    results, problems = check(ws, context)
    if fmt == "json":
        print(
            json.dumps(
                {
                    "contexts": [r.to_dict() for r in results],
                    "problems": [v.to_dict() for v in sorted(problems, key=report.sort_key)],
                },
                indent=2,
            )
        )
        return 1 if report.errors(problems) else 0

    count = sum(len(r.bindings) for r in results)
    if not count:
        print(
            "onto rules: no term declares a binding, so there is nothing to hold to code and "
            "proof. Annotate an enum `binding: rule` or a slot `binding: computed` to start."
        )
        return 0
    for result in results:
        print(f"{result.context}:")
        for b in result.bindings:
            proofs = result.proofs.get(b.term, ())
            proof = _listed([f"{p.requirement} by {_listed(list(p.tests))}" for p in proofs])
            print(f"  {b.term}  [{b.kind}]")
            print(f"      produced by: {_listed(list(b.functions)) or '-'}")
            print(f"      proven by:   {proof or '-'}")
    if problems:
        print("\n" + report.render_text(problems))
    print(f"\nonto rules: {count} bound term(s), {report.summary(problems)}")
    return 1 if report.errors(problems) else 0
