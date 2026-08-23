from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc3c" / "characterize.py"


def test_kc3c_local_contact_selection_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc3c-activation.json"
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
        "unit": "KC-3C-D",
        "verdict": "KC_3C_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["manager_source_sha256"] == "af28edf692724d3bdc4a4737cd546f055f42832c6ae854898f7c7cf6b595f8f7"
    assert payload["child_creation_source_sha256"] == "f3fdf0d4ae6bda8d103549c22c20f7a8d4e53fcf7b54700b6aedc1198b900046"
    assert payload["share_source_sha256"] == "45a1e6f76721f6e5988323276dce2defb8463dafbd491da34974263b2728b223"
    assert payload["export_source_sha256"] == "e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264"
    assert payload["cell_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert all(payload["checks"].values())
    assert payload["characterization"]["linear_wave"]["c2_to_c3"] is True
    assert payload["characterization"]["branching_wave"]["left_has_packet"] is True
    assert payload["characterization"]["branching_wave"]["right_has_packet"] is True
    assert payload["characterization"]["last_copy_death"]["registry_cannot_reconstruct"] is True
    assert payload["characterization"]["population_cap"]["at_cap"] is True
    assert payload["activate_source_audit"]["runtime_signature"] == ["population", "source_id"]
    assert payload["activate_source_audit"]["source_signature"] == ["population", "source_id"]
    assert payload["activate_source_audit"]["direct_state_snapshot_calls_in_activate"] == 1
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64
