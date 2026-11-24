---
name: principle-prove-it-works
description: "Apply after completing a task, before declaring done. Verify against the real artifact (run the feature, read the actual value, inspect the diff), not a proxy, self-report, or 'it compiles.'"
user-invocable: false
---

# Prove It Works

<!-- Adapted from pstack: skills/principle-prove-it-works/SKILL.md. The last section is new.
     See .claude/pstack/NOTICE.md. -->

Verify every output by checking the real thing directly: run the feature, read the actual value, inspect the diff. Proxies (file mtimes, self-reports, cached output, "it compiles") do not count. When a check fails, suspect the observation method before the system.

Before you report success (merged, sent, started), read the real state and the exit code. Truncated output (`| tail -1`) and your own echo prove nothing.

Verify the process as well as the outcome. A correct result can rest on a broken process: a clause reconstructed from the user's paste instead of the durable record, a constraint honored by chance from a file never read. For each fact you relied on, name the record it came from and confirm that record is the one the project's rules point at.

Red is a colour, not a measurement. A failing check proves the instrument only when the failure content is the disagreement you predicted. Quote the assertion's diff (`Extra items in the right set`), never the assertion (`assert {...} == {...}`).

Script the check when you can. A deterministic script that reruns the comparison beats a one-time look. Keep its output where the human can see it, and commit it only when the trail must be auditable later.

## In this repository

"Done" is typed. A Requirement or Task with status `done` is a claim, and `bin/onto trace` checks it against Evidence that only a test run can write (`bin/onto evidence collect`). You cannot write Evidence by hand and you should not want to: if the gate does not hold, the work is `in_progress`, and saying so is the correct report.

A passing gate proves the tests that exist passed. It does not prove the tests are the right ones. Read the Test item's `path` and ask whether that test would fail without your change.
