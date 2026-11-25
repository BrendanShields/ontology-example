"""Acceptance test for REQ-0008: the text of an Utterance stays out of the logs.

What counts as a log is settled in DEC-0009: everything `call-qa` writes other
than its result on stdout. Here that is stderr, every record that reaches a
logger while the command runs, the SDK's loggers included, and the ledger
file, which is the one file the app writes.

Each path below is run on a synthetic Call whose every Utterance carries one
planted phrase and on Findings whose every rationale carries another. A
failure names the stream or the logger the phrase reached, never what was
written there.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic
import httpx2
import pytest
import yaml
from call_qa_agent import cli

from ..conftest import FakeClaude, reply

SPOKEN = "zqx-spoken-words-7731"
REASONED = "zqx-reasoned-words-4409"
PLANTED = (SPOKEN, REASONED)

SCORECARD = {
    "scorecard_id": "planted-v1",
    "pass_mark": 50,
    "criteria": [
        {"criterion_id": "c0", "statement": "First.", "weight": 1, "critical": True},
        {"criterion_id": "c1", "statement": "Second.", "weight": 1},
    ],
}
CALL = {
    "call_id": "CALL-9100",
    "representative": "REP-9100",
    "utterances": [
        {"sequence": 1, "speaker": "CUSTOMER", "text": f"{SPOKEN} one"},
        {"sequence": 2, "speaker": "REPRESENTATIVE", "text": f"{SPOKEN} two"},
    ],
}


def finding(criterion: str, **changes) -> tuple[str, dict]:
    proposal = {
        "criterion": criterion,
        "finding_outcome": "MET",
        "cited_utterances": [1],
        "rationale": f"{REASONED} because of what was said: {SPOKEN} one",
    }
    return ("record_finding", {**proposal, **changes})


# A script that is rejected in each way the write path can reject, then completes.
STEPS = [
    finding("zz"),
    finding("c0", cited_utterances=[9]),
    finding("c0", cited_utterances=[]),
    finding("c0", finding_outcome=f"{SPOKEN} is not an outcome"),
    {"tool": "record_finding", "input": f"{SPOKEN} is not a Finding at all"},
    finding("c0", **{SPOKEN: REASONED}),
    ("finish_evaluation", {}),
    finding("c0", finding_outcome="NOT_MET"),
    finding("c0"),
    finding("c1"),
    ("finish_evaluation", {}),
]


def as_step(step) -> dict:
    return step if isinstance(step, dict) else {"tool": step[0], "input": step[1]}


class Logged(logging.Handler):
    """Every record that reaches the root logger, rendered as a handler would write it."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.written: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.written.append((record.name, f"{record.getMessage()} {record.__dict__!r}"))


@pytest.fixture
def files(tmp_path) -> dict[str, Path]:
    def write(name: str, text: str) -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    broken = {**CALL, "utterances": [{**CALL["utterances"][0], "text": [SPOKEN], SPOKEN: 1}]}
    return {
        "scorecard": write("scorecard.yaml", yaml.safe_dump(SCORECARD)),
        "call": write("call.yaml", yaml.safe_dump(CALL)),
        "not-a-call": write("not-a-call.yaml", yaml.safe_dump(broken)),
        "not-yaml": write("not-yaml.yaml", yaml.safe_dump(CALL) + f"\n  {SPOKEN}: [unclosed\n"),
        "steps": write("steps.json", json.dumps({"steps": [as_step(s) for s in STEPS]})),
        "too-few-steps": write("few.json", json.dumps({"steps": [as_step(STEPS[0])]})),
        "not-json": write("not-json.json", f'{{"steps": [{{"tool": "{SPOKEN}" '),
        "not-steps": write("not-steps.json", json.dumps({"steps": [{"input": SPOKEN}]})),
    }


@pytest.fixture
def logged():
    """Catch everything, with the SDK's loggers as ANTHROPIC_LOG=debug leaves them."""
    handler = Logged()
    root = logging.getLogger()
    sdk = [logging.getLogger(name) for name in ("anthropic", "httpx2", "httpx", "httpcore")]
    before = [(logger, logger.level) for logger in (root, *sdk)]
    root.addHandler(handler)
    for logger, _ in before:
        logger.setLevel(logging.DEBUG)
    yield handler
    root.removeHandler(handler)
    for logger, level in before:
        logger.setLevel(level)


def scripted(monkeypatch, *replies: dict) -> FakeClaude:
    claude = FakeClaude(*replies)
    monkeypatch.setattr(cli, "make_client", lambda settings: claude.client)
    return claude


def answering(status: int, body: dict) -> anthropic.Anthropic:
    """A client whose every request gets the same answer."""
    transport = httpx2.MockTransport(lambda request: httpx2.Response(status, json=body))
    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=transport),
    )


def run(argv: list[str], capsys, logged: Logged, stdout: bool = False) -> tuple[int, list[str]]:
    """Run `call-qa`. Returns its exit code and where a planted phrase was logged.

    stdout is looked at too when the command's result is not an Evaluation.
    """
    try:
        code = cli.main(argv)
    except SystemExit as stopped:  # argparse
        code = stopped.code
    except Exception as error:
        # What the interpreter would print on stderr for an error nobody caught.
        code = None
        logged.written.append((f"uncaught {type(error).__name__}", str(error)))
    captured = capsys.readouterr()
    reached = {"stderr"} if any(phrase in captured.err for phrase in PLANTED) else set()
    if stdout and any(phrase in captured.out for phrase in PLANTED):
        reached.add("stdout")
    reached |= {name for name, text in logged.written if any(phrase in text for phrase in PLANTED)}
    return code, sorted(reached)


def evaluate(files, call: str = "call", *more: str) -> list[str]:
    return ["evaluate", str(files[call]), "--scorecard", str(files["scorecard"]), "--trace", *more]


def test_a_replayed_evaluation_logs_no_planted_phrase(files, capsys, logged):
    code, reached = run(evaluate(files, "call", "--replay", str(files["steps"])), capsys, logged)

    assert code == 0
    assert reached == []


def test_the_trace_still_says_what_each_step_did(files, capsys, logged):
    cli.main(evaluate(files, "call", "--replay", str(files["steps"])))
    trace = capsys.readouterr().err

    # Identifiers, outcomes, Utterance numbers and rule names are what a trace may show.
    assert "record_finding" in trace and "c0" in trace and "NOT_MET" in trace
    for rule in ("UNKNOWN_CRITERION", "UNKNOWN_UTTERANCE", "MISSING_CITATION", "MALFORMED_FINDING"):
        assert rule in trace
    assert "MISSING_FINDING" in trace and "DUPLICATE_FINDING" in trace


def test_an_evaluation_by_the_model_logs_no_planted_phrase(files, capsys, logged, monkeypatch):
    claude = scripted(
        monkeypatch,
        reply(*STEPS[:3], text=f"{REASONED} {SPOKEN}"),
        reply(*STEPS[7:]),
    )

    code, reached = run(evaluate(files), capsys, logged)

    assert code == 0 and len(claude.requests) == 2
    assert SPOKEN in claude.requests[0].content.decode()  # the Call did go to the model
    assert reached == []


def test_no_evaluation_logs_no_planted_phrase(files, capsys, logged, monkeypatch):
    code, reached = run(
        evaluate(files, "call", "--replay", str(files["too-few-steps"])), capsys, logged
    )
    assert (code, reached) == (1, [])

    scripted(monkeypatch, reply(STEPS[0], text=SPOKEN), reply(stop_reason="refusal", text=SPOKEN))
    code, reached = run(evaluate(files), capsys, logged)
    assert (code, reached) == (1, [])


def test_an_error_from_the_api_logs_no_planted_phrase(files, capsys, logged, monkeypatch):
    # The API refuses the request and its message quotes what it was sent.
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": SPOKEN}}
    monkeypatch.setattr(cli, "make_client", lambda settings: answering(400, body))

    code, reached = run(evaluate(files), capsys, logged)

    assert (code, reached) == (2, [])


@pytest.mark.parametrize(
    ("call", "more"),
    [
        ("not-a-call", ()),
        ("not-yaml", ()),
        ("call", ("--replay", "not-json")),
        ("call", ("--replay", "not-steps")),
    ],
)
def test_input_that_cannot_be_read_logs_no_planted_phrase(files, capsys, logged, call, more):
    more = tuple(str(files[part]) if part in files else part for part in more)

    code, reached = run(evaluate(files, call, *more), capsys, logged)

    assert (code, reached) == (2, [])


def test_the_ledger_and_its_commands_hold_no_planted_phrase(files, tmp_path, capsys, logged):
    ledger = tmp_path / "ledger.jsonl"
    on_ledger = [str(ledger), CALL["call_id"], SCORECARD["scorecard_id"]]
    staging = evaluate(files, "call", "--replay", str(files["steps"]), "--stage", str(ledger))

    assert run(staging, capsys, logged) == (0, [])
    for argv, code in (
        (["publish", *on_ledger], 1),  # the critical Criterion failed: REVIEW_REQUIRED
        (["review", *on_ledger, "--reviewer", "QA-0007", "--outcome", "CONFIRMED"], 0),
        (["publish", *on_ledger], 0),
        (["show", *on_ledger], 0),
    ):
        assert run(argv, capsys, logged, stdout=True) == (code, []), argv[0]

    written = ledger.read_text(encoding="utf-8")
    assert len(written.splitlines()) == 3
    assert not any(phrase in written for phrase in PLANTED)
