"""Stateless, explicitly invoked whole-population tick over KC-3C."""
from __future__ import annotations

from sim.kc0.kc1a.cell import SLOT_COUNT
from sim.kc2b.export import export_slot
from sim.kc3a.manager import MAX_POPULATION, PopulationManager, REGISTRY_FIELDS
from sim.kc3c.activate import activate_cell


MAX_ACTIVATIONS_PER_TICK = MAX_POPULATION
MAX_SLOT_CONTACTS_PER_TICK = 2 * (MAX_POPULATION - 1) * SLOT_COUNT


def _start_schedule(population: PopulationManager) -> list[str]:
    records = population.registry_snapshot()
    live_ids: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if set(record) != set(REGISTRY_FIELDS):
            raise ValueError("lifecycle metadata is invalid")
        cell_id = record["cell_id"]
        if cell_id != f"C{index}" or cell_id in seen:
            raise ValueError("lifecycle registry order is invalid")
        if not isinstance(record["alive"], bool):
            raise ValueError("lifecycle alive flag is invalid")
        seen.add(cell_id)
        if record["alive"]:
            live_ids.append(cell_id)
    if len(live_ids) > MAX_ACTIVATIONS_PER_TICK:
        raise ValueError("live population exceeds tick activation bound")
    return live_ids


def _prevalidate_states(population: PopulationManager, live_ids: list[str]) -> None:
    for cell_id in live_ids:
        state = population.state_snapshot(cell_id)
        for slot_id in range(SLOT_COUNT):
            export_slot(state, slot_id)


def population_tick(population: PopulationManager) -> dict[str, object]:
    """Activate each start-of-tick live cell once in registry order."""
    live_ids = _start_schedule(population)
    _prevalidate_states(population, live_ids)

    activations: list[dict[str, object]] = []
    contact_count = 0
    delivery_count = 0
    for cell_id in live_ids:
        activation = activate_cell(population, cell_id)
        activations.append(activation)
        contact_count += int(activation["contact_count"])
        delivery_count += int(activation["delivery_count"])

    if contact_count > MAX_SLOT_CONTACTS_PER_TICK:
        raise RuntimeError("tick exceeded slot-contact bound")
    return {
        "activation_order": list(live_ids),
        "live_ids_at_tick_start": list(live_ids),
        "activation_count": len(activations),
        "contact_count": contact_count,
        "delivery_count": delivery_count,
        "activations": activations,
    }


def resource_manifest() -> dict[str, object]:
    return {
        "scheduler_state_bytes": 0,
        "persistent_scheduler_fields": [],
        "automatic_ticks": 0,
        "background_execution": False,
        "creates_children": False,
        "kills_cells": False,
        "registry_mutation": False,
        "max_activations_per_tick": MAX_ACTIVATIONS_PER_TICK,
        "max_slot_contacts_per_tick": MAX_SLOT_CONTACTS_PER_TICK,
    }

