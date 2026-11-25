"""The permission rules that keep Claude Code out of generated files and evidence.

The guard hook answers for the Edit, Write and NotebookEdit tools. A deny rule
in .claude/settings.json reaches further: Claude Code also applies an Edit rule
to the target of a shell redirect and to the file commands it recognises, such
as `sed` and `tee`. The rules are derived from onto.toml, so the list in the
settings file is checked against it rather than kept by hand.

Ontology sources get no rule: a deny cannot be lifted while a request is in
progress, and the guard can.
"""

from __future__ import annotations

import json

from .config import Config
from .report import ERROR, Violation

SETTINGS = ".claude/settings.json"


def rules(cfg: Config) -> list[str]:
    """One rule per generated file and one for the evidence folder, anchored at the root."""
    targets = [*sorted(cfg.generated_files()), cfg.rel(cfg.evidence_dir) + "/**"]
    return [f"Edit(/{target})" for target in targets]


def render(cfg: Config) -> str:
    """The rules as the JSON list to put under permissions.deny."""
    return json.dumps(rules(cfg), indent=2)


def missing(cfg: Config) -> list[Violation]:
    """One violation per derived rule that the settings file does not deny."""
    try:
        settings = json.loads((cfg.root / SETTINGS).read_text(encoding="utf-8"))
        denied = settings.get("permissions", {}).get("deny", [])
    except (OSError, ValueError, AttributeError):
        denied = []
    return [
        Violation(
            "deny-rule",
            ERROR,
            f"permissions.deny does not list {rule}",
            file=SETTINGS,
            found=rule,
            fix="add the rules `onto guard --deny-rules` prints to permissions.deny",
        )
        for rule in rules(cfg)
        if rule not in denied
    ]
