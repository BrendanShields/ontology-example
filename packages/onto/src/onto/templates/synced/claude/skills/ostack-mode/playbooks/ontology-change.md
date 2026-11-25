### Ontology change

<!-- Written for this repository. pstack has no counterpart. -->

**A person decides. You prepare.** A glossary term is a commitment every requirement, test and line of domain code will be held to, so it changes only through an OntologyChangeRequest that a person approves.

1. [intake] Find the OntologyChangeRequest under `work/`, or raise one: `{{onto_cmd}} ocr new --context <context> --term <Term> --justification "..."`. Say which Requirement needs the term.
2. [vocabulary] Check it is really new: `{{onto_cmd}} resolve <Term>`, then the same for each synonym you can think of. An alias or a denied synonym of an existing term is a finding, not a new term.
3. [design] Draft the definition in one or two sentences a person who works in the domain would agree with. State what the term is not. List the names that should be denied in its favour. Put the open questions in the request's body.
4. [design] Stop. Ask the person who owns the bounded context to decide. They move the request to `in_progress` when they approve. Do not change its status yourself.
5. [implement] With the request `in_progress`, edit `ontology/domains/<context>.yaml`. The guard asks the person to confirm each edit. Change only what the request covers.
6. [implement] `{{onto_cmd}} gen`, then fix what the new types break. Never edit a generated file.
7. [verify] `{{onto_cmd}} validate`, `{{onto_cmd}} check-terms` and the test suite pass. A renamed term leaves its old name as a denied synonym, so the old name cannot come back.
8. [trace] Record the Decision that explains the change, with `supersedes` if it replaces one. Set the request to `done`.
9. [ship] Open the pull request. The owners of `ontology/` in CODEOWNERS review it: that review is the control, the guard is only a reminder.

**Reply:** the term, its definition, what was denied in its favour, what the generated types changed, and who approved.
