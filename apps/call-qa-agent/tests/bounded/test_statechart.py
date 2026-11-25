"""The committed diagram of the evaluation loop is the one the code draws today."""

from __future__ import annotations

from . import statechart


def test_statechart_matches_the_code():
    committed = statechart.COMMITTED.read_text(encoding="utf-8")
    assert committed == statechart.render(), f"regenerate it: {statechart.REGENERATE}"
