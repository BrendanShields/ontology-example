"""`onto rules`, the binding annotations it reads and the manifest `onto gen` writes from it.

Everything here runs against a toy bounded context, a shop that refuses some
orders and totals the rest, so that no test depends on what the real glossary binds.
"""

from __future__ import annotations

import io
import json
import subprocess

import pytest
from onto import gen, guard
from onto.cli import main
from onto.config import load_config
from onto.hooks import BLOCK
from onto.testing import scratch_repo

SCHEMA = """\
id: https://shop.example/ontology/shop
name: shop
prefixes:
  linkml: https://w3id.org/linkml/
  shop: https://shop.example/ontology/shop/
default_prefix: shop
default_range: string
imports:
  - linkml:types
classes:
  Order:
    description: What a customer asks the shop for.
    slots: [total]
  Refusal:
    description: Why the shop did not take an Order.
    slots: [refusal_rule]
slots:
  total:
    description: The sum of the lines of an Order.
    range: integer
    annotations:
      binding: computed
  refusal_rule:
    description: The rule a Refusal reports as broken.
    range: RefusalRule
enums:
  RefusalRule:
    description: The rules an Order can break.
    annotations:
      binding: rule
    permissible_values:
      EMPTY_ORDER:
        description: The Order has no lines.
        annotations:
          precondition_of: Step.PLACE_ORDER
      OVER_LIMIT:
        description: The Order is worth more than the shop takes at once.
  Step:
    description: What the shop can do with an Order.
    permissible_values:
      PLACE_ORDER:
        description: Take the Order.
"""
# The same glossary with nothing bound.
UNBOUND = (
    SCHEMA.replace("    annotations:\n      binding: computed\n", "")
    .replace("    annotations:\n      binding: rule\n", "")
    .replace("        annotations:\n          precondition_of: Step.PLACE_ORDER\n", "")
)

ORDERS = "apps/shop/src/shop/domain/orders.py"
TILL = "apps/shop/src/shop/till.py"
MANIFEST = "apps/shop/src/shop/schemas/shop.bindings.json"
STALL_MANIFEST = "apps/stall/stall.bindings.json"

CHECKS = """\
from ..generated import Refusal, RefusalRule


def check(lines, limit):
    if not lines:
        return Refusal(refusal_rule=RefusalRule.EMPTY_ORDER)
    if sum(lines) > limit:
        return Refusal(refusal_rule=RefusalRule.OVER_LIMIT)
    return None
"""
PLACE = """\
from .generated import Order


class Till:
    def place(self, lines):
        return Order(total=sum(lines))
"""
EVERY_TERM = ["RefusalRule.EMPTY_ORDER", "RefusalRule.OVER_LIMIT", "total"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    scratch = scratch_repo(tmp_path)
    monkeypatch.setenv("ONTO_ROOT", str(scratch.root))
    return scratch


def shop(repo, schema: str = SCHEMA, checks: str = CHECKS, place: str = PLACE, **table) -> None:
    """The toy context, its code, and one done Requirement that a passing Test verifies."""
    settings = {
        "paths": ["apps/shop/**"],
        "domain_paths": ["apps/shop/src/shop/domain/**"],
        "write_paths": [TILL],
        "bindings_json": MANIFEST,
        **table,
    }
    repo.context("shop", schema, **{k: v for k, v in settings.items() if v is not None})
    repo.write(ORDERS, checks)
    repo.write(TILL, place)
    requirement(repo)
    repo.item("TST-0001", bounded_context="shop", verifies=["REQ-0001"])
    repo.item("EVD-0001", of_test="TST-0001", result="pass")


def requirement(repo, identifier: str = "REQ-0001", terms=EVERY_TERM, status: str = "done"):
    repo.item(
        identifier,
        bounded_context="shop",
        status=status,
        ears_text="The shop shall " + " ".join(f"`{term}`" for term in terms) + ".",
        uses_terms=list(terms),
    )


def stall(repo) -> None:
    """A second context with the same term names and nothing bound."""
    repo.context("stall", UNBOUND.replace("shop", "stall"), bindings_json=STALL_MANIFEST)


def rules(capsys, context: str = "shop") -> tuple[int, dict]:
    code = main(["rules", "--json", "--context", context])
    return code, json.loads(capsys.readouterr().out)


def report(capsys) -> tuple[int, str]:
    code = main(["rules", "--context", "shop"])
    return code, capsys.readouterr().out


def problems(capsys) -> tuple[int, list[tuple[str, str, str | None]]]:
    """(exit code, [(severity, rule, the term or file it is about), ...])."""
    code, answer = rules(capsys)
    return code, [
        (p["severity"], p["rule"], p.get("subject") or p.get("file")) for p in answer["problems"]
    ]


# --- the gate ------------------------------------------------------------------------


def test_a_context_that_binds_nothing_passes_and_says_so(repo, capsys):
    stall(repo)
    assert main(["rules", "--context", "stall"]) == 0
    assert "no term declares a binding" in capsys.readouterr().out
    assert rules(capsys, "stall") == (0, {"contexts": [], "problems": []})


def test_a_rule_with_code_and_proof_passes(repo, capsys):
    shop(repo)
    code, answer = rules(capsys)
    assert code == 0 and answer["problems"] == []
    (context,) = answer["contexts"]
    assert context["context"] == "shop"
    assert context["bindings"] == [
        {
            "term": "RefusalRule.EMPTY_ORDER",
            "binding": "rule",
            "precondition_of": "Step.PLACE_ORDER",
            "functions": [f"{ORDERS}::check"],
            "proven_by": [{"requirement": "REQ-0001", "tests": ["TST-0001"]}],
        },
        {
            "term": "RefusalRule.OVER_LIMIT",
            "binding": "rule",
            "functions": [f"{ORDERS}::check"],
            "proven_by": [{"requirement": "REQ-0001", "tests": ["TST-0001"]}],
        },
        {
            "term": "total",
            "binding": "computed",
            "functions": [f"{TILL}::Till.place"],
            "proven_by": [{"requirement": "REQ-0001", "tests": ["TST-0001"]}],
        },
    ]

    code, text = report(capsys)
    assert code == 0
    assert (
        f"produced by: {TILL}::Till.place" in text and "proven by:   REQ-0001 by TST-0001" in text
    )
    assert "3 bound term(s), 0 error(s), 0 warning(s)" in text


def test_a_rule_nothing_implements_is_unbound(repo, capsys):
    shop(repo, checks=CHECKS.replace("RefusalRule.OVER_LIMIT", "None"))
    assert problems(capsys) == (1, [("error", "unbound-rule", "RefusalRule.OVER_LIMIT")])

    code, text = report(capsys)
    assert code == 1
    assert (
        "ontology/domains/shop.yaml: error[unbound-rule] RefusalRule.OVER_LIMIT is declared" in text
    )
    assert "Looked in 2 file(s) of apps/shop/src/shop/domain/**, apps/shop/src/shop/till.py" in text
    assert "fix: write a function that enforces the rule and reports it as" in text
    assert "onto ocr new --context shop --term RefusalRule.OVER_LIMIT" in text
    assert '--title "Withdraw the binding on RefusalRule.OVER_LIMIT"' in text


@pytest.mark.parametrize(
    "reading",
    [
        "def is_over(refusal):\n    return refusal.refusal_rule == RefusalRule.OVER_LIMIT\n",
        "def is_over(rule):\n    return rule in (RefusalRule.OVER_LIMIT, None)\n",
        "def is_over(rule):\n    match rule:\n        case RefusalRule.OVER_LIMIT:\n"
        "            return True\n",
        "LIMITS = {RefusalRule.OVER_LIMIT: 100}\n",  # a table at module level, not a function
    ],
)
def test_reading_a_rule_is_not_producing_it(repo, capsys, reading):
    shop(repo, checks=CHECKS.replace("RefusalRule.OVER_LIMIT", "None") + "\n\n" + reading)
    assert problems(capsys) == (1, [("error", "unbound-rule", "RefusalRule.OVER_LIMIT")])


@pytest.mark.parametrize(
    "naming",
    [
        "def refuse(order, rule=RefusalRule.OVER_LIMIT):\n    return rule\n",
        "def refuse(order, *, rule=RefusalRule.OVER_LIMIT):\n    return rule\n",
        "def refuse(order) -> Literal[RefusalRule.OVER_LIMIT]:\n    return order.rule\n",
        "def refuse(rule: Literal[RefusalRule.OVER_LIMIT]):\n    return rule\n",
    ],
    ids=["default", "keyword-default", "return-annotation", "argument-annotation"],
)
def test_naming_a_rule_in_a_signature_is_not_producing_it(repo, capsys, naming):
    shop(repo, checks=CHECKS.replace("RefusalRule.OVER_LIMIT", "None") + "\n\n" + naming)
    assert problems(capsys) == (1, [("error", "unbound-rule", "RefusalRule.OVER_LIMIT")])


def test_a_computed_slot_is_bound_only_where_a_generated_class_is_given_it(repo, capsys):
    elsewhere = "def place(lines):\n    return dict(total=sum(lines))\n"
    shop(repo, place=elsewhere)
    assert problems(capsys) == (1, [("error", "unbound-rule", "total")])
    assert "no function passes total= to Order(...)" in report(capsys)[1]


def test_code_outside_the_domain_layer_counts_only_when_it_is_on_the_write_path(repo, capsys):
    shop(repo, write_paths=None)
    code, found = problems(capsys)
    assert (code, found) == (1, [("error", "unbound-rule", "total")])


@pytest.mark.parametrize(
    ("change", "found", "fix"),
    [
        (
            lambda repo: requirement(repo, terms=EVERY_TERM[:2]),
            "no Requirement of shop lists total in uses_terms",
            "onto new Requirement bounded_context=shop",
        ),
        (
            lambda repo: requirement(repo, status="in_progress"),
            "total is used by REQ-0001 (in_progress), and none of them is done",
            "finish the Requirement",
        ),
        (
            lambda repo: (repo.root / "work/TST-0001.md").unlink(),
            "total is used by REQ-0001, which no Test of shop verifies",
            "onto new Test bounded_context=shop",
        ),
        (
            lambda repo: (repo.root / "work/evidence/EVD-0001.md").unlink(),
            "total is used by REQ-0001, whose Tests are TST-0001 (no evidence)",
            "uv run pytest --onto-evidence",
        ),
        (
            lambda repo: repo.item("EVD-0001", of_test="TST-0001", result="fail"),
            "total is used by REQ-0001, whose Tests are TST-0001 (fail)",
            "uv run pytest --onto-evidence",
        ),
    ],
)
def test_a_rule_without_a_verified_requirement_is_unproven(repo, capsys, change, found, fix):
    shop(repo)
    change(repo)
    code, answer = rules(capsys)
    unproven = [p for p in answer["problems"] if p["subject"] == "total"]
    assert code == 1 and [p["rule"] for p in unproven] == ["unproven-rule"]
    assert unproven[0]["message"].startswith(found)
    assert "Accepted: a Requirement with status done" in unproven[0]["message"]
    assert fix in unproven[0]["fix"]
    assert unproven[0]["file"] == "ontology/domains/shop.yaml"


def test_a_requirement_of_another_context_proves_nothing(repo, capsys):
    shop(repo)
    requirement(repo, terms=EVERY_TERM[:2])
    stall(repo)
    repo.item(
        "REQ-0002",
        bounded_context="stall",
        status="done",
        uses_terms=["total"],
        ears_text="The stall shall `total`.",
    )
    repo.item("TST-0002", bounded_context="stall", verifies=["REQ-0002"])
    repo.item("EVD-0002", of_test="TST-0002", result="pass")
    code, answer = rules(capsys)
    found = [(p["rule"], p["subject"]) for p in answer["problems"]]
    assert (code, found) == (1, [("unproven-rule", "total")])


def test_a_test_of_another_context_proves_nothing(repo, capsys):
    shop(repo)
    stall(repo)
    repo.item("TST-0001", bounded_context="stall", verifies=["REQ-0001"])
    code, answer = rules(capsys)
    assert code == 1
    assert {(p["rule"], p["subject"]) for p in answer["problems"]} == {
        ("unproven-rule", term) for term in EVERY_TERM
    }
    assert "which no Test of shop verifies" in answer["problems"][0]["message"]

    repo.item("TST-0002", bounded_context="shop", verifies=["REQ-0001"])
    repo.item("EVD-0002", of_test="TST-0002", result="pass")
    code, answer = rules(capsys)
    assert (code, answer["problems"]) == (0, [])
    proofs = [b["proven_by"] for c in answer["contexts"] for b in c["bindings"]]
    assert "TST-0001" not in json.dumps(proofs) and "TST-0002" in json.dumps(proofs)


@pytest.mark.parametrize(
    "checks",
    [
        CHECKS.replace("RefusalRule", "Rule").replace("import Refusal, Rule", "import Refusal")
        + "from ..generated import RefusalRule as Rule\n",
        CHECKS.replace("RefusalRule.", "generated.RefusalRule.") + "from .. import generated\n",
        CHECKS.replace("RefusalRule.", "Rule.") + "Rule = RefusalRule\n",
    ],
    ids=["imported-under-another-name", "through-the-module", "assigned-to-another-name"],
)
def test_a_rule_written_through_another_name_is_still_bound(repo, capsys, checks):
    shop(
        repo,
        checks=checks,
        place=PLACE.replace("Order", "O").replace("import O", "import Order as O"),
    )
    assert problems(capsys) == (0, [])


def test_what_the_scan_cannot_see_is_reported_where_it_happens(repo, capsys):
    looked_up = (
        "from ..generated import Refusal, RefusalRule\n\n\n"
        "def check(lines, limit):\n"
        "    name = 'EMPTY_ORDER' if not lines else 'OVER_LIMIT'\n"
        "    return Refusal(refusal_rule=RefusalRule[name])\n"
    )
    from_data = (
        "from .generated import Order\n\n\n"
        "def place(lines):\n"
        "    fields = {'total': sum(lines)}\n"
        "    return Order(**fields)\n"
    )
    shop(repo, checks=looked_up, place=from_data)
    code, answer = rules(capsys)
    assert code == 1  # fails closed: what cannot be seen is not taken on trust
    found = [(p["severity"], p["rule"], p.get("subject") or p["file"]) for p in answer["problems"]]
    assert found == [
        ("error", "unbound-rule", "RefusalRule.EMPTY_ORDER"),
        ("error", "unbound-rule", "RefusalRule.OVER_LIMIT"),
        ("error", "unbound-rule", "total"),
        ("warning", "hidden-binding", ORDERS),
        ("warning", "hidden-binding", TILL),
    ]
    by_file = {p["file"]: p for p in answer["problems"] if p["rule"] == "hidden-binding"}
    assert by_file[ORDERS]["line"] == 6 and by_file[TILL]["line"] == 6
    assert "`RefusalRule[name]` in check looks a RefusalRule up" in by_file[ORDERS]["message"]
    assert "RefusalRule.EMPTY_ORDER, RefusalRule.OVER_LIMIT" in by_file[ORDERS]["message"]
    assert "`Order(**fields)` in place builds Order from data" in by_file[TILL]["message"]
    assert by_file[TILL]["fix"] == "pass total= to Order(...) by name"


def test_a_lookup_does_not_warn_about_rules_that_are_bound_elsewhere(repo, capsys):
    shop(repo, checks=CHECKS + "\n\ndef parse(name):\n    return RefusalRule[name]\n")
    assert problems(capsys) == (0, [])


def test_one_context_can_be_checked_alone(repo, capsys):
    shop(repo, checks="")
    stall(repo)
    assert rules(capsys)[0] == 1
    assert rules(capsys, "stall")[0] == 0
    assert main(["rules", "--context", "nowhere"]) == 1
    assert "no bounded context 'nowhere'" in capsys.readouterr().err


# --- the manifest --------------------------------------------------------------------


def generate(repo, check: bool = False) -> dict[str, str]:
    return {r.path: r.status for r in gen.generate(load_config(repo.root), check=check)}


def test_a_context_that_binds_nothing_has_no_manifest(repo):
    stall(repo)
    assert STALL_MANIFEST not in generate(repo) and not (repo.root / STALL_MANIFEST).exists()


def test_the_manifest_says_which_function_produces_each_bound_term(repo):
    shop(repo)
    assert generate(repo, check=True)[MANIFEST] == "drift"
    assert generate(repo)[MANIFEST] == "written"
    written = json.loads((repo.root / MANIFEST).read_text(encoding="utf-8"))
    assert "GENERATED by `onto gen`" in written.pop("$comment")
    assert written == {
        "context": "shop",
        "bindings": {
            "RefusalRule.EMPTY_ORDER": {
                "binding": "rule",
                "precondition_of": "Step.PLACE_ORDER",
                "functions": [f"{ORDERS}::check"],
            },
            "RefusalRule.OVER_LIMIT": {"binding": "rule", "functions": [f"{ORDERS}::check"]},
            "total": {"binding": "computed", "functions": [f"{TILL}::Till.place"]},
        },
        "preconditions": {"Step.PLACE_ORDER": ["RefusalRule.EMPTY_ORDER"]},
    }
    assert generate(repo, check=True)[MANIFEST] == "unchanged"
    decision, reason = guard.decide(repo.ws(), MANIFEST)
    assert decision == guard.DENY and "the functions it binds" in reason
    assert "OntologyChangeRequest" not in reason  # a function that moved needs none


def test_the_manifest_holds_nothing_that_a_test_run_decides(repo):
    shop(repo)
    generate(repo)
    before = (repo.root / MANIFEST).read_text(encoding="utf-8")
    (repo.root / "work/evidence/EVD-0001.md").unlink()
    (repo.root / "work/REQ-0001.md").unlink()
    assert generate(repo, check=True)[MANIFEST] == "unchanged"
    assert "REQ-0001" not in before and "TST-0001" not in before


def test_moving_a_producing_function_is_drift_until_the_manifest_is_regenerated(repo, capsys):
    shop(repo)
    generate(repo)
    repo.write(TILL, PLACE.replace("def place", "def take"))
    assert main(["gen", "--check"]) == 1
    assert f'+        "{TILL}::Till.take"' in capsys.readouterr().out
    assert generate(repo)[MANIFEST] == "written"
    assert main(["gen", "--check"]) == 0


def test_no_manifest_is_written_from_a_file_that_does_not_parse(repo, capsys):
    shop(repo)
    generate(repo)
    before = (repo.root / MANIFEST).read_text(encoding="utf-8")
    repo.write(ORDERS, CHECKS + "def broken(:\n")

    # A manifest written now would say that nothing in orders.py produces a rule.
    for command in (["gen"], ["gen", "--check"]):
        assert main(command) == 1
        said = capsys.readouterr().err
        assert MANIFEST in said and ORDERS in said and "could not be parsed" in said
    assert (repo.root / MANIFEST).read_text(encoding="utf-8") == before


def test_the_stop_gate_blocks_on_a_bound_file_left_unparsable(repo, monkeypatch, capsys):
    shop(repo)
    generate(repo)
    git = ["git", "-C", str(repo.root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    for command in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run([*git, "-c", "commit.gpgsign=false", *command], check=True)
    repo.write(ORDERS, CHECKS + "def broken(:\n")
    repo.write(MANIFEST, "{}\n")  # the branch touched a generated file, so they are compared

    monkeypatch.setattr("sys.stdin", io.StringIO('{"hook_event_name": "Stop"}'))
    code = main(["trace", "--gate", "stop", "--scope", "branch"])

    said = capsys.readouterr().err
    assert code == BLOCK
    assert f"{ORDERS}: error[gate:GeneratedMatchesSource]" in said and "parsed" in said


def test_the_manifest_goes_when_the_last_binding_does(repo):
    shop(repo)
    generate(repo)
    repo.write("ontology/domains/shop.yaml", UNBOUND)
    assert generate(repo, check=True)[MANIFEST] == "drift"
    assert generate(repo)[MANIFEST] == "removed"
    assert not (repo.root / MANIFEST).exists() and MANIFEST not in generate(repo, check=True)


def test_bindings_without_a_place_for_the_manifest_are_pointed_out(repo, capsys):
    shop(repo, bindings_json=None)
    assert problems(capsys) == (0, [("warning", "no-manifest", "onto.toml")])


# --- the annotations -----------------------------------------------------------------


def lint(repo, capsys) -> list[dict]:
    code = main(["validate", "--format", "json"])
    found = [p for p in json.loads(capsys.readouterr().out) if p["rule"] == "glossary"]
    assert code == (1 if found else 0)
    return found


def test_a_glossary_with_bindings_and_its_own_annotations_is_valid(repo, capsys):
    shop(repo, schema=SCHEMA.replace("binding: computed", "binding: computed\n      owner: tills"))
    assert lint(repo, capsys) == []
    glossary = repo.ws().glossary("shop")
    assert [term.name for term in glossary.bound()] == EVERY_TERM
    assert glossary.get("EMPTY_ORDER").precondition_of == "Step.PLACE_ORDER"


@pytest.mark.parametrize(
    ("old", "new", "subject", "message", "hint"),
    [
        ("binding: rule", "binding: rul", "RefusalRule", "has binding 'rul'", "rule"),
        ("binding: computed", "binding: derived", "total", "has binding 'derived'", "computed"),
        (
            "binding: rule",
            "bindng: rule",
            "RefusalRule",
            "'bindng' on 'RefusalRule' is not a key",
            "binding",
        ),
        (
            "precondition_of:",
            "precondition-of:",
            "RefusalRule.EMPTY_ORDER",
            "is not a key",
            "precondition_of",
        ),
        ("binding: rule", "binding: computed", "RefusalRule", "belongs on a slot", None),
        (
            "binding: computed",
            "binding: rule",
            "total",
            "belongs on an enum or a value",
            "computed",
        ),
        (
            "Step.PLACE_ORDER\n",
            "PLACE_ORDR\n",
            "RefusalRule.EMPTY_ORDER",
            "is not another term",
            "Step.PLACE_ORDER",
        ),
        (
            "Step.PLACE_ORDER\n",
            "RefusalRule.EMPTY_ORDER\n",
            "RefusalRule.EMPTY_ORDER",
            "is not another term",
            None,
        ),
        (
            "    annotations:\n      binding: rule\n",
            "",
            "RefusalRule.EMPTY_ORDER",
            "is not a bound rule",
            None,
        ),
    ],
)
def test_a_binding_annotation_the_tooling_cannot_act_on_is_an_error(
    repo, capsys, old, new, subject, message, hint
):
    assert old in SCHEMA
    shop(repo, schema=SCHEMA.replace(old, new))
    found = [p for p in lint(repo, capsys) if p["subject"] == subject]
    assert len(found) == 1 and message in found[0]["message"]
    assert found[0]["file"] == "ontology/domains/shop.yaml"
    if hint:
        assert hint in found[0].get("allowed", []) + found[0].get("suggestions", [])


# --- the configuration ---------------------------------------------------------------


@pytest.mark.parametrize(
    "key, value, reason",
    [
        ("write_paths", TILL, "a list of globs"),
        ("domain_paths", "apps/shop/src/shop/domain/**", "a list of globs"),
        ("paths", "apps/shop/**", "a list of globs"),
        ("write_paths", 3, "a list of globs"),
        ("write_paths", [3], "a list of globs"),
        ("write_paths", ["/etc/**"], "inside the repository"),
        ("write_paths", ["../**"], "inside the repository"),
        ("domain_paths", ["apps/shop/../../../**"], "inside the repository"),
    ],
)
def test_a_path_list_that_would_send_the_scan_astray_is_a_config_error(
    repo, capsys, key, value, reason
):
    shop(repo, **{key: value})
    for command in (["rules"], ["gen", "--check"]):
        assert main(command) == 1
        message = capsys.readouterr().err
        assert f"[contexts.shop] {key}" in message and reason in message
