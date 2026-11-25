"""Whether onto.toml and the Claude Code settings still switch the gates on.

Every gate reads its configuration from files the branch under review can
change. A gate that was configured away passes in silence, so the settings
that would do that are checked for themselves: `onto validate` and `onto trace`
report them. This checks what the files say now. It cannot tell that a branch
loosened a setting which is still a valid one: that is what the review of
onto.toml by its owners is for.
"""

from __future__ import annotations

import json
import re

from .config import CONFIG_FILE, Config, matches
from .report import ERROR, Violation

RULE = "gate-config"
SETTINGS = ".claude/settings.json"
EDITS = ("Edit", "Write")
# Event -> (what the hook's command has to run, the tools its matcher has to cover).
HOOKS = {
    "PreToolUse": (r"\bonto guard\b", EDITS),
    "PostToolUse": (r"\bonto check-terms --changed-from-stdin\b", EDITS),
    "Stop": (r"\bonto trace --gate stop\b", ()),
}
_ITSELF = re.compile(r"(HEAD|@)([~^@].*)?")  # the branch compared with itself changed nothing


def problems(cfg: Config) -> list[Violation]:
    """One violation per setting in onto.toml that leaves a gate with nothing to check."""

    def found(message: str, value: str, fix: str) -> Violation:
        return Violation(RULE, ERROR, message, file=CONFIG_FILE, found=value, fix=fix)

    out = []
    if not cfg.gate_shapes:
        out.append(
            found(
                "[workflow] gates lists no file, so no graph gate runs and a done "
                "Requirement needs no Test",
                "gates = []",
                'list the graph gates, such as gates = ["ontology/shapes/gates.shacl.ttl"]',
            )
        )
    sources = [cfg.workflow_schema, *(c.schema for c in cfg.contexts.values()), *cfg.gate_shapes]
    for rel in sorted({cfg.rel(source) for source in sources}):
        if not matches(rel, cfg.protected):
            out.append(
                found(
                    f"[guard] protected does not cover {rel}, so it changes without an "
                    "OntologyChangeRequest",
                    rel,
                    f"add {rel}, or a glob that matches it, to protected",
                )
            )
    if _ITSELF.fullmatch(cfg.base_ref.strip()):
        out.append(
            found(
                f"[workflow] base_ref is {cfg.base_ref}, the branch itself, so the gates "
                "over what the branch changed see no change",
                cfg.base_ref,
                'set base_ref to the default branch, such as "origin/main"',
            )
        )
    return out


def hooks_missing(cfg: Config) -> list[Violation]:
    """One violation per hook of the gates that the settings file no longer registers."""
    try:
        registered = json.loads((cfg.root / SETTINGS).read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError):
        registered = {}
    return [
        Violation(
            "hook",
            ERROR,
            f"hooks.{event} runs no command matching `{command.replace(chr(92) + 'b', '')}`"
            + (f" for {' and '.join(tools)}" if tools else ""),
            file=SETTINGS,
            found=event,
            fix="put back the hook `onto init` writes: run `onto init`, or copy it from "
            "the settings template",
        )
        for event, (command, tools) in HOOKS.items()
        if not _registered(registered, event, command, tools)
    ]


def _registered(registered, event: str, command: str, tools: tuple[str, ...]) -> bool:
    groups = registered.get(event, []) if isinstance(registered, dict) else []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict) or not _covers(group.get("matcher"), tools):
            continue
        for hook in group.get("hooks", []) if isinstance(group.get("hooks"), list) else []:
            if isinstance(hook, dict) and re.search(command, str(hook.get("command", ""))):
                return True
    return False


def _covers(matcher, tools: tuple[str, ...]) -> bool:
    if matcher in (None, "", "*"):
        return True
    try:
        return isinstance(matcher, str) and all(re.fullmatch(matcher, tool) for tool in tools)
    except re.error:
        return False
