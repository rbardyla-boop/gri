from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc0" / "kc1c" / "characterize.py"


def test_kc1c_interference_characterization_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc1c-interference.json"
    result = subprocess.run(
        [sys.executable, str(CHARACTERIZE), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "matrix_row_count": 168,
        "scenario_count": 13,
        "status": "PASS",
        "unit": "KC-1C-D",
        "verdict": "KC_1C_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["candidate_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["checks"] == {
        "anchors": True,
        "matrix_complete": True,
        "replay": True,
        "restart": True,
        "sequence_length_constant": True,
    }
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64

