"""The domain layer decides and reaches nothing: what an import contract cannot hold.

`lint-imports` forbids a list of modules, so a module nobody listed passes, and
it cannot see a builtin. This reads the source of the domain layer instead: it
may import only what is listed here, and it may not open a file or read the
clock. Another module of the domain layer is allowed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[1] / "src" / "call_qa_agent" / "domain"
ALLOWED = {"__future__", "collections.abc", "datetime", "call_qa_agent.generated"}
BUILTINS = {"open", "print", "input", "exec", "eval", "__import__", "breakpoint"}
CLOCK = {"now", "utcnow", "today"}


def reached(path: Path, source: str) -> list[str]:
    """What the module reaches that the domain layer may not, each with its line."""
    package = ["call_qa_agent", *path.relative_to(DOMAIN.parent).parts[:-1]]
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            above = package[: len(package) - node.level + 1] if node.level else []
            modules = [".".join([*above, *([node.module] if node.module else [])])]
        else:
            modules = []
            if isinstance(node, ast.Name) and node.id in BUILTINS:
                found.append(f"line {node.lineno}: {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in CLOCK:
                found.append(f"line {node.lineno}: .{node.attr}")
        found += [
            f"line {node.lineno}: import {m}"
            for m in modules
            if m not in ALLOWED and not f"{m}.".startswith("call_qa_agent.domain.")
        ]
    return found


@pytest.mark.parametrize("path", sorted(DOMAIN.rglob("*.py")), ids=lambda path: path.name)
def test_a_domain_module_imports_only_what_is_allowed_and_reaches_nothing(path):
    assert reached(path, path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "line",
    [
        "import requests",
        "import hashlib",
        "from pathlib import Path",
        "from ..ledger import Ledger",
        "from .. import ledger",
        "open('/tmp/x.jsonl', 'a').write('x')",
        "recorded_at = datetime.now()",
        "import datetime as d; d.date.today()",
    ],
)
def test_the_check_reports_what_a_domain_module_may_not_reach(line):
    source = (DOMAIN / "publication.py").read_text(encoding="utf-8") + "\n" + line + "\n"

    assert len(reached(DOMAIN / "publication.py", source)) == 1
