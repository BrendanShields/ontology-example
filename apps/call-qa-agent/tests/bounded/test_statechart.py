"""The committed diagrams are the ones the code draws today."""

from __future__ import annotations

from . import statechart


def test_statechart_matches_the_code():
    committed = statechart.COMMITTED.read_text(encoding="utf-8")
    assert committed == statechart.render(), f"regenerate it: {statechart.REGENERATE}"


def test_publication_statechart_matches_the_code():
    committed = statechart.PUBLICATION.read_text(encoding="utf-8")
    assert committed == statechart.render_publication(), f"regenerate it: {statechart.REGENERATE}"


def test_the_check_reports_a_committed_diagram_that_no_longer_matches(
    tmp_path, monkeypatch, capsys
):
    # Every answer in the publication diagram is also held by a property, so no planted
    # fault reaches this check first. What it adds is shown on a copy that was edited.
    committed = statechart.PUBLICATION.read_text(encoding="utf-8")
    assert "| refused (REVIEW_REQUIRED) |" in committed
    edited = tmp_path / statechart.PUBLICATION.name
    edited.write_text(committed.replace("| refused (REVIEW_REQUIRED) |", "| recorded |"), "utf-8")
    monkeypatch.setattr(statechart, "PUBLICATION", edited)

    assert statechart.main(["--check"]) == 1
    said = capsys.readouterr().out
    assert "docs/publication.md no longer matches the code" in said
    assert "evaluation-loop.md" not in said
