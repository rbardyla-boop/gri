from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALIFY = ROOT / "sim" / "qualify.py"


def test_simulator_qualification_is_pass_without_scientific_verdict(tmp_path: Path) -> None:
    receipt = tmp_path / "qualification.json"
    result = subprocess.run(
        [sys.executable, str(QUALIFY), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "scientific_verdict": "FORBIDDEN",
        "status": "PASS",
        "unit": "GRI-SIM-0-QUALIFICATION",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert all(payload["checks"].values())
    assert payload["candidate_present"] is False
    assert payload["scientific_execution"] == "FORBIDDEN"
    assert len(payload["receipt_sha256"]) == 64
