"""`call-qa`: evaluate a Call from the command line.

    call-qa evaluate CALL.yaml --scorecard SCORECARD.yaml              # asks Claude
    call-qa evaluate CALL.yaml --scorecard SCORECARD.yaml --replay STEPS.json   # offline
    call-qa tools --scorecard SCORECARD.yaml                           # what the model is given

Exit codes: 0 an Evaluation was produced, 1 none was (the Rejections are
printed), 2 the request could not be made.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic
import yaml

from .agent import EvaluationIncomplete, Settings, Trace, evaluate, make_client, with_overrides
from .generated import Call, Scorecard
from .prompts import system_prompt
from .replay import load_steps, replay
from .tools import render_rejections, tool_definitions


def load_call(path: Path) -> Call:
    return Call.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_scorecard(path: Path) -> Scorecard:
    return Scorecard.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


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

    for name, text in (
        ("tools", "print the tool definitions"),
        ("prompt", "print the system prompt"),
    ):
        show = sub.add_parser(name, help=f"{text} the model gets for a Scorecard")
        show.add_argument("--scorecard", type=Path, required=True)

    args = parser.parse_args(argv)
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
            evaluation = replay(call, scorecard, load_steps(args.replay), trace)
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
        _show_trace(args, trace)
        print(f"No Evaluation: {incomplete.reason}.", file=sys.stderr)
        if incomplete.rejections:
            print(render_rejections(incomplete.rejections), file=sys.stderr)
        return 1
    except anthropic.APIConnectionError as error:
        print(f"call-qa: could not reach the API: {error}", file=sys.stderr)
        return 2
    except anthropic.RateLimitError:
        print("call-qa: rate limited after retries. Try again shortly.", file=sys.stderr)
        return 2
    except anthropic.APIStatusError as error:
        print(f"call-qa: the API returned {error.status_code}: {error.message}", file=sys.stderr)
        return 2
    except anthropic.AnthropicError as error:  # no credentials, bad configuration
        print(f"call-qa: {error}", file=sys.stderr)
        return 2

    _show_trace(args, trace)
    data = evaluation.model_dump(mode="json", exclude_none=True)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), end="")
    return 0


def _show_trace(args, trace: Trace) -> None:
    if not args.trace:
        return
    for number, step in enumerate(trace.steps, start=1):
        mark = "REJECTED" if step.rejected else "ok"
        print(f"[{number}] {step.tool} {json.dumps(step.tool_input)} -> {mark}", file=sys.stderr)
        if step.rejected:
            print(step.result, file=sys.stderr)
    print(file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
