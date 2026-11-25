# Ontology gates. Written by `onto init`, yours to edit.
# ONTO is the one command every target here runs.
ONTO ?= {{onto_cmd}}

.PHONY: onto-gen onto-check onto-view

onto-gen:         ## compile the ontologies into JSON Schema, SHACL and Pydantic
	$(ONTO) gen

onto-check:       ## every ontology gate CI runs, in the order CI runs them
	$(ONTO) gen --check
	$(ONTO) validate
	$(ONTO) check-terms
	$(ONTO) trace --collect
	$(ONTO) rules

onto-view:        ## where every task stands
	$(ONTO) view
