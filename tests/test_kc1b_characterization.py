from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc0" / "kc1b" / "characterize.py"


def test_kc1b_development_characterization_is_replayable_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc1b-characterization.json"
    result = subprocess.run(
        [sys.executable, str(CHARACTERIZE), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "row_count": 36,
        "status": "PASS",
        "unit": "KC-1B-D",
        "verdict": "KC_1B_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["candidate_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["restart_pass"] is True
    assert payload["replay_pass"] is True
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert {row["distractor_set"] for row in payload["characterization"]} == {"standard", "altered"}
    assert {row["condition"] for row in payload["characterization"]} == {"correct_packet", "no_packet", "wrong_packet"}
    assert len(payload["canonical_receipt_sha256"]) == 64
