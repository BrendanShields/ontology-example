### Ontology change

<!-- Written for this repository. pstack has no counterpart. -->

**A person decides. You prepare.** A glossary term is a commitment every requirement, test and line of domain code will be held to, so it changes only through an OntologyChangeRequest that a person approves.

1. [intake] Find the OntologyChangeRequest under `work/`, or raise one: `bin/onto ocr new --context <context> --term <Term> --justification "..."`. Say which Requirement needs the term.
2. [vocabulary] Check it is really new: `bin/onto resolve <Term>`, then the same for each synonym you can think of. An alias or a denied synonym of an existing term is a finding, not a new term.
3. [design] Draft the definition in one or two sentences a person who works in the domain would agree with. State what the term is not. List the names that should be denied in its favour. Put the open questions in the request's body.
4. [design] Stop. Ask the person who owns the bounded context to decide. They move the request to `in_progress` when they approve. Do not change its status yourself.
5. [implement] With the request `in_progress`, edit `ontology/domains/<context>.yaml`. The guard asks the person to confirm each edit. Change only what the request covers.
6. [implement] `bin/onto gen`, then fix what the new types break. Never edit a generated file.
7. [verify] `bin/onto validate`, `bin/onto check-terms` and the test suite pass. A renamed term leaves its old name as a denied synonym, so the old name cannot come back.
8. [trace] Record the Decision that explains the change, with `supersedes` if it replaces one. Set the request to `done`.
9. [ship] Open the pull request. The owners of `ontology/` in CODEOWNERS review it: that review is the control, the guard is only a reminder.

**Reply:** the term, its definition, what was denied in its favour, what the generated types changed, and who approved.

#### Retirement

Retiring a glossary term, or an app together with its bounded context, is an ontology change. It starts at step 1 with a request that says what is retired and what, if anything, takes its place. Two things come before step 5.

- `bin/onto cq CQ-06 --bind term=<Term>` lists the Requirements, Tests and Decisions that depend on the term. Each Requirement that still states a rule on it is replaced through the Rule change playbook first, so that nothing in force rests on a retired term.
- Put to the person what happens to the record. `bin/onto validate` holds every work item to the glossary, superseded ones too: a term that a work item still lists in `uses_terms` cannot leave, and the work items of a bounded context that is gone would no longer validate. Do not delete or rewrite work items to make a gate pass.

A retired name is added to `denied_synonyms` of the term that takes its place, as for a rename.
