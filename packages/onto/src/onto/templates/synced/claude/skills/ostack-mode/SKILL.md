---
name: ostack-mode
description: The engineering workflow of this repository. pstack's poteto-mode with the ontology gates built into its playbooks. Use for any change to an app, for /ostack-mode, or when asked to work the ostack way.
---

# ostack mode

<!-- Adapted from pstack: skills/poteto-mode/SKILL.md at the commit in .claude/pstack/provenance.json.
     What changed and why is in .claude/pstack/NOTICE.md. MIT, (c) 2026 Lauren Tan, Michael Denyer. -->

This is pstack's way of working, kept where it fits and changed where this repository differs. Kept: a playbook copied into the task list step by step, a small set of principles, deliberate subagents, a decision trail and verified work. Changed: the playbooks carry the ontology gates as steps of their own, the subagents are Claude models only, and the autonomy rules are those of a regulated team.

The ontology layer is in `onto.toml`. `{{onto_cmd}} --help` lists every command named below.

## Non-negotiables

- First message → restate the user's goal and the smallest change that meets it, then proceed. Open each subagent brief, PR `## Why`, and final report with the goal.
- A name for a domain concept → `{{onto_cmd}} resolve <name>` before you write it. If it is not a term, run **term-gap**. Never coin a name, and never edit `ontology/` to make a check pass.
- Work on an app → read the ontology slice first: `{{onto_cmd}} slice --task <TASK-id>`. It holds the terms, the Decisions in force and the Requirements already established on them.
- Code → name the data shape first. In a domain layer the shapes are the generated types. Across a function boundary → **architect**. Contested design → **interrogate**.
- A fork you could settle by running something → run it instead of asking.
- "Done" is a claim the gate checks. Collect the evidence first, then set the status: `{{onto_cmd}} evidence collect`, then `{{onto_cmd}} trace`.
- Every playbook keeps a decision trail (**show-me-your-work**): `{{onto_cmd}} log --phase <stage> ...` at each fork and at the end of each stage.

## Principles

Read the leaf skill in full for any principle you apply. In your reply, name each principle that shaped a decision and the specific choice it changed. Cite only principles whose leaf SKILL.md you read this session.

- **Model the Domain** (**principle-model-the-domain**). Writing stateful logic, or code that branches a lot or repeats a shape assumption across files. Here the domain is modelled once, in `ontology/domains/`, and the code gets its types from it.
- **Type System Discipline** (**principle-type-system-discipline**). Designing types or a signature. Derive types from the authoritative schema, parse external data at boundaries.
- **Boundary Discipline** (**principle-boundary-discipline**). Wiring validation, error handling, or adapters. Guards at system boundaries, trust internal types, keep business logic pure.
- **Prove It Works** (**principle-prove-it-works**). After a task, before declaring done. Verify against the real artifact, not a proxy or "it compiles".

pstack has nineteen more. They are not vendored here: see `.claude/pstack/README.md` to add one.

## Autonomy

**Just do it.** Reversible work inside this repository proceeds without asking: reading, editing code and work items, running tests and `{{onto_cmd}}`.

**Always pause** for irreversible writes (force-push to shared branches, deploys, data deletion) and for anything that leaves the repository: a message to a person, a ticket update, a call to an outside service. Edits to the ontology sources pause by themselves: the guard hook asks the person.

**Session overrides:** "Don't stop" / "run until done" → keep going on reversible work. The pauses above still hold.

**No is an acceptable answer.** Asked whether to do something, invited to add scope, or shown an approach, reply with your real judgment. Decline, push back, or say "this doesn't earn its place" when true. A recommendation is a judgment, not a validation.

## Subagents

Use the project agents for work inside a playbook step. All of them run on Claude models.

- `implementer` writes code for one Task. The ontology slice of the task in hand is put into its context when it starts.
- `domain-analyst` is read-only. It finds the gap between a request and the glossary.
- `reviewer` is read-only. It tries to break a change and reports only what it proved by running something.
- `ontology-steward` drafts an OntologyChangeRequest and, once a person has approved it, the edit.

You own every subagent's work. Review the diff and write your own summary. Give a fix round, a follow-up or a retry to a fresh subagent with the original brief, every later directive and the prior agent's report. Never count your own review, passing tests or CI as the independent verdict a playbook asks for.

## The gates you will meet

Each is a hook in `.claude/settings.json` running `{{onto_cmd}}`. When one answers, do what it says: it names what was found, what would have been accepted and the command that fixes it.

| When | Gate | It checks |
| --- | --- | --- |
| before an edit | `onto guard` | generated files, evidence and ontology sources are not edited casually |
| after an edit | `onto check-terms` | a work item validates, and domain-layer code uses no denied synonym |
| when you stop | `onto trace` | what this branch touched is verified by passing evidence |
| in CI | all of the above, on everything | plus `onto gen --check` and the competency questions |

## Playbooks

Match the task to a playbook and open its steps at `playbooks/<title>.md`, with the title in kebab case. Copy its steps into the task list first, word for word. A step you choose not to do stays in the list with a one-line `skip: <reason>`.

Feature, Bug fix, Investigation, Ontology change.

Each step is tagged with the stage it belongs to: intake, vocabulary, design, implement, verify, trace, ship. Use the tag as `--phase` when you log a decision. `{{onto_cmd}} view` reads the repository and says which stage each Task has reached.

## Writing the reply

Write short declarative sentences with no long dash and no colon as a connector. Lead with what changes for the user. Give each claim its evidence or a label (measured, inferred, or guess). Never hand the human a check you could run. Keep every item the playbook's reply names, each rendered as prose, with no section headers.
