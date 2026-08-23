from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "sim" / "kc0" / "kc1a" / "lifecycle.py"


def test_kc1a_lifecycle_mount_passes_without_scientific_verdict(tmp_path: Path) -> None:
    receipt = tmp_path / "kc1a-lifecycle.json"
    result = subprocess.run(
        [sys.executable, str(LIFECYCLE), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "sequence_count": 24,
        "status": "PASS",
        "unit": "KC-1A-LIFECYCLE",
        "verdict": "KC_1A_LIFECYCLE_PASS",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert all(payload["checks"].values())
    assert payload["scientific_execution"] == "FORBIDDEN"
    assert payload["scientific_verdicts"] == ["ADVANTAGE", "NO_ADVANTAGE", "LEARNED", "GENERALIZED", "REPLICATED"]
    assert len(payload["receipt_sha256"]) == 64

