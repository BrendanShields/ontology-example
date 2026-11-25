### Bug fix

<!-- Adapted from pstack: skills/poteto-mode/playbooks/bug-fix.md. Steps 1, 6 and 7 are new, and
     the focused-fix exception is shortened. See .claude/pstack/NOTICE.md. -->

A bug that was observed in operation starts in the Incident playbook, which records it and hands over to step 3 here.

**You own this task. Plan, review, verify.** Delegate investigation and the fix to subagents, stay in the lead.

Be scientific. Every shipped line traces to runtime evidence. Belt-and-suspenders that "might help" is a hypothesis, not a fix. It does not ship. When evidence refutes a hypothesis, revert what it motivated. The smallest change the evidence justifies ships, nothing more.

Select known non-sensitive fields before printing diagnostic output. Never print a value of a term the glossary classifies as PII or confidential, anything the project's CLAUDE.md says never to print, a whole configuration or an environment.

1. [intake] Name the Requirement the bug breaks. If there is none, the missing Requirement is the first finding: write it with `bin/onto new Requirement` and a Task that implements it.
2. [intake] Reproduce it yourself, on the matching surface. Ask the user only with a stated, specific reason you cannot reach the target. If it won't reproduce directly, synthesize the trigger, tighten conditions, or instrument until it fires.
3. [design] Binary-search the cause. Form the candidate hypotheses, then rule them out until one survives. Seed them with a trace of the affected subsystem and the **why** skill for the Decisions in force and the regression history. Each pass, take the split that cuts the most remaining problem space, get runtime evidence, eliminate. Don't guess.
4. [design] Plan the fix. If it crosses a function boundary, `architect` first. If it reverses a Decision in force, write the Decision that supersedes it before the code.
5. [implement] Delegate the fix to the `implementer` subagent with a specific scope.
6. [verify] The failing repro becomes a Test item that `verifies` the Requirement from step 1. Stage the commits so the failing test lands before the fix. Unit tests show branch behavior, not bug absence: the original repro must now pass on the same surface.
7. [trace] `bin/onto evidence collect --scope branch`, then `bin/onto trace --scope branch` reports no error.
8. [ship] Open the pull request as in the Feature playbook's last step.

For any bug fix, run `architect` in step 4 before implementing changes to interfaces, ownership, schema, or concurrency guarantees, even within one function. Before marking the fix merge-ready, require the `reviewer` subagent for changes to code that enforces a security or data-integrity invariant, even when the fix preserves that invariant. A review gate stays closed when no independent reviewer can run: record `BLOCKED: independent review` in the task list and say so.

**Reply:** what was broken, root cause, fix, how you verified. Quote the decisive failing and passing output, trimmed to the assertion and the counts.

#### Focused-fix exception

Skip **how**, **why** and step 4's `architect` only when all of these hold, and record the evidence for each in the task list before the skip:

- Runtime evidence establishes the cause in one subsystem.
- The correction preserves interfaces and state semantics, and reverses no Decision in force.
- A cheap regression check exercises the failure, and verification on the original surface is available.
- No competing design or contradictory evidence remains.

Every other step stays in force. Patch size alone never qualifies a fix.
