from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc0" / "kc1d" / "characterize.py"


def test_kc1d_capacity_characterization_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc1d-capacity.json"
    result = subprocess.run(
        [sys.executable, str(CHARACTERIZE), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "load_count": 12,
        "status": "PASS",
        "unit": "KC-1D-D",
        "verdict": "KC_1D_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["candidate_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["checks"] == {
        "anchors": True,
        "load_bank_complete": True,
        "replay": True,
        "restart": True,
    }
    loads = payload["characterization"]["loads"]
    assert [row["load"] for row in loads] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16]
    assert [row["result"]["uninterrupted"]["recoverable_current_values"] for row in loads[:8]] == list(range(1, 9))
    assert all(row["result"]["uninterrupted"]["recoverable_current_values"] == 8 for row in loads[8:])
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64

