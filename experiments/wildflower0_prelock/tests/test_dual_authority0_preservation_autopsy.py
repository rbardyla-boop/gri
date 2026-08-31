from __future__ import annotations

import numpy as np

import dual_authority0 as d


def _first_left_of(bundle: dict[str, object]) -> d.Packet:
    return next(
        packet
        for packet in bundle["relation_packets"]
        if packet.relation == d.REL_LEFT_OF and packet.subject < packet.object
    )


def _support_for(bundle: dict[str, object], stable_reference: int) -> int:
    return next(
        support_id
        for packet, support_id in zip(
            bundle["relation_packets"],
            bundle["relation_supports"],
            strict=True,
        )
        if packet.stable_reference == stable_reference
    )


def test_correct_derived_value_can_lose_old_support_before_recompute() -> None:
    predicted = np.array(
        [-0.5, -0.5, 0.5, -0.5, 0.0, 0.5],
        dtype=np.float32,
    )
    observed = np.array(
        [-0.3, -0.5, 0.6, -0.5, 0.0, 0.5],
        dtype=np.float32,
    )
    store = d.EpistemicStore()
    prediction = d.materialize_prediction(store, predicted, 0, 20)
    relation = _first_left_of(prediction)
    support_id = _support_for(prediction, relation.stable_reference)
    original_support = store.supports[support_id]
    truth = d.evaluator_truth(observed, 0, 20)
    truth_by_reference = {
        packet.stable_reference: packet
        for packet in (
            *truth["coordinate_packets"],
            *truth["relation_packets"],
            truth["parity_packet"],
        )
    }

    # The relation remains true even though both coordinate claim values used
    # by its original support are contradicted by the direct witness.
    assert relation.value == truth_by_reference[relation.stable_reference].value
    assert len(original_support.parents) == 2
    assert all(store.status(*parent) == d.STATUS_PROVISIONAL for parent in original_support.parents)

    d.materialize_world_witness(store, observed, 0, 20)

    # The runner's preservation opportunity is true here, but the old support
    # has no effective parent path. No alternate support exists yet.
    assert store.status(relation.stable_reference, relation.value) == d.STATUS_REVOKED
    assert store.supports[support_id].enabled
    assert not store.support_effective(support_id)
    assert store.claims[(relation.stable_reference, relation.value)].support_ids == [support_id]
    assert all(
        store.status(*parent) == d.STATUS_REVOKED
        for parent in original_support.parents
    )

    # Grounded recomputation later creates a new support with corrected parents;
    # that repairs the claim but is not counted by the pre-recompute metric.
    d.derive_from_committed_coordinates(store, observed, 0, 20)
    support_ids = store.claims[(relation.stable_reference, relation.value)].support_ids
    assert support_ids[0] == support_id
    assert len(support_ids) == 2
    assert store.status(relation.stable_reference, relation.value) == d.STATUS_COMMITTED
    assert any(
        sid != support_id and store.support_effective(sid)
        for sid in support_ids
    )


def test_genuine_alternate_support_survives_parent_support_retirement() -> None:
    state = np.array(
        [-0.5, -0.5, 0.0, 0.0, 0.5, 0.5],
        dtype=np.float32,
    )
    store = d.EpistemicStore()
    prediction = d.materialize_prediction(store, state, 0, 20)
    relation = _first_left_of(prediction)
    support_id = _support_for(prediction, relation.stable_reference)

    d.materialize_world_witness(store, state, 0, 20)

    # When the parent claim keys remain the same, retiring proposal supports
    # exposes the independent world-rooted supports and preserves the child.
    assert store.supports[support_id].enabled
    assert store.support_effective(support_id)
    assert store.status(relation.stable_reference, relation.value) == d.STATUS_COMMITTED
