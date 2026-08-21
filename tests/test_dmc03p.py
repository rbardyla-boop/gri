from __future__ import annotations

import inspect
import json
from pathlib import Path

import torch

from dmc02p.controller import MemoryRecord, RetentionMetadata
from dmc03p.preregistration import build_training_examples, load_cases
from dmc03p.retention import (
    AFFINE_PARAMETER_COUNT,
    CAPACITY,
    FEATURE_DIM,
    AffineRetentionScorer,
    DMC03PController,
    FEATURE_ENCODER,
    LearnedRetention16Ledger,
    build_retention_optimizer,
    initialize_scorer,
    load_frozen_processor,
    model_state_hash,
    retention_features,
    shuffle_metadata_permutation,
    stateless_order,
    trainable_parameter_count,
)


ROOT = Path(__file__).resolve().parents[1]


def record(index: int, *, salience: str | None = "LOW") -> MemoryRecord:
    return MemoryRecord(
        memory_id=f"dmc03p-test-{index:03d}",
        entity=f"entity-{index:03d}",
        field="value",
        creation_episode=index,
        supersedes=None,
        source_episode=index,
        hidden_value=torch.zeros(49),
        salience=salience,
    )


def test_feature_map_is_minimal_and_metadata_only():
    metadata = RetentionMetadata("mission_set", "mission-0", "value", 7, None, None)
    assert FEATURE_DIM == 2
    assert tuple(FEATURE_ENCODER.feature_names) == ("mission_membership", "high_salience")
    assert retention_features(metadata, {"mission-0"}).tolist() == [1.0, 0.0]
    assert retention_features(RetentionMetadata("salience", "d", "value", 7, "HIGH", None), None).tolist() == [0.0, 1.0]
    assert not set(inspect.signature(FEATURE_ENCODER.encode).parameters) & {"hidden_value", "answer", "query"}


def test_affine_scorer_is_exactly_the_preregistered_model():
    scorer = initialize_scorer(9090)
    assert isinstance(scorer, AffineRetentionScorer)
    assert scorer.parameter_count == AFFINE_PARAMETER_COUNT == 3
    assert trainable_parameter_count(scorer) == 3
    with torch.no_grad():
        scorer.linear.weight.copy_(torch.tensor([[1.0, 1.0]]))
        scorer.linear.bias.fill_(-0.5)
    logits = scorer(torch.tensor([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))
    assert logits.tolist() == [-0.5, 0.5, 0.5]


def test_learned_ledger_has_hard_capacity_and_sha256_tie_break():
    scorer = initialize_scorer(9090)
    with torch.no_grad():
        scorer.linear.weight.zero_()
        scorer.linear.bias.zero_()
    ledger = LearnedRetention16Ledger(scorer, family="distractor_flood")
    for index in range(32):
        ledger.consider(record(index))
    expected = sorted((item.memory_id for item in [record(i) for i in range(32)]), key=ledger.tie_key)[:CAPACITY]
    assert len(ledger) == CAPACITY
    assert sorted(item.memory_id for item in ledger.records()) == sorted(expected)
    assert not hasattr(ledger, "archive")
    assert not hasattr(ledger, "overflow")


def test_processor_is_frozen_and_optimizer_contains_scorer_only():
    processor, _ = load_frozen_processor(ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt")
    scorer = initialize_scorer(9090)
    controller = DMC03PController(processor, scorer, family="mission_set")
    optimizer = build_retention_optimizer(scorer)
    optimizer_ids = {id(parameter) for group in optimizer.param_groups for parameter in group["params"]}
    processor_ids = {id(parameter) for parameter in controller.processor.parameters()}
    assert all(not parameter.requires_grad for parameter in controller.processor.parameters())
    assert optimizer_ids == {id(parameter) for parameter in scorer.parameters()}
    assert not optimizer_ids & processor_ids
    assert trainable_parameter_count(controller.processor) == 0


def test_training_examples_are_train_only_and_answer_free():
    cases = load_cases()
    examples_a = build_training_examples(cases)
    examples_b = build_training_examples(cases)
    assert examples_a == examples_b
    assert examples_a
    assert all(set(example) == {"example_id", "features", "target"} for example in examples_a)
    assert all(len(example["features"]) == FEATURE_DIM for example in examples_a)
    assert all(example["target"] == int(bool(example["features"][0] or example["features"][1])) for example in examples_a)


def test_stateless_order_and_metadata_shuffle_are_deterministic():
    ids = [f"example-{index}" for index in range(20)]
    assert stateless_order(ids, seed=9090, epoch=0) == stateless_order(ids, seed=9090, epoch=0)
    assert sorted(stateless_order(ids, seed=9090, epoch=3)) == sorted(ids)
    permutation = shuffle_metadata_permutation("utility_change", "load_1024_overlap_25")
    assert len(permutation) == 16
    assert sorted(permutation) == list(range(16))
    assert permutation == shuffle_metadata_permutation("utility_change", "load_1024_overlap_25")


def test_frozen_dmc01_processor_state_is_reproducible():
    path = ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
    processor_a, _ = load_frozen_processor(path)
    processor_b, _ = load_frozen_processor(path)
    assert model_state_hash(processor_a) == model_state_hash(processor_b)

