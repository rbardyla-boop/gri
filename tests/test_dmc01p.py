from __future__ import annotations

import torch

from dmc00.benchmark import VALUES
from dmc01.memory import (
    DMC01Controller,
    ExactEpisodicLedger,
    HIDDEN_DIM,
    MemoryRecord,
    build_paired_controllers,
    build_shuffle_mapping,
    encode_event,
    memory_record_field_names,
    state_dict_equal,
    trainable_parameter_count,
)


WRITE_RED = {"kind": "write", "memory_id": "m-0", "entity": "entity-00", "field": "value", "value": "RED"}
WRITE_BLUE = {"kind": "write", "memory_id": "m-1", "entity": "entity-00", "field": "value", "value": "BLUE"}
QUERY_CURRENT = {"kind": "query", "entity": "entity-00", "field": "value", "mode": "current", "as_of_episode": None}
QUERY_HISTORY = {"kind": "query", "entity": "entity-00", "field": "value", "mode": "history", "as_of_episode": 0}


def test_exact_ledger_is_zero_parameter_append_only_and_preserves_history():
    ledger = ExactEpisodicLedger()
    assert ledger.trainable_parameter_count == 0
    first = ledger.append(memory_id="m-0", entity="entity-00", field="value", creation_episode=0, hidden_value=torch.zeros(HIDDEN_DIM))
    second = ledger.append(memory_id="m-1", entity="entity-00", field="value", creation_episode=20, hidden_value=torch.ones(HIDDEN_DIM))
    assert ledger.retrieve(entity="entity-00", mode="current", as_of_episode=None) is second
    assert ledger.retrieve(entity="entity-00", mode="history", as_of_episode=0) is first
    assert second.supersedes == first.memory_id
    assert len(ledger.entries("entity-00")) == 2


def test_memory_record_has_hidden_state_but_no_symbolic_answer():
    names = set(memory_record_field_names())
    assert names == {"memory_id", "entity", "field", "creation_episode", "supersedes", "source_episode", "hidden_value"}
    assert not {"answer", "label", "value", "oracle_result"} & names
    assert "Tensor" in str(MemoryRecord.__annotations__["hidden_value"])


def test_paired_models_are_tensor_identical_and_parameter_matched():
    exact, no_memory = build_paired_controllers(9091)
    assert trainable_parameter_count(exact) == 30_912
    assert trainable_parameter_count(no_memory) == 30_912
    assert state_dict_equal(exact, no_memory)
    assert type(exact.processor) is type(no_memory.processor)
    assert exact.ledger is not None
    assert no_memory.ledger is None


def test_write_representation_is_hidden_and_query_has_no_value_channel():
    exact, no_memory = build_paired_controllers(9091)
    graph = encode_event(WRITE_RED)
    assert graph.edges[0, 1, VALUES.index("RED")] == 1
    assert encode_event(QUERY_CURRENT).edges.sum() == 0
    record = exact.process_write(WRITE_RED, 0)
    assert record is not None
    assert record.hidden_value.shape == (HIDDEN_DIM,)
    assert exact.answer_query(QUERY_CURRENT).shape == (len(VALUES),)
    assert no_memory.answer_query(QUERY_CURRENT).shape == (len(VALUES),)


def test_no_memory_does_not_retain_prior_write_and_exact_history_is_addressed():
    exact, no_memory = build_paired_controllers(9091)
    exact.process_write(WRITE_RED, 0)
    exact.process_write(WRITE_BLUE, 20)
    assert exact.ledger is not None
    assert torch.equal(exact.ledger.retrieve(entity="entity-00", mode="history", as_of_episode=0).hidden_value, exact.ledger.entries("entity-00")[0].hidden_value)
    assert no_memory.process_write(WRITE_RED, 0) is None
    assert no_memory.ledger is None
    no_memory.reset_case()
    exact.reset_case()
    assert exact.ledger is not None and exact.ledger.all_entries() == ()


def test_shuffle_mapping_is_deterministic_same_condition_and_nonidentity():
    cases = [{"case_id": f"case-{i}", "family": "delayed_recall", "condition": "delay_1"} for i in range(16)]
    first = build_shuffle_mapping(cases)
    second = build_shuffle_mapping(cases)
    assert first == second
    assert set(first) == {case["case_id"] for case in cases}
    assert all(left != right for left, right in first.items())
