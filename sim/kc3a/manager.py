"""Deterministic bounded KC-3A population lifecycle manager."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import torch

from sim.kc0.kc1a.cell import KC1ACell
from sim.kc2d.spawn import spawn_child
from sim.runtime import canonical, tensor_digest


MAX_POPULATION = 8
MAX_GENERATION = 3
REGISTRY_FIELDS = ("cell_id", "parent_id", "generation", "alive")
SERIAL_SCHEMA = "KC-3A-D-POPULATION-1"


class PopulationManager:
    """In-memory lifecycle metadata plus physically owned KC-1A states."""

    def __init__(self) -> None:
        self._registry: list[dict[str, Any]] = []
        self._cells: dict[str, tuple[KC1ACell, torch.Tensor]] = {}

    def create_founder(self) -> str:
        if self._registry:
            raise ValueError("founder already exists")
        cell = KC1ACell()
        state = cell.initial_state(1, dtype=torch.int64, device=torch.device("cpu"))
        cell_id = "C0"
        self._registry.append({"cell_id": cell_id, "parent_id": None, "generation": 0, "alive": True})
        self._cells[cell_id] = (cell, state)
        return cell_id

    def _record(self, cell_id: str) -> dict[str, Any]:
        for record in self._registry:
            if record["cell_id"] == cell_id:
                return record
        raise KeyError(cell_id)

    def _live_record(self, cell_id: str) -> dict[str, Any]:
        record = self._record(cell_id)
        if not record["alive"] or cell_id not in self._cells:
            raise ValueError("cell is not alive")
        return record

    def live_ids(self) -> list[str]:
        return [record["cell_id"] for record in self._registry if record["alive"]]

    def registry_snapshot(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._registry]

    def state_snapshot(self, cell_id: str) -> torch.Tensor:
        self._live_record(cell_id)
        return self._cells[cell_id][1].detach().clone()

    def live_state_digests(self) -> dict[str, str]:
        return {cell_id: tensor_digest(self._cells[cell_id][1]) for cell_id in self.live_ids()}

    def consume(self, cell_id: str, token_id: int) -> None:
        self._live_record(cell_id)
        if isinstance(token_id, bool) or not isinstance(token_id, int) or not 0 <= token_id <= 65534:
            raise ValueError("token is invalid")
        cell, state = self._cells[cell_id]
        self._cells[cell_id] = (cell, cell.step(torch.tensor([token_id], dtype=torch.int64), state))

    def spawn(self, parent_id: str) -> str:
        parent_record = self._live_record(parent_id)
        if len(self.live_ids()) >= MAX_POPULATION:
            raise ValueError("population cap reached")
        if parent_record["generation"] >= MAX_GENERATION:
            raise ValueError("generation cap reached")

        parent_cell, parent_state = self._cells[parent_id]
        child_cell, child_state = spawn_child(parent_cell, parent_state)
        child_id = f"C{len(self._registry)}"
        self._cells[child_id] = (child_cell, child_state)
        self._registry.append({
            "cell_id": child_id,
            "parent_id": parent_id,
            "generation": parent_record["generation"] + 1,
            "alive": True,
        })
        return child_id

    def kill(self, cell_id: str) -> None:
        record = self._live_record(cell_id)
        record["alive"] = False
        del self._cells[cell_id]

    def serialize(self) -> bytes:
        live_states: dict[str, str] = {}
        for cell_id in self.live_ids():
            cell, state = self._cells[cell_id]
            payload = cell.serialize_state(state)
            live_states[cell_id] = base64.b64encode(payload).decode("ascii")
        document = {
            "schema": SERIAL_SCHEMA,
            "registry": self.registry_snapshot(),
            "live_states": live_states,
        }
        return canonical(document).encode("utf-8")

    @classmethod
    def restore(cls, payload: bytes) -> "PopulationManager":
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid population payload") from exc
        if set(document) != {"schema", "registry", "live_states"} or document["schema"] != SERIAL_SCHEMA:
            raise ValueError("unsupported population payload")
        registry = document["registry"]
        live_states = document["live_states"]
        if not isinstance(registry, list) or not isinstance(live_states, dict):
            raise ValueError("population payload sections are invalid")
        if len(registry) > MAX_POPULATION + MAX_GENERATION * MAX_POPULATION:
            raise ValueError("population registry is oversized")

        manager = cls()
        ids: set[str] = set()
        for index, record in enumerate(registry):
            if not isinstance(record, dict) or set(record) != set(REGISTRY_FIELDS):
                raise ValueError("registry contains non-lifecycle fields")
            cell_id = record["cell_id"]
            parent_id = record["parent_id"]
            generation = record["generation"]
            alive = record["alive"]
            if cell_id != f"C{index}" or cell_id in ids:
                raise ValueError("registry cell ids are not canonical")
            if parent_id is not None and not isinstance(parent_id, str):
                raise ValueError("registry parent id is invalid")
            if not isinstance(generation, int) or isinstance(generation, bool) or not 0 <= generation <= MAX_GENERATION:
                raise ValueError("registry generation is invalid")
            if not isinstance(alive, bool):
                raise ValueError("registry alive flag is invalid")
            ids.add(cell_id)
            manager._registry.append(dict(record))

        roots = [record for record in manager._registry if record["parent_id"] is None]
        if len(roots) > 1 or (roots and (roots[0]["generation"] != 0 or roots[0]["cell_id"] != "C0")):
            raise ValueError("population roots are invalid")
        for record in manager._registry:
            parent_id = record["parent_id"]
            if parent_id is not None:
                if parent_id not in ids:
                    raise ValueError("registry parent is missing")
                parent = manager._record(parent_id)
                if record["generation"] != parent["generation"] + 1:
                    raise ValueError("registry generation lineage is invalid")
        live_ids = {record["cell_id"] for record in manager._registry if record["alive"]}
        if len(live_ids) > MAX_POPULATION or set(live_states) != live_ids:
            raise ValueError("live-state set does not match registry")
        for cell_id in sorted(live_ids):
            encoded = live_states[cell_id]
            if not isinstance(encoded, str):
                raise ValueError("live state encoding is invalid")
            try:
                state_payload = base64.b64decode(encoded.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError) as exc:
                raise ValueError("live state payload is invalid") from exc
            cell = KC1ACell()
            state = cell.restore_state(state_payload, dtype=torch.int64, device=torch.device("cpu"))
            manager._cells[cell_id] = (cell, state)
        return manager

    def population_digest(self) -> str:
        document = {
            "registry": self.registry_snapshot(),
            "live_states": self.live_state_digests(),
        }
        return hashlib.sha256(canonical(document).encode("utf-8")).hexdigest()

    def resource_manifest(self) -> dict[str, object]:
        return resource_manifest()


def resource_manifest() -> dict[str, object]:
    return {
        "registry_fields": list(REGISTRY_FIELDS),
        "knowledge_state_in_registry": False,
        "max_population": MAX_POPULATION,
        "max_generation": MAX_GENERATION,
        "automatic_spawn_calls": 0,
        "external_infrastructure": False,
        "uses_fitness": False,
        "uses_selection": False,
        "uses_mutation_at_birth": False,
    }
