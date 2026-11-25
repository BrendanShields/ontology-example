"""Acceptance tests for loading a Scorecard: REQ-0011."""

from __future__ import annotations

import itertools

import yaml
from call_qa_agent.cli import load_scorecard

NAMES = ("c0", "c1", "c2")


def test_scorecard_is_loaded_exactly_when_every_criterion_id_is_its_own(tmp_path):
    """REQ-0011, for every Scorecard of one to three Criteria named from three names."""
    path = tmp_path / "scorecard.yaml"
    for count in range(1, len(NAMES) + 1):
        for names in itertools.product(NAMES, repeat=count):
            criteria = [
                {"criterion_id": name, "statement": "A thing.", "weight": 1} for name in names
            ]
            path.write_text(
                yaml.safe_dump(
                    {"scorecard_id": "example-v1", "pass_mark": 50, "criteria": criteria}
                ),
                encoding="utf-8",
            )
            try:
                loaded = [criterion.criterion_id for criterion in load_scorecard(path).criteria]
            except ValueError:
                loaded = None
            want = list(names) if len(set(names)) == len(names) else None
            assert loaded == want, f"criterion_ids {names}"
