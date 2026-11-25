"""Check the vocabulary of domain-layer code against its context's glossary.

Two rules, with different weight on purpose:

* denied-term (error, blocks): an identifier, string or comment uses a name the
  glossary has explicitly retired. This is precise, so it may block.
* unknown-term (warning): a class or field is *defined* in the domain layer
  under a name the glossary does not have. Definitions are where vocabulary is
  coined, but a helper class is not always a domain concept, so this only warns.

Nothing is checked outside the `domain_paths` of a bounded context.
"""

from __future__ import annotations

import ast

from .glossary import Glossary
from .report import ERROR, WARNING, Violation
from .textscan import DeniedMatcher
from .workspace import Workspace


def check_file(
    ws: Workspace, rel_path: str, text: str, only_lines: set[int] | None = None
) -> list[Violation]:
    """Vocabulary problems in one file. `only_lines` restricts the report to changed lines."""
    context = ws.cfg.domain_context_of(rel_path)
    if context is None:
        return []
    glossary = ws.glossaries[context.name]
    problems = _denied(glossary, rel_path, text)
    if rel_path.endswith(".py"):
        problems.extend(_coined(glossary, rel_path, text))
    if only_lines is not None:
        problems = [p for p in problems if p.line in only_lines]
    return problems


def unchecked_layers(ws: Workspace) -> list[Violation]:
    """A warning for each bounded context that has code and a domain layer matching no file.

    Such a pattern is usually mistyped, a folder without a glob or a path that
    is not relative to the repository root, and the vocabulary check then
    passes because it reads nothing.
    """
    from .config import matches

    def any_file(patterns) -> bool:
        for pattern in patterns:
            base = ws.cfg.root / pattern.split("*", 1)[0]
            base = base if base.is_dir() else base.parent
            for path in base.rglob("*") if base.is_dir() else ():
                rel = ws.cfg.rel(path)
                if path.is_file() and "__pycache__" not in rel and matches(rel, (pattern,)):
                    return True
        return False

    return [
        Violation(
            rule="unchecked-layer",
            severity=WARNING,
            message=(
                f"domain_paths of [contexts.{context.name}] ({', '.join(context.domain_paths)}) "
                "match no file although the context has code, so its vocabulary is not checked"
            ),
            file="onto.toml",
            fix="write each as a glob from the repository root, such as src/app/domain/**",
        )
        for context in ws.cfg.contexts.values()
        if context.domain_paths and not any_file(context.domain_paths) and any_file(context.paths)
    ]


def _ocr_hint(glossary: Glossary, name: str) -> str:
    return (
        "if this is a different concept, raise an OntologyChangeRequest: "
        f'onto ocr new --context {glossary.name} --term {name} --justification "..."'
    )


def _denied(glossary: Glossary, rel_path: str, text: str) -> list[Violation]:
    problems: list[Violation] = []
    for hit in DeniedMatcher(glossary.denied_entries()).find(text):
        if hit.suppressed:
            continue
        problems.append(
            Violation(
                "denied-term",
                ERROR,
                f"'{hit.text}' uses '{hit.synonym}', a denied synonym: "
                f"the {glossary.name} glossary calls this {hit.term.name}",
                file=rel_path,
                line=hit.line,
                found=hit.text,
                suggestions=(hit.term.name,),
                fix=f"rename it to use {hit.term.name}; {_ocr_hint(glossary, hit.text)}",
            )
        )
    return problems


def suppressed(ws: Workspace, rel_path: str, text: str) -> int:
    """How many denied synonyms the file accepts with the allow pragma."""
    context = ws.cfg.domain_context_of(rel_path)
    if context is None:
        return 0
    matcher = DeniedMatcher(ws.glossaries[context.name].denied_entries())
    return sum(1 for hit in matcher.find(text) if hit.suppressed)


def _coined(glossary: Glossary, rel_path: str, text: str) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []  # not this gate's job: the interpreter and the linter report it

    problems: list[Violation] = []

    def warn(name: str, what: str, line: int) -> None:
        problems.append(
            Violation(
                "unknown-term",
                WARNING,
                f"{what} is defined in the domain layer but '{name}' is not a term of the "
                f"{glossary.name} glossary",
                file=rel_path,
                line=line,
                found=name,
                suggestions=glossary.suggest(name),
                fix=f"use the glossary's name for it; {_ocr_hint(glossary, name)}",
            )
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name.startswith("_") or _is_error(node):
            continue
        term = glossary.get(node.name)
        if term is None or term.kind not in ("class", "enum"):
            warn(node.name, f"class {node.name}", node.lineno)
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                name = statement.target.id
                slot = glossary.get(name)
                if not name.startswith("_") and (slot is None or slot.kind != "slot"):
                    warn(name, f"field {node.name}.{name}", statement.lineno)
    return problems


def _is_error(node: ast.ClassDef) -> bool:
    """Exception classes are plumbing, not vocabulary."""
    names = [node.name]
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return any(n.endswith(("Error", "Exception")) for n in names)


def changed_lines(text: str, new_string: str | None) -> set[int] | None:
    """The lines an edit touched, given the text it inserted.

    None means "the whole file" (a full write, or an insertion that cannot be
    located). An empty set means the edit only removed text.
    """
    if new_string is None:
        return None
    if not new_string.strip():
        return set()
    lines: set[int] = set()
    start = text.find(new_string)
    if start < 0:
        return None
    while start >= 0:
        first = text.count("\n", 0, start) + 1
        last = first + new_string.count("\n")
        lines.update(range(first, last + 1))
        start = text.find(new_string, start + len(new_string))
    return lines
