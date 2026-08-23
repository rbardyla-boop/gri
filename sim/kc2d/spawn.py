"""Stateless bounded child creation for one unchanged KC-1A parent."""
from __future__ import annotations

import torch

from sim.kc0.kc1a.cell import KC1ACell, SLOT_COUNT
from sim.kc2b.export import deliver_export, export_slot


def spawn_child(parent_cell: KC1ACell, parent_state: torch.Tensor) -> tuple[KC1ACell, torch.Tensor]:
    """Create exactly one fresh child after fully validating parent state."""
    if not isinstance(parent_cell, KC1ACell):
        raise ValueError("parent cell is not KC-1A")
    payloads = [export_slot(parent_state, slot_id) for slot_id in range(SLOT_COUNT)]
    child_cell = KC1ACell()
    child_state = child_cell.initial_state(1, dtype=torch.int64, device=parent_state.device)
    for payload in payloads:
        if payload is not None:
            child_state = deliver_export(child_cell, child_state, payload)
    return child_cell, child_state


def resource_manifest() -> dict[str, object]:
    return {
        "coordinator_state_bytes": 0,
        "coordinator_persistent_fields": [],
        "children_created_per_call": 1,
        "automatic_spawn_calls": 0,
        "population_registry": False,
        "uses_filesystem": False,
        "uses_network": False,
        "uses_threads": False,
        "uses_processes": False,
        "uses_timers": False,
        "uses_scheduler": False,
        "uses_replication": False,
    }
