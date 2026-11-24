---
name: principle-boundary-discipline
description: "Apply when wiring validation, error handling, or framework adapters. Concentrate guards at system boundaries (CLI, config, network, external APIs); trust internal types and keep business logic in pure functions."
user-invocable: false
---

# Boundary Discipline

<!-- Adapted from pstack: skills/principle-boundary-discipline/SKILL.md. The last section is new.
     See .claude/pstack/NOTICE.md. -->

Validate, narrow types, and handle errors where data crosses a system boundary (CLI args, config files, external APIs, network). Inside, trust the types: no re-validation and no redundant nil checks. Parse raw data into domain types at the boundary, and keep transport and framework types out of the public surface. Business logic lives in pure functions with no framework dependencies. The shell that calls them is thin.

Two tests. Is this data crossing a boundary right now? If not, the validation is redundant. Can this be a pure function the shell just calls? If yes, extract it.

## In this repository

The boundary of a bounded context is drawn in `onto.toml`: `domain_paths` is the inside. Inside, only glossary vocabulary is used and only generated types are passed around. `bin/onto check-terms` holds that line after every edit.

Another system's vocabulary stops at the boundary too. Where an adapter has to spell a name the glossary denies, because an outside API calls it that, keep the adapter outside the domain layer and translate there.
