"""The `onto` command: every gate, query and generator of the ontology layer.

Exit codes: 0 clean, 1 problems found (or the tool itself failed), 2 only from
the hook modes, where Claude Code reads it as "blocked: here is why".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, report
from .config import ConfigError
from .failures import SourceUnreadable, describe
from .hooks import BLOCK


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 1
    try:
        return args.handler(args)
    except (ConfigError, FileNotFoundError, ValueError, KeyError) as exc:
        # Deliberately not exit code 2: a tool that cannot run must not block a session.
        print(f"onto: {describe(exc)}", file=sys.stderr)
        return 1


def _workspace():
    from .workspace import Workspace

    return Workspace.at()


def _emit(problems: list, fmt: str, stream=None) -> None:
    stream = stream or sys.stdout
    if fmt == "json":
        print(report.render_json(problems), file=stream)
    elif problems:
        print(report.render_text(problems), file=stream)


# --- orientation -----------------------------------------------------------------


def _overview(args) -> int:
    from .slicing import render_overview

    print(render_overview(_workspace(), args.context), end="")
    return 0


def _resolve(args) -> int:
    import json

    ws = _workspace()
    glossaries = [ws.glossaries[args.context]] if args.context else list(ws.glossaries.values())
    found = False
    answers = []
    for glossary in glossaries:
        resolution = glossary.resolve(args.name)
        found = found or resolution.found
        answers.append((glossary, resolution))
    if args.format == "json":
        print(
            json.dumps(
                [
                    {
                        "query": r.query,
                        "context": g.name,
                        "status": r.status,
                        "terms": [
                            {
                                "name": t.short_name,
                                "kind": t.kind,
                                "iri": t.iri,
                                "definition": t.definition,
                                "classification": t.classification,
                            }
                            for t in r.terms
                        ],
                        "denied_synonym": r.denied_synonym,
                        "suggestions": list(r.suggestions),
                    }
                    for g, r in answers
                ],
                indent=2,
            )
        )
        return 0 if found else 1

    from .workitems import explain

    for glossary, resolution in answers:
        if resolution.found:
            for term in resolution.terms:
                note = "" if resolution.status == "exact" else f"  <- write it as {term.short_name}"
                tags = f"{term.kind}, {glossary.name}"
                if term.classification != "internal":
                    tags += f", {term.classification}"
                print(f"{term.short_name} ({tags}){note}")
                print(f"  {term.definition}")
                print(f"  iri: {term.iri}")
                if term.denied_synonyms:
                    print(f"  never write: {', '.join(term.denied_synonyms)}")
        else:
            _, message, extra = explain(glossary, resolution)
            print(message)
            if extra.get("suggestions"):
                print(f"  did you mean: {', '.join(extra['suggestions'])}")
            print(f"  fix: {extra['fix']}")
    return 0 if found else 1


def _current_task(args) -> int:
    from .slicing import current_task

    task = current_task(_workspace())
    if task is None:
        print(
            "onto: no task in hand (set ONTO_TASK, name the branch after it, or have "
            "exactly one Task in_progress)",
            file=sys.stderr,
        )
        return 1
    print(task.id)
    return 0


def _slice(args) -> int:
    from . import hooks, slicing

    ws = _workspace()
    task = args.task
    if not task and not args.term:
        current = slicing.current_task(ws)
        task = current.id if current else None
    if not task and not args.term:
        if args.for_subagent:
            note = (
                "No task is in hand, so no ontology slice was prepared. Before writing domain "
                "code run `onto slice --task <TASK-id>`."
            )
            print(hooks.additional_context("SubagentStart", note))
            return 0
        raise ValueError("no task in hand: pass --task TASK-0000 or --term <Term>")

    built, text = slicing.build_within_budget(
        ws,
        args.max_tokens,
        task=task,
        terms=args.term or None,
        context=args.context,
        depth=args.depth,
        files=[_from_here(ws, name) for name in args.file or ()] or None,
    )
    fmt = "context-json" if args.for_subagent else args.format
    if fmt == "json":
        print(slicing.render_json(ws, built))
    elif fmt == "context-json":
        print(hooks.additional_context("SubagentStart", text))
    else:
        print(text, end="")
        size = slicing.estimate_tokens(text)
        over = f", over the budget of {args.max_tokens}" if size >= args.max_tokens else ""
        print(f"(about {size} tokens, estimated{over})", file=sys.stderr)
    return 0


def _from_here(ws, name: str) -> str:
    """A path as the person wrote it: from where they stand, when that is inside the repository."""
    here = Path.cwd().resolve()
    return str(here / name) if here.is_relative_to(ws.cfg.root) else name


# --- file-level gates ------------------------------------------------------------


def _glossary_problems(ws) -> list:
    allowed = ws.schema.enum_values("ClassificationEnum")
    problems = []
    for glossary in ws.glossaries.values():
        problems.extend(glossary.lint(allowed, ws.cfg.rel(glossary.context.schema)))
    return problems


def _validate(args) -> int:
    from .workitems import validate

    ws = _workspace()
    only = {ws.cfg.rel(Path(p).resolve()) for p in args.paths} or None
    loaded = {item.rel for item in ws.items} | {p.file for p in ws.load_problems}
    for rel in sorted((only or set()) - loaded):
        # Saying "0 errors" of a file that was never read would be a clean check of nothing.
        print(f"onto validate: {rel} is not a work item file under work/", file=sys.stderr)
        return 1
    problems = validate(ws, only)
    if only is None:
        from . import gateconfig

        problems = gateconfig.problems(ws.cfg) + _glossary_problems(ws) + problems
    _emit(problems, args.format)
    if args.format == "text":
        checked = len(only) if only else len(ws.items)
        print(f"onto validate: {checked} work item(s), {report.summary(problems)}")
    return 1 if report.errors(problems) else 0


def _domain_files(ws) -> list[str]:
    """Every file in the domain layer of any bounded context."""
    from .config import matches

    found: set[str] = set()
    for context in ws.cfg.contexts.values():
        for pattern in context.domain_paths:
            base = ws.cfg.root / pattern.split("*", 1)[0]
            base = base if base.is_dir() else base.parent
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                rel = ws.cfg.rel(path)
                if path.is_file() and "__pycache__" not in rel and matches(rel, (pattern,)):
                    found.add(rel)
    return sorted(found)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _check_terms(args) -> int:
    from . import hooks, terms

    ws = _workspace()
    if args.changed_from_stdin:
        return _check_terms_hook(ws, hooks.read_event())

    files = [ws.cfg.rel(Path(p).resolve()) for p in args.paths] or _domain_files(ws)
    problems: list = [] if args.paths else terms.unchecked_layers(ws)
    allowed = 0
    for rel in files:
        text = _read(ws.cfg.root / rel)
        if text is None and args.paths:
            print(f"onto check-terms: {rel} cannot be read as text", file=sys.stderr)
            return 1
        if text is not None:
            problems.extend(terms.check_file(ws, rel, text))
            allowed += terms.suppressed(ws, rel, text)
    _emit(problems, args.format)
    if args.format == "text":
        note = f", {allowed} accepted with '# onto: allow-term'" if allowed else ""
        print(f"onto check-terms: {len(files)} file(s), {report.summary(problems)}{note}")
    return 1 if report.errors(problems) else 0


def _check_terms_hook(ws, event: dict) -> int:
    """PostToolUse: check the file an Edit or Write just touched."""
    from . import hooks, paths, terms
    from .workitems import validate

    file = hooks.edited_file(event)
    if not file:
        return 0
    rel = ws.cfg.rel(paths.stored(ws.cfg.root / file))
    text = _read(ws.cfg.root / rel)
    if text is None:
        return 0

    work_prefix = ws.cfg.rel(ws.cfg.work_dir) + "/"
    if rel.startswith(work_prefix) and rel.endswith(".md"):
        problems = validate(ws, {rel})
        what = "work item"
    else:
        lines = terms.changed_lines(text, hooks.inserted_text(event))
        problems = terms.check_file(ws, rel, text, lines)
        what = "domain vocabulary"
    if not problems:
        return 0
    rendered = report.render_text(problems)
    if report.errors(problems):
        print(f"onto: {what} check failed for {rel}\n{rendered}", file=sys.stderr)
        return BLOCK
    print(hooks.additional_context("PostToolUse", f"onto: {what} warnings for {rel}\n{rendered}"))
    return 0


def _guard(args) -> int:
    """PreToolUse: decide whether an Edit or Write may touch its target."""
    from . import guard, hooks
    from .config import find_root
    from .workspace import Workspace

    root = find_root()  # no ontology layer here: nothing to guard, and main() says so
    if args.deny_rules or args.check_settings:
        return _deny_rules(_workspace().cfg, check=args.check_settings)
    event = {} if args.path else hooks.read_event()
    file = args.path or hooks.edited_file(event)
    if not file:
        return 0
    try:
        decision, reason = guard.decide(Workspace.at(root), file, event.get("tool_input"))
    except Exception as exc:
        if args.path:
            raise
        # A guard that cannot decide must not wave the edit through: an exit code of 1 is
        # a non-blocking error to Claude Code. It does not block either. A person decides.
        decision = guard.ASK
        reason = (
            f"The guard could not decide on this edit ({type(exc).__name__}: {describe(exc)}). "
            "Confirm that the file is not one it protects, and run `onto validate`."
        )
    if args.path:  # asked by hand: just say what would happen
        print(f"{decision}: {reason}" if reason else decision)
        return 0
    if decision == guard.DENY:
        print(f"onto guard: {reason}", file=sys.stderr)
        return BLOCK
    if decision == guard.ASK:
        print(hooks.permission_decision("ask", reason))
    return 0


def _deny_rules(cfg, *, check: bool) -> int:
    from . import denyrules, gateconfig

    if not check:
        print(denyrules.render(cfg))
        return 0
    problems = denyrules.missing(cfg) + gateconfig.hooks_missing(cfg)
    _emit(problems, "text")
    print(f"onto guard --check-settings: {report.summary(problems)}")
    return 1 if problems else 0


# --- the graph -------------------------------------------------------------------


def _build(args) -> int:
    from rdflib import RDF

    from . import guard
    from .graph import build_graph

    ws = _workspace()
    if args.out:
        # `onto` runs without a permission prompt, so it must not be a way round the guard.
        out = Path(args.out).resolve()
        decision, reason = guard.decide(ws, str(out))
        if decision != guard.ALLOW or reason:
            raise ValueError(
                f"--out {ws.cfg.rel(out)} is a file the guard protects, and the graph "
                "is not written over it: name another file"
            )
    graph = build_graph(ws)
    if args.out:
        out.write_text(graph.serialize(args.format), encoding="utf-8")
    counts: dict[str, int] = {}
    for item in ws.items:
        if item.cls:
            counts[item.cls] = counts.get(item.cls, 0) + 1
    terms = len(set(graph.rdf.subjects(RDF.type, graph.node("wf:Term"))))
    print(
        f"{len(graph.rdf)} triples: {terms} terms, "
        + ", ".join(f"{n} {cls}" for cls, n in sorted(counts.items()))
    )
    if args.out:
        print(f"written to {args.out}")
    return 0


def _view(args) -> int:
    import json

    from . import view

    document = view.build(_workspace())
    print(
        json.dumps(document, indent=2) if args.format == "json" else view.render_text(document),
        end="" if args.format == "text" else "\n",
    )
    return 0


def _bindings(pairs: list[str]) -> dict[str, str]:
    bindings = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator:
            raise ValueError(f"--bind takes name=value, not '{pair}'")
        bindings[key] = value
    return bindings


def _cq(args) -> int:
    from . import cq
    from .graph import build_graph

    ws = _workspace()
    questions = cq.load(ws.cfg)
    if not args.ids and not args.check:
        for question in questions.values():
            needs = (
                f"  [--bind {', '.join(f'{b}=...' for b in question.binds)}]"
                if question.binds
                else ""
            )
            print(f"{question.id}  {question.question}{needs}")
        return 0

    graph = build_graph(ws)
    bindings = _bindings(args.bind)
    failed = False
    selected = args.ids or [q.id for q in questions.values() if q.expect_none and not q.binds]
    for identifier in selected:
        if identifier not in questions:
            raise ValueError(f"no competency question {identifier} in {ws.cfg.rel(ws.cfg.cq_dir)}")
        question = questions[identifier]
        rows = cq.run(graph, question, **bindings)
        print(f"{question.id}: {question.question}")
        print(cq.table(rows))
        if question.expect_none and rows:
            failed = True
            print(f"  ^ {question.id} expects no rows: each one is a problem")
        print()
    return 1 if failed else 0


def _scope(ws, name: str, *, stop: bool = False):
    from .gates import branch_scope

    return None if name == "all" else branch_scope(ws, or_uncommitted=stop)


def _trace(args) -> int:
    from . import changes, evidence, gateconfig, gates, hooks, namespaces
    from .graph import build_graph

    ws = _workspace()
    stop = args.gate == "stop"
    event = hooks.read_event() if stop else {}
    branch_problems: list = []
    try:
        scope = _scope(ws, args.scope, stop=stop)
        branch_problems = gateconfig.problems(ws.cfg) + changes.branch_problems(ws, stop=stop)
        # A gate written for another namespace concerns every branch, also one with no work item.
        nothing_to_judge = not branch_problems and not namespaces.problems(ws)
        if scope is not None and not scope and nothing_to_judge:
            if not stop:
                print("onto trace: nothing in scope on this branch")
            return 0

        if args.collect:
            run = evidence.collect(ws, evidence.tests_for(ws, scope))
            if not run.ok:
                print(f"onto trace: the test run could not complete\n{run.output}", file=sys.stderr)
                return 1

        graph = build_graph(ws)
        gate_problems = gates.in_scope(gates.run_shacl(ws, graph), gates.answerable(ws, scope))
        problems = gate_problems + branch_problems
        rows = [
            row
            for row in gates.traceability(graph)
            if (scope is None or row.requirement in scope)
            and (not args.context or row.context == args.context)
        ]
    except SourceUnreadable as exc:
        if not stop:
            raise
        # Nothing can be judged past it. The session can put that right, so it is told
        # which file, along with what the branch gates found before the source was needed.
        unreadable = changes.unreadable(ws.cfg, exc)
        if unreadable not in branch_problems:
            branch_problems.append(unreadable)
        problems, rows = list(branch_problems), []

    problems += gates.unverified(ws, rows, problems)

    if args.format == "json":
        import json

        print(
            json.dumps(
                {
                    "coverage": gates.coverage(rows),
                    "requirements": [
                        {
                            "id": r.requirement,
                            "status": r.status,
                            "risk_tier": r.risk,
                            "tasks": sorted(r.tasks),
                            "tests": dict(sorted(r.tests.items())),
                            "verdict": r.verdict,
                            "replaced_by": r.replaced_by,
                        }
                        for r in rows
                    ],
                    "violations": [p.to_dict() for p in sorted(problems, key=report.sort_key)],
                },
                indent=2,
            )
        )
    elif not stop:
        print(_trace_table(rows))
        cover = gates.coverage(rows)
        if cover["requirements"]:
            print(
                f"\ncoverage of {cover['requirements']} agreed requirement(s): "
                f"{cover['with_test']} with a test, "
                f"{cover['verified']} verified by passing evidence"
            )
        if problems:
            print("\n" + report.render_text(problems))
        print(f"\nonto trace: {report.summary(problems)}")

    if not report.errors(problems):
        return 0
    if not stop:
        return 1
    blocking = report.errors(problems)
    message = (
        "onto trace: the gates do not hold for what this branch touched.\n"
        f"{report.render_text(blocking)}"
    )
    if any(problem not in branch_problems for problem in blocking):
        message += (
            "\nMake the tests pass, or take back the claim: a Requirement or Task that is "
            "not verified is in_progress, not done."
        )
    print(message, file=sys.stderr)
    # One forced continuation is enough. If the gate still fails after it, hand
    # back to the person rather than loop: CI holds the line.
    return 1 if event.get("stop_hook_active") else BLOCK


def _trace_table(rows: list) -> str:
    from .cq import table

    return table(
        [
            {
                "requirement": row.requirement,
                "status": row.status,
                "risk": row.risk or "-",
                "tasks": " ".join(sorted(row.tasks)) or "-",
                "tests": " ".join(f"{t}:{r or 'none'}" for t, r in sorted(row.tests.items()))
                or "-",
                "verdict": f"replaced by {', '.join(row.replaced_by)}"
                if row.status == "superseded" and row.replaced_by
                else row.verdict,
            }
            for row in rows
        ]
    )


def _rules(args) -> int:
    from . import rules

    return rules.run(_workspace(), args.format, args.context)


def _evidence_collect(args) -> int:
    from . import evidence

    ws = _workspace()
    scope = _scope(ws, args.scope)
    tests = evidence.tests_for(ws, scope)
    run = evidence.collect(ws, tests)
    tail = run.output.splitlines()[-args.tail :] if args.tail else []
    print("\n".join(tail))
    if not run.ok:
        print("onto evidence: the test run could not complete", file=sys.stderr)
        return 1
    recorded = sorted(item.id for item in ws.of_class("Evidence"))
    print(
        f"onto evidence: ran {len(tests)} test item(s); "
        f"evidence on record: {', '.join(recorded) or 'none'}"
    )
    return 0


# --- provenance ------------------------------------------------------------------


def _prov_emit(args) -> int:
    from . import prov
    from .graph import build_graph

    ws = _workspace()
    if args.change:
        missing = [c for c in args.change if c not in ws.by_id or ws.by_id[c].cls != "Change"]
        if missing:
            raise ValueError(f"not a Change under work/: {', '.join(missing)}")
        changes = [ws.by_id[c] for c in args.change]
    else:
        scope = _scope(ws, args.scope)
        changes = [c for c in ws.of_class("Change") if scope is None or c.id in scope]
    if not changes:
        return 0
    log_dir = Path(args.from_decision_log) if args.from_decision_log else ws.cfg.audit_dir
    out_dir = Path(args.out) if args.out else ws.cfg.prov_dir
    for path in prov.emit(ws, build_graph(ws), out_dir, changes=changes, log_dir=log_dir):
        print(ws.cfg.rel(path))
    return 0


def _log(args) -> int:
    from . import prov
    from .slicing import current_task

    ws = _workspace()
    subject = args.about
    if not subject:
        task = current_task(ws)
        subject = task.id if task else "general"
    elif subject not in ws.by_id:
        raise ValueError(f"{subject} is not a work item under work/")
    path = prov.append_decision(
        ws.cfg,
        subject,
        phase=args.phase,
        decision=args.decision,
        why=args.why,
        evidence=args.evidence,
        result=args.result,
    )
    print(ws.cfg.rel(path))
    return 0


# --- writing ---------------------------------------------------------------------


def _created(ws, path, problems) -> int:
    if path is None:
        print("onto: nothing was written.", file=sys.stderr)
        print(report.render_text(problems), file=sys.stderr)
        return 1
    if problems:
        print(report.render_text(problems), file=sys.stderr)
    print(ws.cfg.rel(path))
    return 0


def _write(ws, args, cls: str, fields: dict) -> int:
    from . import create

    if not args.dry_run:
        return _created(ws, *create.create(ws, cls, fields))
    item, problems = create.draft(ws, cls, fields)
    if problems:
        print(report.render_text(problems), file=sys.stderr)
    if item is None:
        print("onto: dry run: this would be refused.", file=sys.stderr)
        return 1
    print(f"onto: dry run: nothing was written. {item.rel} would be:", file=sys.stderr)
    print(item.text, end="")
    return 0


def _new(args) -> int:
    from . import create

    ws = _workspace()
    fields = (
        create.parse_fields(ws, args.cls, args.fields)
        if args.cls in ws.schema.record_classes
        else {}
    )
    return _write(ws, args, args.cls, fields)


def _ocr_new(args) -> int:
    ws = _workspace()
    fields = {
        "title": args.title or f"Add {args.term} to the {args.context} glossary",
        "bounded_context": args.context,
        "proposed_term": args.term,
        "justification": args.justification,
    }
    if args.definition:
        fields["proposed_definition"] = args.definition
    return _write(ws, args, "OntologyChangeRequest", fields)


def _gen(args) -> int:
    from . import gen
    from .config import load_config

    try:
        results = gen.generate(load_config(), check=args.check)
    except gen.GeneratorUnavailable as exc:
        print(f"onto: {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(f"{result.status:9} {result.path}")
    drifted = [r for r in results if r.status == "drift"]
    for result in drifted:
        print("\n" + result.diff, end="")
    if drifted:
        print(
            "\nonto gen --check: generated files are out of date. Run `onto gen` and commit "
            "the result. If a generated file was edited by hand, edit its source instead."
        )
        return 1
    return 0


def _verify(args) -> int:
    from . import verify

    return verify.run(args.scope, Path(args.out) if args.out else None)


def _init(args) -> int:
    from . import scaffold

    return scaffold.run(args)


# --- argument parsing ------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onto", description="Ontology gates for the monorepo. See onto.toml for the wiring."
    )
    parser.add_argument("--version", action="version", version=f"onto {__version__}")
    sub = parser.add_subparsers(metavar="command")

    def command(name: str, handler, help_text: str, parent=sub) -> argparse.ArgumentParser:
        p = parent.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(handler=handler)
        return p

    def fmt(p, *choices: str) -> None:
        p.add_argument("--format", choices=choices, default=choices[0])

    def dry_run(p) -> None:
        p.add_argument(
            "--dry-run", action="store_true", help="validate and print the item; write nothing"
        )

    p = command("overview", _overview, "the table of contents of the ontology")
    p.add_argument("--context")

    p = command(
        "resolve", _resolve, "look a name up in the glossaries; exits 1 if it is not a term"
    )
    p.add_argument("name")
    p.add_argument("--context")
    fmt(p, "text", "json")

    p = command("slice", _slice, "the terms, decisions and requirements one piece of work needs")
    p.add_argument("--task", help="a Task id (default: the task in hand)")
    p.add_argument("--term", action="append", help="a term to slice around; repeatable")
    p.add_argument(
        "--file",
        action="append",
        help="a file or folder the work touches: a Decision whose affects globs match it "
        "joins the slice; repeatable (for a Task the files the branch changed are added)",
    )
    p.add_argument("--context")
    p.add_argument("--depth", type=int, default=1, choices=(0, 1))
    p.add_argument("--max-tokens", type=int, default=3000)
    p.add_argument(
        "--for-subagent",
        action="store_true",
        help="SubagentStart hook mode: emit the slice as additional context",
    )
    fmt(p, "md", "json", "context-json")

    command("current-task", _current_task, "the id of the task in hand")

    p = command("validate", _validate, "check work items and glossaries: shape, links, vocabulary")
    p.add_argument("paths", nargs="*", help="work item files (default: everything)")
    fmt(p, "text", "json")

    p = command("check-terms", _check_terms, "check domain-layer code against its glossary")
    p.add_argument("paths", nargs="*", help="files (default: every domain layer)")
    p.add_argument(
        "--changed-from-stdin",
        action="store_true",
        help="PostToolUse hook mode: check the file named in the hook event",
    )
    fmt(p, "text", "json")

    p = command("guard", _guard, "PreToolUse hook: protect ontology sources and generated files")
    p.add_argument("path", nargs="?", help="ask what the guard would decide for a path")
    p.add_argument(
        "--deny-rules",
        action="store_true",
        help="print the permissions.deny rules for generated files and evidence",
    )
    p.add_argument(
        "--check-settings",
        action="store_true",
        help="fail if .claude/settings.json lacks one of those rules",
    )

    p = command("build", _build, "build the traceability graph and report its size")
    p.add_argument("--out", help="also write the graph to this file")
    fmt(p, "turtle", "nt")

    p = command("view", _view, "where each task stands, the ontology and the plan, for displays")
    fmt(p, "text", "json")

    p = command("cq", _cq, "list or run the competency questions")
    p.add_argument("ids", nargs="*", help="question ids, such as CQ-03")
    p.add_argument("--bind", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument(
        "--check",
        action="store_true",
        help="run every question that expects no rows; exit 1 if one returns any",
    )

    p = command("trace", _trace, "traceability matrix and SHACL gates")
    p.add_argument("--scope", choices=("all", "branch"), default="all")
    p.add_argument(
        "--gate",
        choices=("ci", "stop"),
        default="ci",
        help="stop: Stop hook mode, silent unless the gate fails",
    )
    p.add_argument("--collect", action="store_true", help="run the tests in scope first")
    p.add_argument("--context")
    fmt(p, "text", "json")

    p = command("rules", _rules, "hold each bound rule to the code and the proof behind it")
    p.add_argument("--context")
    fmt(p, "text", "json")
    p.add_argument("--json", action="store_const", const="json", dest="format", help="as JSON")

    evidence = sub.add_parser("evidence", help="record what the tests show")
    evidence_sub = evidence.add_subparsers(metavar="command", required=True)
    p = command(
        "collect", _evidence_collect, "run the Test items and record their Evidence", evidence_sub
    )
    p.add_argument("--scope", choices=("all", "branch"), default="all")
    p.add_argument("--tail", type=int, default=3, help="lines of pytest output to show")

    prov = sub.add_parser("prov", help="provenance bundles")
    prov_sub = prov.add_subparsers(metavar="command", required=True)
    p = command("emit", _prov_emit, "write a PROV-O bundle per Change", prov_sub)
    p.add_argument("--change", action="append", help="a Change id; repeatable (default: by scope)")
    p.add_argument("--scope", choices=("all", "branch"), default="all")
    p.add_argument("--from-decision-log", metavar="DIR")
    p.add_argument("--out", metavar="DIR")

    p = command("log", _log, "append a decision to the decision log (.audit/)")
    p.add_argument("--phase", required=True)
    p.add_argument("--decision", required=True)
    p.add_argument("--why", required=True)
    p.add_argument("--evidence", default="")
    p.add_argument("--result", default="")
    p.add_argument("--about", help="a work item id (default: the task in hand)")

    p = command("new", _new, "create a validated work item: onto new Requirement key=value ...")
    p.add_argument("cls", metavar="CLASS")
    p.add_argument("fields", nargs="*", metavar="key=value")
    dry_run(p)

    ocr = sub.add_parser("ocr", help="ontology change requests")
    ocr_sub = ocr.add_subparsers(metavar="command", required=True)
    p = command("new", _ocr_new, "propose a change to a glossary", ocr_sub)
    p.add_argument("--context", required=True)
    p.add_argument("--term", required=True)
    p.add_argument("--justification", required=True)
    p.add_argument("--definition")
    p.add_argument("--title")
    dry_run(p)

    from . import scaffold

    scaffold.arguments(
        command("init", _init, "scaffold the ontology layer into the git repository you are in")
    )

    p = command("gen", _gen, "compile the LinkML sources into JSON Schema, SHACL and Pydantic")
    p.add_argument("--check", action="store_true", help="fail if a generated file is out of date")

    p = command("verify", _verify, "run every gate and write one index of what they showed")
    p.add_argument("--scope", choices=("all", "branch"), default="all")
    p.add_argument("--out", metavar="DIR", help="where the index and the bundles go")
    return parser


if __name__ == "__main__":
    sys.exit(main())
