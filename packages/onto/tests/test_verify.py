"""`onto verify`: one index of what every gate showed, written whether or not they hold."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time

import pytest
from onto import cli
from onto.cli import main
from onto.testing import scratch_repo

INDEX = "prov/verify.json"
GATES = [
    "gen --check",
    "validate",
    "check-terms",
    "evidence collect",
    "trace",
    "rules",
    "prov emit",
]
# Stands for the text of an Utterance or the rationale of a Finding. Shaped like
# an identifier so that it can also be planted in code.
SENTINEL = "zqx_planted_words_7731"
DOMAIN = "apps/call-qa-agent/src/call_qa_agent/domain/example.py"
# A bounded context that binds one rule, which no code enforces.
SHOP = """\
id: https://shop.example/ontology/shop
name: shop
prefixes:
  linkml: https://w3id.org/linkml/
  shop: https://shop.example/ontology/shop/
default_prefix: shop
default_range: string
imports:
  - linkml:types
enums:
  RefusalRule:
    description: The rules an Order can break.
    annotations:
      binding: rule
    permissible_values:
      OVER_LIMIT:
        description: The Order is worth more than the shop takes at once.
"""


@pytest.fixture(scope="module")
def unbound(tmp_path_factory):
    """These tests are about `onto verify`, so they start from a glossary `onto rules` has
    nothing to hold against. The two that are about the rules gate bring a bound rule of
    their own.
    """
    pytest.importorskip("linkml")
    return scratch_repo(tmp_path_factory.mktemp("unbound"), bind_rules=False).root


@pytest.fixture
def repo(unbound, tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path, unbound)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    monkeypatch.delenv("ONTO_TASK", raising=False)
    return scratch


def verified(repo) -> None:
    repo.item("REQ-0001", status="done")
    repo.item("TASK-0001", status="done")
    repo.item("TST-0001")


def verify(repo, *options: str) -> tuple[int, dict]:
    code = main(["verify", *options])
    return code, json.loads((repo.root / INDEX).read_text())


def gate(index: dict, name: str) -> dict:
    (found,) = (g for g in index["gates"] if g["name"] == name)
    return found


def with_rules(monkeypatch, handler) -> None:
    """Put a handler in place of `onto rules`, to make that gate say or do anything."""
    monkeypatch.setattr(cli, "_rules", handler)


def test_verify_writes_one_index_of_what_the_gates_showed(repo, capsys):
    verified(repo)
    repo.item("CHG-0001")

    code, index = verify(repo)
    out = capsys.readouterr().out

    assert code == 0 and index["ok"] is True
    assert "every gate holds" in out and INDEX in out
    assert [g["name"] for g in index["gates"]] == GATES
    assert {g["name"]: g["status"] for g in index["gates"]} == dict.fromkeys(GATES, "passed")
    assert gate(index, "trace")["counts"] == {
        "requirements": 1,
        "with_test": 1,
        "verified": 1,
        "errors": 0,
        "warnings": 0,
    }
    assert index["trace"]["requirements"] == [
        {
            "id": "REQ-0001",
            "status": "done",
            "risk_tier": None,
            "tasks": ["TASK-0001"],
            "tests": {"TST-0001": "pass"},
            "verdict": "verified",
        }
    ]
    assert index["evidence"] == [{"id": "EVD-0001", "of_test": "TST-0001", "result": "pass"}]
    assert index["varies_per_run"]["evidence"]["EVD-0001"]["recorded_at"].endswith("Z")
    assert index["provenance_bundles"] == ["prov/CHG-0001.ttl"]
    assert (repo.root / "prov/CHG-0001.ttl").is_file()


def test_the_index_pins_each_ontology_source_and_generated_file_by_hash(repo):
    _, index = verify(repo)

    def digest(rel: str) -> str:
        return hashlib.sha256((repo.root / rel).read_bytes()).hexdigest()

    cfg = repo.ws().cfg
    assert {s["path"] for s in index["ontology_sources"]} == {
        "ontology/workflow.yaml",
        "ontology/shapes/gates.shacl.ttl",
        "ontology/domains/call-qa.yaml",
    }
    # A bindings manifest is declared, and written only once the glossary binds something.
    assert {g["path"]: g["source"] for g in index["generated_files"]} == {
        path: source
        for path, source in cfg.generated_files().items()
        if (repo.root / path).is_file()
    }
    assert "ontology/schemas/workflow.schema.json" in {g["path"] for g in index["generated_files"]}
    for entry in (*index["ontology_sources"], *index["generated_files"]):
        assert entry["sha256"] == digest(entry["path"])
    assert {g["status"] for g in index["generated_files"]} == {"unchanged"}


def test_a_failing_gate_fails_verify_and_the_index_is_still_written(repo, capsys):
    verified(repo)
    edited = "ontology/schemas/workflow.schema.json"
    (repo.root / edited).write_text((repo.root / edited).read_text() + "\n")

    code, index = verify(repo)

    assert code == 1 and index["ok"] is False
    assert "failed   onto gen --check" in capsys.readouterr().out
    assert gate(index, "gen --check") == {
        "name": "gen --check",
        "command": "onto gen --check",
        "exit_status": 1,
        "status": "failed",
        "counts": {"files": len(index["generated_files"]), "drift": 1},
    }
    assert [g["path"] for g in index["generated_files"] if g["status"] == "drift"] == [edited]
    # The gates after the failed one ran all the same.
    assert gate(index, "trace")["status"] == "passed" and index["evidence"]


def test_an_unverified_claim_is_in_the_index_as_a_rule_and_an_id(repo):
    verified(repo)
    repo.write("tests/test_example.py", "def test_example():\n    assert 1 + 1 == 3\n")

    code, index = verify(repo)

    assert code == 1
    assert gate(index, "evidence collect")["counts"] == {"evidence": 1, "pass": 0, "fail": 1}
    assert gate(index, "trace")["status"] == "failed"
    assert gate(index, "trace")["counts"]["by_rule"] == {"gate:CompleteRequirementIsVerified": 1}
    assert index["trace"]["violations"] == [
        {
            "rule": "gate:CompleteRequirementIsVerified",
            "severity": "error",
            "subject": "REQ-0001",
            "file": "work/REQ-0001.md",
        }
    ]


def test_a_rerun_differs_only_in_the_one_field_that_says_so(repo):
    verified(repo)
    repo.item("CHG-0001")

    _, first = verify(repo)
    time.sleep(1.1)  # evidence is stamped to the second: make sure the two runs do differ
    _, second = verify(repo)

    assert first.pop("varies_per_run")["evidence"] != second.pop("varies_per_run")["evidence"]
    assert first == second


def test_the_index_never_carries_text_only_ids_counts_and_rule_names(
    repo, monkeypatch, capsys, tmp_path
):
    # Everywhere a careless index would pick the words up from: a call on disk,
    # the output of a failing test, work items, domain code, another gate's report.
    repo.write("apps/call-qa-agent/data/calls/call.yaml", f"utterances:\n- text: {SENTINEL}\n")
    repo.write(
        "tests/test_example.py",
        "from pathlib import Path\n\n"
        "def test_example():\n"
        "    call = Path('apps/call-qa-agent/data/calls/call.yaml').read_text()\n"
        "    print(call)\n"
        "    assert False, call\n",
    )
    repo.item("REQ-0001", status="done", title=f"Record {SENTINEL}", body=SENTINEL)
    repo.item("REQ-0002", status=SENTINEL, risk_tier=SENTINEL)
    repo.item("TST-0001", title=SENTINEL)
    repo.item(
        "EVD-0009", of_test=SENTINEL, result=SENTINEL, recorded_at=SENTINEL, commit_sha=SENTINEL
    )
    repo.item("DEC-0001", rationale=f"Because {SENTINEL}.", status=SENTINEL)
    repo.write(DOMAIN, f"def load_rubric_{SENTINEL}():\n    return '{SENTINEL}'\n")

    def rules(args) -> int:
        report = {"rule": "unproven-rule", "severity": "error", "subject": SENTINEL}
        print(json.dumps([report | {"message": SENTINEL, "found": SENTINEL}]))
        return 1

    with_rules(monkeypatch, rules)
    out_dir = tmp_path / "bundle"

    code = main(["verify", "--out", str(out_dir)])
    printed = capsys.readouterr()

    index = json.loads((out_dir / "verify.json").read_text())
    # The gates did see the planted material ...
    assert code == 1
    assert gate(index, "validate")["counts"]["errors"] >= 1
    assert gate(index, "check-terms")["counts"]["errors"] >= 1
    assert gate(index, "evidence collect")["counts"]["fail"] == 1
    assert gate(index, "rules")["counts"]["by_rule"] == {"unproven-rule": 1}
    assert index["trace"]["violations"]
    # ... and none of it reached the bundle or the terminal.
    for path in out_dir.rglob("*"):
        assert SENTINEL not in path.read_text(), path.name
    assert SENTINEL not in printed.out + printed.err


def test_a_gate_that_crashes_is_an_error_named_by_its_kind_alone(repo, monkeypatch):
    def rules(args) -> int:
        raise RuntimeError(SENTINEL)

    with_rules(monkeypatch, rules)
    code, index = verify(repo)

    assert code == 1
    assert gate(index, "rules") == {
        "name": "rules",
        "command": "onto rules --format json",
        "exit_status": None,
        "status": "error",
        "reason": "RuntimeError",
        "counts": {},
    }
    assert gate(index, "prov emit")["status"] == "passed"


def test_an_interrupted_run_is_not_recorded_as_holding(repo, monkeypatch):
    def rules(args) -> int:
        raise KeyboardInterrupt

    with_rules(monkeypatch, rules)
    with pytest.raises(KeyboardInterrupt):
        main(["verify"])

    index = json.loads((repo.root / INDEX).read_text())
    assert index["ok"] is False
    assert [g["name"] for g in index["gates"]] == GATES[: GATES.index("rules")]


def test_the_rules_gate_is_the_real_onto_rules(repo, capsys):
    code, index = verify(repo)

    assert code == 0
    assert gate(index, "rules") == {
        "name": "rules",
        "command": "onto rules --format json",
        "exit_status": 0,
        "status": "passed",
        "counts": {"errors": 0, "warnings": 0},
    }


def test_a_rule_that_onto_rules_finds_unbound_fails_verify(repo, capsys):
    repo.context(
        "shop",
        SHOP,
        paths=["apps/shop/**"],
        domain_paths=["apps/shop/src/shop/domain/**"],
        bindings_json="apps/shop/src/shop/schemas/shop.bindings.json",
    )
    repo.write("apps/shop/src/shop/domain/orders.py", "def check(lines):\n    return None\n")

    code, index = verify(repo)

    assert code == 1 and index["ok"] is False
    assert gate(index, "rules")["status"] == "failed"
    assert gate(index, "rules")["counts"] == {
        "errors": 2,
        "warnings": 0,
        "by_rule": {"unbound-rule": 1, "unproven-rule": 1},
    }
    out = capsys.readouterr().out
    assert "by_rule" not in out and "OVER_LIMIT" not in out


def test_verify_of_a_branch_that_touched_nothing_names_the_commit(repo):
    git = ["git", "-C", str(repo.root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    git += ["-c", "commit.gpgsign=false"]
    repo.item("REQ-0001", status="done")  # a claim with nothing behind it, made before this branch
    repo.write(".gitignore", "work/evidence/\nprov/\n.pytest_cache/\n__pycache__/\n")
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], check=True)
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True)

    code, index = verify(repo, "--scope", "branch")

    assert code == 0 and index["scope"] == "branch" and index["trace"] is None
    assert index["scope_applied"] == "branch"
    assert gate(index, "trace")["counts"] == {"in_scope": 0}
    assert index["varies_per_run"]["commit"] == head.stdout.strip()
    assert index["varies_per_run"]["uncommitted_files"] == 0

    code, index = verify(repo, "--scope", "all")
    assert code == 1 and index["trace"]["violations"]


def test_a_branch_whose_base_cannot_be_found_answers_for_everything(repo, capsys):
    git = ["git", "-C", str(repo.root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    git += ["-c", "commit.gpgsign=false"]
    repo.item("REQ-0001", status="done")  # committed, and nothing verifies it
    repo.write(".gitignore", "work/evidence/\nprov/\n.pytest_cache/\n__pycache__/\n")
    # As a single-branch or shallow clone leaves it: no origin/main, no main, no master.
    subprocess.run([*git, "init", "-q", "-b", "work"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "claim"], check=True)

    code, index = verify(repo, "--scope", "branch")

    assert code == 1 and index["ok"] is False
    assert index["scope"] == "branch" and index["scope_applied"] == "all"
    assert index["varies_per_run"]["base_commit"] is None
    # The unverified claim is in scope, and so is the missing base: the gates over
    # what the branch changed cannot be answered by checking everything.
    assert [(v["rule"], v.get("subject")) for v in index["trace"]["violations"]] == [
        ("gate:BranchBaseIsKnown", None),
        ("gate:CompleteRequirementIsVerified", "REQ-0001"),
    ]
    assert "no base branch" in capsys.readouterr().out


def test_a_run_that_cannot_read_onto_toml_does_not_leave_an_index_that_says_ok(repo, capsys):
    verified(repo)
    code, index = verify(repo)
    assert code == 0 and index["ok"] is True

    config = repo.root / "onto.toml"
    config.write_text(config.read_text().replace('on_open_ocr = "ask"', 'on_open_ocr = "never"'))
    code, index = verify(repo)

    assert code == 1 and "on_open_ocr" in capsys.readouterr().err
    assert index["ok"] is False and index["gates"] == []
    assert index["reason"] == "ConfigError"


def test_an_out_that_is_a_file_is_refused_in_one_line(repo, capsys, tmp_path):
    taken = tmp_path / "taken"
    taken.write_text("a file, where a folder was asked for\n")

    assert main(["verify", "--out", str(taken)]) == 1

    said = capsys.readouterr().err
    assert "--out" in said and "taken" in said and "Traceback" not in said
    assert taken.read_text() == "a file, where a folder was asked for\n"
