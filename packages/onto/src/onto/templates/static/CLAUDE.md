# Ontology layer

This repository carries an ontology layer that governs how its code is built.
`onto.toml` wires it to the repository.

## Start here

- Any change to code a bounded context governs: `/ostack-mode`. It picks a playbook and copies its steps into the task list.
- A name for a domain concept: `{{onto_cmd}} resolve <name>` before writing it. Never coin one.
- What a task needs to know: `{{onto_cmd}} slice --task <TASK-id>`.
- Where every task stands: `{{onto_cmd}} view`.

## Layout

- `ontology/workflow.yaml` types the work itself. `ontology/domains/<context>.yaml` is a bounded context's glossary.
- `work/` holds the typed work items: REQ, TASK, DEC, TST, CHG, OCR, INC. Create them with `{{onto_cmd}} new`.
- The `domain_paths` of a context in `onto.toml` are its domain layer: glossary vocabulary only, generated types only.

## Rules the hooks enforce

- Generated files are never edited: `ontology/schemas/`, `ontology/shapes/workflow.shacl.ttl`, and each context's generated types and schemas. Change the ontology and run `{{onto_cmd}} gen`.
- `ontology/` changes only through an OntologyChangeRequest a person has approved: `/ontology-change`.
- `work/evidence/` is written only by a test run.
- A Requirement or Task is `done` only when `{{onto_cmd}} trace` holds. Otherwise it is `in_progress`.
