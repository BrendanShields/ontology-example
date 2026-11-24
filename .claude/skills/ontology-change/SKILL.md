---
name: ontology-change
description: Use to add, rename, redefine or retire a glossary term, or when a gate says to raise an OntologyChangeRequest. The only route by which ontology/ changes, and a person approves it.
allowed-tools: Read, Grep, Bash(${CLAUDE_PROJECT_DIR}/bin/onto *), Bash(bin/onto *)
---

# Ontology change

The glossaries and the requests open now:

!`"${CLAUDE_PROJECT_DIR}"/bin/onto overview`

Follow the **Ontology change** playbook of **ostack-mode**: open `.claude/skills/ostack-mode/playbooks/ontology-change.md`, copy its steps into the task list word for word, and work through them. A step you do not do stays listed with `skip: <reason>`.

Three things are not negotiable:

- You propose and a person decides. Step 4 of the playbook is a stop. The request's status is theirs to change.
- The guard will ask the person to confirm each edit under `ontology/`. If it denies the edit instead, no request is in progress: go back to step 1. Do not reach the file another way.
- A renamed or retired name is added to `denied_synonyms` of the term that replaces it, so the old name cannot return through new code.
