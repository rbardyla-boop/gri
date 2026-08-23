from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc3d" / "characterize.py"


def test_kc3d_bounded_population_tick_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc3d-population-tick.json"
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
        "unit": "KC-3D-D",
        "verdict": "KC_3D_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["manager_source_sha256"] == "af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7"
    assert payload["share_source_sha256"] == "45a1e6f76721f6e5988323276dce2defb8463dafbd491da34974263b2728b223"
    assert payload["activation_source_sha256"] == "780c9209cb1cf199e1a719edbad24ce873b4fe33e24874a2387cda1561ad567d"
    assert payload["cell_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert all(payload["checks"].values())
    assert payload["hard_bounds"] == {"max_activations_per_tick": 8, "max_slot_contacts_per_tick": 112}
    assert payload["characterization"]["reverse_cascade"]["three_explicit_ticks"] is True
    assert payload["characterization"]["malformed_state_preflight"]["no_mutation_before_failure"] is True
    assert payload["characterization"]["hard_budget"]["maximum_case_reached"] is True
    assert payload["tick_source_audit"]["runtime_signature"] == ["population"]
    assert payload["tick_source_audit"]["source_signature"] == ["population"]
    assert payload["tick_source_audit"]["direct_activate_cell_calls"] == 1
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64

