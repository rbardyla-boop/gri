from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc2b" / "characterize.py"


def test_kc2b_oracle_free_export_characterization_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc2b-export.json"
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
        "unit": "KC-2B-D",
        "verdict": "KC_2B_DEV_COMPLETE",
    }

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["cell_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["fixture_bank_sha256"] == "0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5"
    assert payload["checks"] == {
        "anchors": True,
        "bank_validation": True,
        "coordinator_state_zero": True,
        "no_oracle_interface": True,
        "empty_slot": True,
        "single_export": True,
        "wrong_slot_request": True,
        "tampered_state": True,
        "full_bank_export": True,
        "source_destruction": True,
        "interruption_restart": True,
        "destination_loss_before_transfer": True,
        "replay": True,
    }
    assert payload["export_source_audit"]["status"] == "PASS"
    assert payload["export_source_audit"]["runtime_signature"] == ["source_state", "slot_id"]
    assert payload["export_source_audit"]["source_signature"] == ["source_state", "slot_id"]
    assert payload["characterization"]["full_bank_export"]["exact_state_copy"] is True
    assert payload["characterization"]["source_destruction"]["target_retains_all"] is True
    assert payload["characterization"]["interruption_restart"]["matches_uninterrupted"] is True
    assert all(row["failed_closed"] for row in payload["characterization"]["tampered_state"])
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64
