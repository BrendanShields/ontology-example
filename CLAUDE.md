# ontology-example

A monorepo whose root carries an ontology layer that governs how the apps under
`apps/` are built. The one app is `apps/call-qa-agent`. `onto init` scaffolds the
same layer into another repository: `docs/adopting.md`.

## Start here

- Any change to an app: `/ostack-mode`. It picks a playbook and copies its steps into the task list.
  Playbooks: Feature, Bug fix, Incident, Rule change, Investigation, Ontology change.
- A name for a domain concept: `bin/onto resolve <name>` before writing it. Never coin one.
- What a task needs to know: `bin/onto slice --task <TASK-id>`. What constrains a file: `bin/onto slice --file <path>`.
- Where every task stands: `bin/onto view`.
- A person corrected you, or a mistake came back: `/encode-correction`. Make it a check, and watch the check fail.
- A rule over a value space, a state machine or a guarded write path: `/bounded-verification`.

## Commands

- `uv sync` installs everything into `.venv`.
- `make check` runs every gate CI runs, in order. It takes a little over three minutes.
- `uv run pytest` runs the tests. Add `--onto-evidence` to record Evidence, or `-m 'not mutants'` for a fast run.
- `bin/onto verify` reruns the ontology gates and writes `prov/verify.json`. It is not `make check`.
- `bin/onto rules` holds each bound rule to its code and its proof.
- `bin/onto new <Class> --dry-run ...` validates a work item and writes nothing.
- `make templates` after any change under `.claude/`, to `ontology/workflow.yaml`, the gates or a competency question. Commit the result.
- `make hooks` drives every hook with a documented event.
- `bin/onto --help` lists the ontology commands. `onto.toml` wires them to the repository.

## Layout

- `ontology/workflow.yaml` types the work itself. `ontology/domains/<context>.yaml` is a bounded context's glossary.
- `work/` holds the typed work items: REQ, TASK, DEC, TST, CHG, OCR, INC. Create them with `bin/onto new`.
- `apps/<app>/src/<package>/domain/` is a domain layer: glossary vocabulary only, generated types only, no I/O.
- `apps/<app>/tests/bounded/` runs the real code over every case within a bound, with mutants.
- `packages/onto/` is the tooling behind `bin/onto`. `packages/onto/src/onto/templates/synced/` is generated.
- `mods/` holds three Claude mods that draw `bin/onto view`.

## Rules the hooks and gates enforce

- Generated files are never edited: `ontology/schemas/`, `ontology/shapes/workflow.shacl.ttl`, `docs/generated/`,
  each app's `generated.py`, `schemas/` and `docs/`, and the synced templates. Change the source and run the generator.
- `ontology/` changes only through an OntologyChangeRequest a person has approved: `/ontology-change`.
  A branch that changes an ontology source must also carry a request that is `in_progress` or `done`, or `bin/onto trace` fails.
- You never approve a request. Create it as a draft. A person sets its status.
- An edit to `onto.toml`, `.claude/settings.json`, `.github/CODEOWNERS` or `.github/workflows/` is put to a person. Do not route around the prompt.
- A term the glossary binds as a rule or a computed value needs a function that produces it and a `done` Requirement
  with a passing Test: `bin/onto rules`.
- `work/evidence/` is written only by a test run.
- A Requirement or Task is `done` only when `bin/onto trace` holds. Otherwise it is `in_progress`.
- A `done` Requirement is never edited to say something else. A new Requirement `replaces` it: the Rule change playbook.
- An Incident is closed as `done`, never `superseded`.
- Never print or log the text of an Utterance or the rationale of a Finding.
- Say "holds for every case within the bound". Never say "proved".
