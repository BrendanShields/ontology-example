---
name: show-me-your-work
description: "Keep a reviewable decision trail: a TSV log with one row per decision (what, why, evidence, result). In this repository the trail is committed and becomes provenance. Use for /show-me-your-work, and in every playbook of ostack-mode."
---

# Show me your work

<!-- Adapted from pstack: skills/show-me-your-work/SKILL.md. pstack keeps the log local by default
     and writes it with a shell script. Here `{{onto_cmd}} log` writes it, it is committed, and
     `{{onto_cmd}} prov emit` turns it into PROV-O. The transcript audit and the cross-model
     review are shortened. See .claude/pstack/NOTICE.md. -->

Keep one canonical log per work item.

## The format

A single TSV file, one row per decision. Cells stay single-line. Evidence is a pointer, not prose. Columns:

- **ts.** ISO8601 timestamp.
- **phase.** The stage: intake, vocabulary, design, implement, verify, trace or ship.
- **decision.** What was chosen or done, one line.
- **why.** The reason in plain words. If a principle drove it, say it plainly, not as a jargon tag.
- **evidence.** A link or path that proves it: commit SHA, work item id, `file:line`, or an artifact path. Never a paragraph.
- **result.** The outcome or predicate state: `tests green`, `reverted`, `INCONCLUSIVE`, `open`.

## Logging a row

Write each entry the way you'd tell a teammate what you did. Plain words, concrete actions.

```bash
{{onto_cmd}} log --phase design --decision "score in the domain layer, not from the model" \
  --why "the model is unreliable at arithmetic" --evidence DEC-0006 --result "tests green"
```

It stamps `ts`, writes the header on first use and strips stray tabs and newlines. The row goes to `.audit/<TASK-id>.tsv` for the task in hand, or name another work item with `--about`.

Log decision points and checkpoints, not every action: a fork chosen, a unit completed with its verification result, a pivot or revert with its trigger, a blocker surfaced, a gate fixed. Skip the trivial and self-evident.

## Where it lives

`.audit/` is committed. A reviewer, and later an auditor, needs the trail to trust the result, and `{{onto_cmd}} prov emit` reads it: each row becomes a `wf:LoggedDecision` in the PROV-O bundle of the Change that resolves the task. A choice that outlives the task belongs in a Decision under `work/` as well: the log says what happened, the Decision says what holds.

## Rules

- Append-only. A wrong call gets a new row that supersedes it. Never edit or delete history.
- Prefer evidence produced by committed scripts and by `{{onto_cmd}}` over hand-made one-offs.

## Before handing back

Check the log told the truth. Walk its rows against what actually happened: every row maps to a real decision or action, each row's evidence resolves and shows what the row claims, and a fork, pivot or abandoned approach that shaped the work but isn't logged is a gap. Add it. Correct the log, not the story: never edit a row, add one that supersedes it.

Then have the `reviewer` subagent read the trail and flag what the user should pay attention to: decisions logged with weak or absent evidence, verification claimed without proof, choices that look risky in hindsight. End your reply with an "Attention" line listing each flag by row. "No flags" is a valid value.
