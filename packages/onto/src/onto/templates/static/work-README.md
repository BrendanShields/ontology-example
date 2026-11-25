# work/

The typed work items of this repository. Each file is markdown with YAML
frontmatter that must validate against a class of `ontology/workflow.yaml`.
The prefix of the id says which class.

| Prefix | Class | Links to |
| --- | --- | --- |
| `REQ-` | Requirement | glossary terms (`uses_terms`), the Requirement it `replaces`, the Incident it was `raised_from` |
| `TASK-` | Task | the Requirements it `implements`, the Tasks it is `blocked_by` |
| `DEC-` | Decision | the Decision it `supersedes`, glossary terms, the path globs it `affects` |
| `TST-` | Test | the Requirements it `verifies`, the pytest node at `path` |
| `CHG-` | Change | the Tasks it `resolves` |
| `OCR-` | OntologyChangeRequest | the term it proposes |
| `INC-` | Incident | the Requirements it `breaks` |

Create one with `{{onto_cmd}} new <Class> key=value ...`: it is validated before
it is written. Check them all with `{{onto_cmd}} validate`. See where each Task
stands with `{{onto_cmd}} view`.

`evidence/` is not in git. A test run writes it (`{{onto_cmd}} evidence collect`,
or `pytest --onto-evidence`), one `EVD-` file per Test, and the traceability
gate reads it.
