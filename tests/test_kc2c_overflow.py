from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc2c" / "characterize.py"


def test_kc2c_cooperative_overflow_characterization_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc2c-overflow.json"
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
        "unit": "KC-2C-D",
        "verdict": "KC_2C_DEV_COMPLETE",
    }

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["cell_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["export_source_sha256"] == "e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264"
    assert payload["fixture_bank_sha256"] == "0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5"
    assert all(payload["checks"].values())
    assert payload["characterization"]["collision_stream_16"]["pair_current"] == 16
    assert payload["characterization"]["seventeenth_packet_saturation"]["pair_current"] == 16
    assert payload["characterization"]["concentrated_collision_recency"]["oldest_lost"] is True
    assert payload["characterization"]["loss_of_a"]["b_retains_displaced_wave"] is True
    assert payload["characterization"]["loss_of_b"]["a_retains_newest_wave"] is True
    assert payload["protocol_source_audit"]["runtime_signature"] == ["incoming_token", "cell_a", "state_a", "cell_b", "state_b"]
    assert payload["protocol_source_audit"]["source_signature"] == ["incoming_token", "cell_a", "state_a", "cell_b", "state_b"]
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64
