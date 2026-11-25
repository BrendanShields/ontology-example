---
name: bounded-verification
description: Use when a guarded write path, a state machine in one process, or a pure rule function (scoring, pricing, eligibility) must hold for every input, not only the examples someone thought of. Runs the real code over every case within a stated bound, with mutants that each check must catch, wired to the Requirements as a Test item. Not for concurrency or liveness: use a model checker there.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# Bounded verification

Run the real code on every case within a bound you state, and check each result against the Requirements. No model of the code is written, so nothing can drift from it. What you get is "every case within the bound". It is never a proof, and you never call it one.

The worked example is the `tests/bounded/` folder of the example app in the repository this framework comes from: `explore.py` (three explorers), `mutants.py`, `statechart.py`, and one Test item per explorer.

## When it fits, and when it does not

- **Fits**: a pure function over a small closed vocabulary, or one object whose state changes one call at a time. The whole behaviour within a small bound can be listed in seconds.
- **Use a model checker (TLA+ with TLC) instead** when the question is about order between actors: concurrency, interleavings, retries, crash and resume, or liveness ("it always finishes eventually"). Listing inputs to single-threaded code cannot show an interleaving. A model has its own cost: it is a second description of the system, so plan a conformance check between model and code.
- **Use neither** for a rule that reads one snapshot, such as a SHACL gate. Example-based tests per rule are enough.

## Steps

1. Name the target and its Requirements. Read each `ears_text` with `bin/onto slice --task <TASK-id>`. If the behaviour you want to check has no Requirement, write the Requirement first.
2. State the bound in plain words before writing code: how many of each thing, which values, how many steps. Choose the smallest bound in which every rule can be both kept and broken. Write down what falls outside it.
3. Write an explorer in the app's `tests/bounded/` that calls the real functions on every case, smallest first.
   - Pure function: nested `itertools.product` over the bound.
   - Stateful object: breadth-first search from the start state. Copy the object, apply every possible call, keep each state not seen before.
   - Loop around a model: script the model's replies from a small alphabet of turns, and run every sequence up to a length.
4. Take every enum value from the generated types (`for value in SomeEnum`), never from a literal. An ontology change must break the explorer loudly.
5. Write the oracle from the Requirement sentences and the glossary, with the source file closed. Give each property a short id and one sentence. Do not copy the code's formula: state it another way, for example rounding down as an inequality. An oracle copied from the code only shows that the code equals itself.
6. Make a violation name the property id and the first case that breaks it, using ids, outcomes and numbers only. Never put personal information or free text from the domain in a failure message.
7. Add one pytest node per requirement area. Assert the number of cases explored as a literal, so that a bound which shrinks by accident fails the test.
8. Ship mutants. For each property, plant at least one fault: an exact piece of source text, its replacement, and the property that must report it.
   - Apply each to a temporary copy of the package, put the copy first on `PYTHONPATH`, and run the explorer in a fresh interpreter.
   - Assert the text occurs exactly once. A mutant that stops applying means the guarded line changed, and a person must look again.
   - Assert the property named is the one reported, and that an untouched copy reports nothing.
   - A property no mutant can reach before another reports it is not a check. Remove it or fold it into the one that fires.
   - Mark these nodes (`@pytest.mark.mutants`) so a fast run can pass `-m 'not mutants'`. `make check` and CI run them.
9. Wire it to the Requirements. For each node run `bin/onto new Test title=... status=done bounded_context=<context> verifies=<REQ ids> path=<pytest node id>`, then write the bound in the body of the item in plain words. Run `uv run pytest --onto-evidence` and `bin/onto trace`: each Requirement must show the new Test as `pass`.
10. If the object has states worth drawing, generate the diagram from the runs and commit it, with a test that fails when the committed file and the code disagree. Label arrows from what the runs returned, not from the script that drove them.

## When the explorer finds something

A violation on untouched code is a bug or a wrong oracle. Decide which by reading the Requirement, not the code. A bug goes through the bug-fix playbook of **ostack-mode**: Requirement, failing test, fix. Behaviour that is wrong but that no Requirement covers is a missing Requirement: write it, do not quietly assert it.

## What to say about the result

Say this, in the Test item and in any report:

- the bound, in numbers a reader can check ("every Scorecard of up to 3 Criteria with weights 1 to 3");
- the count explored and the properties checked;
- what is outside the bound, including any part of the real path the explorer replaced with a stand-in;
- that the oracle is one person's reading of the Requirements.

Never write "proved", "verified for all inputs" or "formally verified". Write "holds for every case within the bound".
