"""The typed write path for work items: `onto new`.

A work item created here is validated before anything touches the disk. If it
breaks a rule, nothing is written and the caller gets the violations, with the
values that would have been accepted, so it can correct itself and try again.
"""

from __future__ import annotations

from pathlib import Path

from . import frontmatter
from .guard import APPROVED
from .report import ERROR, Violation, errors
from .workitems import validate_item
from .workspace import WorkItem, Workspace

DERIVED = {"Evidence": "evidence is recorded by a test run: `onto evidence collect`"}


def next_id(ws: Workspace, cls: str) -> str:
    """The next free id of a class: one past the highest in use."""
    prefix = ws.schema.id_prefix(cls)
    used = [int(item.id.rsplit("-", 1)[1]) for item in ws.items if item.cls == cls]
    return f"{prefix}-{max(used, default=0) + 1:04d}"


def parse_fields(ws: Workspace, cls: str, pairs: list[str]) -> dict:
    """Turn `key=value` arguments into frontmatter. Multivalued slots take commas or repeats."""
    multivalued = {slot.name for slot in ws.schema.slots(cls) if slot.multivalued}
    fields: dict = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            raise ValueError(f"'{pair}' is not of the form key=value")
        if key in multivalued:
            fields.setdefault(key, []).extend(v.strip() for v in value.split(",") if v.strip())
        else:
            fields[key] = value
    return fields


def create(
    ws: Workspace, cls: str, fields: dict, body: str = ""
) -> tuple[Path | None, list[Violation]]:
    """Create a work item. Returns (path, warnings) or (None, violations) if it was refused."""
    classes = tuple(c for c in ws.schema.record_classes if c not in DERIVED)
    if cls in DERIVED:
        return None, [
            Violation("derived", ERROR, f"{cls} is never created by hand: {DERIVED[cls]}")
        ]
    if cls not in classes:
        return None, [
            Violation(
                "unknown-class",
                ERROR,
                f"'{cls}' is not a class of work item",
                found=cls,
                allowed=classes,
            )
        ]

    if cls == "OntologyChangeRequest" and fields.get("status") in APPROVED:
        return None, [
            Violation(
                "approval",
                ERROR,
                f"a person approves an OntologyChangeRequest: it is not created {fields['status']}",
                found=fields["status"],
                fix="create it as a draft and have a person set its status",
            )
        ]

    order = [slot.name for slot in ws.schema.slots(cls)]
    given = {"status": "draft", **fields, "id": next_id(ws, cls)}
    meta = {key: given[key] for key in order if key in given}
    meta.update({key: value for key, value in given.items() if key not in meta})

    path = ws.cfg.work_dir / f"{meta['id']}.md"
    text = frontmatter.render(meta, body)
    item = WorkItem(path, ws.cfg.rel(path), meta, body, text, cls)
    problems = validate_item(ws, item)
    if errors(problems):
        return None, problems

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    ws.reload()
    return path, problems
