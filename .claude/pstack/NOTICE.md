# Notice: material adapted from pstack

The workflow skills of this repository are adapted from **pstack**, Lauren Tan's
agent workflow, through its Claude Code port:

- pstack: <https://github.com/cursor/plugins/tree/main/pstack>, (c) 2026 Lauren Tan, MIT
- pstack-claude (the port): <https://github.com/michael-denyer/pstack-claude>, (c) 2026 Michael Denyer, MIT

The exact commit, and the hash of every file taken, are in [`provenance.json`](provenance.json).
The files as taken, unchanged, are under [`upstream/`](upstream/). The MIT licence
they came under is [`LICENSE`](LICENSE) and applies to those files and to the
adapted skills listed below.

## What was taken

Fourteen files out of several hundred: the router (`poteto-mode`), three of its
playbooks, five workflow skills, four principles and the decision-log header.
No script, hook or agent definition was taken.

## What was changed

| Adapted skill | From | Changes |
| --- | --- | --- |
| `ostack-mode` | `poteto-mode/SKILL.md` | Renamed. Non-negotiables cut to the skills vendored here, with three added for the ontology gates. Principles index cut to the four vendored. Autonomy narrowed: anything that leaves the repository pauses. Subagents are this repository's four, on Claude models only. Model-sheet, multi-runtime and project-playbook machinery removed. A table of the gates added. |
| `ostack-mode/playbooks/feature.md` | `poteto-mode/playbooks/feature.md` | Four steps added (intake, vocabulary gap, evidence, trace). Every step tagged with its stage. Delegation goes to the `implementer` subagent, and the worktree and arena instructions are removed. The PR step is written out. |
| `ostack-mode/playbooks/bug-fix.md` | `poteto-mode/playbooks/bug-fix.md` | Three steps added (the Requirement the bug breaks, the repro as a Test item, the trace). Focused-fix exception shortened. Publication paragraph removed. |
| `ostack-mode/playbooks/investigation.md` | `poteto-mode/playbooks/investigation.md` | A first step added: ask the graph. |
| `how` | `how/SKILL.md` | Other runtimes' mappings removed. The brief names this monorepo's layers. |
| `why` | `why/SKILL.md` | Reads the recorded Decisions before the history. |
| `architect` | `architect/SKILL.md` | Domain types come from the ontology. A lasting choice becomes a Decision. Pointer to `arena` removed. |
| `interrogate` | `interrogate/SKILL.md` | The fan-out is written out instead of delegated to `arena`. Reviewers are Claude models only and are sized by risk tier. |
| `show-me-your-work` | `show-me-your-work/SKILL.md` | The log is written by `bin/onto log`, committed, and turned into PROV-O. Transcript audit and cross-model review shortened. |
| `principle-*` (four) | the same four | Text kept. An "In this repository" section added to each. |

`ostack-mode/playbooks/ontology-change.md`, `term-gap`, `ontology-change` and the
four agents under `.claude/agents/` were written for this repository.

To see every change line by line: `python tools/check_vendored.py --diff`.
