# work/

The typed work items of this monorepo. Each file is markdown with YAML
frontmatter that must validate against a class of `ontology/workflow.yaml`.
The prefix of the id says which class.

| Prefix | Class | Links to |
| --- | --- | --- |
| `REQ-` | Requirement | glossary terms (`uses_terms`) |
| `TASK-` | Task | the Requirements it `implements`, the Tasks it is `blocked_by` |
| `DEC-` | Decision | the Decision it `supersedes`, glossary terms |
| `TST-` | Test | the Requirements it `verifies`, the pytest node at `path` |
| `CHG-` | Change | the Tasks it `resolves` |
| `OCR-` | OntologyChangeRequest | the term it proposes |

Create one with `bin/onto new <Class> key=value ...`: it is validated before it
is written. Check them all with `bin/onto validate`. See where each Task stands
with `bin/onto view`.

`evidence/` is not in git. A test run writes it (`uv run pytest --onto-evidence`),
one `EVD-` file per Test, and the traceability gate reads it.

Everything here is example data for the call-qa-agent app: the people and dates
in the Decisions are invented.
