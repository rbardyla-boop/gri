from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "sim" / "kc0" / "dev_smoke.py"
BANK = ROOT / "sim" / "kc0" / "trial_bank.json"


def test_kc0_fixture_smoke_replays_without_a_candidate(tmp_path: Path) -> None:
    receipt = tmp_path / "kc0-smoke.json"
    result = subprocess.run(
        [sys.executable, str(SMOKE), "--bank", str(BANK), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary == {
        "mode": "DEV_SMOKE",
        "scientific_verdict": "FORBIDDEN",
        "status": "PASS",
        "trial_count": 10,
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["candidate_present"] is False
    assert payload["replay"]["matched"] is True
    assert len(payload["receipt_sha256"]) == 64
    assert all(trial["trial_id"].startswith("KC-0") for trial in payload["trials"])
