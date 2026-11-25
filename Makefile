# Everything here is a thin wrapper. The commands are the documentation.
ONTO := bin/onto

.PHONY: setup gen check verify test view lint mods vendored hooks

setup:            ## install the workspace into .venv
	uv sync

gen:              ## compile the ontologies into JSON Schema, SHACL and Pydantic
	$(ONTO) gen

check:            ## every gate CI runs, in the order CI runs them
	$(ONTO) gen --check
	$(ONTO) validate
	$(ONTO) check-terms
	$(ONTO) guard --check-settings
	uv run ruff check .
	uv run lint-imports
	uv run pytest --onto-evidence
	$(ONTO) trace
	$(ONTO) rules
	uv run python tools/check_vendored.py

verify:           ## the ontology gates again, leaving one index of what they showed
	$(ONTO) verify

test:             ## the tests alone
	uv run pytest

view:             ## where every task stands
	$(ONTO) view

lint:
	uv run ruff check .

mods:             ## validate and test the Claude mods (needs the claude CLI)
	claude plugin validate .
	for mod in mods/*/; do claude plugin test $$mod || exit 1; done

vendored:         ## the vendored pstack files still match their pinned commit
	uv run python tools/check_vendored.py

hooks:            ## drive every hook with a documented event: decision, exit code, latency
	uv run python tools/drive_hooks.py
