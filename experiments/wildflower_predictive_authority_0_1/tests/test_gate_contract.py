from __future__ import annotations

import pytest

from experiments.wildflower_predictive_authority_0_1 import design


EXPECTED_GATE_CONTRACT = {
    "old_h1_max": ("<=", 1.10),
    "old_h8_max": ("<=", 1.00),
    "old_h8_mean": ("<=", 0.90),
    "old_h32_max": ("<=", 1.00),
    "old_h32_mean": ("<=", 0.85),
    "old_event_h8_mean": ("<=", 0.90),
    "h8_worse_learned_protection": ("<=", 1.05),
    "h8_useful_learner_capture": (">=", 0.50),
    "h1_global_regression": ("<=", 1.05),
    "h32_global_noninferiority": ("<=", 1.05),
    "h8_nontrivial_fraction": (">=", 0.05),
    "h8_nontrivial_mean": (">=", 0.05),
}


def test_machine_readable_contract_matches_frozen_gate_table() -> None:
    actual = {
        name: (spec["operator"], spec["threshold"])
        for name, spec in design.GATE_CONTRACT.items()
    }
    assert actual == EXPECTED_GATE_CONTRACT


@pytest.mark.parametrize("name", EXPECTED_GATE_CONTRACT)
def test_every_gate_contract_has_equality_boundary_and_direction(name: str) -> None:
    operator, threshold = EXPECTED_GATE_CONTRACT[name]
    assert design.gate_passes(name, threshold)
    if operator == "<=":
        assert design.gate_passes(name, threshold - 0.001)
        assert not design.gate_passes(name, threshold + 0.001)
    else:
        assert design.gate_passes(name, threshold + 0.001)
        assert not design.gate_passes(name, threshold - 0.001)
