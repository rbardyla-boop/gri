from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.forge.forge import Chain
from experiments.forge_e2.develop_te0_e2 import rank_key
from experiments.forge_e2.interface_tools import canonicalize_label_evidence_schema


def test_schema_canonicalizer_preserves_direct_information():
    value = {"label": "KAV", "evidence": ["E2", "E1", "E2"]}
    assert canonicalize_label_evidence_schema(value, allowed=["KAV", "MIR", "TOV"]) == value


def test_schema_canonicalizer_recovers_nested_explicit_schema_without_invention():
    value = {
        "mir": {
            "evidenceMultiset": ["E2", "E1", "E2"],
            "evidenceArray": ["E1", "E2"],
        }
    }
    out = canonicalize_label_evidence_schema(value, allowed=["KAV", "MIR", "TOV"])
    assert out == {"label": "mir", "evidence": ["E1", "E2"]}


def test_schema_canonicalizer_fails_closed_on_conflicting_evidence():
    value = {"TOV": {"evidenceArray": ["E1"], "evidenceMultiset": ["E2"]}}
    with pytest.raises(ValueError, match="CONFLICTING_EVIDENCE_FIELDS"):
        canonicalize_label_evidence_schema(value, allowed=["KAV", "MIR", "TOV"])


def metric(chain: Chain, *, gates: int, floor: float, exact: float) -> dict:
    return {
        "chain": chain,
        "pre_gate_count": gates,
        "robust_floor": floor,
        "dev_exact_rate": exact,
        "attack_set_exact_rate": floor,
        "structural_validity_rate": floor,
        "preservation_rate": 1.0,
        "improvement_over_raw": 0.2,
        "margin_over_null": 0.5,
    }


def test_gate_aware_ranking_prefers_more_gates_over_raw_exact():
    brittle = Chain(("brittle",), "text", "json", 1)
    robust = Chain(("robust",), "text", "json", 1)
    # E1-style exact-first selection would prefer brittle. E2 must prefer the
    # candidate that survives more registered development gates.
    m_brittle = metric(brittle, gates=4, floor=0.5, exact=1.0)
    m_robust = metric(robust, gates=6, floor=0.95, exact=0.95)
    assert sorted([m_brittle, m_robust], key=rank_key)[0]["chain"] == robust


def test_e2_operator_has_no_vault_surface():
    root = Path(__file__).resolve().parents[1]
    text = (root / "experiments" / "forge_e2" / "run_local_dev.sh").read_text()
    assert "judge_te0" not in text
    assert "authorize_te0" not in text
    assert "vault-seed-file" not in text
    assert "vault_created': False" in text
    assert "te0-e2-gate-aware-composer" in text


def test_e2_protocol_preserves_e1_terminal_boundary():
    root = Path(__file__).resolve().parents[1]
    text = (root / "experiments" / "forge_e2" / "TE0_E2_PROTOCOL.md").read_text()
    assert "TE0_E1_INTERFACE_REPAIR_FAIL" in text
    assert "does **not** rerun, repair, rescore, or reinterpret E1" in text
    assert "TE0-E2-PUBLIC-BUILD-v1" in text
    assert "TE0-E2-PUBLIC-DEV-v1" in text
