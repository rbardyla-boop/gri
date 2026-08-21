from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from dmc04p.matcher import (
    EVIDENCE_SEEDS,
    NON_EVIDENCE_SEED,
    FactorizedAssociativeMatcher,
    build_optimizer,
    build_shuffle_query_mapping,
    candidate_scores,
    descriptor_groups,
    load_training_cases,
    resolver,
    scorer_view,
    target_group,
    trainable_parameter_count,
    training_order,
    validate_scorer_view,
)


ROOT = Path(__file__).resolve().parents[1]


def test_factorized_matcher_has_only_two_8x8_matrices_and_no_bias():
    model = FactorizedAssociativeMatcher(seed=NON_EVIDENCE_SEED)
    assert [(name, tuple(parameter.shape)) for name, parameter in model.named_parameters()] == [("W_A", (8, 8)), ("W_B", (8, 8))]
    assert trainable_parameter_count(model) == 128
    optimizer = build_optimizer(model)
    assert len(optimizer.param_groups) == 1
    assert sum(len(group["params"]) for group in optimizer.param_groups) == 2


def test_scorer_view_excludes_hidden_content_oracle_and_case_identity():
    cases = load_training_cases(ROOT)
    for case in cases:
        view = scorer_view(case)
        assert validate_scorer_view(view)["pass"]
        text = json.dumps(view, sort_keys=True)
        for forbidden in ("logical_key", "answer", "hidden_value", "record_id", "case_id", "oracle_view"):
            assert forbidden not in text
        assert len(view["candidates"]) <= 16


def test_factorized_score_is_sum_of_atomic_bilinear_terms():
    case = load_training_cases(ROOT)[0]
    model = FactorizedAssociativeMatcher(seed=NON_EVIDENCE_SEED)
    with torch.no_grad():
        model.W_A.zero_()
        model.W_B.zero_()
        model.W_A[0, 0] = 3.0
        model.W_B[0, 0] = 5.0
    scores = candidate_scores(model, case)
    target = target_group(case)
    assert scores.ndim == 1
    assert scores.shape[0] == len(case["neural_view"]["memory"])
    assert scores[target["target_candidate_index"]].item() == pytest.approx(8.0)


def test_version_resolver_is_zero_parameter_and_replayable():
    cases = load_training_cases(ROOT)
    for case in cases:
        view = scorer_view(case)
        groups = descriptor_groups(view)
        target = target_group(case)
        scores = torch.zeros(len(view["candidates"]))
        scores[groups[target["target_group_index"]]] = 1.0
        first = resolver(case, scores)
        second = resolver(case, scores)
        assert first == second
        assert first["selected_record_id"] == case["oracle_view"]["target_record_id"]


def test_ordering_and_query_shuffle_are_deterministic_without_evidence_training():
    cases = []
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / "artifacts/dmc04a/datasets" / f"{split}.jsonl"
        cases.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    ids = [case["case_id"] for case in cases if case["split"] == "train"]
    first = training_order(ids, seed=NON_EVIDENCE_SEED, epoch=0)
    second = training_order(ids, seed=NON_EVIDENCE_SEED, epoch=0)
    assert first == second
    assert first["case_count"] == 128
    mapping = build_shuffle_query_mapping(cases)
    assert len(mapping) == len(cases)
    assert all(source != target for source, target in mapping.items())
    assert list(EVIDENCE_SEEDS) == [1337, 1338, 1339, 1340, 1341]


def test_preregistration_receipt_prohibits_evidence_training_and_integration():
    receipt = json.loads((ROOT / "artifacts/dmc04p/DMC04P_RECEIPT.json").read_text())
    assert receipt["terminal_state"] == "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED"
    assert receipt["evidence_training_executed"] is False
    assert receipt["scientific_retrieval_accuracy_measured"] is False
    assert receipt["dmc03_integration_executed"] is False
