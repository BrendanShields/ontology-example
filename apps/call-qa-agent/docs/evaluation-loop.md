# The evaluation loop

<!-- Generated from runs of the real loop. Do not edit: run
     cd apps/call-qa-agent && uv run python -m tests.bounded.statechart -->

What `agent.evaluate` did over 2,380 scripted runs: every sequence of up to
3 turns over 13 kinds of turn, for a Scorecard of 2 Criteria. A state or an arrow
that needs a longer run or another kind of turn is not drawn.

Each arrow is one turn, labelled with what its tool results showed. The runs took
46 different turns. Where several lead from one state to another, the 29 with the
fewest tool results are drawn.

```mermaid
stateDiagram-v2
    state "Collecting, 0 of 2 Findings recorded" as s0
    state "Collecting, 1 of 2 Findings recorded" as s1
    state "Collecting, 2 of 2 Findings recorded" as s2
    state "Evaluation" as s3
    state "No Evaluation, out of turns" as s4
    state "No Evaluation, the model declined" as s5
    state "No Evaluation, the reply was cut off" as s6
    [*] --> s0
    s0 --> s1: Finding recorded
    s0 --> s2: Finding recorded, Finding recorded
    s0 --> s3: Finding recorded, Finding recorded, finish accepted, call after completion refused
    s0 --> s0: Finding rejected (MISSING_CITATION)
    s0 --> s0: finish refused (MISSING_FINDING)
    s0 --> s0: no tool call
    s0 --> s5: the model declines
    s0 --> s6: the reply is cut off
    s0 --> s4: the turn limit is reached
    s0 --> s0: unknown tool refused
    s1 --> s2: Finding recorded
    s1 --> s3: Finding recorded, finish accepted
    s1 --> s1: Finding rejected (DUPLICATE_FINDING)
    s1 --> s1: Finding rejected (DUPLICATE_FINDING, MISSING_CITATION)
    s1 --> s1: Finding rejected (MISSING_CITATION)
    s1 --> s1: finish refused (MISSING_FINDING)
    s1 --> s1: no tool call
    s1 --> s5: the model declines
    s1 --> s6: the reply is cut off
    s1 --> s4: the turn limit is reached
    s1 --> s1: unknown tool refused
    s2 --> s2: Finding rejected (DUPLICATE_FINDING)
    s2 --> s2: Finding rejected (DUPLICATE_FINDING, MISSING_CITATION)
    s2 --> s3: finish accepted
    s2 --> s3: no tool call
    s2 --> s5: the model declines
    s2 --> s6: the reply is cut off
    s2 --> s4: the turn limit is reached
    s2 --> s2: unknown tool refused
    s3 --> [*]
    s4 --> [*]
    s5 --> [*]
    s6 --> [*]
```
