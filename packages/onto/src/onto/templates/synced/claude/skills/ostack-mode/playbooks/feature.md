### Feature

<!-- Adapted from pstack: skills/poteto-mode/playbooks/feature.md. Steps 1, 2, 7 and 8 are new, and step 4 has a sentence added.
     See .claude/pstack/NOTICE.md. -->

**You own the design. Plan, review, verify.** Delegate implementation. Stay in the lead.

1. [intake] Find the Task and the Requirements it implements under `work/`, or create them with `{{onto_cmd}} new`. One EARS sentence per Requirement, glossary terms in backticks, the same terms in `uses_terms`.
2. [vocabulary] Run **term-gap** on the request and on each Requirement. Every name that is not a term becomes a question to the person or an OntologyChangeRequest. `{{onto_cmd}} validate` reports no error before you go on.
3. [design] Trace the affected subsystem with **how**. Read `{{onto_cmd}} slice --task <TASK-id>` for the terms, the Decisions in force and the Requirements already established on them.
4. [design] `architect` for the shape. Record the choice as a Decision under `work/` when it constrains later work, with `supersedes` if it replaces one. A changed rule supersedes the Decision that set it.
5. [design] Write the throughput checkpoint as four todo items. A dimension that genuinely does not apply keeps its item with `n/a: <reason>` rather than being dropped:
   - **Blocking first steps.** Gates run before fan-out.
   - **Independent workstreams.** Disjoint files, services, or layers parallelize. Shared writes serialize.
   - **Shared mutable state.** Default to splitting the target. Serialize only for real invariants.
   - **Smallest safe decomposition.** If one worker is best, name why.
6. [implement] Delegate code-writing to the `implementer` subagent with a specific scope: file paths, the named data shape and its organizing structure per **principle-model-the-domain**, and success criteria. The slice reaches it by itself. Surgical edits. Commit liberally.
7. [verify] Each Requirement has a Test item whose `path` is a pytest node that fails without the change. A rule over a value space (a score, a threshold, a count) gets a bounded or property test, not hand-picked examples. Run `{{onto_cmd}} evidence collect --scope branch`. "Inconclusive" or wrong-surface is not a pass. Flag it.
8. [trace] Only now set the Task and its Requirements to `done`. `{{onto_cmd}} trace --scope branch` reports no error.
9. [trace] If the design is contested, or a Requirement's `risk_tier` is high or critical, `interrogate` before shipping.
10. [ship] Rebase into small, ordered commits, each one verified before the next.
11. [ship] Open the pull request: a Change item that `resolves` the Task, `{{onto_cmd}} prov emit --change <CHG-id>`, and a body with these headings in this order, empty ones dropped: `Why`, `What changed`, `Scope`, `Tradeoffs`, `Blast Radius`, `Verification`.

**Reply:** what you built, what you chose and why, the throughput checkpoint, open decisions. Tables for design alternatives. Name the stage `{{onto_cmd}} view` reports for the Task.
