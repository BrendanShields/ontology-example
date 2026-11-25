# call-qa-agent

An agent that evaluates one recorded customer call against a scorecard: a finding
per criterion, each citing the utterances that show it, then a score, an outcome
and whether a person must review the result. An evaluation that needs review is
not published until a person has confirmed it.

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
    publication.py   the state machine: staged, then published or withheld
  session.py       the guarded write path: the only way a Finding is recorded
  ledger.py        the one file the app writes: Reviews and AuditRecords, JSON lines
  tools.py         the model's two tools, their schema compiled from the ontology
  prompts.py       the system prompt, quoting definitions from the glossary
  agent.py         the tool loop against Claude
  replay.py        the same loop driven by recorded tool calls, offline
  cli.py           `call-qa`
data/              a synthetic scorecard, two synthetic calls, two replays
docs/              two state diagrams, drawn from runs of the code. Generated.
tests/
  acceptance/      examples for each Requirement under work/
  bounded/         every case within a stated bound, with planted faults each check must catch
```

Only glossary vocabulary may be used under `domain/`. `bin/onto check-terms`
enforces it after every edit. The domain layer reads and writes nothing, and
`uv run lint-imports` holds it to that: `ledger.py` does the reading and the
writing, and is handed the time.

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

`evaluate` writes nothing anywhere unless you give it `--stage`.

## Publishing an evaluation

The model proposes, a person permits, the system commits. An evaluation is
staged on a ledger, and from there it is published or withheld:

```bash
LEDGER=/tmp/call-qa-ledger.jsonl
DATA=apps/call-qa-agent/data

# Stage it. The evaluation still goes to stdout: keep it, the ledger does not.
uv run call-qa evaluate $DATA/calls/CALL-0002.yaml \
  --scorecard $DATA/scorecards/retail-banking-v1.yaml \
  --replay $DATA/replays/CALL-0002.json --stage $LEDGER > /tmp/CALL-0002.evaluation.yaml

# CALL-0002 failed a critical criterion, so this is refused: exit 1, REVIEW_REQUIRED.
uv run call-qa publish $LEDGER CALL-0002 retail-banking-v1

# A person confirms it, or overturns it with --outcome OVERTURNED.
uv run call-qa review $LEDGER CALL-0002 retail-banking-v1 --reviewer QA-0007 --outcome CONFIRMED

uv run call-qa publish $LEDGER CALL-0002 retail-banking-v1
uv run call-qa show $LEDGER CALL-0002 retail-banking-v1
```

| Where it stands | What can happen |
| --- | --- |
| staged, and it stands as it is | `publish` records it as published |
| staged, and it needs review | `publish` is refused until a review confirmed it. A review that overturns it withholds it |
| published, or withheld | nothing. Both are final |

[docs/publication.md](docs/publication.md) has the diagram and every answer each
command gives in each state. It is generated from runs of the real ledger.

What to know before relying on it:

- **Publishing is a record and nothing more.** `publish` writes the state
  PUBLISHED on the ledger. There is no system behind this example that an
  evaluation is sent to. Put yours where the ledger is.
- **The ledger holds no evaluation.** A line holds identifiers, states, times
  and a SHA-256 of the evaluation: never the text of an utterance, a rationale
  or a score. So keep the output of the `evaluate` that staged it.
- **One evaluation per call and scorecard.** The same evaluation staged again
  changes nothing. A different one for the same call and scorecard is refused,
  whatever state the first is in, so that a review of one never publishes
  another (`DEC-0012`). A live model gives a different evaluation each time, so a
  second `--stage` of the same call is refused. A withheld evaluation cannot be
  replaced: that would take a change to the ontology.
- **A reviewer is whatever identifier you pass.** Nothing checks it. The ledger
  is a record of what was permitted, not an access control.
- **One writer at a time.** There is no lock on the file.
- **A ledger someone edited is not believed.** Every read runs each line through
  the state machine again, and a line that records a change it does not permit
  fails the command.
- **Giving a command again is safe.** It finds its effect on the ledger and
  records nothing more.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done, or it had been done already |
| 1 | Refused. No evaluation was produced, or a rule or the state of the evaluation does not permit what was asked. The reason is on stderr, as rejections where a rule names it |
| 2 | Failed. A file or the ledger could not be read or written, or the request to the model could not be made |

`evaluate --stage` prints the evaluation and exits 1 when the staging is refused.

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
  the app writes, which is the ledger. `--trace` shows names, numbers and rule
  names, an unreadable file is reported by position and not by content, and the
  SDK's loggers are held at WARNING whatever `ANTHROPIC_LOG` says. Not covered:
  stdout, which carries the evaluation and its rationales, the request to the
  model, which carries the whole call, and anything you attach to the process
  yourself.
- The transcript is untrusted input. The prompt tells the model that the call is
  material to evaluate, and the rules hold whatever the model does: it cannot
  invent a criterion, cite an utterance that is not there, set the score, or
  have an evaluation that needs review published without a person.
- A reviewer's identifier is personal information too (`reviewer` is classified
  `PII`), and the ledger holds it.
- The scorecard under `data/` is illustrative. A real one comes from your quality
  team and the obligations that apply to your calls.

## Not yet done

Nobody is told that an evaluation is waiting for review: `evaluate --stage` says
so on stderr and that is all. A withheld evaluation cannot be evaluated again
under the same call and scorecard.

The agent has not been run against a live model from this repository, so there
is no measurement of how well it judges a call. That needs an evaluation set of
calls scored by your quality team, which is also what the open change request
`OCR-0002` (Calibration) is about.
