"""Two Mermaid state diagrams, drawn from runs of the real code.

Nothing in either is written by hand. In docs/evaluation-loop.md the states
and arrows are what `explore.check_loop` saw `agent.evaluate` do, and every
arrow label is read from the tool results and the outcome of a run, not from
the script that drove it. In docs/publication.md they are what
`explore.check_ledger` saw the `Ledger` do: each state is read back from the
ledger file, and each answer is the one the command got.

    cd apps/call-qa-agent && uv run python -m tests.bounded.statechart          # rewrite both
    cd apps/call-qa-agent && uv run python -m tests.bounded.statechart --check  # exit 1 on drift
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from call_qa_agent import ledger as ledger_module
from call_qa_agent.generated import PublicationState, ReviewOutcome
from call_qa_agent.tools import FINISH_EVALUATION, RECORD_FINDING

from . import explore

DOCS = Path(__file__).resolve().parents[2] / "docs"
COMMITTED = DOCS / "evaluation-loop.md"
PUBLICATION = DOCS / "publication.md"
MAX_TURNS = 3
MAX_COMMANDS = 4
REGENERATE = "cd apps/call-qa-agent && uv run python -m tests.bounded.statechart"

ENDS = {
    explore.EVALUATED: "Evaluation",
    explore.DECLINED: "No Evaluation, the model declined",
    explore.CUT_OFF: "No Evaluation, the reply was cut off",
    explore.OUT_OF_TURNS: "No Evaluation, out of turns",
}


def _collecting(recorded: int) -> str:
    return f"Collecting, {recorded} of {len(explore.LOOP_CRITERIA)} Findings recorded"


def _rules(result: str) -> str | None:
    """The rules named by the Rejections in a tool result, or None if it carries none."""
    try:
        rejections = json.loads(result)["rejections"]
    except (ValueError, KeyError, TypeError):
        return None
    return ", ".join(sorted({rejection["rejection_rule"] for rejection in rejections}))


def _observed(step) -> tuple[str, bool]:
    """What one tool result showed, and whether it recorded a Finding."""
    known = step.tool in (RECORD_FINDING, FINISH_EVALUATION)
    rules = _rules(step.result) if known else None
    if not known:
        return "unknown tool refused", False
    if step.rejected and rules is None:
        return "call after completion refused", False
    if step.tool == RECORD_FINDING:
        return (
            (f"Finding rejected ({rules})", False) if step.rejected else ("Finding recorded", True)
        )
    return (f"finish refused ({rules})" if step.rejected else "finish accepted"), False


class Chart:
    def __init__(self) -> None:
        self.edges: set[tuple[str, tuple[str, ...], str]] = set()

    def observe(self, run: explore.Run) -> None:
        """Fold one run of the real loop into the diagram."""
        steps = iter(run.steps)
        state, recorded = _collecting(0), 0
        turns = len(run.requests)
        for turn in range(turns):
            seen = []
            for _ in explore.TURNS[run.script[turn]][1]:
                label, was_recorded = _observed(next(steps))
                seen.append(label)
                recorded += was_recorded
            last = turn == turns - 1
            target = _collecting(recorded)
            if last and run.result != explore.OUT_OF_TURNS:
                target = ENDS[run.result]
            if not seen:
                seen = [
                    "the model declines"
                    if target == ENDS[explore.DECLINED]
                    else "the reply is cut off"
                    if target == ENDS[explore.CUT_OFF]
                    else "no tool call"
                ]
            self.edges.add((state, tuple(seen), target))
            state = target
        if run.result == explore.OUT_OF_TURNS:
            self.edges.add((state, ("the turn limit is reached",), ENDS[run.result]))

    def drawn(self) -> list[tuple[str, tuple[str, ...], str]]:
        """Between two states, only the turns with the fewest tool results: the rest repeat them."""
        fewest: dict[tuple[str, str], int] = {}
        for source, label, target in self.edges:
            fewest[source, target] = min(len(label), fewest.get((source, target), len(label)))
        return sorted(edge for edge in self.edges if len(edge[1]) == fewest[edge[0], edge[2]])

    def mermaid(self) -> str:
        states = sorted({state for source, _, target in self.edges for state in (source, target)})
        names = {state: f"s{index}" for index, state in enumerate(states)}
        lines = ["stateDiagram-v2"]
        lines += [f'    state "{state}" as {name}' for state, name in names.items()]
        lines.append(f"    [*] --> {names[_collecting(0)]}")
        for source, label, target in self.drawn():
            lines.append(f"    {names[source]} --> {names[target]}: {', '.join(label)}")
        lines += [f"    {names[end]} --> [*]" for end in sorted(ENDS.values()) if end in names]
        return "\n".join(lines) + "\n"


def render() -> str:
    chart = Chart()
    counted = explore.check_loop(MAX_TURNS, observe=chart.observe)
    return (
        "# The evaluation loop\n\n"
        "<!-- Generated from runs of the real loop. Do not edit: run\n"
        f"     {REGENERATE} -->\n\n"
        f"What `agent.evaluate` did over {counted['runs']:,} scripted runs: every sequence of up to\n"
        f"{MAX_TURNS} turns over {len(explore.TURNS)} kinds of turn, for a Scorecard of "
        f"{len(explore.LOOP_CRITERIA)} Criteria. A state or an arrow\n"
        "that needs a longer run or another kind of turn is not drawn.\n\n"
        "Each arrow is one turn, labelled with what its tool results showed. The runs took\n"
        f"{len(chart.edges)} different turns. Where several lead from one state to another, the "
        f"{len(chart.drawn())} with the\nfewest tool results are drawn.\n\n"
        "```mermaid\n" + chart.mermaid() + "```\n"
    )


NOT_STAGED = "Not staged"
STAGE_AGAIN = "stage the same Evaluation"
STAGE_ANOTHER = "stage another Evaluation"
ASKED = (
    STAGE_AGAIN,
    STAGE_ANOTHER,
    *(f"Review {outcome.value}" for outcome in ReviewOutcome),
    "publish",
)


def _standing(entry: ledger_module.Entry | None) -> str:
    """Where an Evaluation stands, as the ledger file says."""
    if entry is None:
        return NOT_STAGED
    if entry.publication_state is not PublicationState.STAGED:
        return entry.publication_state.value
    confirmed = any(made.review_outcome == ReviewOutcome.CONFIRMED.value for made in entry.reviews)
    return f"STAGED, {entry.disposition.value}" + (", CONFIRMED" if confirmed else "")


class Publication:
    def __init__(self) -> None:
        self.answers: dict[tuple[str, str], set[str]] = {}
        self.changes: set[tuple[str, str, str]] = set()

    def observe(self, before, command: tuple, got: explore.Answer) -> None:
        """Fold one command given to the real Ledger into the diagram and the table."""
        source, target = _standing(before), _standing(got.entry)
        if command[0] == explore.STAGE:
            same = before and before.sha256 == ledger_module.digest(explore.EVALUATIONS[command[1]])
            asked = STAGE_AGAIN if same else STAGE_ANOTHER
        elif command[0] == explore.REVIEW:
            asked = f"Review {command[2].value}"
        else:
            asked = "publish"
        answer = got.answer + (f" ({', '.join(got.rules)})" if got.rules else "")
        self.answers.setdefault((source, asked), set()).add(answer)
        if target != source:
            self.changes.add((source, "stage" if command[0] == explore.STAGE else asked, target))

    def mermaid(self) -> str:
        states = sorted({state for source, _, target in self.changes for state in (source, target)})
        names = {state: f"s{index}" for index, state in enumerate(states)}
        ends = sorted(set(states) - {source for source, _, _ in self.changes})
        lines = ["stateDiagram-v2"]
        lines += [f'    state "{state}" as {name}' for state, name in names.items()]
        lines.append(f"    [*] --> {names[NOT_STAGED]}")
        lines += [f"    {names[s]} --> {names[t]}: {asked}" for s, asked, t in sorted(self.changes)]
        lines += [f"    {names[end]} --> [*]" for end in ends]
        return "\n".join(lines) + "\n"

    def table(self) -> str:
        states = sorted({source for source, _ in self.answers})
        rows = [
            "| Where it stands | " + " | ".join(ASKED) + " |",
            "| --- " * (len(ASKED) + 1) + "|",
        ]
        for state in states:
            cells = [", ".join(sorted(self.answers.get((state, asked), ()))) for asked in ASKED]
            rows.append(f"| {state} | " + " | ".join(cell or "-" for cell in cells) + " |")
        return "\n".join(rows) + "\n"


def render_publication() -> str:
    chart = Publication()
    counted = explore.check_ledger(MAX_COMMANDS, observe=chart.observe)
    return (
        "# The publication of an Evaluation\n\n"
        "<!-- Generated from runs of the real ledger. Do not edit: run\n"
        f"     {REGENERATE} -->\n\n"
        f"What the `Ledger` did over {counted['commands']:,} commands: every sequence of up to\n"
        f"{MAX_COMMANDS} commands over {len(explore.COMMANDS)} commands, for "
        f"{len(explore.EVALUATIONS)} Evaluations of one Call against one Scorecard\n"
        f"and {len(explore.REVIEWERS)} reviewers. A state or an answer that needs a longer "
        "sequence is not shown.\n\n"
        "Each state is what the ledger file said after a command. An arrow is a command that\n"
        "changed it. A CONFIRMED Review changes no PublicationState: it is drawn because it\n"
        "changes what `publish` answers.\n\n"
        "```mermaid\n" + chart.mermaid() + "```\n\n"
        "Every answer each command got in each state. `recorded` added a line to the ledger,\n"
        "`done already` and `refused` added nothing. A refusal names a rule only where the\n"
        "glossary has one.\n\n" + chart.table()
    )


def main(argv: list[str]) -> int:
    drifted = False
    for committed, text in ((COMMITTED, render()), (PUBLICATION, render_publication())):
        if "--check" in argv:
            if not committed.is_file() or committed.read_text(encoding="utf-8") != text:
                print(
                    f"docs/{committed.name} no longer matches the code. Regenerate it: {REGENERATE}"
                )
                drifted = True
            continue
        committed.parent.mkdir(parents=True, exist_ok=True)
        committed.write_text(text, encoding="utf-8")
        print(f"wrote {committed}")
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
