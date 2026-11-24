---
name: interrogate
description: "Use for \"interrogate\", \"adversarial review\", \"challenge this\", \"stress test this code\", \"find blind spots\", or \"tear this apart\". Adversaries try to break a change or design, and only findings proven by a run survive."
---

# Interrogate

<!-- Adapted from pstack: skills/interrogate/SKILL.md. pstack fans out through its arena skill to
     models of several families. Here the fan-out is written out, the reviewers are Claude
     models only, and the frame starts from the traceability graph.
     See .claude/pstack/NOTICE.md. -->

Adversaries try to break a change or a design. A finding survives only when a run proves it. Report the findings. Do not apply fixes.

## Frame

The scope is what the user names. Otherwise it is the branch diff from its merge base with the base branch, through the working tree. State the intent in your own words, from the user's message, the commits and the Requirements the branch touches. Ask the user when the intent is unclear.

Read what the graph says is at stake: `bin/onto trace --scope branch` for the Requirements in scope and their risk tier, `bin/onto slice --task <TASK-id>` for the Decisions in force. A Requirement at risk tier high or critical gets three adversaries, anything else two.

## Fan out

Spawn each adversary as the `reviewer` subagent, in the background, each with a different lens so they do not find the same thing: one on the Requirements (does the change do what each EARS sentence says, at the edges), one on the Decisions in force (does it quietly reverse one), and for high risk one on the data (can a classified term leak, can a guard be bypassed). Give each the scope, the intent, and this brief:

> Break this change. Prove each finding with a run against the real code, such as a failing test, a repro script, or command output that shows the wrong behavior. For a design or plan, run a prototype or probe the current tree. Report each finding with a title, the exact command, the output it printed, and the output the intent requires. Leave out anything you did not run. That covers style, naming, structure, and risks that need a future change to matter. No findings is a valid result.

## Verify

Verify each finding by rerunning its command yourself. Keep a finding when the output shows the failure and the failure breaks the intent. Drop the rest. Merge findings that share a root cause. Adversaries find different failures, so the verdict keeps every verified finding, not one adversary's list.

## Output

- **Intent**: the restatement.
- **Findings**: for each verified finding, the command, its output, how it breaks the intent, the Requirement or Decision it breaks, and the adversaries that found it. Say "no verified findings" when none survive.
- **Dropped**: for each adversary, the count of dropped findings and why.

A review by reviewers of one model family is weaker than pstack's mixed panel. Say so in the output when the risk tier is critical, and name the person who should also read the change.
