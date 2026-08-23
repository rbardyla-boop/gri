from __future__ import annotations

from pathlib import Path

from gauntlet.autopsy import OUTCOME_PRECEDENCE, autopsy_claim


ROOT = Path(__file__).resolve().parents[1]


def _run(name: str) -> dict:
    return autopsy_claim(ROOT / "examples" / "gauntlet" / "autopsy" / f"{name}.toml")


def test_outcome_precedence_is_generic_and_negative_signals_beat_advance() -> None:
    assert OUTCOME_PRECEDENCE.index("TRANSFER_FAILURE") < OUTCOME_PRECEDENCE.index("ADVANCE")
    assert OUTCOME_PRECEDENCE.index("CONFOUND_EXPLAINS_ADVANTAGE") < OUTCOME_PRECEDENCE.index("ADVANCE")
    assert OUTCOME_PRECEDENCE.index("TRANSPARENT_NULL_DOMINATES") < OUTCOME_PRECEDENCE.index("ADVANCE")
    assert OUTCOME_PRECEDENCE.index("COMPONENT_UNNECESSARY") < OUTCOME_PRECEDENCE.index("ADVANCE")


def test_dmc05a_is_diagnosed_as_confound_without_experiment_specific_engine_code() -> None:
    result = _run("dmc05a")
    assert result["outcome"] == "CONFOUND_EXPLAINS_ADVANTAGE"
    assert result["credit_disposition"] == "REMOVED"
    assert result["boundary"]["prospective_credit"] is False


def test_dmc05r_is_diagnosed_as_transparent_null_dominance() -> None:
    result = _run("dmc05r")
    assert result["outcome"] == "TRANSPARENT_NULL_DOMINATES"
    assert result["credit_disposition"] == "REMOVED"


def test_mco03_is_diagnosed_as_unnecessary_learned_component_from_underlying_metrics() -> None:
    result = _run("mco03")
    assert result["outcome"] == "COMPONENT_UNNECESSARY"
    assert result["credit_disposition"] == "REMOVED"
    signal = result["signals"][0]
    assert signal["triggered"] is True
    assert len(signal["predicates"]) == 4
    assert all(row["pass"] for row in signal["predicates"])


def test_mco05_transfer_failure_overrides_small_relative_lead() -> None:
    result = _run("mco05")
    assert "TRANSFER_FAILURE" in result["triggered_outcomes"]
    assert "ADVANCE" in result["triggered_outcomes"]
    assert result["outcome"] == "TRANSFER_FAILURE"
    assert result["credit_disposition"] == "WITHHELD"


def test_generic_engine_contains_no_historical_experiment_labels() -> None:
    source = (ROOT / "src" / "gauntlet" / "autopsy.py").read_text(encoding="utf-8")
    for forbidden in ("DMC-05A", "DMC-05R", "MCO-03", "MCO-05", "DMC_05A", "DMC_05R", "MCO_03", "MCO_05"):
        assert forbidden not in source
