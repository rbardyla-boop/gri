"""Stateless local contact selection over frozen KC-3A lifecycle metadata."""
from __future__ import annotations

from sim.kc2b.export import export_slot
from sim.kc3a.manager import PopulationManager, REGISTRY_FIELDS
from sim.kc3b.share import share_slot


def _live_neighbors(population: PopulationManager, source_id: str) -> list[str]:
    records = population.registry_snapshot()
    source = next((record for record in records if record["cell_id"] == source_id), None)
    if source is None or not source["alive"]:
        raise ValueError("source cell is not alive")
    if set(source) != set(REGISTRY_FIELDS):
        raise ValueError("lifecycle metadata is invalid")
    parent_id = source["parent_id"]
    neighbors = {
        record["cell_id"]
        for record in records
        if record["alive"] and (
            record["cell_id"] == parent_id or record["parent_id"] == source_id
        )
    }
    neighbors.discard(source_id)
    return sorted(neighbors)


def activate_cell(population: PopulationManager, source_id: str) -> dict[str, object]:
    """Share every occupied source slot with live lifecycle neighbors."""
    source_state = population.state_snapshot(source_id)
    occupied_slots = [
        slot_id
        for slot_id in range(8)
        if export_slot(source_state, slot_id) is not None
    ]
    neighbors = _live_neighbors(population, source_id)
    deliveries = 0
    for target_id in neighbors:
        for slot_id in occupied_slots:
            deliveries += int(share_slot(population, source_id, target_id, slot_id))
    return {
        "source_id": source_id,
        "neighbor_ids": neighbors,
        "occupied_slot_count": len(occupied_slots),
        "contact_count": len(neighbors) * len(occupied_slots),
        "delivery_count": deliveries,
    }


def resource_manifest() -> dict[str, object]:
    return {
        "policy_state_bytes": 0,
        "persistent_policy_fields": [],
        "automatic_activation": 0,
        "automatic_contacts": 0,
        "creates_children": False,
        "target_state_policy_inspection": False,
        "knowledge_map": False,
        "registry_mutation": False,
    }
