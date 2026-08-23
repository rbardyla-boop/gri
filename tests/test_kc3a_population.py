from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERIZE = ROOT / "sim" / "kc3a" / "characterize.py"


def test_kc3a_bounded_population_lifecycle_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc3a-population.json"
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
        "unit": "KC-3A-D",
        "verdict": "KC_3A_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["cell_source_sha256"] == "2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173"
    assert payload["export_source_sha256"] == "e52eeca7266584c7ee963a2a0d2b4ca8da2c63530dd6337a3fb7008bb76b4264"
    assert payload["child_creation_source_sha256"] == "f3fdf0d4ae6bda8d103549c22c20f7a8d4e53fcf7b54700b6aedc1198b900046"
    assert payload["fixture_bank_sha256"] == "0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5"
    assert all(payload["checks"].values())
    assert payload["resource_manifest"]["registry_fields"] == ["cell_id", "parent_id", "generation", "alive"]
    assert payload["resource_manifest"]["knowledge_state_in_registry"] is False
    assert payload["resource_manifest"]["max_population"] == 8
    assert payload["resource_manifest"]["max_generation"] == 3
    assert payload["characterization"]["population_cap"]["live_count_before_attempt"] == 8
    assert payload["characterization"]["generation_cap"]["max_generation"] == 3
    assert payload["characterization"]["knowledge_containment"]["no_live_state_payloads"] is True
    assert payload["manager_source_audit"]["registry_fields_exact"] is True
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert len(payload["canonical_receipt_sha256"]) == 64
