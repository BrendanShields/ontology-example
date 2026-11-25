"""Every case within a stated bound, through the real code: one node per requirement area.

Each node also pins how much was explored, so a bound that shrinks without
anyone deciding it fails here. The bounds are in the docstrings of `explore`.
"""

from __future__ import annotations

from . import explore


def test_scoring_holds_for_every_scorecard_within_the_bound():
    # 1 to 3 Criteria, each 3 weights x critical or not x 3 outcomes, times 101 pass marks.
    # For REQ-0010, every list of up to one Finding more than the Criteria: 7 + 40 + 341.
    assert explore.check_scoring(max_criteria=3, max_weight=3) == {
        "evaluations": 623_574,
        "finding_lists": 388,
    }


def test_session_holds_in_every_state_within_the_bound():
    assert explore.check_session(max_criteria=3) == {"states": 438, "transitions": 34_014}


def test_loop_holds_for_every_script_within_the_bound():
    # Every sequence of 0 to 4 turns over the 13 kinds of turn: 1 + 13 + 169 + 2,197 + 28,561.
    assert explore.check_loop(max_turns=4) == {"runs": 30_941}
