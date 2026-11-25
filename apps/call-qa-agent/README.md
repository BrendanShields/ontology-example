# call-qa-agent

An agent that evaluates one recorded customer call against a scorecard: a finding
per criterion, each citing the utterances that show it, then a score, an outcome
and whether a person must review the result.

Its vocabulary and its types come from `ontology/domains/call-qa.yaml` at the
monorepo root. Nothing in `src/call_qa_agent/generated.py` or `schemas/` is
written by hand: `bin/onto gen` produces them.

## Layout

```text
src/call_qa_agent/
  generated.py     types from the ontology (Pydantic). Generated.
  schemas/         JSON Schema and glossary definitions. Generated.
  domain/          the domain layer: pure rules over the generated types
    guardrails.py    what a proposed Finding must satisfy
    scoring.py       score, outcome and disposition from accepted Findings
  session.py       the guarded write path: the only way a Finding is recorded
  tools.py         the model's two tools, their schema compiled from the ontology
  prompts.py       the system prompt, quoting definitions from the glossary
  agent.py         the tool loop against Claude
  replay.py        the same loop driven by recorded tool calls, offline
  cli.py           `call-qa`
data/              a synthetic scorecard, two synthetic calls, two replays
tests/             66 tests. tests/acceptance/ verifies the Requirements under work/
```

Only glossary vocabulary may be used under `domain/`. `bin/onto check-terms`
enforces it after every edit.

## Running it

Offline, with recorded tool calls in place of the model:

```bash
uv run call-qa evaluate apps/call-qa-agent/data/calls/CALL-0002.yaml \
  --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml \
  --replay apps/call-qa-agent/data/replays/CALL-0002.json --trace
```

The evaluation goes to stdout and holds every rationale. `--trace` goes to
stderr and shows each tool call by criterion, outcome, cited utterance numbers
and the rules it broke.

Against Claude:

```bash
uv run call-qa evaluate apps/call-qa-agent/data/calls/CALL-0001.yaml \
  --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml --trace
```

What the model is given for a scorecard:

```bash
uv run call-qa tools --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml
```

```bash
uv run call-qa prompt --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml
```

Exit codes: 0 an evaluation was produced, 1 none was and the outstanding
rejections are printed, 2 the request could not be made.

## Settings

Flags override the environment, which overrides the defaults.

| Setting | Flag | Environment | Default |
| --- | --- | --- | --- |
| Model | `--model` | `CALL_QA_MODEL` | `claude-opus-5-5` |
| Platform | `--platform` | `CALL_QA_PLATFORM` | `anthropic`, or `bedrock` |
| Effort | `--effort` | `CALL_QA_EFFORT` | `high` |
| Turn limit | `--max-turns` | `CALL_QA_MAX_TURNS` | 8 model requests per call |
| Refusal fallback | `--no-fallback` | `CALL_QA_REFUSAL_FALLBACK=off` | on |
| Fallback model on Bedrock | | `CALL_QA_FALLBACK_MODEL` | none |

Credentials come from the environment in the usual way for each platform: an
Anthropic API key or profile, or AWS credentials and `AWS_REGION` for Bedrock.

**Refusal fallback.** A safety classifier can decline a request. With the
fallback on, the Claude API retries a declined request on another model that the
server chooses, so an evaluation may come from a model other than the one you
named. On Bedrock there is no server-side fallback: the SDK's middleware does it
if you name the model in `CALL_QA_FALLBACK_MODEL`, and otherwise a declined
request produces no evaluation. Decide which behaviour your model governance
wants. With `--no-fallback`, a declined request always produces no evaluation.

## Before sending real calls to a model

The two calls under `data/` are invented. A real transcript is personal
information, which the ontology records: `Call`, `Utterance` and `text` are
classified `PII`, and a Requirement that uses them must carry a high risk tier.

- Decide where inference may run and what the provider retains, and check that
  the model and platform you choose meet it.
- Redact what the scorecard does not need before the transcript leaves your
  boundary. This app sends the transcript as it is given.
- `REQ-0008` keeps utterance text out of the logs, and `DEC-0009` says what a
  log is: stderr, every logger record made while a command runs, and every file
  the app writes. `--trace` shows names, numbers and rule names, an unreadable
  file is reported by position and not by content, and the SDK's loggers are
  held at WARNING whatever `ANTHROPIC_LOG` says. Not covered: stdout, which
  carries the evaluation and its rationales, the request to the model, which
  carries the whole call, and anything you attach to the process yourself.
- The transcript is untrusted input. The prompt tells the model that the call is
  material to evaluate, and the rules hold whatever the model does: it cannot
  invent a criterion, cite an utterance that is not there, set the score, or let
  a failed critical criterion stand without a person.
- The scorecard under `data/` is illustrative. A real one comes from your quality
  team and the obligations that apply to your calls.

## Not yet done

The agent has not been run against a live model from this repository, so there
is no measurement of how well it judges a call. That needs an evaluation set of
calls scored by your quality team, which is also what the open change request
`OCR-0002` (Calibration) is about.
