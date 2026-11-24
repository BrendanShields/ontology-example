# Claude mods for this monorepo

Three mods for Claude Code. Each opens a pane beside the conversation and draws
the state of the ontology layer. None of them computes anything: each runs
`bin/onto view --format json` at the monorepo root and draws what it reports, so
the rules about what stage a task is at live in `packages/onto`, where they are
tested.

| Mod | Slash command | Shows |
| --- | --- | --- |
| [`sdlc-stages`](sdlc-stages/) | `/sdlc` | For each Task, the seven stages (intake, vocabulary, design, implement, verify, trace, ship), which one it has reached, why, and the gate that guards it. Also a one-line band above the prompt for the task in hand. |
| [`ontology-map`](ontology-map/) | `/ontology` | Each bounded context's classes with definitions, attributes, classifications and denied synonyms, its enums, and how the workflow classes link. |
| [`work-plan`](work-plan/) | `/work-plan` | The playbook steps Claude copied into its task list, the open Tasks in dependency order, Requirements by status, the Decisions in force and open ontology change requests. |

Each pane reads the repository again when a turn ends and when you press Refresh.

## Loading them

For one session, from the repository root:

```bash
claude --plugin-dir mods/sdlc-stages --plugin-dir mods/ontology-map --plugin-dir mods/work-plan
```

Or install them from the marketplace file at the repository root
(`.claude-plugin/marketplace.json`):

```bash
claude plugin marketplace add .
```

then, inside Claude Code, `/plugin install sdlc-stages`, and the same for the
other two.

Start Claude Code inside the monorepo: a mod finds the root by looking for
`onto.toml` in the working directory and its parents. `bin/onto` must work, so
run `uv sync` first.

## What a mod is made of

```text
<mod>/
  .claude-plugin/plugin.json   name, version, description, the state contract
  hooks/hooks.json             names the one hooks module
  hooks/register.tsx           the mod: commands, refreshes, and what the pane draws
  hooks/onto.ts                runs `bin/onto view`. The same file in all three mods.
  types/index.d.ts             the part of `onto view` the mod draws, and its state
  tests/*.test.tsx             mounts the pane on every surface against a stubbed engine
```

`work-plan` also watches Claude's task tools (`TaskCreate`, `TaskUpdate`,
`TodoWrite`) to mirror the playbook steps. It only observes: a call it fails to
mirror still runs.

## Checking them

```bash
make mods
```

runs `claude plugin validate .` over the marketplace and all three mods, then
`claude plugin test` on each. The mod API is early access and changes between
Claude Code releases. These were written and validated against Claude Code
2.1.331. If a later release refuses one, the validator says which line.

What has not been done: nobody has looked at these panes rendered in a live
session. The tests mount each pane on the terminal, desktop, VS Code and mobile
surfaces and check what it contains, not how it looks.
