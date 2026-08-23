from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "sim" / "kc0" / "validate_bank.py"
BANK = ROOT / "sim" / "kc0" / "trial_bank.json"


def run_validator(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--bank", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_kc0_bank_passes_as_development_only() -> None:
    result = run_validator(BANK)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["trial_ids"] == [f"KC-0{letter}" for letter in "ABCDEFGHIJ"]
    assert payload["packet_count"] == 21
    assert payload["sequence_count"] == 24


def test_kc0_bank_has_no_candidate_or_scientific_authority() -> None:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    assert bank["candidate_present"] is False
    assert bank["scientific_authorization"] is False
    assert bank["scientific_execution"] == "FORBIDDEN"
    assert all(card["status"] == "SPEC_ONLY" for card in bank["trial_cards"])
    assert all(card["scientific_execution_authorized"] is False for card in bank["trial_cards"])


def test_kc0_validator_rejects_scientific_authority(tmp_path: Path) -> None:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    bank["scientific_authorization"] = True
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(bank), encoding="utf-8")
    result = run_validator(tampered)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert any("scientific_authorization" in error for error in payload["errors"])


def test_kc0_validator_rejects_unknown_fixture_reference(tmp_path: Path) -> None:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    bank["sequences"][0]["events"][0]["packet_id"] = "not-a-packet"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(bank), encoding="utf-8")
    result = run_validator(tampered)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert any("unknown packet" in error for error in payload["errors"])

