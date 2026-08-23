"""Stateless KC-1A state export adapter for KC-2B-D."""
from __future__ import annotations

import torch

from sim.kc0.kc1a.cell import KC1ACell, STATE_WIDTH, SLOT_COUNT


EMPTY = None


def export_slot(source_state: torch.Tensor, slot_id: int) -> int | None:
    """Derive one transient packet from a physical slot, or return EMPTY."""
    if isinstance(slot_id, bool) or not isinstance(slot_id, int) or not 0 <= slot_id < SLOT_COUNT:
        raise ValueError("slot_id must be an integer in the physical slot range")
    if source_state.ndim != 2 or source_state.shape != (1, STATE_WIDTH) or source_state.dtype != torch.int64:
        raise ValueError("source state does not match KC-1A")

    value = source_state.detach().cpu()
    stored_value = int(value[0, slot_id])
    occupied = int(value[0, SLOT_COUNT + slot_id])
    if occupied not in (0, 1):
        raise ValueError("occupancy bit is invalid")
    if occupied == 0:
        if stored_value != 0:
            raise ValueError("empty slot contains a nonzero value")
        return EMPTY
    if not 1 <= stored_value <= 65535:
        raise ValueError("occupied slot contains an invalid value")

    derived = stored_value - 1
    if derived % SLOT_COUNT != slot_id:
        raise ValueError("occupied slot value is inconsistent with its physical slot")
    return derived


def deliver_export(destination_cell: KC1ACell, destination_state: torch.Tensor, payload: int) -> torch.Tensor:
    """Deliver one transient export payload without retaining adapter state."""
    if isinstance(payload, bool) or not isinstance(payload, int) or not 0 <= payload <= 65534:
        raise ValueError("export payload is invalid")
    return destination_cell.step(torch.tensor([payload], dtype=torch.int64), destination_state)


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
