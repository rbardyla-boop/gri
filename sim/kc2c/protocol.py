"""Stateless cooperative overflow protocol for two unchanged KC-1A cells."""
from __future__ import annotations

import torch

from sim.kc0.kc1a.cell import KC1ACell, SLOT_COUNT
from sim.kc2b.export import deliver_export, export_slot


def _validate_state(state: torch.Tensor) -> None:
    for slot_id in range(SLOT_COUNT):
        export_slot(state, slot_id)


def cooperative_step(
    incoming_token: int,
    cell_a: KC1ACell,
    state_a: torch.Tensor,
    cell_b: KC1ACell,
    state_b: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Process one incoming token using only the two current cell states."""
    if isinstance(incoming_token, bool) or not isinstance(incoming_token, int) or not 0 <= incoming_token <= 65534:
        raise ValueError("incoming token is invalid")
    _validate_state(state_a)
    _validate_state(state_b)

    slot_id = incoming_token % SLOT_COUNT
    displaced = export_slot(state_a, slot_id)
    if displaced is not None and displaced != incoming_token:
        state_b = deliver_export(cell_b, state_b, displaced)
    state_a = cell_a.step(torch.tensor([incoming_token], dtype=torch.int64), state_a)
    return state_a, state_b


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
