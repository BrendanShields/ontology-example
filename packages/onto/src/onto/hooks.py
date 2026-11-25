"""Glue for Claude Code hooks: reading the event on stdin and answering in its formats.

Exit codes follow the hooks reference: 0 lets the action through (JSON on stdout
is honoured), 2 blocks and feeds stderr back to Claude, and any other code is a
non-blocking error, so a broken tool never stops the session by accident.
"""

from __future__ import annotations

import json
import sys

BLOCK = 2  # the exit code Claude Code treats as "blocked: here is why"


def read_event(stream=None) -> dict:
    """The hook's JSON input, or {} when there is none (run by hand, or not JSON)."""
    stream = stream if stream is not None else sys.stdin
    try:
        if stream.isatty():
            return {}
        raw = stream.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return event if isinstance(event, dict) else {}


def edited_file(event: dict) -> str | None:
    """The file an Edit, Write or NotebookEdit tool call is about."""
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for name in ("file_path", "notebook_path"):
            if isinstance(tool_input.get(name), str):
                return tool_input[name]
    return None


def readable(tool_input: dict) -> bool:
    """False if `edits` is there and is not a list of edits: nothing can say what it writes."""
    edits = tool_input.get("edits")
    return edits is None or (isinstance(edits, list) and all(isinstance(e, dict) for e in edits))


def text_after(tool_input: dict, current: str | None) -> str | None:
    """The file's text once the tool call has run. None if the call would not apply."""
    if isinstance(tool_input.get("content"), str):  # Write
        return tool_input["content"]
    edits = tool_input.get("edits") if isinstance(tool_input.get("edits"), list) else [tool_input]
    text = current
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        old, new = edit.get("old_string"), edit.get("new_string")
        if text is None or not isinstance(old, str) or not isinstance(new, str) or old not in text:
            return None
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def inserted_text(event: dict) -> str | None:
    """The text an Edit put in. None for a Write, which replaces the whole file."""
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict) and isinstance(tool_input.get("new_string"), str):
        return tool_input["new_string"]
    return None


def permission_decision(decision: str, reason: str) -> str:
    """PreToolUse answer: 'allow', 'deny' or 'ask', with the reason shown for it."""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        }
    )


def additional_context(event_name: str, text: str) -> str:
    """Non-blocking context for Claude (PostToolUse) or for a starting subagent (SubagentStart)."""
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}
    )
