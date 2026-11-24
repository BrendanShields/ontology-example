---
name: how
description: "Use for \"how does X work\", code walkthroughs before changing something, and placement / ownership / layering questions (\"where should this live\", \"which package owns this\", \"is this the right layer\"). Explains subsystem architecture, runtime flow, onboarding mental models. Use why for motivation."
---

# How

<!-- Adapted from pstack: skills/how/SKILL.md. The mappings for other runtimes are dropped and the
     brief names this repository's layers. See .claude/pstack/NOTICE.md. -->

Explore the codebase to answer "how does X work?" questions.

If the scope is ambiguous, state your interpretation and explore. The user can redirect.

## 1. Explain

Spawn one `Agent` subagent with `subagent_type: "Explore"` that explores and explains in one pass. Give it the user's question and this brief:

> You are writing an architectural explanation for a senior engineer. Explore the codebase and write an explanation that a senior engineer unfamiliar with this area could read and walk away with a solid mental model. They should understand the architecture well enough to start working in it confidently. You have read-only access to the codebase.
>
> This is a monorepo. `onto.toml` maps each bounded context to the app it governs. Inside an app, the `domain/` folder is the domain layer: pure functions over types generated from the context's ontology in `ontology/domains/`. Use the glossary's names for domain concepts (`bin/onto overview` lists them, `bin/onto resolve <name>` looks one up) and say which layer each thing you describe lives in.

## 2. Present

Present the subagent's output. Light edits for clarity or context from the conversation are fine. Do not substantially rewrite it.
