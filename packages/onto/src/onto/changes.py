"""Gates over what a branch changed, whatever tool changed it.

The guard hook sees only Claude's own file tools. A shell command, a script or
a person's editor writes the same files without it. These gates look at the
result instead: the difference between the branch and its base.

* An ontology source changed only if the branch also carries the
  OntologyChangeRequest that asks for it, in progress or done. A branch that
  brings the ontology layer into a repository has no earlier ontology to change.
* A generated file still matches the source it is generated from.
"""

from __future__ import annotations

from .config import CONFIG_FILE, Config, matches
from .failures import SourceUnreadable
from .gates import base_commit, base_refs, changed_files, has_commits, layer_at_base
from .guard import APPROVED
from .report import ERROR, Violation
from .workspace import Workspace

REQUESTED = "gate:OntologyChangeIsRequested"
GENERATED = "gate:GeneratedMatchesSource"
BASE = "gate:BranchBaseIsKnown"


def branch_problems(ws: Workspace, *, stop: bool = False) -> list[Violation]:
    """What the branch's changes break. Nothing outside a git repository.

    A branch with commits and no base cannot be judged by its changes, and
    these gates cannot fall back on judging everything, so that is a violation
    itself. At Stop it is passed over, since the agent cannot fetch a branch
    and blocking would hold the session for nothing: the uncommitted changes
    are judged, and the generated files are compared with their sources.
    """
    changed = changed_files(ws.cfg, or_uncommitted=True)
    if changed is None:
        return []
    problems = ontology_change_is_requested(ws, changed) if layer_at_base(ws.cfg) else []
    if stop:
        problems += generated_matches_source(ws.cfg, changed)
    else:
        problems += base_is_known(ws.cfg)
    return problems


def base_is_known(cfg: Config) -> list[Violation]:
    """A violation if the branch has commits and nothing to compare them with.

    Without a base every committed change is invisible, so the gates over what
    the branch changed would pass whatever it changed.
    """
    if not has_commits(cfg) or base_commit(cfg) is not None:
        return []
    tried = ", ".join(base_refs(cfg))
    return [
        Violation(
            BASE,
            ERROR,
            f"none of {tried} is in this repository, so what the branch committed cannot "
            "be compared with its base and the gates over its changes cannot fail",
            file=CONFIG_FILE,
            found=cfg.base_ref,
            fix=(
                "set base_ref under [workflow] in onto.toml to the default branch, and fetch "
                "it: in GitHub Actions, check out with `fetch-depth: 0`"
            ),
        )
    ]


def ontology_change_is_requested(ws: Workspace, changed: set[str]) -> list[Violation]:
    """One violation per changed ontology source that no request on the branch covers."""
    cfg = ws.cfg
    sources = sorted(rel for rel in changed if matches(rel, cfg.protected))
    if not sources:
        return []
    requested = {
        item.context
        for item in ws.of_class("OntologyChangeRequest")
        if item.rel in changed and item.status in APPROVED
    }
    context_of = {cfg.rel(ctx.schema): ctx.name for ctx in cfg.contexts.values()}
    problems = []
    for rel in sources:
        # Anything that is not one context's glossary is shared by all of them.
        context = context_of.get(rel)
        if context in requested or (context is None and requested):
            continue
        whose = f"for the {context} context" if context else "for any context"
        problems.append(
            Violation(
                REQUESTED,
                ERROR,
                f"{rel} is an ontology source and this branch changed it without an "
                f"OntologyChangeRequest {whose} that is in_progress or done",
                file=rel,
                allowed=APPROVED,
                fix=(
                    f"raise one with `onto ocr new --context {context or '<context>'} "
                    '--term <Term> --justification "..."` and have a person approve it on '
                    "this branch, or take the change back"
                ),
            )
        )
    return problems


def unreadable(cfg: Config, exc: SourceUnreadable) -> Violation:
    rel = cfg.rel(exc.path)
    return Violation(
        GENERATED,
        ERROR,
        f"{rel} cannot be read as YAML{exc.where}, so nothing can be generated from it",
        file=rel,
        fix="fix the syntax there, or take the change back",
    )


def generated_matches_source(cfg: Config, changed: set[str]) -> list[Violation]:
    """One violation per generated file that differs from what its source compiles to.

    Compiling takes over half a second, so it runs only when the branch touched
    a generated file or a source of one.
    """
    from . import gen

    generated = cfg.generated_files()
    if not changed & (set(generated) | set(generated.values())):
        return []
    try:
        results = gen.generate(cfg, check=True)
    except gen.GeneratorUnavailable:
        return []  # CI runs `onto gen --check`: a missing generator must not block a session
    except SourceUnreadable as exc:
        return [unreadable(cfg, exc)]
    return [
        Violation(
            GENERATED,
            ERROR,
            f"{result.path} no longer matches {generated[result.path]}",
            file=result.path,
            fix=(
                "run `onto gen`. If the generated file was edited, make the change in "
                f"{generated[result.path]} instead"
            ),
        )
        for result in results
        if result.status == "drift"
    ]
