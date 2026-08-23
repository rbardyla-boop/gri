from __future__ import annotations

import json
from pathlib import Path

import torch

from sim.kc0.kc1a.audit import audit_source
from sim.kc0.kc1a.cell import KC1ACell


ROOT = Path(__file__).resolve().parents[1]
CELL = ROOT / "sim" / "kc0" / "kc1a" / "cell.py"
MANIFEST = ROOT / "sim" / "kc0" / "kc1a" / "manifest.json"


def test_kc1a_resource_manifest_and_source_audit_pass() -> None:
    audit = audit_source(CELL, MANIFEST)
    assert audit["status"] == "PASS"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["scientific_execution"] == "FORBIDDEN"
    assert manifest["state"]["has_step_counter"] is False
    assert manifest["state"]["has_population_logic"] is False


def test_kc1a_cold_start_and_step_are_deterministic() -> None:
    cell = KC1ACell()
    first = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    second = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    assert torch.equal(first, second)
    assert torch.equal(cell.step(torch.tensor([3]), first), cell.step(torch.tensor([3]), second))


def test_kc1a_serialization_is_canonical_and_exact() -> None:
    cell = KC1ACell()
    state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
    state = cell.step(torch.tensor([17]), state)
    payload_a = cell.serialize_state(state)
    payload_b = cell.serialize_state(state.clone())
    restored = cell.restore_state(payload_a, dtype=torch.int64, device=torch.device("cpu"))
    assert payload_a == payload_b
    assert torch.equal(state, restored)
    assert len(payload_a) == 137
