---
name: principle-model-the-domain
description: "Apply when writing stateful logic, or when code branches a lot or repeats a shape assumption across files."
user-invocable: false
---

# Model the Domain

<!-- Adapted from pstack: skills/principle-model-the-domain/SKILL.md. The last section is new.
     See .claude/pstack/NOTICE.md. -->

Encode the domain in a data structure instead of scattering it across conditionals. The right structure makes invalid states unrepresentable and deletes branches.

Reach for a state machine instead of scattered booleans or phase checks, a typed model instead of loose parameters, a map, registry, or discriminated union instead of branching spread across files, a reducer instead of ad hoc mutations, and an index, queue, or normalized collection where the access pattern calls for it.

Do not force it. Keep boring code when the shape is clear, local, and unlikely to grow, and distrust an abstraction that adds indirection without removing branches or invalid states.

The sign that you skipped this: a feature that grows an if/else chain by one more branch, or a second boolean that must stay in sync with the first.

## In this repository

The domain is modelled once, in `ontology/domains/<context>.yaml`, and the model is compiled into the types the code uses. So the structure you reach for usually exists already: an enum instead of a string comparison, a generated class instead of a dict. Look before you build: `bin/onto slice --task <TASK-id>`.

When the structure you need is missing from the ontology, the model is what is wrong, not the code. Raise an OntologyChangeRequest (**ontology-change**) instead of encoding the concept in conditionals, or in a class of your own beside the generated ones.
