"""Guard the files nobody should edit casually.

* Generated artefacts are never edited: their source is.
* Evidence is never written by hand: a test run produces it.
* The ontology sources change only while an OntologyChangeRequest is in
  progress, and then (by default) each edit is put to a person to confirm.

The guard is a speed bump with a paper trail, not the control itself: the
control is the pull request, reviewed by the owners named in CODEOWNERS.
"""

from __future__ import annotations

from .config import matches
from .workspace import Workspace

ALLOW, DENY, ASK = "allow", "deny", "ask"


def decide(ws: Workspace, path: str) -> tuple[str, str]:
    """(decision, reason) for an edit to `path`."""
    cfg = ws.cfg
    rel = cfg.rel(path)

    generated = cfg.generated_files()
    manifests = {cfg.rel(c.bindings_json) for c in cfg.contexts.values() if c.bindings_json}
    if rel in manifests:
        return DENY, (
            f"{rel} is generated from {generated[rel]} and the functions it binds. "
            "Run `onto gen` to bring it up to date."
        )
    if rel in generated:
        return DENY, (
            f"{rel} is generated from {generated[rel]}. Change {generated[rel]} "
            "(through an OntologyChangeRequest) and run `onto gen`."
        )

    if rel.startswith(cfg.rel(cfg.evidence_dir) + "/"):
        return DENY, (
            f"{rel} is evidence, which only a test run may write: "
            "run `onto evidence collect` or `pytest --onto-evidence`."
        )

    if not matches(rel, cfg.protected):
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
