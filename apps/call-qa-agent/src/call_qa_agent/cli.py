"""`call-qa`: evaluate a Call from the command line, and publish the Evaluation.

    call-qa evaluate CALL.yaml --scorecard SCORECARD.yaml              # asks Claude
    call-qa evaluate CALL.yaml --scorecard SCORECARD.yaml --replay STEPS.json   # offline
    call-qa tools --scorecard SCORECARD.yaml                           # what the model is given

    call-qa evaluate ... --stage LEDGER                                # and stage the Evaluation
    call-qa review LEDGER CALL_ID SCORECARD_ID --reviewer WHO --outcome CONFIRMED
    call-qa publish LEDGER CALL_ID SCORECARD_ID
    call-qa show LEDGER CALL_ID SCORECARD_ID                           # state and audit trail

`evaluate` writes nothing anywhere unless it is given `--stage`. The ledger is
one file of JSON lines. Publishing means recording the state PUBLISHED on it:
there is no system behind this example that an Evaluation is sent to.

Exit codes: 0 done, or it had been done already. 1 refused: no Evaluation was
produced, or a rule or the state of the Evaluation does not permit what was
asked, and the reason is printed. 2 failed: a file or the ledger could not be
read or written, or the request to the model could not be made.

Whatever this writes besides the result on stdout names things and counts
them and quotes nothing from a Call or a rationale (REQ-0008, DEC-0009).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import traceback
from pathlib import Path

import anthropic
import yaml
from pydantic import BaseModel, ValidationError

from .agent import EvaluationIncomplete, Settings, Trace, evaluate, make_client, with_overrides
from .domain.publication import Refused
from .generated import (
    Call,
    Criterion,
    Disposition,
    Evaluation,
    FindingOutcome,
    PublicationState,
    ReviewOutcome,
    Scorecard,
    Utterance,
)
from .ledger import Corrupt, Entry, Ledger, is_identifier
from .prompts import system_prompt
from .replay import load_steps, replay
from .tools import FINISH_EVALUATION, RECORD_FINDING, render_rejections, tool_definitions

_FIELDS = {name for cls in (Call, Utterance, Scorecard, Criterion) for name in cls.model_fields}


class Unreadable(ValueError):
    """A file the command was given cannot be used. The message quotes nothing from the file."""


def _parsed(path: Path, cls: type[BaseModel]):
    """The file as an instance of a generated class, or Unreadable saying where it went wrong."""
    try:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except OSError as error:
        raise Unreadable(f"{path}: {error.strerror or type(error).__name__}") from None
    except UnicodeDecodeError:
        raise Unreadable(f"{path}: not UTF-8 text") from None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise Unreadable(f"{path}: not valid YAML{where}") from None
    except ValidationError as error:
        # The location and the kind of each error. Not its message and not the value: a
        # misplaced Utterance would be echoed. A field the ontology does not have is not named.
        problems = sorted(
            {
                ".".join(
                    str(part) if isinstance(part, int) or part in _FIELDS else "<undeclared>"
                    for part in item["loc"]
                )
                + f" ({item['type']})"
                for item in error.errors(include_url=False, include_input=False)
            }
        )
        raise Unreadable(f"{path}: not a valid {cls.__name__}: {'; '.join(problems)}") from None


def load_call(path: Path) -> Call:
    return _parsed(path, Call)


def load_scorecard(path: Path) -> Scorecard:
    """The Scorecard in a file. Raises ValueError if two of its Criteria share a criterion_id."""
    scorecard = _parsed(path, Scorecard)
    names = [criterion.criterion_id for criterion in scorecard.criteria]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        # REQ-0011: one Finding per Criterion means nothing unless a criterion_id names one.
        raise Unreadable(
            f"Scorecard {scorecard.scorecard_id} has more than one Criterion with the "
            f"criterion_id {', '.join(repeated)}"
        )
    return scorecard


def _identifier(value: str) -> str:
    if not is_identifier(value):
        raise argparse.ArgumentTypeError("an identifier has no spaces and is not empty")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="call-qa", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("evaluate", help="evaluate one Call against a Scorecard")
    run.add_argument("call", type=Path)
    run.add_argument("--scorecard", type=Path, required=True)
    run.add_argument(
        "--replay", type=Path, help="replay recorded tool calls instead of asking Claude"
    )
    run.add_argument("--trace", action="store_true", help="show each tool call and its result")
    run.add_argument("--json", action="store_true", help="print the Evaluation as JSON")
    run.add_argument("--model")
    run.add_argument("--platform", choices=("anthropic", "bedrock"))
    run.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"))
    run.add_argument("--max-turns", type=int)
    run.add_argument(
        "--no-fallback",
        action="store_true",
        help="fail instead of retrying on another model when the request is declined",
    )
    run.add_argument(
        "--stage",
        type=Path,
        metavar="LEDGER",
        help="stage the Evaluation on this ledger file. Without it nothing is written anywhere",
    )

    for name, text in (
        ("tools", "print the tool definitions"),
        ("prompt", "print the system prompt"),
    ):
        show = sub.add_parser(name, help=f"{text} the model gets for a Scorecard")
        show.add_argument("--scorecard", type=Path, required=True)

    for name, text in (
        ("review", "record a person's Review of a STAGED Evaluation that needs one"),
        (
            "publish",
            "record that an Evaluation is PUBLISHED. Nothing is sent anywhere: this example "
            "has no system behind it, so the record on the ledger is the publication",
        ),
        ("show", "print where an Evaluation stands, its Reviews and its audit trail"),
    ):
        command = sub.add_parser(name, help=text, description=text[0].upper() + text[1:] + ".")
        command.add_argument("ledger", type=Path, metavar="LEDGER", help="the ledger file")
        command.add_argument("call", type=_identifier, metavar="CALL_ID")
        command.add_argument("scorecard", type=_identifier, metavar="SCORECARD_ID")
        if name == "review":
            command.add_argument(
                "--reviewer",
                type=_identifier,
                required=True,
                help="the identifier of the person. It is recorded as given and not checked",
            )
            command.add_argument(
                "--outcome", required=True, choices=[outcome.value for outcome in ReviewOutcome]
            )
        if name == "show":
            command.add_argument("--json", action="store_true", help="print it as JSON")

    args = parser.parse_args(argv)
    # At DEBUG the SDK logs each request whole, which is the whole Call (DEC-0009).
    held = logging.root.manager.disable
    logging.disable(logging.INFO)
    try:
        return _run(args)
    except (Unreadable, Corrupt) as error:
        print(f"call-qa: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        # The message of an error nobody expected can quote what was being handled.
        frame = traceback.extract_tb(error.__traceback__)[-1]
        where = "/".join(Path(frame.filename).parts[-2:])
        print(
            f"call-qa: failed with {type(error).__name__} in {frame.name} ({where}:{frame.lineno})",
            file=sys.stderr,
        )
        return 2
    finally:
        logging.disable(held)


def _run(args) -> int:
    if args.command in ("review", "publish", "show"):
        return _on_ledger(args)
    scorecard = load_scorecard(args.scorecard)
    if args.command == "tools":
        print(json.dumps(tool_definitions(scorecard), indent=2))
        return 0
    if args.command == "prompt":
        print(system_prompt(scorecard), end="")
        return 0
    return _evaluate(args, scorecard)


def _evaluate(args, scorecard: Scorecard) -> int:
    call = load_call(args.call)
    trace = Trace()
    try:
        if args.replay:
            evaluation = replay(call, scorecard, _steps(args.replay), trace)
        else:
            settings = with_overrides(
                Settings.from_env(),
                model=args.model,
                platform=args.platform,
                effort=args.effort,
                max_turns=args.max_turns,
                refusal_fallback=False if args.no_fallback else None,
            )
            evaluation = evaluate(call, scorecard, make_client(settings), settings, trace)
    except EvaluationIncomplete as incomplete:
        _show_trace(args, trace, scorecard)
        print(f"No Evaluation: {incomplete.reason}.", file=sys.stderr)
        if incomplete.rejections:
            print(render_rejections(incomplete.rejections), file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("call-qa: could not reach the API.", file=sys.stderr)
        return 2
    except anthropic.RateLimitError:
        print("call-qa: rate limited after retries. Try again shortly.", file=sys.stderr)
        return 2
    except anthropic.APIStatusError as error:
        print(f"call-qa: the API returned {error.status_code}{_kind(error)}.", file=sys.stderr)
        return 2
    except anthropic.AnthropicError as error:  # no credentials, bad configuration
        print(
            f"call-qa: the request could not be made ({type(error).__name__}). "
            "Check the credentials and the platform settings.",
            file=sys.stderr,
        )
        return 2

    _show_trace(args, trace, scorecard)
    _print(evaluation.model_dump(mode="json", exclude_none=True), args.json)
    return _stage(args.stage, evaluation) if args.stage else 0


def _print(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), end="")


def _stage(path: Path, evaluation: Evaluation) -> int:
    ledger = Ledger(path)
    try:
        recorded = _written(path, lambda: ledger.stage(evaluation))
    except Refused as refused:
        print(f"Not staged: {refused.reason}, and it is not this one.", file=sys.stderr)
        return 1
    found = ledger.entry(evaluation.call, evaluation.scorecard)
    print(_standing(evaluation.call, evaluation.scorecard, found, recorded), file=sys.stderr)
    return 0


def _on_ledger(args) -> int:
    ledger = Ledger(args.ledger)
    recorded = True
    try:
        if args.command == "review":
            outcome = ReviewOutcome(args.outcome)
            recorded = _written(
                args.ledger,
                lambda: ledger.review(args.call, args.scorecard, args.reviewer, outcome),
            )
        elif args.command == "publish":
            recorded = _written(args.ledger, lambda: ledger.publish(args.call, args.scorecard))
    except Refused as refused:
        print(f"Refused: {refused.reason}.", file=sys.stderr)
        if refused.rejections:
            print(render_rejections(refused.rejections), file=sys.stderr)
        return 1

    found = ledger.entry(args.call, args.scorecard)
    if found is None:
        print(f"No Evaluation of {args.call} against {args.scorecard} is staged.", file=sys.stderr)
        return 1
    if args.command != "show":
        print(_standing(args.call, args.scorecard, found, recorded), file=sys.stderr)
        return 0
    _print(
        {
            "call": args.call,
            "scorecard": args.scorecard,
            "disposition": found.disposition.value,
            "publication_state": found.publication_state.value,
            "sha256": found.sha256,
            "reviews": [made.model_dump(mode="json") for made in found.reviews],
            "audit_records": [record.model_dump(mode="json") for record in found.records],
        },
        args.json,
    )
    return 0


def _written(path: Path, command):
    try:
        return command()
    except OSError as error:
        raise Unreadable(f"{path}: {error.strerror or type(error).__name__}") from None


def _standing(call: str, scorecard: str, found: Entry, recorded: bool) -> str:
    """One line on where an Evaluation stands, in identifiers and states."""
    line = (
        f"{call} against {scorecard}: {found.publication_state.value}, "
        f"disposition {found.disposition.value}, {len(found.reviews)} Review(s), "
        f"{len(found.records)} AuditRecord(s)."
    )
    if not recorded:
        line += " Nothing was recorded: this had been done already."
    elif (
        found.publication_state is PublicationState.STAGED
        and found.disposition is not Disposition.FINAL
        and not any(made.review_outcome == ReviewOutcome.CONFIRMED.value for made in found.reviews)
    ):
        line += " It needs a Review with the outcome CONFIRMED before it can be published."
    return line


def _steps(path: Path) -> list[dict]:
    try:
        return load_steps(path)
    except OSError as error:
        raise Unreadable(f"{path}: {error.strerror or type(error).__name__}") from None
    except json.JSONDecodeError as error:
        where = f"line {error.lineno}, column {error.colno}"
        raise Unreadable(f"{path}: not valid JSON at {where}") from None
    except ValueError as error:  # load_steps says which step, by its number
        raise Unreadable(f"{path}: {error}") from None


def _kind(error: anthropic.APIStatusError) -> str:
    """The API's own name for the error and the id of the request. Not its message."""
    body = error.body if isinstance(error.body, dict) else {}
    detail = body.get("error") if isinstance(body.get("error"), dict) else {}
    kind = detail.get("type")
    named = f" ({kind})" if isinstance(kind, str) and re.fullmatch(r"[a-z_]+", kind) else ""
    request = getattr(error, "request_id", None)
    return named + (f", request {request}" if request else "")


def _show_trace(args, trace: Trace, scorecard: Scorecard) -> None:
    if not args.trace:
        return
    for number, step in enumerate(trace.steps, start=1):
        print(f"[{number}] {_shown(step, scorecard)}", file=sys.stderr)
    print(file=sys.stderr)


def _shown(step, scorecard: Scorecard) -> str:
    """One step of the trace: what was proposed, by name and number, and what became of it.

    Anything the model or a replay file wrote is shown only if it is a name the
    Scorecard or the glossary already has, or a number. The rest is a "?".
    """
    if step.tool not in (RECORD_FINDING, FINISH_EVALUATION):
        return "a tool that does not exist -> REJECTED"
    shown = step.tool
    if step.tool == RECORD_FINDING:
        proposal = step.tool_input if isinstance(step.tool_input, dict) else {}
        criteria = [criterion.criterion_id for criterion in scorecard.criteria]
        outcomes = [outcome.value for outcome in FindingOutcome]
        criterion = proposal.get("criterion")
        outcome = proposal.get("finding_outcome")
        cited = proposal.get("cited_utterances")
        numbers = isinstance(cited, list) and all(type(number) is int for number in cited)
        shown += (
            f" criterion={criterion if criterion in criteria else '?'}"
            f" finding_outcome={outcome if outcome in outcomes else '?'}"
            f" cited_utterances={cited if numbers else '?'}"
        )
    if not step.rejected:
        return f"{shown} -> ok"
    try:
        rules = {rejection["rejection_rule"] for rejection in json.loads(step.result)["rejections"]}
    except (ValueError, KeyError, TypeError):
        return f"{shown} -> REJECTED"
    return f"{shown} -> REJECTED ({', '.join(sorted(rules))})"


if __name__ == "__main__":
    sys.exit(main())
