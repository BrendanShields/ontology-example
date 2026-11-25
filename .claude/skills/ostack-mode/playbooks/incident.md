### Incident

<!-- Written for this repository. pstack has no counterpart. Step 4 hands over to the Bug fix
     playbook, which is adapted from pstack. See .claude/pstack/NOTICE.md. -->

**An Incident is closed by Requirements, not by saying so.** Something was observed in operation that the system should not have done. It comes back into the work as a Requirement it shows broken or a Requirement raised from it, and it is closed when those are verified.

Record what kind of thing happened, not the data it happened to. Never put a value of a term the glossary classifies as PII or confidential, or anything the project's CLAUDE.md says never to print, into the Incident, a log row or a test.

1. [intake] Record the Incident before anything else: `bin/onto new Incident title="..." bounded_context=<context> observed_on=<YYYY-MM-DD> status=in_progress`. The title says what the system did. The body says where it was seen and by whom.
2. [intake] Reproduce it yourself, on the matching surface. If it won't reproduce directly, synthesize the trigger, tighten conditions, or instrument until it fires. An Incident you cannot reproduce stays open with what you tried in its body. Do not close it.
3. [intake] Decide which of three it is, and write the link. `bin/onto slice --term <Term>` lists the Requirements established on the terms involved.
   - **A Requirement already forbids it.** The Requirement is broken: add its id to `breaks` of the Incident and set the Requirement back to `in_progress`, because its claim does not hold today. Create a Task that implements it.
   - **No Requirement covers it.** The missing Requirement is the first finding: `bin/onto new Requirement ... raised_from=<INC-id>`, and a Task that implements it.
   - **The system did what a Requirement says, and the rule is wrong.** Switch to the Rule change playbook. Its new Requirement carries both `replaces=<REQ-id>` and `raised_from=<INC-id>`.
4. [design] Copy steps 3 to 8 of the Bug fix playbook into the task list after this step and work through them with the Requirement and the Task from step 3. The failing repro from step 2 is the Test item its step 6 asks for.
5. [trace] Close the Incident only when the gate holds. Every Requirement in `breaks` and every Requirement raised from it is `done`, so `bin/onto cq CQ-08` has no row for the Incident. Then set the Incident to `done`, and `bin/onto trace --scope branch` reports no error. If a Requirement is still open, the Incident stays `in_progress`. `done` is the only status that closes an Incident: `bin/onto validate` refuses `superseded` on one, and an Incident recorded by mistake is deleted, with the reason in the commit. The gate reads the status of each Requirement and nothing else. It cannot tell a Requirement that was reopened and verified again from one that was never reopened, which is why step 3 sets a broken Requirement back to `in_progress`.
6. [ship] The pull request names the Incident in `Why`. `bin/onto view` no longer lists it under open incidents.

**Reply:** what was observed, which of the three it was and the Requirement that answers it, root cause, fix, how you verified, and the status of the Incident. Quote the decisive failing and passing output, trimmed to the assertion and the counts.
