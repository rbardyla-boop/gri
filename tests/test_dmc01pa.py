from __future__ import annotations

import inspect
import random

import numpy as np
import pytest
import torch
import torch.nn.functional as F

from dmc01.memory import HIDDEN_DIM, build_paired_controllers
from dmc01.training import (
    FROZEN_TRAINING_CONFIG,
    case_cross_entropy,
    case_batches,
    checkpoint_payload,
    complete_case_batch_loss,
    order_key,
    ordered_cases,
    run_case_logits,
    target_for_case,
    train_complete_case_batch,
)


def _case(value: str = "RED", case_id: str = "structural-0") -> dict:
    return {
        "case_id": case_id,
        "episodes": [
            {"index": 0, "events": [{"kind": "write", "memory_id": f"{case_id}-write", "entity": "entity-00", "field": "value", "value": value}]},
            {"index": 1, "events": [{"kind": "query", "entity": "entity-00", "field": "value", "mode": "current", "as_of_episode": None}]},
        ],
        "answer": value,
    }


def test_loss_is_exact_arithmetic_mean_of_case_cross_entropies():
    logits = [torch.tensor([float(index) for index in range(8)]), torch.tensor([float(7 - index) for index in range(8)])]
    targets = [2, 5]
    expected = torch.stack([F.cross_entropy(logit.unsqueeze(0), torch.tensor([target]), reduction="mean") for logit, target in zip(logits, targets)]).mean()
    actual = torch.stack([case_cross_entropy(logit, target) for logit, target in zip(logits, targets)]).mean()
    assert torch.equal(actual, expected)
    assert FROZEN_TRAINING_CONFIG.batch_size == 16


def test_ordering_is_stateless_reproducible_and_seed_epoch_sensitive():
    cases = [_case(case_id=f"case-{index:02d}") for index in range(32)]
    first = [case["case_id"] for case in ordered_cases(cases, seed=1337, epoch=0)]
    second = [case["case_id"] for case in ordered_cases(cases, seed=1337, epoch=0)]
    changed_seed = [case["case_id"] for case in ordered_cases(cases, seed=1338, epoch=0)]
    changed_epoch = [case["case_id"] for case in ordered_cases(cases, seed=1337, epoch=1)]
    assert first == second
    assert first != changed_seed
    assert first != changed_epoch
    assert order_key(1337, 0, "case-00") != order_key(1338, 0, "case-00")
    batches = list(case_batches(cases, seed=1337, epoch=0))
    assert [len(batch) for batch in batches] == [16, 16]


def test_exact_and_no_memory_receive_identical_paired_ordering():
    cases = [_case(case_id=f"case-{index:02d}") for index in range(17)]
    exact_ids = [[case["case_id"] for case in batch] for batch in case_batches(cases, seed=1337, epoch=4)]
    no_memory_ids = [[case["case_id"] for case in batch] for batch in case_batches(cases, seed=1337, epoch=4)]
    assert exact_ids == no_memory_ids


def test_one_optimizer_step_occurs_for_one_complete_case_batch():
    exact, _ = build_paired_controllers(9090)
    optimizer = torch.optim.AdamW(exact.parameters(), lr=3e-3, weight_decay=1e-4)
    calls = []
    original_step = optimizer.step

    def counted_step(*args, **kwargs):
        calls.append(True)
        return original_step(*args, **kwargs)

    optimizer.step = counted_step
    report = train_complete_case_batch(exact, [_case(case_id="a"), _case("BLUE", "b")], optimizer)
    assert len(calls) == 1
    assert set(report) == {"batch_loss", "gradient_norm"}


def test_exact_memory_query_gradient_reaches_stored_write_vector_and_parameters():
    exact, _ = build_paired_controllers(9090)
    case = _case()
    exact.train()
    exact.reset_case()
    record = exact.process_write(case["episodes"][0]["events"][0], 0)
    assert record is not None
    seen = []
    record.hidden_value.register_hook(lambda gradient: seen.append(gradient))
    logits = exact.answer_query(case["episodes"][1]["events"][0])
    loss = case_cross_entropy(logits, target_for_case(case))
    loss.backward()
    assert seen and seen[0].shape == (HIDDEN_DIM,)
    assert any(parameter.grad is not None and torch.isfinite(parameter.grad).all() for parameter in exact.parameters())


def test_no_memory_has_no_prior_write_state_or_gradient_path():
    _, no_memory = build_paired_controllers(9090)
    case = _case()
    no_memory.train()
    no_memory.reset_case()
    logits_without_write = no_memory.answer_query(case["episodes"][1]["events"][0])
    no_memory.reset_case()
    assert no_memory.process_write(case["episodes"][0]["events"][0], 0) is None
    logits_after_discarded_write = no_memory.answer_query(case["episodes"][1]["events"][0])
    assert torch.equal(logits_without_write, logits_after_discarded_write)
    assert no_memory.ledger is None


def test_answer_is_only_read_by_target_constructor_not_event_path():
    assert 'case["answer"]' not in inspect.getsource(run_case_logits)
    assert 'case["answer"]' in inspect.getsource(target_for_case)
    import dmc01.memory as memory
    assert "oracle_answer" not in inspect.getsource(memory)


def test_checkpoint_payload_freezes_post_step_resume_state():
    exact, _ = build_paired_controllers(9090)
    optimizer = torch.optim.AdamW(exact.parameters(), lr=3e-3, weight_decay=1e-4)
    random.seed(9090)
    np.random.seed(9090)
    torch.manual_seed(9090)
    payload = checkpoint_payload(
        exact,
        optimizer,
        seed=9090,
        completed_epoch=0,
        next_batch_index=1,
        source_commit="structural",
        dataset_identity={"train_sha256": "test"},
        final_loss=1.0,
    )
    required = {"model_state_dict", "optimizer_state", "seed", "completed_epoch", "next_batch_index", "python_rng_state", "numpy_rng_state", "torch_rng_state", "training_config", "source_commit", "dmc00_dataset_identity", "final_loss", "metrics"}
    assert required <= set(payload)
    assert payload["next_batch_index"] == 1
    assert payload["checkpoint_boundary"].startswith("immediately after")
