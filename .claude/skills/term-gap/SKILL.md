---
name: term-gap
description: Use at intake and when writing a Requirement, to find the names in a request that are not in the bounded context's glossary. Each gap becomes a question to the person or an OntologyChangeRequest, never a coined name.
allowed-tools: Read, Grep, Bash(${CLAUDE_PROJECT_DIR}/bin/onto *), Bash(bin/onto *)
---

# Term gap

The glossary is the closed list of names this context may use. A request arrives in whatever words its author had. The gap between the two is found here, before any Requirement or code is written, because a name coined now is a name every later artefact inherits.

What exists today:

!`"${CLAUDE_PROJECT_DIR}"/bin/onto overview`

## Steps

1. List the candidate domain names in the request: the nouns it treats as things, the states and outcomes it distinguishes, the fields it mentions. Leave out the system's own name and ordinary prose.
2. Run `bin/onto resolve "<name>"` for each. Never judge from memory whether a name is a term. The command answers one of four ways:
   - **a term**: use its canonical name, spelled exactly as printed.
   - **another spelling** (an alias, a plural, different case): use the canonical name it points to.
   - **a denied synonym**: the glossary has retired this name. Use the term it names, and say so to the person, because their words differ from the team's.
   - **not a term**: this is a gap.
3. For each gap, decide which it is:
   - the request means an existing term by another name → ask the person to confirm, naming the term and quoting its definition;
   - the concept is new → it needs an OntologyChangeRequest. Do not raise one on your own judgement: propose it to the person with a draft definition, and on their yes run `bin/onto ocr new --context <context> --term <Term> --justification "..."`. The **ontology-change** skill takes it from there.
4. Report the result as a table: name in the request, what `onto resolve` said, what you will write instead or what you asked.

A Requirement is ready when every backticked name in its `ears_text` is in `uses_terms` and `bin/onto validate` reports no error for it.
