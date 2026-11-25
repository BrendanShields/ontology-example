---
name: why
description: "Use for 'why does X work this way', 'why we picked Y', design rationale, regressions, postmortems, or data-backed thresholds. Returns a cited read on decisions and tradeoffs. Use how for runtime behavior."
---

# Why

<!-- Adapted from pstack: skills/why/SKILL.md. The first paragraph is new: this repository keeps
     its decisions as typed records, so the record is read before the history.
     See .claude/pstack/NOTICE.md. -->

Start with the decisions this repository has recorded. `{{onto_cmd}} slice --term <Term>` lists the Decisions in force about a term, with superseded ones left out. `{{onto_cmd}} cq CQ-04 --bind decision=<DEC-id>` walks back through everything a Decision replaced. Each Decision under `work/` carries its rationale, who decided and when. Quote them by id.

Then answer from the record, not the code: read the commits and PR discussions that introduced the target and each later change, and other sources if the trail is thin. Cite what the authors wrote, mark your own inferences as inferences, and say what the record does not answer.

If the question has no recorded Decision and deserves one, say so. That gap is a finding.
