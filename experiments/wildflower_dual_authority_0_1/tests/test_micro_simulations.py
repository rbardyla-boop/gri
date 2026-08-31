from __future__ import annotations

import numpy as np
import pytest

from experiments.wildflower_dual_authority_0_1 import store as d
from experiments.wildflower_dual_authority_0_1.metrics import (
    classify_derived_transition,
    graph_quality_metrics,
    snapshot_store,
)
from experiments.wildflower_dual_authority_0_1.micro_simulations import (
    CASE_FUNCTIONS,
    all_micro_cases,
    semantic_signature,
)
from experiments.wildflower_dual_authority_0_1.qualification_guard import (
    assert_qualification_locked,
    qualification_is_locked,
)


@pytest.mark.parametrize(
    "case_function",
    CASE_FUNCTIONS,
    ids=lambda function: function.__name__,
)
def test_each_adversarial_case_is_deterministic_and_traceable(case_function) -> None:
    first = case_function()
    second = case_function()
    assert len(first.snapshots) >= 2
    assert first.snapshots == second.snapshots
    assert first.details.keys() == second.details.keys()


def test_one_bad_support_and_valid_alternate_leave_child_committed() -> None:
    result = all_micro_cases()[0]
    child = result.details["child"]
    final = result.snapshots[-1]
    assert final.status(child) == d.STATUS_COMMITTED
    assert result.details["bad_support"] != result.details["good_support"]


def test_two_bad_supports_and_shared_parent_revoke_descendants() -> None:
    two_bad = all_micro_cases()[1]
    shared = all_micro_cases()[2]
    assert two_bad.snapshots[-1].status(two_bad.details["child"]) == d.STATUS_REVOKED
    assert shared.snapshots[-1].status(shared.details["child"]) == d.STATUS_REVOKED


def test_independent_alternate_support_survives() -> None:
    result = all_micro_cases()[3]
    assert result.snapshots[-1].status(result.details["child"]) == d.STATUS_COMMITTED


def test_parent_change_is_recomputation_not_preservation() -> None:
    result = all_micro_cases()[5]
    relation = result.details["relation"]
    after_witness = result.snapshots[-2]
    after_recompute = result.snapshots[-1]
    assert after_witness.status(relation) == d.STATUS_REVOKED
    assert after_recompute.status(relation) == d.STATUS_COMMITTED


def test_changed_derived_value_does_not_preserve_old_claim() -> None:
    result = all_micro_cases()[6]
    assert result.snapshots[-2].status(result.details["old_claim"]) == d.STATUS_REVOKED


def test_cycle_attempt_is_rejected_without_mutation() -> None:
    result = all_micro_cases()[9]
    assert result.details["error"] == result.details["expected_error"]
    assert result.snapshots[-1] == result.snapshots[-2]


def test_duplicate_supports_have_unique_ids_and_are_measurable() -> None:
    result = all_micro_cases()[10]
    first, second = result.details["support_ids"]
    assert first != second
    assert len(result.snapshots[-1].supports) == 2


def test_support_removal_order_is_semantically_independent() -> None:
    result = all_micro_cases()[11]
    assert result.details["semantic_equal"]
    assert semantic_signature(result.snapshots[0]) == semantic_signature(
        result.snapshots[1]
    )


def test_witness_precedes_recomputation_and_contradictory_witnesses_do_not_commit() -> None:
    witness = all_micro_cases()[12]
    assert witness.snapshots[-2].status(witness.details["relation"]) == d.STATUS_REVOKED
    assert witness.snapshots[-1].status(witness.details["relation"]) == d.STATUS_COMMITTED

    multiple = all_micro_cases()[13]
    contradictory = all_micro_cases()[14]
    assert multiple.details["committed_values"] == ()
    assert all(
        contradictory.snapshots[-1].status(claim) == d.STATUS_CONFLICTED
        for claim in contradictory.details["world_claims"]
    )
    assert contradictory.snapshots[-1].status(contradictory.details["child"]) == d.STATUS_REVOKED


def test_bounded_store_rejects_without_mutating_provenance() -> None:
    result = all_micro_cases()[15]
    assert result.details["error"] == "epistemic active-claim bound exceeded"
    assert result.details["unchanged"]


def test_successor_rejects_nonfinite_and_noninteger_packets() -> None:
    with pytest.raises(ValueError, match="finite"):
        d.quantize_state(np.full(6, np.nan, dtype=np.float32))
    with pytest.raises(ValueError, match="finite"):
        d.quantize_state(np.full(6, np.inf, dtype=np.float32))
    with pytest.raises(TypeError, match="integers"):
        d.Packet(1, d.ACT_PROPOSE, 1, d.REL_X, 0, 1.5).validate()


def test_graph_quality_metrics_cover_integrity_bound_and_replay() -> None:
    store = d.EpistemicStore(max_claims=8)
    packet = d.Packet(1, d.ACT_PROPOSE, 1, d.REL_X, 0, 1)
    store.propose(packet)
    metrics = graph_quality_metrics(store)
    assert metrics["support_DAG_integrity"]
    assert metrics["active_store_bound"]
    assert metrics["deterministic_replay"]
    assert metrics["orphan_support_rate"] == 0.0


def test_untouched_qualification_seeds_remain_locked() -> None:
    assert qualification_is_locked()
    with pytest.raises(RuntimeError, match="locked"):
        assert_qualification_locked(314)
    with pytest.raises(RuntimeError, match="locked"):
        assert_qualification_locked(315)


def test_metric_classifier_separates_preservation_and_recomputation() -> None:
    predicted = np.array([-0.5, -0.5, 0.5, -0.5, 0.0, 0.5], dtype=np.float32)
    observed = np.array([-0.3, -0.5, 0.6, -0.5, 0.0, 0.5], dtype=np.float32)
    store = d.EpistemicStore()
    prediction = d.materialize_prediction(store, predicted, 0, 20)
    relation = next(
        packet
        for packet in prediction["relation_packets"]
        if packet.relation == d.REL_LEFT_OF and packet.subject < packet.object
    )
    support_id = next(
        support_id
        for packet, support_id in zip(
            prediction["relation_packets"], prediction["relation_supports"], strict=True
        )
        if packet.stable_reference == relation.stable_reference
    )
    truth = d.evaluator_truth(observed, 0, 20)
    truth_packet = next(
        packet
        for packet in truth["relation_packets"]
        if packet.stable_reference == relation.stable_reference
    )
    before = snapshot_store(store)
    d.materialize_world_witness(store, observed, 0, 20)
    after_witness = snapshot_store(store)
    d.derive_from_committed_coordinates(store, observed, 0, 20)
    after_recompute = snapshot_store(store)
    transition = classify_derived_transition(
        relation,
        truth_packet,
        support_id,
        before,
        after_witness,
        after_recompute,
    )
    assert not transition.preservation_opportunity
    assert transition.recomputation_opportunity
    assert transition.recomputation_success
