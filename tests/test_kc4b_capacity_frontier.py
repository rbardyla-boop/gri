from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "sim" / "kc4b" / "benchmark.py"


def test_kc4b_capacity_frontier_is_complete_and_non_scientific(tmp_path: Path) -> None:
    receipt = tmp_path / "kc4b-frontier.json"
    result = subprocess.run(
        [sys.executable, str(BENCHMARK), "--receipt", str(receipt)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "PASS",
        "unit": "KC-4B-D",
        "verdict": "KC_4B_DEV_COMPLETE",
    }
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert all(payload["checks"].values())
    assert payload["budget"] == {"logical_slots": 64, "declared_state_bytes": 1024, "kc_cells": 8, "slots_per_cell": 8}
    assert payload["redundancy_levels"] == [1, 2, 4, 8]
    assert payload["horizon_ticks"] == 4
    assert payload["scientific_thresholds"] == "UNDEFINED_IN_DEVELOPMENT"
    assert payload["scientific_verdict"] == "FORBIDDEN"
    assert payload["advantage_claim"] == "NOT_COMPUTED"
    assert payload["source_audit"]["while_loop_count"] == 0
    assert payload["source_audit"]["async_function_count"] == 0
    assert payload["source_audit"]["execution_mutation_calls"] == []
    assert payload["characterization"]["case_count"] == 68
    expected = {"1": (64, 1), "2": (32, 2), "4": (16, 4), "8": (8, 8)}
    for level, (identities, copies) in expected.items():
        snapshot = payload["characterization"]["frontier_t0"][level]["kc"]
        assert snapshot["recovered_packet_count"] == identities
        assert set(snapshot["copies_per_packet"].values()) == {copies}
        assert payload["characterization"]["frontier_t0"][level]["baseline"]["recovered_packet_count"] == identities
    assert len(payload["canonical_receipt_sha256"]) == 64
