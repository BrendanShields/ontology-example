### Investigation

<!-- Adapted from pstack: skills/poteto-mode/playbooks/investigation.md. Step 1 is new.
     See .claude/pstack/NOTICE.md. -->

**You own the answer. Plan, route, write.**

Investigation requests are read-only. They produce a cited explanation or a recommendation, not a code change.

1. [intake] Ask the graph first. Questions about what exists, what is decided, what is verified and what a change would touch have exact answers: `bin/onto cq` lists the competency questions, `bin/onto slice --term <Term>` gives a term with its Decisions and Requirements, `bin/onto trace` gives the traceability matrix. Quote what they return.
2. [design] Trace the code the question is about with **how**. For motivation questions, also route through the **why** skill.
3. [design] Throughput checkpoint stays one line: `throughput checkpoint: n/a, read-only investigation`.
4. [design] Produce the output (Overview / Key Concepts / How It Works / Where Things Live / Gotchas), or a recommendation with a tradeoffs table if the request is a decision between alternatives.

No PR, no `architect` unless the investigation precedes a code change. If it does, hand back to the user and re-route to Bug fix or Feature.

**Reply:** the investigation output. For "are we sure?" answers, include your real judgment with reasons. Push back if the premise is wrong. Say which parts came from the graph (exact) and which from reading code (your reading).
