from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc2a" / "characterize.py"


def test_kc2a_transfer_characterization_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc2a-transfer.json"
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
        "unit": "KC-2A-D",
        "verdict": "KC_2A_DEV_COMPLETE",
    }

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["cell_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["fixture_bank_sha256"] == "0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5"
    assert payload["checks"] == {
        "anchors": True,
        "bank_validation": True,
        "coordinator_state_zero": True,
        "transfer_source_audit": True,
        "isolation": True,
        "explicit_transfer": True,
        "duplicate_delivery": True,
        "collision_delivery": True,
        "restart_during_transfer": True,
        "distributed_capacity": True,
        "source_loss_survival": True,
        "destination_loss_before_transfer": True,
        "replay": True,
    }
    assert payload["coordinator_resource"] == {
        "coordinator_state_bytes": 0,
        "coordinator_persistent_fields": [],
        "transfer_payload_persistent": False,
        "uses_packet_history": False,
        "uses_shadow_slot_table": False,
        "uses_global_memory": False,
        "uses_population_logic": False,
        "uses_replication": False,
    }
    assert payload["transfer_source_audit"] == {
        "class_count": 0,
        "forbidden_names": [],
        "global_statement_count": 0,
        "status": "PASS",
    }
    assert payload["characterization"]["distributed_capacity"]["pair_current"] == 16
    assert payload["characterization"]["source_loss_survival"]["target_survives"] is True
    assert payload["characterization"]["destination_loss_before_transfer"]["replacement_target_receives"] is True
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64
