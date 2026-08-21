from __future__ import annotations

import inspect
import json
from pathlib import Path

import torch

from dmc02a.benchmark import VALUES
from dmc01.memory import trainable_parameter_count as dmc01_parameter_count
from dmc02p.controller import (
    CAPACITY,
    DMC02PController,
    ExactRetention16Controller,
    ExactRetentionPolicy,
    FIFO16Controller,
    MemoryRecord,
    Random16Controller,
    build_processor,
    load_dmc01_checkpoint,
    memory_record_field_names,
    retention_metadata_field_names,
)


ROOT = Path(__file__).resolve().parents[1]


def write_event(index: int, entity: str, *, value: str = "RED", salience: str | None = None, supersedes: str | None = None) -> dict:
    return {
        "kind": "write",
        "memory_id": f"test-memory-{index}",
        "entity": entity,
        "field": "value",
        "value": value,
        "salience": salience,
        "supersedes": supersedes,
    }


def scope(kind: str, entities: list[str]) -> dict:
    return {"kind": kind, "entities": entities}


def query(entity: str, mode: str = "current", as_of_episode: int | None = None) -> dict:
    return {"kind": "query", "entity": entity, "field": "value", "mode": mode, "as_of_episode": as_of_episode}


def test_memory_schema_and_policy_firewall_are_metadata_only():
    forbidden = {"value", "answer", "query", "case_id", "future_event", "oracle_answer"}
    assert not forbidden.intersection(memory_record_field_names())
    assert not forbidden.intersection(retention_metadata_field_names())
    assert list(inspect.signature(ExactRetentionPolicy.admits).parameters) == ["self", "metadata"]
    assert DMC02PController.trainable_memory_parameter_count.fget is not None


def test_exact_retention_has_a_hard_sixteen_record_invariant():
    controller = ExactRetention16Controller(build_processor(), family="mission_set", case_id="capacity-test")
    mission = [f"mission-{index}" for index in range(16)]
    controller.process_scope_event(scope("mission_set", mission))
    with torch.no_grad():
        for index, entity in enumerate(mission):
            controller.process_write(write_event(index, entity, value=VALUES[index % len(VALUES)]), index + 1)
        for index in range(16, 40):
            controller.process_write(write_event(index, f"distractor-{index}"), index + 1)
    assert len(controller.ledger) == CAPACITY
    assert not hasattr(controller, "archive")
    assert not hasattr(controller, "overflow")
    assert controller.trainable_memory_parameter_count == 0


def test_exact_supersession_retains_current_and_history_without_overwrite():
    controller = ExactRetention16Controller(build_processor(), family="supersession", case_id="supersession-test")
    entities = [f"entity-{index}" for index in range(8)]
    controller.process_scope_event(scope("mission_set", entities))
    with torch.no_grad():
        ordinal = 0
        original_ids = {}
        for entity in entities:
            original = write_event(ordinal, entity, value="RED")
            original_ids[entity] = original["memory_id"]
            record = controller.make_record(original, ordinal + 1, hidden_value=torch.full((49,), float(ordinal)))
            assert controller.retain_record(record)
            ordinal += 1
            current = write_event(ordinal, entity, value="BLUE", supersedes=original_ids[entity])
            record = controller.make_record(current, ordinal + 1, hidden_value=torch.full((49,), float(ordinal)))
            assert controller.retain_record(record)
            ordinal += 1
    assert len(controller.ledger) == 16
    history = controller.retrieve(query(entities[0], mode="history", as_of_episode=1))
    current = controller.retrieve(query(entities[0], mode="current"))
    assert history.memory_id == original_ids[entities[0]]
    assert current.memory_id != history.memory_id
    assert current.supersedes == history.memory_id


def test_utility_change_evicts_only_after_explicit_update():
    controller = ExactRetention16Controller(build_processor(), family="utility_change", case_id="utility-test")
    phase_a = [f"a-{index}" for index in range(16)]
    phase_b = phase_a[:8] + [f"b-{index}" for index in range(8)]
    controller.process_scope_event(scope("mission_set", phase_a))
    for index, entity in enumerate(phase_a):
        controller.retain_record(controller.make_record(write_event(index, entity), index + 1, hidden_value=torch.zeros(49)))
    assert {record.entity for record in controller.ledger.records()} == set(phase_a)
    controller.process_scope_event(scope("mission_update", phase_b))
    assert {record.entity for record in controller.ledger.records()} == set(phase_a[:8])
    for index, entity in enumerate(phase_b, start=100):
        controller.retain_record(controller.make_record(write_event(index, entity, value="BLUE"), index + 1, hidden_value=torch.ones(49)))
    assert len(controller.ledger) == 16
    assert {record.entity for record in controller.ledger.records()} == set(phase_b)


def test_fifo_and_random_are_zero_parameter_deterministic_controls():
    processors = [build_processor() for _ in range(3)]
    reference = {key: value.clone() for key, value in processors[0].state_dict().items()}
    for processor in processors[1:]:
        processor.load_state_dict(reference)
    fifo = FIFO16Controller(processors[0], family="distractor_flood", case_id="control")
    random_a = Random16Controller(processors[1], family="distractor_flood", case_id="control")
    random_b = Random16Controller(processors[2], family="distractor_flood", case_id="control")
    for index in range(32):
        record = fifo.make_record(write_event(index, f"entity-{index}"), index, hidden_value=torch.full((49,), float(index)))
        fifo.retain_record(record)
        record_a = random_a.make_record(write_event(index, f"entity-{index}"), index, hidden_value=torch.full((49,), float(index)))
        record_b = random_b.make_record(write_event(index, f"entity-{index}"), index, hidden_value=torch.full((49,), float(index)))
        random_a.retain_record(record_a)
        random_b.retain_record(record_b)
    assert len(fifo.ledger) == len(random_a.ledger) == len(random_b.ledger) == 16
    assert [r.memory_id for r in random_a.ledger.records()] == [r.memory_id for r in random_b.ledger.records()]
    assert [r.memory_id for r in fifo.ledger.records()] == [f"test-memory-{index}" for index in range(16, 32)]
    assert all(controller.trainable_memory_parameter_count == 0 for controller in (fifo, random_a, random_b))


def test_hidden_vector_identity_and_dmc01_checkpoint_compatibility():
    checkpoint_path = ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
    controller, payload = load_dmc01_checkpoint(checkpoint_path, family="mission_set", mode="exact16", case_id="identity-test")
    case = json.loads((ROOT / "artifacts/dmc02a/datasets/train.jsonl").read_text().splitlines()[0])
    controller.process_scope_event(case["episodes"][0]["events"][0])
    event = next(episode["events"][0] for episode in case["episodes"] if episode["events"][0]["kind"] == "write")
    hidden_before = controller.encode_hidden(event)
    record = controller.make_record(event, 1, hidden_value=hidden_before)
    controller.retain_record(record)
    hidden_after = controller.ledger.records()[0].hidden_value
    assert torch.equal(hidden_before, hidden_after)
    assert hidden_before.data_ptr() == hidden_after.data_ptr()
    assert hidden_after.shape == (49,)
    assert dmc01_parameter_count(controller.processor) == 30_912
    assert controller.trainable_memory_parameter_count == 0
