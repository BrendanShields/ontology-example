---
name: principle-type-system-discipline
description: "Apply when designing types, reviewing a function signature, or writing code in any statically-typed language. Make illegal states unrepresentable, brand semantic primitives, parse external data at boundaries, exhaust variants, derive from authoritative schemas."
user-invocable: false
---

# Type System Discipline

<!-- Adapted from pstack: skills/principle-type-system-discipline/SKILL.md. The pointer to the
     TypeScript skill is dropped and the last section is new. See .claude/pstack/NOTICE.md. -->

Make the compiler reject impossible states, mismatched primitives, and unhandled variants.

- **Brand semantic primitives.** If two arguments share a primitive type but mean different things, give each its own type. Validate once at creation.
- **External data is untyped until parsed.** JSON, RPC payloads, CLI args, config, environment variables, and database rows go through a parse function at the boundary that returns the typed model.
- **Derive types from authoritative schemas.** When a schema file owns a shape, derive the type from it instead of hand-rolling a parallel one.

## In this repository

The authoritative schema is the ontology. `bin/onto gen` derives the Pydantic types and the JSON Schema from it, and `bin/onto gen --check` fails the build when they drift. A language model's output is external data like any other: it is parsed into the generated types at the boundary and rejected there, with what would have been accepted, before any domain function sees it.

Generated does not mean correct. A generator can drop a constraint. `apps/call-qa-agent/tests/test_generated_types.py` checks the generated types against the generated schema for that reason: extend it when you add a constraint to the ontology.
