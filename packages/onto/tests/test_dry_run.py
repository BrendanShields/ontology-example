"""`onto new --dry-run` and `onto ocr new --dry-run`: the answer without the write."""

from __future__ import annotations

import pytest
from onto import frontmatter
from onto.cli import main
from onto.testing import scratch_repo

REQUIREMENT = [
    "new",
    "Requirement",
    "title=Scores are whole numbers",
    "bounded_context=call-qa",
    "ears_text=The system shall store each `score` as a whole number.",
    "uses_terms=score",
]
REQUEST = ["ocr", "new", "--context", "call-qa", "--term", "Calibration", "--justification", "x"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    scratch.item("REQ-0001")
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    return scratch


def files(repo) -> set[str]:
    return {p.relative_to(repo.root).as_posix() for p in repo.root.rglob("*")}


@pytest.mark.parametrize(("argv", "identifier"), [(REQUIREMENT, "REQ-0002"), (REQUEST, "OCR-0001")])
def test_a_dry_run_prints_the_item_and_writes_nothing(repo, capsys, argv, identifier):
    before = files(repo)
    assert main([*argv, "--dry-run"]) == 0
    out, err = capsys.readouterr()
    assert files(repo) == before
    assert f"work/{identifier}.md would be" in err and "nothing was written" in err
    meta, _ = frontmatter.split(out)
    assert meta["id"] == identifier and meta["status"] == "draft"

    # The same arguments without the flag write exactly what the dry run showed.
    assert main(argv) == 0
    assert (repo.root / f"work/{identifier}.md").read_text(encoding="utf-8") == out


def test_a_dry_run_of_an_item_that_would_be_refused_says_why(repo, capsys):
    before = files(repo)
    task = ["new", "Task", "title=Do it", "bounded_context=call-qa", "implements=REQ-0777"]
    assert main(task) == 1
    refused = capsys.readouterr().err
    assert main([*task, "--dry-run"]) == 1
    out, err = capsys.readouterr()
    assert out == "" and "would be refused" in err
    assert "dangling-reference" in err and "dangling-reference" in refused
    assert files(repo) == before
