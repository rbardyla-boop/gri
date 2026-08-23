from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.forge.ecology import (
    Ablator,
    Composer,
    FailureClass,
    Judge,
    JudgeVerdict,
    Ledger,
    NullSmith,
    ToolBlueprint,
    ToolSmith,
    classify_failure,
    promote_skill,
)
from experiments.forge.forge import Case, Chain, Forge, Registry, SearchConfig, Tool


def test_failure_classifier_stops_on_integrity_before_resource_or_model() -> None:
    diagnosis = classify_failure({
        "model_wrong_after_controls": True,
        "oom": True,
        "holdout_leak": True,
    })
    assert diagnosis.failure_class is FailureClass.INTEGRITY
    assert "holdout_leak" in diagnosis.evidence


def test_failure_classifier_separates_host_failure_from_science() -> None:
    diagnosis = classify_failure({"gpu_unavailable": True})
    assert diagnosis.failure_class is FailureClass.RESOURCE
    assert "do not interpret as science" in diagnosis.recommended_action


def test_toolsmith_rejects_arbitrary_code_operations() -> None:
    smith = ToolSmith()
    blueprint = ToolBlueprint(
        "evil",
        "exec",
        "text",
        "text",
        1,
        {"code": "import os; os.system('true')"},
        FailureClass.TOOL,
    )
    with pytest.raises(ValueError, match="FORGE_TOOL_OP_FORBIDDEN"):
        smith.factory.compile(blueprint)


def test_composer_prefers_simple_recipe_when_scores_tie() -> None:
    reg = Registry()
    reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
    reg.register(Tool("identity", "int", "int", 1, lambda x: x))
    forge = Forge(reg)
    dev = [Case("d1", 1, 3), Case("d2", 2, 4)]
    ranked = Composer(forge).search(
        dev,
        SearchConfig("int", "int", max_depth=2, max_cost=2),
        complexity_penalty=0.05,
        cost_penalty=0.05,
    )
    assert ranked[0].chain.tools == ("plus_two",)
    assert ranked[0].dev_score == 1.0


def test_nullsmith_exposes_embarrassing_simple_control() -> None:
    cases = [Case("a", "x", "YES"), Case("b", "y", "YES"), Case("c", "z", "NO")]
    nulls = NullSmith.constant_null(cases)
    assert nulls[0].score == pytest.approx(2 / 3)
    assert nulls[0].name.startswith("constant:")


def test_ablator_identifies_component_that_does_not_earn_credit() -> None:
    reg = Registry()
    reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
    reg.register(Tool("identity", "int", "int", 1, lambda x: x))
    forge = Forge(reg)
    chain = Chain(("identity", "plus_two"), "int", "int", 2)
    cases = [Case("d1", 1, 3), Case("d2", 2, 4)]
    rows = Ablator(forge).single_tool_ablations(chain, cases)
    by_name = {row.removed_tool: row for row in rows}
    assert by_name["identity"].valid is True
    assert by_name["identity"].delta_from_full == pytest.approx(0.0)


def test_judge_burns_vault_before_scoring_and_promotes_only_pass(tmp_path: Path) -> None:
    reg = Registry()
    reg.register(Tool("plus_two", "int", "int", 1, lambda x: x + 2))
    forge = Forge(reg)
    chain = Chain(("plus_two",), "int", "int", 1)
    cases = [Case("v1", 10, 12), Case("v2", 20, 22)]
    consume = tmp_path / "consumed.json"
    receipt_path = tmp_path / "receipt.json"

    receipt = Judge(forge).evaluate_once(
        chain,
        cases,
        threshold=1.0,
        min_margin_over_null=0.5,
        receipt_path=receipt_path,
        consumption_path=consume,
    )
    assert receipt.verdict is JudgeVerdict.PASS
    assert consume.exists()
    assert receipt_path.exists()
    packet = promote_skill(chain, receipt)
    assert packet.authority is True
    assert packet.chain_id == chain.chain_id

    with pytest.raises(RuntimeError, match="FORGE_VAULT_ALREADY_CONSUMED"):
        Judge(Forge(reg)).evaluate_once(
            chain,
            cases,
            threshold=1.0,
            consumption_path=consume,
        )


def test_failed_judge_cannot_create_skill_packet() -> None:
    reg = Registry()
    reg.register(Tool("identity", "int", "int", 1, lambda x: x))
    chain = Chain(("identity",), "int", "int", 1)
    receipt = Judge(Forge(reg)).evaluate_once(
        chain,
        [Case("v1", 1, 2)],
        threshold=1.0,
    )
    assert receipt.verdict is JudgeVerdict.FAIL
    with pytest.raises(ValueError, match="FORGE_PROMOTION_REQUIRES_JUDGE_PASS"):
        promote_skill(chain, receipt)


def test_ledger_is_hash_chained_and_tamper_evident(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    ledger.append({"experiment": "TE0-1", "authority": False})
    ledger.append({"experiment": "TE0-2", "authority": False})
    assert ledger.verify() is True

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["experiment"] = "TAMPERED"
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    assert ledger.verify() is False
