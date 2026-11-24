# ontology-example

A Python monorepo that shows ontology-driven development with Claude Code, end to end, on one real app: **a call quality assurance agent** that scores recorded customer calls against a scorecard.

The ontology is small and lives in git. It is used in two places, and the repository exists to show both:

- **While the app is being built**, the ontology is the vocabulary and the typed spine of the work. Hooks and CI check every requirement, every edit to domain code and every claim of "done" against it, without a model in the loop.
- **While the app runs**, the same ontology is compiled into the agent's types and its tool schema. The language model can only propose findings in the ontology's shape, and a proposal that breaks a rule comes back with what would have been accepted.

## Try it

```bash
uv sync
```

```bash
make check
```

`make check` runs what CI runs: generated files match the ontology, work items validate, the domain layer uses glossary vocabulary, 176 tests pass and record evidence, and the traceability gate holds.

```bash
bin/onto view
```

```text
TASK-0003 [done] Bound the model's turns and report outstanding Rejections
  [x] intake  [x] vocabulary  [x] design  [x] implement  [x] verify  [x] trace  [x] ship

TASK-0004 [in_progress] Keep Utterance text out of the logs  <- in hand
  [x] intake  [x] vocabulary  [>] design  [ ] implement  [ ] verify  [ ] trace  [ ] ship
      design: no Decision on these terms yet  (gate: onto slice)

7 of 8 agreed requirement(s) verified, 0 gate error(s)
```

Then run the agent offline, on a synthetic call in which the representative reads out a balance before verifying identity:

```bash
uv run call-qa evaluate apps/call-qa-agent/data/calls/CALL-0002.yaml \
  --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml \
  --replay apps/call-qa-agent/data/replays/CALL-0002.json --trace
```

It prints each tool call, the four that were rejected with the reason, and the evaluation: score 35, `FAIL`, `NEEDS_REVIEW`.

## How it fits together

```text
 ontology/workflow.yaml  ontology/domains/call-qa.yaml        the only hand-written sources (LinkML)
          |                         |
          +----------- onto gen ----+                          compiled, committed, drift-checked
          |                         |
  JSON Schema + SHACL        Pydantic types + JSON Schema + glossary
          |                         |
   work/*.md is typed        apps/call-qa-agent imports the types,
   and validated             builds its tool schema and its prompt from them
          |                         |
          +---- traceability graph (RDF) ----+                 rebuilt from the files on every run
                         |
        SHACL gates . competency questions . slices . provenance
                         |
        Claude Code hooks (while working) and CI (on everything)
```

## The monorepo

```text
onto.toml                  which ontology governs which app: one table per bounded context
ontology/
  workflow.yaml            L1: Requirement, Task, Decision, Change, Test, Evidence, shared by every app
  domains/call-qa.yaml     L2: the glossary of the call-qa context, 57 terms
  schemas/  shapes/        generated JSON Schema and SHACL, plus the hand-written gates
  cq/                      competency questions as SPARQL files, with their tests
work/                      typed work items: REQ-, TASK-, DEC-, TST-, CHG-, OCR-
apps/call-qa-agent/        the app
packages/onto/             the tooling behind bin/onto
mods/                      three Claude mods that draw `onto view`
.claude/                   hooks, skills, subagents, and the vendored pstack files
.github/workflows/         the same gates in CI
```

To add an app: add its glossary under `ontology/domains/`, add a `[contexts.<name>]` table to `onto.toml` pointing at the app's paths, and run `bin/onto gen`. Every command, hook and CI step picks the right glossary from the path of the file it is looking at.

## The ontology

**The workflow ontology** types the work itself. A requirement is one EARS sentence bound to glossary terms. A task implements requirements. A test verifies them. Evidence records a test run. A decision can supersede another. Each is a markdown file under `work/` whose frontmatter must validate:

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

**The domain ontology** is the bounded context's glossary. Every class, slot, enum and enum value is a term with a definition. A term can also carry a data classification, spellings that resolve to it, and synonyms that are denied:

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

`bin/onto gen` compiles both files. Nothing generated is edited by hand, and `bin/onto gen --check` fails when a generated file and its source disagree.

| From | Generated | Used by |
| --- | --- | --- |
| `workflow.yaml` | `ontology/schemas/workflow.schema.json` | validating work item frontmatter |
| `workflow.yaml` | `ontology/shapes/workflow.shacl.ttl` | validating the graph |
| `call-qa.yaml` | `apps/call-qa-agent/.../generated.py` | the app's types (Pydantic) |
| `call-qa.yaml` | `.../schemas/call-qa.schema.json` | the agent's tool schema |
| `call-qa.yaml` | `.../schemas/call-qa.glossary.json` | definitions quoted in the agent's prompt |

## The gates

Each gate is one `bin/onto` command. It answers with what it found, what would have been accepted and the command that fixes it, so a person or an agent can act on it.

| Gate | Runs | Checks | When it fails |
| --- | --- | --- | --- |
| `onto guard` | before an edit | generated files, evidence and ontology sources are not edited casually | blocks the edit, or asks the person |
| `onto check-terms` | after an edit | a work item validates; domain code uses no denied synonym | blocks on a denied synonym, warns on a coined class |
| `onto trace` | when Claude stops, and in CI | what is claimed complete is verified by passing evidence; the other graph rules hold | sends Claude back once, fails CI |
| `onto gen --check` | CI | generated files match the ontology | fails CI |
| `onto validate` | CI | every work item and glossary | fails CI |

Things to break, each of which you can undo with `git checkout`:

**Use a retired name in the domain layer.** Add `def load_rubric(agent_id): ...` to a file under `apps/call-qa-agent/src/call_qa_agent/domain/` and run `bin/onto check-terms`:

```text
.../domain/scoring.py:1: error[denied-term] 'rubric' uses 'Rubric', a denied synonym: the call-qa glossary calls this Scorecard
    did you mean: Scorecard
    fix: rename it to use Scorecard; if this is a different concept, raise an OntologyChangeRequest: ...
```

**Write a requirement that coins a term.** The typed write path refuses it and writes nothing:

```bash
bin/onto new Requirement title="Calibrate against a person" bounded_context=call-qa \
  ears_text='The call-qa-agent shall record a `Calibration` for every tenth `Evaluation`.' \
  uses_terms=Calibration,Evaluation risk_tier=urgent
```

```text
onto: nothing was written.
work/REQ-0010.md:5: error[unknown-term] 'Calibration' is not a term of the call-qa glossary
    fix: use an existing term, or if this is a new concept raise an OntologyChangeRequest: onto ocr new --context call-qa --term Calibration --justification "..."
work/REQ-0010.md:6: error[schema] risk_tier is 'urgent', which is not one of its permitted values
    allowed: low, medium, high, critical
```

**Claim something is done without proof.** Set `status: done` in `work/REQ-0008.md`, which has no test, and run `bin/onto trace`:

```text
work/REQ-0008.md: error[gate:CompleteRequirementIsVerified] Requirement is claimed complete (it is done, or all its Tasks are) but no Test verifies it.
```

Evidence cannot be written by hand to get past this. It is recorded by a test run (`uv run pytest --onto-evidence`), lives in `work/evidence/`, and is not committed: CI collects it fresh.

The cross-artefact rules are SHACL shapes in [`ontology/shapes/gates.shacl.ttl`](ontology/shapes/gates.shacl.ttl): a claim of completeness needs passing evidence, a requirement about personal information needs a high risk tier, a done change resolves only done tasks, and supersession is recorded on both ends.

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

Four decisions are about `score`. Two were superseded, and they match the words of the question as well as the two that stand. The answer is right because it follows the links, not the text. The others ask what a change serves (CQ-01), which agreed requirements have no test (CQ-02), what a decision replaced all the way back (CQ-04), which requirements touch personal information (CQ-05, CQ-07) and what depends on a term (CQ-06).

An agent is never handed the whole ontology. It gets a table of contents (`bin/onto overview`), looks names up one at a time (`bin/onto resolve "pass mark"`), and receives a slice for the task in hand (`bin/onto slice --task TASK-0002`): the terms its requirements use, their neighbours, the decisions in force and the requirements already established on those terms. The largest slice in this repository is about 1,660 tokens by a four-characters-per-token estimate.

## The app

[`apps/call-qa-agent`](apps/call-qa-agent/) reads a call transcript and a scorecard and produces an evaluation. What the model controls is small on purpose (`DEC-0006`):

- The model has two tools, `record_finding` and `finish_evaluation`. The input schema of `record_finding` is the JSON Schema generated from the ontology, narrowed to the criteria of the scorecard in use, and sent with `strict: true`.
- Every proposed finding goes through one guarded write path. A finding that names an unknown criterion, cites an utterance that is not in the call, or judges without citing anything is not recorded. The tool result carries a `Rejection`, a type from the ontology, saying which rule broke and what would have been accepted, and the model corrects itself.
- The score, the outcome and whether a person must review the evaluation are computed from the accepted findings in the domain layer. The model is never asked for them.
- If the model has not finished within its turn limit, there is no evaluation, and the outstanding rejections are reported.

Run it against Claude with an API key in the environment:

```bash
uv run call-qa evaluate apps/call-qa-agent/data/calls/CALL-0001.yaml \
  --scorecard apps/call-qa-agent/data/scorecards/retail-banking-v1.yaml --trace
```

The app talks to the Messages API directly and hosts its own tool loop. That is deliberate: Managed Agents is not available on Amazon Bedrock, and `--platform bedrock` runs the same loop there. By default the model is `claude-opus-5-5` at high effort, and on the Claude API a request a safety classifier declines is retried on a fallback model the server picks. Turn that off with `--no-fallback` if your model governance needs one evaluator: a declined request then produces no evaluation. See the [app's README](apps/call-qa-agent/README.md) for settings and for what to decide before sending real calls to a model.

## Working in Claude Code

Open Claude Code at the repository root. [`CLAUDE.md`](CLAUDE.md) orients it and [`.claude/settings.json`](.claude/settings.json) wires the gates in as hooks.

**The workflow is a modified pstack.** `/ostack-mode` is pstack's router adapted for this repository. It picks a playbook (Feature, Bug fix, Investigation, Ontology change) and copies its steps into the task list word for word, so a skipped step stays visible with its reason. The ontology gates are numbered steps in those playbooks, each tagged with its stage:

```text
1. [intake]      Find the Task and the Requirements it implements, or create them with bin/onto new.
2. [vocabulary]  Run term-gap on the request. bin/onto validate reports no error before you go on.
...
7. [verify]      Each Requirement has a Test item. Run bin/onto evidence collect --scope branch.
8. [trace]       Only now set the Task and its Requirements to done. bin/onto trace reports no error.
```

Fourteen pstack files are vendored, unchanged, under [`.claude/pstack/upstream/`](.claude/pstack/) at a pinned commit with their hashes and licence. The adapted versions are the skills under `.claude/skills/`: `ostack-mode`, `how`, `why`, `architect`, `interrogate`, `show-me-your-work` and four principles. [`NOTICE.md`](.claude/pstack/NOTICE.md) lists every change, and `python tools/check_vendored.py --diff` shows them line by line. The main changes: reviewers are Claude models only, anything that leaves the repository pauses for a person, and the decision log is committed and becomes provenance.

Two skills and four subagents were written for this repository: `term-gap`, `ontology-change`, and the `implementer`, `domain-analyst`, `reviewer` and `ontology-steward` agents. When the `implementer` starts, a hook puts the ontology slice of the task in hand into its context.

**Three mods draw the state of the work.** Each runs `bin/onto view` and draws what it reports, so the judgement about a stage stays in tested Python.

| Mod | Command | Shows |
| --- | --- | --- |
| `sdlc-stages` | `/sdlc` | the stage each task has reached and the gate that guards it, plus a one-line band above the prompt |
| `ontology-map` | `/ontology` | each context's classes, definitions, classifications and denied synonyms, and how the workflow classes link |
| `work-plan` | `/work-plan` | the playbook steps from Claude's task list, open tasks in dependency order, decisions in force, open change requests |

Load them for a session with `claude --plugin-dir mods/sdlc-stages --plugin-dir mods/ontology-map --plugin-dir mods/work-plan`, or install them from the marketplace file at the repository root. [`mods/README.md`](mods/README.md) has the details.

## Changing the ontology

A term is a commitment every requirement, test and line of domain code is held to, so the glossary changes only through an OntologyChangeRequest that a person approves. `work/OCR-0002.md` is an open one, for a term the draft requirement `REQ-0009` needs. The steps are the Ontology change playbook: raise the request, prove the term is new, draft the definition, stop for a person, then edit, regenerate and verify.

The guard denies edits to `ontology/` while no request is in progress, and asks the person to confirm each edit while one is. That is a reminder with a paper trail. The control is the pull request: [`.github/CODEOWNERS`](.github/CODEOWNERS) is a template for requiring the context's owners to approve.

## What was checked, and what was not

Checked in the environment this was built in:

- 176 tests pass: 99 for the tooling, 66 for the app, 11 for the competency questions. `make check` passes.
- Each hook command was run with a payload in the shape the Claude Code hooks reference documents, and its exit code and output were checked. Guard and term check took 0.1 to 0.5 seconds, the stop gate 4.1 seconds including the test run.
- The agent's tool loop was run through the real Anthropic SDK against a mocked HTTP transport: the request it builds, tool results, rejection and correction, the turn limit, a declined request.
- The three mods pass `claude plugin validate` and their own tests on the terminal, desktop, VS Code and mobile surfaces.
- LinkML's generators were checked against each other, which found one defect: `gen-pydantic` in LinkML 1.12 turns `minimum_value` on a multivalued slot into a bound on the list. The ontology notes the workaround.

Not checked:

- **The agent has not called a real model.** No API credentials were used. Nothing here says how well Claude judges a call: the tests cover the request, the loop and the rules.
- **The Bedrock path has not been run.** It is written from the SDK's documented client and model-id conventions.
- **The hooks, skills, subagents and mods have not been used in a live Claude Code session.** Their formats follow the current documentation and the mods pass the engine's validator, but nobody has watched a playbook run or a pane render.
- **The CI workflow has not run on GitHub.** Its steps are the ones `make check` runs.

## Design notes

- **LinkML is the only source.** Engineers edit YAML and review it in pull requests. The OWL and SHACL path stays open: `gen-owl` works on the same files.
- **Gates run on generated artefacts and on the files, never on a model.** They are deterministic and fast enough to run after every edit.
- **Blocking is reserved for what is precise.** A denied synonym is an exact match against a list a person wrote, so it blocks. A class defined under an unknown name might be a helper, so it warns. Denied synonyms in plain prose warn too.
- **The graph is derived.** It is rebuilt from the files on every run and never stored, so it cannot go stale.
- **Agents propose and people decide** on the ontology, on what leaves the repository, and on a failed critical criterion at runtime.
- **A broken tool never blocks.** A hook that cannot run exits with a non-blocking error. CI is the backstop.

Left out on purpose: OWL reasoning, a graph server, an MCP server, imports of large external ontologies, a code graph. The glossary maps two classes to schema.org by reference and imports nothing.

## Licence

The files under `.claude/pstack/upstream/` and the skills adapted from them are MIT licensed by their authors: see [`.claude/pstack/LICENSE`](.claude/pstack/LICENSE). The rest of the repository has no licence file yet. Add the one you want before sharing it.
