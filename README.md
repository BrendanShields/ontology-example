# ontology-example

An ontology-backed delivery framework for agentic engineering, in a Python monorepo. A small ontology in git types the work (requirements, tasks, decisions, tests, changes, incidents) and the domain vocabulary, and every stage of the lifecycle from intake to incident is held by a deterministic gate that runs as a Claude Code hook and in CI, with no model in the loop. One app, **a call quality assurance agent** that scores recorded customer calls against a scorecard, is built with it as the worked example, and `onto init` scaffolds the same layer into another repository.

The ontology is used in two places:

- **While an app is being built**, the ontology is the vocabulary and the typed spine of the work. Hooks and CI check every requirement, every edit to domain code and every claim of "done" against it.
- **While the app runs**, the same ontology is compiled into the agent's types and its tool schema. The language model can only propose findings in the ontology's shape, and a proposal that breaks a rule comes back with what would have been accepted.

## Try it

```bash
uv sync
```

```bash
make check
```

`make check` runs what CI runs, in order: generated files match the ontology, work items validate, the domain layer uses glossary vocabulary, the settings deny edits to generated files, lint, the import contracts, 683 tests that record evidence, the traceability gate, and the rule bindings. Two runs on the laptop this was built on took 186 and 194 seconds, nearly all of it in the tests.

```bash
bin/onto view
```

The last lines of what it prints:

```text
TASK-0007 [done] State each rule of the write path in a Requirement of its own
  [x] intake  [x] vocabulary  [x] design  [x] implement  [x] verify  [x] trace  [x] ship

TASK-0008 [done] Name the publication of an Evaluation as a state machine in the domain layer
  [x] intake  [x] vocabulary  [x] design  [x] implement  [x] verify  [x] trace  [x] ship

TASK-0009 [done] Keep a ledger of Reviews and AuditRecords and give call-qa the commands for it
  [x] intake  [x] vocabulary  [x] design  [x] implement  [x] verify  [x] trace  [x] ship

REQ-0016 [done] replaces REQ-0009

24 of 24 agreed requirement(s) verified, 0 gate error(s)
```

Then run the agent offline, on a synthetic call in which the representative reads out a balance before verifying identity. The evaluation goes to stdout and holds every rationale, so this sends it to a file and shows only the trace:

```bash
uv run call-qa evaluate apps/call-qa-agent/data/calls/CALL-0002.yaml \
  --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml \
  --replay apps/call-qa-agent/data/replays/CALL-0002.json --trace > /tmp/CALL-0002.evaluation.yaml
```

```text
[1] record_finding criterion=greeting finding_outcome=NOT_MET cited_utterances=[2] -> ok
[2] record_finding criterion=recording-notice finding_outcome=MET cited_utterances=[1] -> ok
[3] record_finding criterion=? finding_outcome=NOT_MET cited_utterances=[4, 5, 6] -> REJECTED (UNKNOWN_CRITERION)
[4] record_finding criterion=identity-verified finding_outcome=NOT_MET cited_utterances=[4, 5, 6] -> ok
[5] record_finding criterion=request-confirmed finding_outcome=NOT_MET cited_utterances=[] -> REJECTED (MISSING_CITATION)
[6] record_finding criterion=request-confirmed finding_outcome=NOT_MET cited_utterances=[3, 4] -> ok
[7] record_finding criterion=request-resolved finding_outcome=MET cited_utterances=[6, 8, 14] -> REJECTED (UNKNOWN_UTTERANCE)
[8] record_finding criterion=request-resolved finding_outcome=MET cited_utterances=[6, 8] -> ok
[9] finish_evaluation -> REJECTED (MISSING_FINDING)
[10] record_finding criterion=complaint-handled finding_outcome=NOT_MET cited_utterances=[3, 7, 8] -> ok
[11] finish_evaluation -> ok
```

Eleven tool calls, four of them rejected with the rule that broke. The evaluation in the file has score 35, `FAIL`, `NEEDS_REVIEW`.

## How it fits together

```text
 ontology/workflow.yaml  ontology/domains/call-qa.yaml        the only hand-written sources (LinkML)
          |                         |
          +----------- onto gen ----+                          compiled, committed, drift-checked
          |                         |
  JSON Schema + SHACL        Pydantic types + JSON Schema + glossary
  + a page for people        + a page for people + rule bindings (read from the code)
          |                         |
   work/*.md is typed        apps/call-qa-agent imports the types,
   and validated             builds its tool schema and its prompt from them
          |                         |
          +---- traceability graph (RDF) ----+                 rebuilt from the files on every run
                         |
   SHACL gates . branch gates . competency questions . slices . rule bindings
                         |
   Claude Code hooks (while working) and CI (on everything)
                         |
   prov/: a provenance bundle per Change and one index of what the gates showed

 .claude/ + ontology/ --- make templates ---> packages/onto/.../templates ---> onto init, in your repository
```

## The monorepo

```text
onto.toml                  which ontology governs which app: one table per bounded context
ontology/
  workflow.yaml            L1: Requirement, Task, Decision, Change, Test, Evidence, Incident, shared by every app
  domains/call-qa.yaml     L2: the glossary of the call-qa context, 73 terms
  schemas/  shapes/        generated JSON Schema and SHACL, plus the hand-written gates
  cq/                      ten competency questions as SPARQL files, with their tests
work/                      typed work items: REQ-, TASK-, DEC-, TST-, CHG-, OCR-, INC-
apps/call-qa-agent/        the app
packages/onto/             the tooling behind bin/onto, and the templates `onto init` scaffolds
docs/adopting.md           the guide for another repository
docs/generated/            a page per ontology, with a class diagram. Generated.
mods/                      three Claude mods that draw `onto view`
tools/                     vendoring check, template sync, hook driver
.claude/                   hooks, skills, subagents, and the vendored pstack files
.github/workflows/         the same gates in CI
```

To add an app: add its glossary under `ontology/domains/`, add a `[contexts.<name>]` table to `onto.toml` pointing at the app's paths, and run `bin/onto gen`. Every command, hook and CI step picks the right glossary from the path of the file it is looking at.

## The ontology

**The workflow ontology** types the work itself. A requirement is one EARS sentence bound to glossary terms. A task implements requirements. A test verifies them. Evidence records a test run. A decision can supersede another and can name the paths it affects. An incident names the requirements it shows broken. Each is a markdown file under `work/` whose frontmatter must validate:

```yaml
id: REQ-0002
title: A Finding cites only Utterances of its Call
status: done
bounded_context: call-qa
ears_text: >-
  If a `Finding` cites an `Utterance` that is not in the `Call`, then the call-qa-agent shall
  answer with an `UNKNOWN_UTTERANCE` `Rejection` and not record the `Finding`.
uses_terms: [Finding, Utterance, Call, Rejection, UNKNOWN_UTTERANCE]
risk_tier: high
```

**The domain ontology** is the bounded context's glossary. Every class, slot, enum and enum value is a term with a definition. A term can also carry a data classification, spellings that resolve to it, synonyms that are denied, and a binding that says it is a rule or a computed value:

```yaml
Scorecard:
  description: >-
    The list of Criteria that Calls of one kind are evaluated against,
    together with the pass mark an Evaluation has to reach.
  aliases: [QA form]
  annotations:
    denied_synonyms: [Rubric, EvaluationForm]
```

The work items record why. `DEC-0002` replaced "rubric", the machine learning team's word, with "scorecard", the quality team's, and from then on the old name is refused in new code.

`bin/onto gen` compiles both files. Nothing generated is edited by hand, and `bin/onto gen --check` fails when a generated file and its source disagree. It checks eight files:

| From | Generated | Used by |
| --- | --- | --- |
| `workflow.yaml` | `ontology/schemas/workflow.schema.json` | validating work item frontmatter |
| `workflow.yaml` | `ontology/shapes/workflow.shacl.ttl` | validating the graph |
| `workflow.yaml` | `docs/generated/workflow.md` | people: every class and link, with a Mermaid class diagram |
| `call-qa.yaml` | `apps/call-qa-agent/.../generated.py` | the app's types (Pydantic) |
| `call-qa.yaml` | `.../schemas/call-qa.schema.json` | the agent's tool schema |
| `call-qa.yaml` | `.../schemas/call-qa.glossary.json` | definitions quoted in the agent's prompt |
| `call-qa.yaml` | `docs/generated/call-qa.md` | people: every term, classification and denied synonym |
| `call-qa.yaml` and the app's code | `.../schemas/call-qa.bindings.json` | which function produces each bound rule |

## The lifecycle

`bin/onto view` reports seven stages for each task, computed from the files. Work that comes back after ship has no stage of its own. It enters at intake again with a link that says where it came from (`DEC-0018`).

| Stage | What happens | The gate | Command |
| --- | --- | --- | --- |
| intake | a Requirement in one EARS sentence, and a Task that implements it | the typed write path validates before it writes | `bin/onto new Requirement ...` |
| vocabulary | every name in the Requirement is a glossary term | an unknown term or a denied synonym is refused | `bin/onto resolve <name>`, `bin/onto validate` |
| design | the Decisions in force on the terms and the files are read, and a new choice is recorded | a superseded Decision is marked on both ends | `bin/onto slice --task <id>`, `bin/onto new Decision ...` |
| implement | code against the generated types | guard before an edit, term check after it, import contracts in `make check` | `bin/onto check-terms`, `uv run lint-imports` |
| verify | a Test item per Requirement names a pytest node, and a test run records Evidence | Evidence is written only by a test run | `bin/onto evidence collect --scope branch` |
| trace | the Task and its Requirements are set to done | a done Requirement needs a Test with passing Evidence, and a bound rule needs code and proof | `bin/onto trace`, `bin/onto rules` |
| ship | a Change that resolves the Task, and a provenance bundle | a done Change resolves only done Tasks | `bin/onto new Change ...`, `bin/onto prov emit --change <id>` |
| incident | something observed in operation is recorded, and a Requirement is reopened or raised from it | an Incident is done only when those Requirements are done | `bin/onto new Incident ...`, `bin/onto cq CQ-08` |
| rule change | a new Requirement `replaces` the old one, which becomes superseded | a superseded Requirement needs a successor that is done | `bin/onto cq CQ-09 --bind requirement=<id>` |
| ontology change | a person approves an OntologyChangeRequest, then the glossary is edited and regenerated | a branch that changed an ontology source must carry an approved request | `bin/onto ocr new ...`, `bin/onto gen` |

There is no Release class and no operate stage. No Incident has been recorded in `work/`: nothing in this repository's history was observed in operation. The Incident route is exercised by tests on scratch repositories and by the adoption test.

## The gates

Each gate is one command. It answers with what it found, what would have been accepted and the command that fixes it, so a person or an agent can act on it.

| Gate | Runs | Checks | When it fails |
| --- | --- | --- | --- |
| `onto guard` | before an edit by Claude's file tools | generated files and evidence are not edited. An ontology source is edited only with an OntologyChangeRequest in progress. `onto.toml`, the `.claude` settings files, CODEOWNERS and the CI workflows are put to a person. So is an edit that approves a request | denies the edit, or asks the person |
| deny rules in `.claude/settings.json` | on every tool call | nine rules, one per generated file and one for `work/evidence/**`, derived from `onto.toml` by `onto guard --deny-rules` | Claude Code refuses the edit |
| `onto guard --check-settings` | `make check`, CI | every derived deny rule is in the settings file | fails CI |
| `onto check-terms` | after an edit, and in CI | a work item validates. Domain code uses no denied synonym | blocks on a denied synonym, warns on a coined class |
| `onto validate` | `make check`, CI | every work item and glossary: shape, links, vocabulary, binding annotations | fails CI |
| `onto gen --check` | `make check`, CI | the eight generated files match their sources | fails CI |
| `uv run lint-imports` | `make check`, CI | five import contracts: the domain layer reaches only the generated types and does no I/O, and each layer imports only those below it | fails CI |
| `onto trace` | `make check`, CI | six graph gates: a done Requirement is verified by passing Evidence, a done Change resolves done Tasks, a Requirement about personal information has a high risk tier, a superseded Decision is marked, a replaced Requirement is marked, a closed Incident is fixed | fails CI |
| `gate:OntologyChangeIsRequested` | inside `onto trace` | a branch that changed an ontology source also changed an OntologyChangeRequest that is in progress or done, whatever tool made the change | fails CI, holds the stop |
| `gate:BranchBaseIsKnown` | inside `onto trace`, not at stop | the base branch resolves, so "what this branch changed" means something | fails CI |
| `error[namespace]` | inside `onto trace` | every gate file and competency question uses the workflow ontology's namespace | fails CI, holds the stop |
| `onto rules` | `make check`, CI, after the tests | every bound rule and computed value is produced by a function and proved by a done Requirement with a passing Test | fails CI |
| the stop gate | when Claude stops | `onto trace --gate stop --scope branch --collect`: the gates for what the branch touched, the tests its Test items name, and `gate:GeneratedMatchesSource` | sends Claude back once, then hands over |
| `onto verify` | on demand, and in CI | runs the ontology gates again and writes one index, `prov/verify.json` | exits 1, and the index is written either way |
| `tools/check_vendored.py` | `make check`, CI | the 14 vendored pstack files match their pinned commit | fails CI |

The guard sees Claude's file tools only: Edit, Write, MultiEdit and NotebookEdit. A shell command meets no hook. That is why the branch gates sit in `onto trace`: they read the diff against the base branch. `make hooks` drives every hook with a documented event. Part of its output:

```text
event         tool         case                                           answer   exit  median
PreToolUse    Edit         a normal file                                  allow    0      0.05s
PreToolUse    Edit         a generated file                               deny     2      0.05s
PreToolUse    Edit         an ontology source, no request                 deny     2      0.21s
PreToolUse    Edit         an ontology source, request in progress        ask      0      0.21s
PreToolUse    Edit         onto.toml                                      ask      0      0.05s
PreToolUse    Edit         a request, status set to in_progress           ask      0      0.20s
PreToolUse    Bash         a shell command that edits an ontology source  no hook  -          -
PostToolUse   Write        a denied synonym in a domain file              block    2      0.22s
Stop          -            a work item changed, its test passes           allow    0      0.92s
Stop          -            an ontology source changed by a shell command  block    2      1.02s
```

Things to break, each of which you can undo:

**Use a retired name in the domain layer.** Add `def load_rubric(agent_id): ...` to `apps/call-qa-agent/src/call_qa_agent/domain/scoring.py` and run `bin/onto check-terms`. Undo it with `git checkout`:

```text
apps/call-qa-agent/src/call_qa_agent/domain/scoring.py:84: error[denied-term] 'agent' uses 'Agent', a denied synonym: the call-qa glossary calls this Representative
    did you mean: Representative
    fix: rename it to use Representative; if this is a different concept, raise an OntologyChangeRequest: onto ocr new --context call-qa --term agent --justification "..."
apps/call-qa-agent/src/call_qa_agent/domain/scoring.py:84: error[denied-term] 'rubric' uses 'Rubric', a denied synonym: the call-qa glossary calls this Scorecard
    did you mean: Scorecard
    fix: rename it to use Scorecard; if this is a different concept, raise an OntologyChangeRequest: onto ocr new --context call-qa --term rubric --justification "..."
onto check-terms: 4 file(s), 2 error(s), 0 warning(s)
```

**Write a requirement that coins a term.** The typed write path refuses it and writes nothing:

```bash
bin/onto new Requirement title="Calibrate against a person" bounded_context=call-qa \
  ears_text='The call-qa-agent shall record a `Calibration` for every tenth `Evaluation`.' \
  uses_terms=Calibration,Evaluation risk_tier=urgent
```

```text
onto: nothing was written.
work/REQ-0026.md:3: error[unknown-term] ears_text: 'Calibration' is not a term of the call-qa glossary
    fix: use an existing term, or if this is a new concept raise an OntologyChangeRequest: onto ocr new --context call-qa --term Calibration --justification "..."
work/REQ-0026.md:5: error[unknown-term] 'Calibration' is not a term of the call-qa glossary
    fix: use an existing term, or if this is a new concept raise an OntologyChangeRequest: onto ocr new --context call-qa --term Calibration --justification "..."
work/REQ-0026.md:6: error[schema] risk_tier is 'urgent', which is not one of its permitted values
    allowed: low, medium, high, critical
```

**Claim something is done without proof.** Create a Requirement that says it is done and run `bin/onto trace`. Undo it with `rm work/REQ-0026.md`:

```bash
bin/onto new Requirement "title=Every Evaluation names its Scorecard" bounded_context=call-qa \
  'ears_text=The call-qa-agent shall record one `Scorecard` for each `Evaluation`.' \
  uses_terms=Scorecard,Evaluation status=done risk_tier=low
```

```text
work/REQ-0026.md: error[gate:CompleteRequirementIsVerified] Requirement is claimed complete (it is done, or all its Tasks are) but no Test verifies it.

onto trace: 1 error(s), 0 warning(s)
```

Evidence cannot be written by hand to get past this. It is recorded by a test run (`uv run pytest --onto-evidence`), lives in `work/evidence/`, and is not committed: CI collects it fresh.

Those are the three to try. One more gate has no quick way to break it here, because the binding is declared in the glossary: `bin/onto rules` holds every term the glossary marks `binding: rule` or `binding: computed` to a function that produces it and to a proof. It reports 10 bound terms here, each in this shape:

```text
  RejectionRule.DUPLICATE_FINDING  [rule]
      produced by: apps/call-qa-agent/src/call_qa_agent/domain/guardrails.py::check_finding
      proven by:   REQ-0013 by TST-0009, TST-0014
```

The function is found by reading the code, so a rename cannot leave a stale declaration (`DEC-0017`). The scan goes by name. It shows that a function mentions the rule, not that the function enforces it: the Requirement and its Test stand behind that.

The graph gates are SHACL shapes in [`ontology/shapes/gates.shacl.ttl`](ontology/shapes/gates.shacl.ttl), checked with inference off. OWL axioms are not used as gates (`DEC-0013`).

## Asking the graph

Competency questions are the questions the ontology exists to answer. Each is a SPARQL file in [`ontology/cq/`](ontology/cq/) with a test that pins its answer.

```bash
bin/onto cq CQ-03 --bind term=score
```

```text
CQ-03: Which Decisions about a term are still in force?
term      decision  title
--------  --------  -----------------------------------------------------------------
qa:score  DEC-0005  Leave Criteria that do not apply out of the score
qa:score  DEC-0006  The model proposes Findings and the domain layer decides the rest
```

Four decisions are about `score`. Two were superseded, and they match the words of the question as well as the two that stand. The answer is right because it follows the links, not the text. There are ten questions. The others ask what a change serves (CQ-01), which agreed requirements have no test (CQ-02), what a decision replaced all the way back (CQ-04), which requirements touch personal information (CQ-05, CQ-07), what depends on a term (CQ-06), which incidents have no verified fix (CQ-08), what replaced a requirement all the way forward (CQ-09), and which decisions in force affect a path (CQ-10, with `--bind path=<file>`). A query runs `SELECT` or `ASK` only and may not contain `SERVICE`.

An agent is never handed the whole ontology. It gets a table of contents (`bin/onto overview`), looks names up one at a time (`bin/onto resolve "pass mark"`), and receives a slice for the task in hand (`bin/onto slice --task TASK-0002`): the terms its requirements use, their neighbours, the decisions in force on those terms and on the files the branch changed, and the requirements already established. A slice is fitted to a budget of 3,000 tokens by a four-characters-per-token estimate. On this checkout the largest of the nine is about 2,965.

There is no MCP server. The command line answers each tool a server would offer, and hooks do what a server cannot (`DEC-0014`).

## Bounded verification

The app's write path is checked by running the real code on every case within a stated bound and checking each result against the Requirements. This is every case within a bound. It is not a proof. There is no TLA+ or SMT model: both were built and measured during validation and neither found what the bounded run did not (`DEC-0015`).

| Explorer | The bound | Explored | Properties |
| --- | --- | --- | --- |
| scoring | Scorecards of 1 to 3 Criteria, weights 1 to 3, critical or not, every combination of outcomes, pass marks 0 to 100 | 623,574 Evaluations, and 388 lists of Findings | S1 to S7 |
| session | 1 to 3 Criteria, a Call of two Utterances, every proposal from every state | 438 states, 34,014 steps | G1 to G7 |
| loop | 2 Criteria, 0 to 4 turns over 13 kinds of turn, against a scripted stand-in for the model | 30,941 runs | L1 to L6 |
| ledger | every sequence of 0 to 5 commands over 9 commands, for one Call and one Scorecard | 66,430 sequences | P1 to P13 |

Each count is asserted as a literal in [`apps/call-qa-agent/tests/bounded/test_bounded.py`](apps/call-qa-agent/tests/bounded/test_bounded.py), so a bound that shrinks by accident fails the test. Each property is one sentence in `explore.PROPERTIES`.

**Mutants.** 63 planted faults, each an exact swap of source text applied to a copy of the package, each of which a named property must report. A swap whose text no longer occurs exactly once fails on purpose: the guarded line changed and a person must look again. They are 66 test nodes with their controls. `uv run pytest -m 'not mutants'` leaves them out for a fast run. `make check` and CI run them.

**Statecharts.** Two state diagrams are generated from the runs, not drawn by hand: [`docs/evaluation-loop.md`](apps/call-qa-agent/docs/evaluation-loop.md) and [`docs/publication.md`](apps/call-qa-agent/docs/publication.md) under the app. A test fails when a committed diagram and the code disagree.

Outside the bound: larger Scorecards and weights, the SDK's parsing of a response, the refusal fallback, the Bedrock client, the content of the requests sent to the model, two writers on one ledger at once, and a write cut short. The oracle is one author's reading of the Requirements. Mutants show that a check can fail, not that the oracle is right.

The `bounded-verification` skill gives the method for another app, and says when a model checker is the right tool instead: when the question is about order between actors.

## The app

[`apps/call-qa-agent`](apps/call-qa-agent/) reads a call transcript and a scorecard and produces an evaluation. What the model controls is small on purpose (`DEC-0006`):

- The model has two tools, `record_finding` and `finish_evaluation`. The input schema of `record_finding` is the JSON Schema generated from the ontology, narrowed to the criteria of the scorecard in use, and sent with `strict: true`.
- Every proposed finding goes through one guarded write path. A finding that names an unknown criterion, cites an utterance that is not in the call, or judges without citing anything is not recorded. The tool result carries a `Rejection`, a type from the ontology, saying which rule broke and what would have been accepted, and the model corrects itself.
- The score, the outcome and whether a person must review the evaluation are computed from the accepted findings in the domain layer. The model is never asked for them.
- If the model has not finished within its turn limit, there is no evaluation, and the outstanding rejections are reported.

**Review and publication.** The model proposes, a person permits, the system commits (`DEC-0010`). An evaluation is staged on a ledger. One that needs review is published only after a review confirmed it:

```bash
LEDGER=/tmp/call-qa-ledger.jsonl
DATA=apps/call-qa-agent/data
uv run call-qa evaluate $DATA/calls/CALL-0002.yaml --scorecard $DATA/scorecards/retail-banking-v1.yaml \
  --replay $DATA/replays/CALL-0002.json --stage $LEDGER > /tmp/CALL-0002.evaluation.yaml
uv run call-qa publish $LEDGER CALL-0002 retail-banking-v1
```

```text
Refused: the Evaluation of CALL-0002 against retail-banking-v1 has the disposition NEEDS_REVIEW and no Review has confirmed it.
```

`publish` exits 1 and prints a `REVIEW_REQUIRED` rejection. After a review it goes through:

```bash
uv run call-qa review $LEDGER CALL-0002 retail-banking-v1 --reviewer QA-0007 --outcome CONFIRMED
uv run call-qa publish $LEDGER CALL-0002 retail-banking-v1
```

```text
CALL-0002 against retail-banking-v1: STAGED, disposition NEEDS_REVIEW, 1 Review(s), 1 AuditRecord(s).
CALL-0002 against retail-banking-v1: PUBLISHED, disposition NEEDS_REVIEW, 1 Review(s), 2 AuditRecord(s).
```

What this is and is not:

- **The ledger is a local file.** JSON lines in a file you name. A line holds identifiers, states, times and a digest, and never the text of an utterance, a rationale or a score.
- **Publishing records a state and reaches no downstream system.** `publish` writes `PUBLISHED` on the ledger. Nothing receives the evaluation. A team adopting this puts its system of record where the file is and keeps the domain layer.
- **A reviewer is whatever identifier you pass.** Nothing checks who it is.
- **The file is checked for consistency, not for tampering.** Whoever can write the file can publish.
- **The lock is `flock`.** It holds between processes on one machine, on macOS and Linux.

There is no generated action layer with a dry run and a staging step for every verb. The app has one effect outside its process, and that effect has the ledger (`DEC-0011`).

Run it against Claude with an API key in the environment:

```bash
uv run call-qa evaluate apps/call-qa-agent/data/calls/CALL-0001.yaml \
  --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml --trace
```

The app talks to the Messages API directly and hosts its own tool loop, and `--platform bedrock` is written to run the same loop there. By default the model is `claude-opus-5-5` at high effort, and on the Claude API a request a safety classifier declines is retried on a fallback model the server picks. Turn that off with `--no-fallback` if your model governance needs one evaluator: a declined request then produces no evaluation. None of this has been run against a live model from this repository. See the [app's README](apps/call-qa-agent/README.md) for settings, exit codes, the full list of what the ledger is not, and what to decide before sending real calls to a model.

## Adopting it in your own repository

[`docs/adopting.md`](docs/adopting.md) takes you from an empty ontology layer to one requirement verified by a test, with CI and code owners wired. In short:

```bash
# in a checkout of this repository
uv build --package onto-cli --out-dir dist

# in your repository
uv add --dev "onto-cli[gen] @ file:///path/to/dist/onto_cli-0.1.0-py3-none-any.whl"
uv run onto init --context loans --domain-path "src/loans/domain/**" \
  --base-uri https://ontology.your-org.example
```

`onto init` writes `onto.toml`, the workflow ontology, the gates, the ten competency questions, a starter glossary, the Claude Code layer and a CI workflow, then runs `onto gen`. It writes missing files and never overwrites one. What it scaffolds from this repository is 56 template files: the workflow ontology, the gates, the ten questions, the `.claude/` layer and the vendoring check. `make templates` keeps them in step with their sources, and a test fails when they are stale. `packages/onto/tests/test_adoption.py` scaffolds a repository, takes a Requirement from written to verified, closes an Incident, changes a rule, and feeds the scaffolded guard and stop hooks their events. It does not cover the guide's steps for a first glossary term, CI or code owners. It is `onto init` and not a plugin or a fixed layout for the reasons in `DEC-0019`.

What you get is the tooling and the workflow. What you write is your glossary, your requirements and your tests. Read the [limits](docs/adopting.md#limits) first: evidence is pytest only, generated types are Python only, and there is no upgrade command.

## Working in Claude Code

Open Claude Code at the repository root. [`CLAUDE.md`](CLAUDE.md) orients it and [`.claude/settings.json`](.claude/settings.json) wires the gates in as hooks. To see one fire, ask Claude to add the line `rubric = 1` to `apps/call-qa-agent/src/call_qa_agent/domain/scoring.py`: the term check answers that the glossary calls this Scorecard.

The hooks run `bin/onto` on your machine whenever Claude edits a file or stops. Read `.claude/settings.json` before you open a clone of this repository that you did not write.

| Hook | Runs | Measured by `make hooks` |
| --- | --- | --- |
| PreToolUse on Edit, Write, MultiEdit, NotebookEdit | `onto guard` | 0.05 to 0.21 s |
| PostToolUse on the same tools | `onto check-terms` on the file | 0.05 to 0.26 s |
| SubagentStart for `implementer` | `onto slice --for-subagent`: the slice of the task in hand goes into its context | 0.30 s |
| Stop | `onto trace --gate stop --scope branch --collect` | 0.40 to 1.02 s on the driver's scratch repository |
| SessionEnd | `onto prov emit --scope branch` | 0.29 s |

Hooks that run on an edit are exact checks under half a second, and `make hooks` fails if one is slower. The whole suite does not run on an edit, and no gate blocks on comments (`DEC-0016`).

**The workflow is a modified pstack.** `/ostack-mode` is pstack's router adapted for this repository. It picks one of six playbooks and copies its steps into the task list word for word, so a skipped step stays visible with its reason. The ontology gates are numbered steps in those playbooks, each tagged with its stage:

| Playbook | Use it when |
| --- | --- |
| Feature | a Task adds behaviour |
| Bug fix | a Requirement is broken and the repro is a test |
| Incident | something was observed in operation. It records the Incident and hands over to Bug fix |
| Rule change | a done Requirement would have to say something else. It is replaced, not edited |
| Investigation | a question, answered from the graph first |
| Ontology change | a term is added, renamed, redefined or retired. A person approves it |

**Skills.** Fourteen, under `.claude/skills/`. Ten are adapted from pstack: `ostack-mode`, `how`, `why`, `architect`, `interrogate`, `show-me-your-work` and four principles. Four were written here:

- `term-gap` finds the names in a request that the glossary does not have.
- `ontology-change` is the only route by which `ontology/` changes.
- `bounded-verification` runs real code over every case within a bound, with mutants.
- `encode-correction` turns a correction into a check at the highest rung that can hold it: the ontology, then a gate or a contract, then a test, and one line of CLAUDE.md last. The check must be seen failing on the original mistake.

**Agents.** Four subagents: `implementer`, `domain-analyst`, `reviewer` and `ontology-steward`.

Fourteen pstack files are vendored, unchanged, under [`.claude/pstack/upstream/`](.claude/pstack/) at a pinned commit with their hashes and licence. [`NOTICE.md`](.claude/pstack/NOTICE.md) lists every change, and `python tools/check_vendored.py --diff` shows them line by line. The main changes: reviewers are Claude models only, anything that leaves the repository pauses for a person, and the decision log is committed and becomes provenance.

**Three mods draw the state of the work.** Each runs `bin/onto view` and draws what it reports, so the judgement about a stage stays in tested Python.

| Mod | Command | Shows |
| --- | --- | --- |
| `sdlc-stages` | `/sdlc` | the stage each task has reached and the gate that guards it, plus a one-line band above the prompt |
| `ontology-map` | `/ontology` | each context's classes, definitions, classifications and denied synonyms, and how the workflow classes link |
| `work-plan` | `/work-plan` | the playbook steps from Claude's task list, open tasks in dependency order, decisions in force, open change requests |

Load them for a session with `claude --plugin-dir mods/sdlc-stages --plugin-dir mods/ontology-map --plugin-dir mods/work-plan`, or install them from the marketplace file at the repository root. [`mods/README.md`](mods/README.md) has the details.

## Changing the ontology

A term is a commitment every requirement, test and line of domain code is held to, so the glossary changes only through an OntologyChangeRequest that a person approves. `work/OCR-0002.md` is an open one, a draft for a term the quality team has not agreed. The steps are the Ontology change playbook: raise the request, prove the term is new, draft the definition, stop for a person, then edit, regenerate and verify.

Three things hold this, and none of them proves that a person approved:

- **The guard** denies an edit to `ontology/` while no request is in progress, and asks the person to confirm each edit while one is. It also asks before an edit that sets a request to in progress or done. `onto new` refuses to create a request that is already approved.
- **The branch gate** `gate:OntologyChangeIsRequested` fails `onto trace` when a branch changed an ontology source and did not change a request that is in progress or done. It reads the diff, so it applies to a shell command and to a person's editor too.
- **The pull request** is the control. [`.github/CODEOWNERS`](.github/CODEOWNERS) is a template, commented out, for requiring the context's owners to approve.

Three requests on this branch are in progress: `OCR-0003` (rule bindings), `OCR-0004` (Incident, `raised_from`, `replaces`, `affects`) and `OCR-0005` (Review and publication). Each is for a person to set to done.

## The spec this was checked against

The framework was checked, part by part, against a candidate specification for an ontology-driven agentic Python monorepo. Each part was tested on a scratch copy before anything was built. The Decisions hold the measurements. The numbers in this table were measured then and were not run again.

| Part of the candidate spec | Verdict | Reason | Decision |
| --- | --- | --- | --- |
| Data layer: domain nouns as LinkML classes, slots and enums | already here | the glossary is the data layer and the only hand-written source | none |
| Logic layer: each rule names its Python function and its tests | adapted | the glossary marks which terms are rules. The function is found by reading the code and the proof is the Requirement chain, so a rename is not an ontology change | `DEC-0017` |
| Action layer compiled into a typed SDK with `dry_run()` and `stage()` | rejected | two verbs with no effect to rehearse. The one effect has a ledger. `onto new --dry-run` was adopted for work items | `DEC-0011` |
| Memory layer: decisions with supersedes and affects, constraints, anti-patterns | adapted | `affects` was added to Decision. A done Decision is the constraint and a denied synonym is the anti-pattern | `DEC-0018` |
| Types generated from the ontology and never hand-edited | already here | `onto gen`, with a drift check, a guard and deny rules | none |
| Compiled OWL, with `owl:FunctionalProperty` and `owl:disjointWith` as enforcement | rejected | an OWL axiom infers and does not refuse. No axiom rejected bad data in seven cases, and inference hides a violation the gates rely on | `DEC-0013` |
| Compiled SHACL as the validator | already here | generated shapes for each work item, hand-written shapes across them, inference off | `DEC-0013` |
| Generated Markdown and Mermaid documentation | adopted | `onto gen` writes a page per ontology under `docs/generated/`, drift-checked | none |
| Two-gate agent loop: typed input, validated output with a structured verdict | already here | the generated types at the boundary, and a `Rejection` for each proposal, which is stricter than one gate at the end | `DEC-0006` |
| Side effects only after the second gate: propose, permit, commit, with an audit record | adapted | a publication state machine in the domain layer and a ledger of Reviews and AuditRecords, keyed on the disposition | `DEC-0010`, `DEC-0012` |
| Local ontology MCP server | rejected | it returned the same bytes as the command line, and its free-form query gave a wrong answer where the competency question gave the right one | `DEC-0014` |
| PreToolUse deny on generated files and on the harness's own configuration | adopted | deny rules derived from `onto.toml`, and the guard asks a person before an edit to a file that configures the gates | `DEC-0016` |
| PostToolUse hook that runs the whole suite on every edit | rejected | it cannot block, and it measured about 40 times the cost of the hooks in place | `DEC-0016` |
| A gate that blocks on code comments | rejected | it would fail on this repository's own code and cannot tell a reason from narration | `DEC-0016` |
| Stop hook that blocks when the ontology changed without a decision | adapted | a branch gate inside `onto trace` asks for an OntologyChangeRequest, at stop and in CI | `DEC-0016` |
| Import boundaries between layers | adopted | five import-linter contracts in `make check` and CI | `DEC-0016` |
| Formal verification of the domain logic | adapted | bounded runs of the real code with mutants. A TLA+ model and an SMT model were built, measured and rejected | `DEC-0015` |
| Mermaid statechart of reachable states | adapted | generated from runs of the real code and held to it by a test | `DEC-0015` |
| Verification bundle under `artifacts/verify/` | adapted | one derived index, `prov/verify.json`, beside the provenance bundles. Nothing verified is committed | `DEC-0020` |
| `/change-business-rule` skill | adapted | a Rule change playbook: a new Requirement `replaces` the old one, and a gate holds the pair | `DEC-0018` |
| `/correct` skill | adapted | `encode-correction`, with this repository's ladder: ontology, gate or contract, test, prose | none |
| The whole lifecycle, including release and operation | adapted | Incident and three links were added. A Release class is deferred and an operate stage is rejected | `DEC-0018` |
| A layout other teams copy | adapted | `onto init` scaffolds from templates in the package, and the layout is configuration | `DEC-0019` |

`DEC-0009` to `DEC-0020` were decided by Claude during the build, at the repository owner's request. Each says so, and each is for a person to confirm.

## What was checked, and what was not

Checked on 2026-11-26, on one Apple laptop, by running the command named:

- `make check` exits 0. 683 tests are collected: 426 for the tooling, 235 for the app, 22 for the competency questions. 682 pass and 1 is skipped: it needs a volume that tells `DOMAIN` from `domain`.
- `bin/onto validate` reports 113 work items, 0 errors, 0 warnings. `bin/onto trace` reports 24 of 24 agreed requirements verified by passing evidence. `bin/onto rules` reports 10 bound terms, 0 errors. `bin/onto verify --scope all` reports that every gate holds.
- `make hooks` drove each hook with a payload in the shape the Claude Code hooks reference documents, in a scratch repository, and checked its answer and exit code.
- `make mods`: the three mods pass `claude plugin validate` and their 8 tests, with Claude Code 2.1.332.
- `uv run lint-imports` keeps 5 contracts. `tools/check_vendored.py` finds the 14 vendored files unchanged.
- `gen-owl` runs on the call-qa glossary and emits no `FunctionalProperty`, `disjointWith` or `oneOf`. Its output is not kept.
- The offline replay and the review and publication commands above were run, and the output shown is what they printed.
- The adoption guide was walked by hand in a temporary repository: `onto init`, the four checks after it, a Requirement from written to verified, and a rule change that `onto trace` refused while the new Requirement was not done and accepted once it was. This used the editable install of this repository, not a wheel. The guide's steps for a first glossary term, an Incident, CI and code owners were not walked by hand.

Observed in the session that built this, and not by a test: the guard asked a person before each request was approved and before each edit to an ontology source.

Carried over from the first version of this repository, and not run again: the agent's tool loop was run through the real Anthropic SDK against a mocked HTTP transport. LinkML's generators were checked against each other, which found that `gen-pydantic` in LinkML 1.12 turns `minimum_value` on a multivalued slot into a bound on the list.

Not checked:

- **The agent has not called a real model.** No API credentials were used. Nothing here says how well Claude judges a call: the tests cover the request, the loop and the rules.
- **The Bedrock path has not been run.** It is written from the SDK's documented client and model-id conventions.
- **Nothing ran on Linux or on a case-sensitive volume.** The guard's handling of letter case has a branch that only runs there. The ledger's lock was run on macOS only.
- **The CI workflow has not run on GitHub.** Its steps are the ones `make check` runs, then `onto prov emit` and `onto verify`.
- **The Mermaid diagrams were not rendered by Mermaid.** A test reads the structure of the class diagrams, and a test holds the two state diagrams to the code. Neither is Mermaid. Open them on GitHub once.
- **No playbook has been followed end to end by an agent in a live session.** The hooks were driven with payloads. The Incident and Rule change routes were exercised through the command line in tests.
- **The scaffolded Claude Code layer of an adopting repository has not been opened in Claude Code.** The adoption test runs the commands and feeds the hooks their events.
- **Nobody has looked at a mod's pane.** The tests mount each pane on the terminal, desktop, VS Code and mobile surfaces and check what it contains, not how it looks.
- **The independent review that the playbooks ask for is owed** on `TASK-0004`, `TASK-0008` and `TASK-0009`. Their decision logs under `.audit/` say so.
- **The measurements inside the Decisions were taken during validation**, on prototypes in a scratch directory that is not in this repository. Each Decision says which numbers were measured then and which were run for the record.

## Known limits and open decisions

What a reader must know before relying on this. The first five are product decisions somebody has to make.

- **The approval of a request is not cryptographically a person.** The guard asks, and the branch gate checks that a request in progress or done changed on the branch. A shell command can set a request's status, and then only the Bash permission prompt stands in the way. An approved request's context and text can be rewritten with no prompt. Code owner review of the pull request is the control, and the CODEOWNERS file is a template.
- **The ledger is not tamper-evident, and it is POSIX only.** A removed line is not noticed. A reviewer is an unauthenticated string. The lock needs `fcntl`, so there is no Windows path, and it may not hold on a network file system.
- **Evidence is pytest only.** A Test item's `path` is a pytest node. A team with another test runner gets the vocabulary checks and no traceability gate.
- **There is no upgrade path after `onto init`.** It writes missing files and never updates one.
- **An Evaluation has no identifier in the glossary.** A Review names it by Call and Scorecard, so a second Evaluation of the same Call is refused in every state, and a withheld one cannot be replaced (`DEC-0012`).
- **Function and constant names in a domain layer are unchecked.** `onto check-terms` blocks a denied synonym anywhere and warns on a class with a coined name. A function named outside the glossary passes.
- **An Incident reads only statuses.** One that `breaks` a Requirement which was never set back from done can be closed at once. An Incident set to superseded passes the graph gate, and only `onto validate` refuses it.
- **The rule scan goes by name.** A term in a parameter default or in dead code counts as produced. The proof half checks that a verified Requirement lists the term, not that its Test exercises the rule.
- **The import contracts are deny lists.** A new module nobody listed can be imported by the domain layer.
- **A Requirement cannot be withdrawn with nothing in its place, and nothing is retired from the record.**
- **`onto build --out` writes to any path,** and `bin/onto` is allow-listed, so it can overwrite a guarded file without a prompt.
- **With no base branch to compare with, the stop gate sees only uncommitted changes.** `onto trace` in `make check` and CI fails with `gate:BranchBaseIsKnown` instead. A push to the default branch compares it with itself, so the pull-request run is the control for an ontology change.
- **No property reads what is sent to the model.** A fault in the text of a tool result or in the conversation history passes the bounded checks.

[`docs/adopting.md`](docs/adopting.md#limits) lists the limits an adopter meets, and the [app's README](apps/call-qa-agent/README.md) lists the app's.

## Design notes

- **LinkML is the only source.** Engineers edit YAML and review it in pull requests.
- **Gates run on generated artefacts and on the files, never on a model.** They are deterministic.
- **Blocking is reserved for what is exact.** A denied synonym is an exact match against a list a person wrote, so it blocks. A class defined under an unknown name might be a helper, so it warns. Denied synonyms in plain prose warn too.
- **The graph is derived.** It is rebuilt from the files on every run and never stored, so it cannot go stale. Evidence, provenance and the verify index are derived too, and none is committed.
- **A hook is a prompt and a paper trail, not the control.** The controls are the gates that read the diff, and the review of the pull request.
- **Agents propose and people decide** on the ontology, on what leaves the repository, and on an evaluation that needs review at runtime.
- **A check must be seen to fail.** Each gate constraint has a test that breaks it, and each bounded property has a mutant.
- **A broken tool never blocks.** A hook that cannot run exits with a non-blocking error. CI is the backstop.

Left out on purpose, each with its Decision: OWL axioms as gates and a committed OWL file (`DEC-0013`), an MCP server (`DEC-0014`), a TLA+ or SMT model (`DEC-0015`), a hook that runs the suite on every edit and a gate on comments (`DEC-0016`), a generated action layer (`DEC-0011`), a Release class and an operate stage (`DEC-0018`), a plugin as the way to adopt (`DEC-0019`). Also left out, with no Decision: a graph server, imports of large external ontologies, and a code graph. The glossary maps two classes to schema.org by reference and imports nothing.

## Licence

The files under `.claude/pstack/upstream/` and the skills adapted from them are MIT licensed by their authors: see [`.claude/pstack/LICENSE`](.claude/pstack/LICENSE). The rest of the repository has no licence file yet. Add the one you want before sharing it.
