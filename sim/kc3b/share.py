"""Stateless explicit slot sharing over the frozen KC-3A manager."""
from __future__ import annotations

from sim.kc2b.export import export_slot
from sim.kc3a.manager import PopulationManager


def _validate_state(state: object) -> None:
    for slot_id in range(8):
        export_slot(state, slot_id)


def share_slot(population: PopulationManager, source_id: str, target_id: str, slot_id: int) -> bool:
    """Copy one source slot to a live target without exposing its packet."""
    if source_id == target_id:
        raise ValueError("source and target must be different live cells")
    source_state = population.state_snapshot(source_id)
    target_state = population.state_snapshot(target_id)
    _validate_state(source_state)
    _validate_state(target_state)
    payload = export_slot(source_state, slot_id)
    if payload is None:
        return False
    population.consume(target_id, payload)
    return True


def resource_manifest() -> dict[str, object]:
    return {
        "coordinator_state_bytes": 0,
        "persistent_coordinator_fields": [],
        "transfer_payload_persistent": False,
        "automatic_contacts": 0,
        "creates_children": False,
        "knowledge_map": False,
        "registry_mutation": False,
    }
