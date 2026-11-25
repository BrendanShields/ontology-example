---
name: encode-correction
description: Use when a person corrects you, when a review or a gate finds a mistake you made, or when the same mistake turns up a second time. Turns the correction into a check at the highest rung that can hold it (the ontology, then a gate or contract, then a test, and prose last) and proves the check fails on the original mistake.
---

# Encode a correction

A correction that stays in the conversation is lost when the session ends. Written into CLAUDE.md it is read, and followed some of the time. Written as a check it is followed every time, by every agent and every person, without anyone remembering it. So a correction is not finished when the mistake is fixed. It is finished when the mistake can no longer be made quietly.

## Steps

1. **Say the mistake as a rule a check could decide.** One sentence: what was written, where, and what should have been written instead. "Used `rubric` in the domain layer; the term is `Scorecard`." If you cannot state it that way, ask the person what they would want flagged next time.
2. **Keep the mistake.** Note the commit, or save the wrong lines to a scratch file outside the repository. Step 4 needs them.
3. **Pick the rung.** Start at the top of the ladder below and stop at the first rung that can hold the rule.
4. **Watch the new check fail on the original mistake.** Put the mistake back (in a scratch copy, a temporary file, or by reverting the fix for one run) and run the check. It must fail, and its message must say what to do instead. Then run it on the corrected code and see it pass. A check you have never seen fail is not yet a check.
5. **Record it.** `{{onto_cmd}} log --phase verify --decision "<the rule, and the rung it lives on>" --why "<the correction>" --evidence "<the failing run>" --result "<the passing run>"`.

## The ladder

| Rung | Holds a rule about | How it is encoded here |
| --- | --- | --- |
| 1. The ontology and its generated types | a name, a closed set of values, a field that must be present, a number's range | A denied synonym, an enum value, a required slot or a bound in `ontology/`, through the **ontology-change** skill and a request a person approves. After `{{onto_cmd}} gen` the generated type or `{{onto_cmd}} check-terms` refuses the mistake. |
| 2. A graph gate, an import contract, a lint | how artefacts or modules relate: a claim without evidence, a layer reaching upward, a call that is never allowed | A SHACL shape in `ontology/shapes/gates.shacl.ttl` (also through a request), a contract under `[tool.importlinter]` in `pyproject.toml`, or a rule under `[tool.ruff.lint]`. |
| 3. A test | what the code does | A pytest node, registered as a Test item that `verifies` the Requirement, so Evidence follows it. A rule over a value space (a score, a threshold, a count, anything with a range of inputs) gets a bounded or property test with Hypothesis, not three hand-picked examples. A scenario gets an example test. |
| 4. One line in CLAUDE.md | what only judgement can decide | One imperative sentence, in the section where the reader will meet it. Use this rung last. |

Why this order: a higher rung fails earlier and cannot be skipped. A type refuses the value before any test runs. A gate fails the build whatever the tests cover. A test fails only where someone thought to look. Prose fails nowhere.

## Choosing honestly

- Take the rung above if it can hold the rule at all, even when the rung below is quicker to write.
- A rule that needs more than one line of CLAUDE.md usually belongs on a higher rung. Go back to step 3.
- A blocking check must be exact. If deciding the rule takes judgement, it is a warning or a review question, not a gate.
- Per-edit hooks stay under about half a second. A slower check goes into the gates CI runs and the Stop gate.
- When the gate itself was wrong, that is a correction too. Fix the gate through this same ladder. Never loosen one to get past it.
- `ontology/` changes only through a request. A correction does not shorten that route.

## Reply

The rule in one sentence, the rung you chose and why the rung above could not hold it, the failing run on the original mistake, and the passing run on the fix.
