from __future__ import annotations

from dataclasses import replace

import pytest

from experiments.wildflower_dual_authority_0_3 import store as d
from experiments.wildflower_dual_authority_0_3.design import qualification_gates
from experiments.wildflower_dual_authority_0_3.run_dual_authority03 import (
    _epistemic_gates,
)
from experiments.wildflower_dual_authority_0_3.alternate_evidence import (
    CASE_NAMES,
    HOSTILE_CASE_CODES,
    POSITIVE_HOSTILE_CASE_CODES,
    build_alternate_evidence_challenge,
    evaluate_case,
    world_root_identity,
    _build_case,
)


def _consume(store: d.ReferenceProvenanceStore, frame) -> None:
    for claim in frame.predictions:
        if claim.packet.act == d.ACT_DERIVE:
            store.derive(claim.packet, claim.semantic_parents)
        else:
            store.propose(claim.packet)
    for packet in frame.witnesses:
        store.observe(packet)
    for claim in frame.recomputed:
        if claim.packet.act == d.ACT_DERIVE:
            store.derive(claim.packet, claim.semantic_parents)
        else:
            store.propose(claim.packet)


def _signature(epistemic_store: d.ReferenceProvenanceStore) -> tuple[object, ...]:
    return (
        tuple(
            (key, claim.status, tuple(claim.support_ids))
            for key, claim in sorted(epistemic_store.claims.items())
        ),
        tuple(
            (
                support_id,
                support.packet.numeric_tuple(),
                support.kind,
                support.parents,
                support.lineage_fingerprint,
                support.enabled,
                epistemic_store.support_effective(support_id),
                epistemic_store.support_grounded(support_id),
            )
            for support_id, support in sorted(epistemic_store.supports.items())
        ),
    )


def test_guaranteed_valid_cases_produce_exactly_the_declared_denominator() -> None:
    frames, events, summary = build_alternate_evidence_challenge(
        0, valid_cases=40, include_hostile=True
    )
    assert frames
    assert len(events) == 57
    assert summary["guaranteed_valid_cases"] == 40
    assert summary["guaranteed_metric_a_opportunities"] == 40
    assert summary["guaranteed_positive_event_count"] == 40
    assert summary["represented_hostile_case_codes"] == list(HOSTILE_CASE_CODES)
    assert summary["emitted_hostile_case_codes"] == list(range(2, 19))
    assert summary["additional_hostile_case_count"] == 17
    assert summary["expected_positive_hostile_case_codes"] == list(
        POSITIVE_HOSTILE_CASE_CODES
    )
    assert summary["emitted_positive_hostile_case_codes"] == [8, 9, 10, 12]
    assert summary["expected_metric_a_opportunities"] == 44
    assert summary["metric_a_opportunities"] >= 40
    assert summary["metric_a_opportunities"] == 44
    assert summary["metric_a_successes"] == summary["metric_a_opportunities"]
    assert summary["false_opportunity_classifications"] == 0
    assert all(not event["false_opportunity_classification"] for event in events)


def test_false_opportunity_zero_is_a_preregistered_qualification_gate() -> None:
    assert qualification_gates()["false_opportunity_classifications"] == 0


def test_all_eighteen_hostile_cases_are_deterministic_and_serialized() -> None:
    first = build_alternate_evidence_challenge(1, valid_cases=1)
    second = build_alternate_evidence_challenge(1, valid_cases=1)
    assert first == second
    events = first[1]
    assert tuple(event["case_name"] for event in events) == CASE_NAMES
    required = {
        "event_id",
        "claim_key",
        "pre_witness_grounded_path_count",
        "pre_witness_independent_root_count",
        "invalidated_path_ids",
        "surviving_preexisting_path_ids",
        "post_witness_status",
        "recomputation_attempted",
        "new_post_witness_path_ids",
        "primary_classification",
        "metric_a_opportunity",
        "metric_a_success",
        "expected_metric_a_opportunity",
        "false_opportunity_classification",
        "metric_b_opportunity",
        "metric_b_success",
    }
    assert all(required.issubset(event) for event in events)
    assert events[0]["primary_classification"] == "PRESERVED"
    assert events[5]["primary_classification"] == "RECOMPUTED"
    assert events[12]["primary_classification"] == "RECOMPUTED"


def test_recomputation_diagnostics_do_not_enter_carried_forward_metric_b() -> None:
    for case_code in (6, 13):
        event, frames = evaluate_case(_build_case(case_code, case_code, 100))
        assert event["metric_b_opportunity"] is True
        assert event["metric_b_success"] is True
        assert all(not frame.recomputation_targets for frame in frames)


def test_false_opportunity_is_a_scientific_gate_not_runner_failure() -> None:
    metrics = {
        "alternate_support_preservation": {
            "opportunities": 44,
            "rate": 1.0,
        },
        "recomputed_after_parent_change": {
            "opportunities": 30,
            "global_precision": 1.0,
            "global_recall": 1.0,
        },
    }
    passing_gates, passing_verdict = _epistemic_gates(
        metrics, {"false_opportunity_classifications": 0}
    )
    failing_gates, failing_verdict = _epistemic_gates(
        metrics, {"false_opportunity_classifications": 1}
    )
    assert passing_gates["false_opportunity_classifications_zero"] is True
    assert passing_verdict == "PASS"
    assert failing_gates["false_opportunity_classifications_zero"] is False
    assert failing_verdict == "FAIL"


def test_independence_uses_canonical_root_lineage_not_support_ids() -> None:
    preserved = evaluate_case(_build_case(1, 1, 100))
    shared = evaluate_case(_build_case(3, 3, 100))
    duplicate = evaluate_case(_build_case(4, 4, 100))
    assert preserved[0]["pre_witness_independent_root_count"] == 2
    assert preserved[0]["metric_a_opportunity"] is True
    assert shared[0]["pre_witness_independent_root_count"] == 1
    assert shared[0]["metric_a_opportunity"] is False
    assert duplicate[0]["pre_witness_grounded_path_count"] == 1
    assert duplicate[0]["metric_a_opportunity"] is False


def test_reference_and_incremental_stores_are_equivalent_on_challenge() -> None:
    frames, _, _ = build_alternate_evidence_challenge(2, valid_cases=2)
    reference = d.ReferenceProvenanceStore()
    incremental = d.IncrementalProvenanceStore()
    for frame in frames:
        _consume(reference, frame)
        _consume(incremental, frame)
        assert _signature(reference) == _signature(incremental)


def test_same_parent_keys_changed_lineage_does_not_fabricate_survival() -> None:
    event, frames = evaluate_case(_build_case(16, 16, 100))
    assert event["case_name"] == "same_parent_keys_changed_lineage"
    assert event["pre_witness_grounded_path_count"] >= 2
    assert event["metric_a_opportunity"] is False
    assert event["primary_classification"] == "REVOKED"
    target_claims = [
        claim
        for frame in frames
        for claim in frame.predictions
        if claim.packet.stable_reference == event["claim_key"][0]
    ]
    assert len(target_claims) == 2
    assert target_claims[0].semantic_parents == target_claims[1].semantic_parents


def test_world_root_identity_is_stable_and_rejects_fake_independence() -> None:
    packet = d.Packet(700, d.ACT_OBSERVE, 700, d.REL_X, 0, 1)
    same_packet = replace(packet)
    different_packet = d.Packet(700, d.ACT_OBSERVE, 700, d.REL_ABOVE, 0, 1)
    assert world_root_identity(packet) == world_root_identity(same_packet)
    assert world_root_identity(packet) != world_root_identity(different_packet)


@pytest.mark.parametrize("case_code", range(1, 19))
def test_each_hostile_case_can_be_evaluated_without_mechanism_sidecar_leak(
    case_code: int,
) -> None:
    event, frames = evaluate_case(_build_case(100 + case_code, case_code, 100))
    assert event["case_code"] == case_code
    correction = frames[-1]
    assert not hasattr(correction.mechanism_frame, "truth_packets")
    assert not hasattr(correction.mechanism_frame, "preservation_targets")
    assert not hasattr(correction.mechanism_frame, "recomputation_targets")
