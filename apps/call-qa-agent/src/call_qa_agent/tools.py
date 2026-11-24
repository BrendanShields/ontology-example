"""The two tools the model works through, compiled from the ontology.

`record_finding` takes exactly a Finding. Its input schema is the JSON Schema
that `onto gen` generates from ontology/domains/call-qa.yaml, narrowed to the
Criteria of the Scorecard in use, so the model cannot even name a Criterion
that does not exist. The parameter descriptions are the glossary's definitions.

Both tools run against an EvaluationSession, which is where the rules are
enforced. A broken rule comes back as Rejections in the tool result.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources

from .generated import Rejection, Scorecard
from .session import EvaluationSession

RECORD_FINDING = "record_finding"
FINISH_EVALUATION = "finish_evaluation"


@cache
def _generated(name: str) -> dict:
    text = resources.files("call_qa_agent").joinpath("schemas", name).read_text(encoding="utf-8")
    return json.loads(text)


def definition(term: str) -> str:
    """The glossary definition of a term, as generated from the ontology."""
    return _generated("call-qa.glossary.json")["terms"][term]["definition"]


def finding_schema(scorecard: Scorecard) -> dict:
    """The input schema of `record_finding`: a Finding for one Criterion of this Scorecard."""
    schema = _generated("call-qa.schema.json")
    finding = schema["$defs"]["Finding"]
    outcome = schema["$defs"]["FindingOutcome"]
    properties = finding["properties"]
    return {
        "type": "object",
        "properties": {
            "criterion": {
                "type": "string",
                "enum": [criterion.criterion_id for criterion in scorecard.criteria],
                "description": properties["criterion"]["description"],
            },
            "finding_outcome": {
                "type": "string",
                "enum": outcome["enum"],
                "description": properties["finding_outcome"]["description"],
            },
            "cited_utterances": {
                "type": "array",
                "items": {"type": "integer"},
                "description": properties["cited_utterances"]["description"],
            },
            "rationale": {
                "type": "string",
                "description": properties["rationale"]["description"],
            },
        },
        # Strict tool use wants every property required and nothing extra. An
        # empty list is how a NOT_APPLICABLE Finding says it cites nothing.
        "required": ["criterion", "finding_outcome", "cited_utterances", "rationale"],
        "additionalProperties": False,
    }


def tool_definitions(scorecard: Scorecard) -> list[dict]:
    """The tool list sent to the model for one Scorecard. Stable, so it can be cached."""
    return [
        {
            "name": RECORD_FINDING,
            "description": (
                f"Record one Finding. {definition('Finding')} Call this once for every Criterion "
                "of the Scorecard. If the Finding breaks a rule it is not recorded and the "
                "result lists the Rejections: correct the Finding and call again."
            ),
            "strict": True,
            "input_schema": finding_schema(scorecard),
        },
        {
            "name": FINISH_EVALUATION,
            "description": (
                "Complete the Evaluation. Call this once, after a Finding has been recorded for "
                "every Criterion. If a Criterion still has no Finding the result says which."
            ),
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    ]


def run_tool(session: EvaluationSession, name: str, tool_input: object) -> tuple[str, bool]:
    """Run one tool call against the session. Returns (result text, is_error)."""
    if name == RECORD_FINDING:
        rejections = session.record_finding(tool_input)
        recorded = f"Recorded. {len(session.findings)} of {len(session.scorecard.criteria)} done."
    elif name == FINISH_EVALUATION:
        rejections = session.finish()
        recorded = "The Evaluation is complete."
    else:
        return f"There is no tool named {name!r}.", True
    if rejections:
        return render_rejections(rejections), True
    return recorded, False


def render_rejections(rejections: list[Rejection]) -> str:
    """Rejections as JSON, in the shape the ontology gives them."""
    return json.dumps(
        {"rejections": [r.model_dump(mode="json", exclude_none=True) for r in rejections]},
        indent=2,
    )
