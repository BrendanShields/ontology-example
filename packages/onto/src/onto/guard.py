"""Guard the files nobody should edit casually.

* Generated artefacts are never edited: their source is.
* Evidence is never written by hand: a test run produces it. That holds for the
  evidence folder and for any work item file named or identified as Evidence.
* The files that configure the gates are put to a person before they change.
* A request is approved by a person: so is the edit that marks it approved.
* The ontology sources change only while an OntologyChangeRequest is in
  progress, and then (by default) each edit is put to a person to confirm.

The guard is a speed bump with a paper trail, not the control itself: the
control is the pull request, reviewed by the owners named in CODEOWNERS. It
sees Claude's file tools only. What a shell command wrote is caught afterwards
by the branch gates in `onto trace` (see changes.py).
"""

from __future__ import annotations

from . import frontmatter, hooks, paths
from .config import CONFIG_FILE, matches
from .workspace import Workspace

ALLOW, DENY, ASK = "allow", "deny", "ask"
APPROVED = ("in_progress", "done")  # the statuses a person gives a request they accept

# Not configurable: a list read from onto.toml could be emptied by editing onto.toml.
GATE_CONFIG = (CONFIG_FILE, ".claude/settings.json", ".claude/settings.local.json")


def decide(ws: Workspace, path: str, tool_input: dict | None = None) -> tuple[str, str]:
    """(decision, reason) for an edit to `path`, given what the tool was asked to write."""
    cfg = ws.cfg
    rel = cfg.rel(path)  # as written, for messages
    key = paths.key(cfg, path)  # as the filesystem compares it, for deciding

    def fold(patterns) -> tuple[str, ...]:
        return tuple(paths.fold(cfg, pattern) for pattern in patterns)

    manifests = {cfg.rel(c.bindings_json) for c in cfg.contexts.values() if c.bindings_json}
    for target, source in cfg.generated_files().items():
        if key == paths.fold(cfg, target) and target in manifests:
            return DENY, (
                f"{target} is generated from {source} and the functions it binds. "
                "Run `onto gen` to bring it up to date."
            )
        if key == paths.fold(cfg, target):
            return DENY, (
                f"{target} is generated from {source}. Change {source} "
                "(through an OntologyChangeRequest) and run `onto gen`."
            )

    if key.startswith(paths.fold(cfg, cfg.rel(cfg.evidence_dir)) + "/"):
        return DENY, (
            f"{rel} is evidence, which only a test run may write: "
            "run `onto evidence collect` or `pytest --onto-evidence`."
        )

    if matches(key, fold((*GATE_CONFIG, *cfg.gate_files))):
        return ASK, (
            f"{rel} configures the gates: what they protect, when they run, or who reviews. "
            "Confirm that this change to the gates themselves is intended."
        )

    in_work = key.startswith(paths.fold(cfg, cfg.rel(cfg.work_dir)) + "/")
    if in_work and _is_evidence(ws, path, tool_input):
        return DENY, (
            f"{rel} would be Evidence, which only a test run may write, and only under "
            f"{cfg.rel(cfg.evidence_dir)}/: run `onto evidence collect` or "
            "`pytest --onto-evidence`."
        )

    if in_work and tool_input:
        if not hooks.readable(tool_input):
            return ASK, (
                f"The guard cannot read this edit to {rel}, so it cannot tell whether the edit "
                "approves an OntologyChangeRequest. Confirm that it does not."
            )
        approved = _approval(ws, path, tool_input)
        if approved:
            return ASK, (
                f"This edit sets {approved[0]} to {approved[1]}. A person approves an "
                "OntologyChangeRequest: confirm that you do."
            )

    if not matches(key, fold(cfg.protected)):
        return ALLOW, ""

    open_requests = sorted(
        item.id for item in ws.of_class("OntologyChangeRequest") if item.status == "in_progress"
    )
    if not open_requests:
        return DENY, (
            f"{rel} is an ontology source and changes only through an OntologyChangeRequest. "
            "None is in progress. Raise one with `onto ocr new --context <context> --term <Term> "
            '--justification "..."`, and have a person set its status to in_progress. '
            "The ontology-change skill has the steps."
        )
    requests = ", ".join(open_requests)
    if cfg.on_open_ocr == ALLOW:
        return ALLOW, f"ontology edit under {requests}"
    return ASK, (
        f"Ontology edit to {rel} under {requests}. Confirm that this edit is what the "
        "request asks for."
    )


def _is_evidence(ws: Workspace, path: str, tool_input: dict | None) -> bool:
    """Whether the file is named as Evidence is, or the edit leaves it with the id of one."""
    target = ws.cfg.root / path
    names = [target.name.split(".", 1)[0]]
    if tool_input and hooks.readable(tool_input):
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            current = None
        names.append(_frontmatter(hooks.text_after(tool_input, current)).get("id"))
    return any(
        isinstance(name, str) and ws.schema.class_for_id(name) == "Evidence" for name in names
    )


def _approval(ws: Workspace, path: str, tool_input: dict) -> tuple[str, str] | None:
    """(request id, status) if the edit leaves an approved OntologyChangeRequest that was not there.

    The file is compared as a whole, before and after. An approval spread over
    edits that each change one thing (the id away, the status, the id back)
    still ends in one edit that makes the file an approved request.
    """
    target = ws.cfg.root / path
    try:
        current = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        current = None
    after = _approved_request(ws, hooks.text_after(tool_input, current))
    return after if after != _approved_request(ws, current) else None


def _approved_request(ws: Workspace, text: str | None) -> tuple[str, str] | None:
    """(id, status) if the text is an OntologyChangeRequest in an approved status."""
    meta = _frontmatter(text)
    identifier, status = meta.get("id"), str(meta.get("status", ""))
    # Loading the schema is the slow part, so it comes after everything that can say no.
    if status not in APPROVED or not isinstance(identifier, str):
        return None
    if ws.schema.class_for_id(identifier) != "OntologyChangeRequest":
        return None
    return identifier, status


def _frontmatter(text: str | None) -> dict:
    try:
        return frontmatter.split(text or "")[0]
    except frontmatter.FrontmatterError:
        return {}
