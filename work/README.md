# work/

The typed work items of this monorepo. Each file is markdown with YAML
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

Create one with `bin/onto new <Class> key=value ...`: it is validated before it
is written. Add `--dry-run` to see what would be written. Check them all with
`bin/onto validate`. See where each Task stands with `bin/onto view`.

`evidence/` is not in git. A test run writes it (`uv run pytest --onto-evidence`),
one `EVD-` file per Test, and the traceability gate reads it.

There is no `INC-` file here yet: nothing in this repository's history was
observed in operation.

Two kinds of record sit side by side:

- `REQ-0001` to `REQ-0009`, `TASK-0001` to `TASK-0004`, `DEC-0001` to `DEC-0008`,
  `TST-0001` to `TST-0007`, `CHG-0001`, `OCR-0001` and `OCR-0002` were written
  as example data for the call-qa-agent app. The people, dates, ticket keys
  and pull request in them are invented. `TASK-0004` and `REQ-0008` were
  finished for real afterwards, and `REQ-0009` was replaced by `REQ-0016`.
- Everything after them records work that was done in this repository.
  `DEC-0009` to `DEC-0020` were decided by Claude during that work, say so in
  `decided_by`, and are for a person to confirm. `OCR-0003` to `OCR-0005` are
  `in_progress`: a person sets each to `done`.
