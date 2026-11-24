# ontology-example

A monorepo whose root carries an ontology layer that governs how the apps under
`apps/` are built. The one app is `apps/call-qa-agent`.

## Start here

- Any change to an app: `/ostack-mode`. It picks a playbook and copies its steps into the task list.
- A name for a domain concept: `bin/onto resolve <name>` before writing it. Never coin one.
- What a task needs to know: `bin/onto slice --task <TASK-id>`.
- Where every task stands: `bin/onto view`.

## Commands

- `uv sync` installs everything into `.venv`.
- `make check` runs every gate CI runs, in order.
- `uv run pytest` runs the tests. Add `--onto-evidence` to record Evidence.
- `bin/onto --help` lists the ontology commands. `onto.toml` wires them to the repository.

## Layout

- `ontology/workflow.yaml` types the work itself. `ontology/domains/<context>.yaml` is a bounded context's glossary.
- `work/` holds the typed work items: REQ, TASK, DEC, TST, CHG, OCR. Create them with `bin/onto new`.
- `apps/<app>/src/<package>/domain/` is a domain layer: glossary vocabulary only, generated types only.
- `packages/onto/` is the tooling behind `bin/onto`.
- `mods/` holds three Claude mods that draw `bin/onto view`.

## Rules the hooks enforce

- Generated files are never edited: `ontology/schemas/`, `ontology/shapes/workflow.shacl.ttl`, and each app's `generated.py` and `schemas/`. Change the ontology and run `bin/onto gen`.
- `ontology/` changes only through an OntologyChangeRequest a person has approved: `/ontology-change`.
- `work/evidence/` is written only by a test run.
- A Requirement or Task is `done` only when `bin/onto trace` holds. Otherwise it is `in_progress`.
- Never print or log the text of an Utterance.
