from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc3e" / "characterize.py"


def test_kc3e_finite_horizon_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc3e-dynamics.json"
    result = subprocess.run(
        [sys.executable, str(CHARACTERIZE), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "PASS",
        "unit": "KC-3E-D",
        "verdict": "KC_3E_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["population_tick_source_sha256"] == "290ad31ad658318f10e14a39aa0be6a7de684d8f527061447a44ed4fa7bf5502"
    assert payload["population_tick_config_sha256"] == "0eeb04cf496d4bd77c5a1ecf9e81286bc57a8508daa9577eb929694fef2bbb6e"
    assert payload["activation_source_sha256"] == "780c9209cb1cf199e1a719edbad24ce873b4fe33e24874a2387cda1561ad567d"
    assert all(payload["checks"].values())
    assert payload["horizon"] == 4
    assert payload["hard_bounds"] == {
        "max_activations_per_tick": 8,
        "max_slot_contacts_per_tick": 112,
        "max_total_activations": 32,
        "max_total_slot_contacts": 448,
    }
    assert len(payload["characterization"]["single_packet_chain"]) == 4
    assert payload["characterization"]["same_slot_competition"]["physical_slot"] == 1
    assert payload["characterization"]["dead_intermediate_control"]["no_teleportation_to_C2"] is True
    assert payload["characterization"]["dead_intermediate_control"]["no_teleportation_to_C3"] is True
    assert payload["source_audit"]["while_loop_count"] == 0
    assert payload["source_audit"]["async_function_count"] == 0
    assert payload["source_audit"]["execution_mutation_calls"] == []
    assert payload["source_audit"]["population_tick_signature"] == ["population"]
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64
