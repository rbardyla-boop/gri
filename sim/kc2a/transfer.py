"""Stateless explicit transfer adapter for two unchanged KC-1A cells."""
from __future__ import annotations

import torch

from sim.kc0.kc1a.cell import KC1ACell


def source_contains(state: torch.Tensor, token_id: int) -> bool:
    """Check a source state without creating coordinator storage."""
    slot = int(token_id) % 8
    expected = int(token_id) % 65535 + 1
    value = state.detach().cpu().to(torch.int64)
    return bool(value[0, slot] == expected and value[0, 8 + slot] == 1)


def prepare_transfer(source_state: torch.Tensor, token_id: int) -> int:
    """Return a transient packet token only when the source contains it."""
    if not source_contains(source_state, token_id):
        raise ValueError("source does not contain requested packet")
    return int(token_id)


def deliver_transfer(destination_cell: KC1ACell, destination_state: torch.Tensor, payload: int) -> torch.Tensor:
    """Deliver one transient token; no payload is retained by this adapter."""
    return destination_cell.step(torch.tensor([int(payload)], dtype=torch.int64), destination_state)


def resource_manifest() -> dict[str, object]:
    return {
        "coordinator_state_bytes": 0,
        "coordinator_persistent_fields": [],
        "transfer_payload_persistent": False,
        "uses_packet_history": False,
        "uses_shadow_slot_table": False,
        "uses_global_memory": False,
        "uses_population_logic": False,
        "uses_replication": False,
    }

