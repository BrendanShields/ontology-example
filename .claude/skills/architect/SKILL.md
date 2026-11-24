---
name: architect
description: "Sketch types, signatures, and module structure before code, then stay in the loop while implementation fills in. Use for /architect, 'architect this', 'design this', or non-trivial work where jumping to code would lock in the wrong shape."
---

# Architect

<!-- Adapted from pstack: skills/architect/SKILL.md. The second and last paragraphs are new and the
     pointer to the arena skill, which is not vendored, is dropped. See .claude/pstack/NOTICE.md. -->

Before writing code, trace every system the change touches, then sketch two different shapes for it (types, signatures, module boundaries) and pick the one where each piece of state has one owner, each task has one way to do it, and callers need to know least. Redesign instead of patching if workarounds repeat.

In a domain layer the types are not yours to sketch. They are generated from the context's ontology, so start from `bin/onto slice --task <TASK-id>` and design the functions over those types. If the shape you want needs a type, a field or a value the ontology does not have, that is a vocabulary gap: stop and run **term-gap**. Do not define a look-alike type beside the generated ones.

Before closing each implementation unit or handing its contract to the next worker, compare accepted deviations with the saved sketch and rationale. Once the owner or review process accepts a change, update the affected parts of the sketch and record who accepted it. Keep unaccepted changes and unresolved disagreements visible, and never edit the sketch merely to justify what was implemented.

A choice that constrains later work becomes a Decision under `work/` (`bin/onto new Decision ...`), with `supersedes` when it replaces one. The sketch explains the shape. The Decision is what `why` finds next year.
