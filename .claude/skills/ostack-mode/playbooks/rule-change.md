### Rule change

<!-- Written for this repository. pstack has no counterpart. -->

**A rule is replaced, never edited in place.** A business rule that changes gets a new Requirement that `replaces` the old one. The old Requirement keeps its text and becomes `superseded`, so "what did this rule use to say, and since when does it say otherwise?" has an answer in the record.

Use this when a `done` Requirement would have to say something else. A Requirement that is still a draft is just edited.

1. [intake] Find the Requirement that states the rule today: `bin/onto slice --term <Term>`, and `bin/onto cq CQ-09 --bind requirement=<REQ-id>` if it may already have been replaced. Work from the last one that is `done`. Write the new rule as a new Requirement: `bin/onto new Requirement ... replaces=<REQ-id>`, with `raised_from=<INC-id>` if an Incident prompted it, and a Task that implements it. Do not touch the text of the old Requirement.
2. [vocabulary] Run **term-gap** on the new Requirement. If the change needs a new term, another meaning for a term, or a rule value withdrawn from the glossary, that is the Ontology change playbook, and it comes first.
3. [design] Find the Decision that set the old rule: `bin/onto cq CQ-03 --bind term=<Term>` for the terms, `bin/onto cq CQ-10 --bind path=<file>` for the files. Write the Decision that `supersedes` it, with the reason the rule changed, and with `affects` if it constrains particular files. The old Decision becomes `superseded` when the new one is `done`.
4. [design] Read `bin/onto slice --task <TASK-id>`. It shows the old Requirement as replaced, not as one to keep true. Every other Requirement it lists still holds and must hold after the change.
5. [implement] Delegate the change to the `implementer` subagent with a specific scope, as in the Feature playbook.
6. [verify] Restate the tests that pinned the old rule. A rule over a value space keeps its bounded or property test, with the bound and the checks rewritten for the new rule and a mutant that restores the old rule, which a check must catch. Each Test item now `verifies` the new Requirement, and none is left verifying the old one. Run `bin/onto evidence collect --scope branch`.
7. [trace] Set the new Requirement and its Task to `done`, and the old Requirement to `superseded`. The Task that delivered only the old Requirement, and the Change that resolved that Task, become `superseded` with it: as long as that Task reads `done`, the gate holds the old Requirement to a Test it no longer has. If that Task also implements a Requirement still in force, stop and tell the person, because the gates have no route for it yet.
8. [trace] `bin/onto rules` reports no error: a rule the glossary binds is produced by the code and proved by a `done` Requirement, which is now the new one. `bin/onto trace --scope branch` reports no error.
9. [trace] If a Requirement's `risk_tier` is high or critical, `interrogate` before shipping.
10. [ship] Open the pull request as in the Feature playbook's last step. `Why` names the old Requirement, the new one and the Decision.

**Reply:** the rule as it was and as it is now, with both Requirement ids, the Decision and what it supersedes, which tests were restated, and what `bin/onto rules` and `bin/onto trace` report.
