from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import store as d
from .metrics import StoreSnapshot, snapshot_store


@dataclass(frozen=True)
class MicroResult:
    name: str
    snapshots: tuple[StoreSnapshot, ...]
    details: dict[str, object]
    store: d.EpistemicStore | None = None


def _proposal(reference: int, value: int) -> d.Packet:
    return d.Packet(reference, d.ACT_PROPOSE, reference, d.REL_X, 0, value)


def _derived(
    reference: int,
    value: int,
    parents: tuple[d.ClaimKey, ...],
) -> tuple[d.Packet, tuple[d.ClaimKey, ...]]:
    return (
        d.Packet(reference, d.ACT_DERIVE, reference, d.REL_LEFT_OF, 0, value),
        parents,
    )


def _result(
    name: str,
    store: d.EpistemicStore,
    snapshots: list[StoreSnapshot],
    **details: object,
) -> MicroResult:
    return MicroResult(name, tuple(snapshots), details, store)


def _new_store() -> tuple[d.EpistemicStore, list[StoreSnapshot]]:
    store = d.EpistemicStore()
    return store, [snapshot_store(store)]


def one_bad_support_one_valid_alternate() -> MicroResult:
    store, snapshots = _new_store()
    bad_left = _proposal(1, 1)
    bad_right = _proposal(2, 1)
    good_left = _proposal(1, 2)
    good_right = _proposal(2, 2)
    for packet in (bad_left, bad_right, good_left, good_right):
        store.propose(packet)
        snapshots.append(snapshot_store(store))
    child, bad_parents = _derived(
        10,
        7,
        (store.claim_key(bad_left), store.claim_key(bad_right)),
    )
    bad_support = store.derive(child, bad_parents)
    snapshots.append(snapshot_store(store))
    good_support = store.derive(
        child,
        (store.claim_key(good_left), store.claim_key(good_right)),
    )
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 2))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(2, d.ACT_OBSERVE, 2, d.REL_X, 0, 2))
    snapshots.append(snapshot_store(store))
    return _result(
        "one_bad_support_one_valid_alternate",
        store,
        snapshots,
        child=(child.stable_reference, child.value),
        bad_support=bad_support,
        good_support=good_support,
    )


def two_bad_supports() -> MicroResult:
    store, snapshots = _new_store()
    packets = tuple(_proposal(reference, 1) for reference in range(1, 5))
    for packet in packets:
        store.propose(packet)
        snapshots.append(snapshot_store(store))
    child, _ = _derived(
        10,
        7,
        (store.claim_key(packets[0]), store.claim_key(packets[1])),
    )
    first = store.derive(child, (store.claim_key(packets[0]), store.claim_key(packets[1])))
    snapshots.append(snapshot_store(store))
    second = store.derive(child, (store.claim_key(packets[2]), store.claim_key(packets[3])))
    snapshots.append(snapshot_store(store))
    for reference in range(1, 5):
        store.observe(
            d.Packet(reference, d.ACT_OBSERVE, reference, d.REL_X, 0, 9)
        )
        snapshots.append(snapshot_store(store))
    return _result(
        "two_bad_supports",
        store,
        snapshots,
        child=(child.stable_reference, child.value),
        supports=(first, second),
    )


def two_supports_sharing_one_invalid_parent() -> MicroResult:
    store, snapshots = _new_store()
    common = _proposal(1, 1)
    left = _proposal(2, 2)
    right = _proposal(3, 3)
    for packet in (common, left, right):
        store.propose(packet)
        snapshots.append(snapshot_store(store))
    child, _ = _derived(10, 7, ())
    first = store.derive(child, (store.claim_key(common), store.claim_key(left)))
    snapshots.append(snapshot_store(store))
    second = store.derive(child, (store.claim_key(common), store.claim_key(right)))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 9))
    snapshots.append(snapshot_store(store))
    return _result(
        "two_supports_sharing_one_invalid_parent",
        store,
        snapshots,
        child=(child.stable_reference, child.value),
        supports=(first, second),
    )


def alternate_support_with_independent_parents() -> MicroResult:
    store, snapshots = _new_store()
    bad_left = _proposal(1, 1)
    bad_right = _proposal(2, 1)
    good_left = _proposal(3, 2)
    good_right = _proposal(4, 2)
    for packet in (bad_left, bad_right, good_left, good_right):
        store.propose(packet)
        snapshots.append(snapshot_store(store))
    child, _ = _derived(10, 7, ())
    bad_support = store.derive(child, (store.claim_key(bad_left), store.claim_key(bad_right)))
    snapshots.append(snapshot_store(store))
    good_support = store.derive(child, (store.claim_key(good_left), store.claim_key(good_right)))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 9))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(2, d.ACT_OBSERVE, 2, d.REL_X, 0, 9))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(3, d.ACT_OBSERVE, 3, d.REL_X, 0, 2))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(4, d.ACT_OBSERVE, 4, d.REL_X, 0, 2))
    snapshots.append(snapshot_store(store))
    return _result(
        "alternate_support_with_independent_parents",
        store,
        snapshots,
        child=(child.stable_reference, child.value),
        bad_support=bad_support,
        good_support=good_support,
    )


def correct_derived_value_both_parents_corrected() -> MicroResult:
    store, snapshots = _new_store()
    predicted = np.array([-0.5, -0.5, 0.5, -0.5, 0.0, 0.5], dtype=np.float32)
    observed = np.array([-0.3, -0.5, 0.6, -0.5, 0.0, 0.5], dtype=np.float32)
    prediction = d.materialize_prediction(store, predicted, 0, 20)
    snapshots.append(snapshot_store(store))
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
    d.materialize_world_witness(store, observed, 0, 20)
    snapshots.append(snapshot_store(store))
    return _result(
        "correct_derived_value_both_parents_corrected",
        store,
        snapshots,
        predicted=predicted,
        observed=observed,
        relation=relation,
        support_id=support_id,
    )


def correct_derived_value_reconstructed_from_new_parent_keys() -> MicroResult:
    store, snapshots = _new_store()
    predicted = np.array([-0.5, -0.5, 0.5, -0.5, 0.0, 0.5], dtype=np.float32)
    observed = np.array([-0.3, -0.5, 0.6, -0.5, 0.0, 0.5], dtype=np.float32)
    prediction = d.materialize_prediction(store, predicted, 0, 20)
    snapshots.append(snapshot_store(store))
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
    d.materialize_world_witness(store, observed, 0, 20)
    snapshots.append(snapshot_store(store))
    d.derive_from_committed_coordinates(store, observed, 0, 20)
    snapshots.append(snapshot_store(store))
    return _result(
        "correct_derived_value_reconstructed_from_new_parent_keys",
        store,
        snapshots,
        relation=(relation.stable_reference, relation.value),
        original_support=support_id,
    )


def derived_value_changes_after_corrected_parents() -> MicroResult:
    store, snapshots = _new_store()
    predicted = np.array([-0.5, -0.5, 0.5, -0.5, 0.0, 0.5], dtype=np.float32)
    observed = np.array([0.6, -0.5, -0.6, -0.5, 0.0, 0.5], dtype=np.float32)
    prediction = d.materialize_prediction(store, predicted, 0, 20)
    snapshots.append(snapshot_store(store))
    relation = next(
        packet
        for packet in prediction["relation_packets"]
        if packet.relation == d.REL_LEFT_OF and packet.subject < packet.object
    )
    d.materialize_world_witness(store, observed, 0, 20)
    snapshots.append(snapshot_store(store))
    recomputed = d.derive_from_committed_coordinates(store, observed, 0, 20)
    snapshots.append(snapshot_store(store))
    return _result(
        "derived_value_changes_after_corrected_parents",
        store,
        snapshots,
        old_claim=(relation.stable_reference, relation.value),
        recomputed_value=recomputed["relation_packets"][0].value,
    )


def cascading_descendants_three_levels() -> MicroResult:
    store, snapshots = _new_store()
    root = _proposal(1, 1)
    side = _proposal(2, 2)
    store.propose(root)
    snapshots.append(snapshot_store(store))
    store.propose(side)
    snapshots.append(snapshot_store(store))
    first, first_parents = _derived(
        10,
        1,
        (store.claim_key(root), store.claim_key(side)),
    )
    first_support = store.derive(first, first_parents)
    snapshots.append(snapshot_store(store))
    # The explicit parent tuple is used so every level remains inspectable.
    first_key = store.claim_key(first)
    second, _ = _derived(11, 2, (first_key, store.claim_key(side)))
    second_support = store.derive(second, (first_key, store.claim_key(side)))
    snapshots.append(snapshot_store(store))
    second_key = store.claim_key(second)
    third, _ = _derived(12, 3, (second_key, store.claim_key(side)))
    third_support = store.derive(third, (second_key, store.claim_key(side)))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 9))
    snapshots.append(snapshot_store(store))
    return _result(
        "cascading_descendants_three_levels",
        store,
        snapshots,
        supports=(first_support, second_support, third_support),
        claims=(store.claim_key(first), store.claim_key(second), store.claim_key(third)),
    )


def diamond_support_graph() -> MicroResult:
    store, snapshots = _new_store()
    common = _proposal(1, 1)
    left = _proposal(2, 2)
    right = _proposal(3, 3)
    for packet in (common, left, right):
        store.propose(packet)
        snapshots.append(snapshot_store(store))
    left_child, _ = _derived(10, 1, ())
    left_support = store.derive(left_child, (store.claim_key(common), store.claim_key(left)))
    snapshots.append(snapshot_store(store))
    right_child, _ = _derived(11, 2, ())
    right_support = store.derive(right_child, (store.claim_key(common), store.claim_key(right)))
    snapshots.append(snapshot_store(store))
    top, _ = _derived(12, 3, ())
    top_support = store.derive(top, (store.claim_key(left_child), store.claim_key(right_child)))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 9))
    snapshots.append(snapshot_store(store))
    return _result(
        "diamond_support_graph",
        store,
        snapshots,
        supports=(left_support, right_support, top_support),
        claims=(
            store.claim_key(left_child),
            store.claim_key(right_child),
            store.claim_key(top),
        ),
    )


def cycles_attempted_and_rejected() -> MicroResult:
    store, snapshots = _new_store()
    root = _proposal(1, 1)
    store.propose(root)
    snapshots.append(snapshot_store(store))
    child, parents = _derived(10, 2, (store.claim_key(root),))
    store.derive(child, parents)
    snapshots.append(snapshot_store(store))
    error = None
    try:
        cycle_packet = d.Packet(1, d.ACT_DERIVE, 1, d.REL_LEFT_OF, 0, 1)
        store.derive(cycle_packet, (store.claim_key(child),))
    except ValueError as exc:
        error = str(exc)
    snapshots.append(snapshot_store(store))
    return _result(
        "cycles_attempted_and_rejected",
        store,
        snapshots,
        error=error,
        expected_error="support cycle detected",
    )


def duplicate_support_insertion() -> MicroResult:
    store, snapshots = _new_store()
    packet = _proposal(1, 1)
    first = store.propose(packet)
    snapshots.append(snapshot_store(store))
    second = store.propose(packet)
    snapshots.append(snapshot_store(store))
    return _result(
        "duplicate_support_insertion",
        store,
        snapshots,
        support_ids=(first, second),
        claim=(packet.stable_reference, packet.value),
    )


def _order_case(order: tuple[int, int]) -> StoreSnapshot:
    store = d.EpistemicStore()
    first = _proposal(1, 1)
    second = _proposal(2, 1)
    store.propose(first)
    store.propose(second)
    child, _ = _derived(10, 7, ())
    store.derive(child, (store.claim_key(first), store.claim_key(second)))
    for reference in order:
        store.observe(d.Packet(reference, d.ACT_OBSERVE, reference, d.REL_X, 0, 9))
    return snapshot_store(store)


def support_removal_order_independence() -> MicroResult:
    first = _order_case((1, 2))
    second = _order_case((2, 1))
    return MicroResult(
        "support_removal_order_independence",
        (first, second),
        {"semantic_equal": semantic_signature(first) == semantic_signature(second)},
    )


def witness_before_recomputation() -> MicroResult:
    result = correct_derived_value_reconstructed_from_new_parent_keys()
    return MicroResult(
        "witness_before_recomputation",
        result.snapshots,
        result.details,
        result.store,
    )


def multiple_witnesses_correcting_same_parent() -> MicroResult:
    store, snapshots = _new_store()
    proposal = _proposal(1, 1)
    store.propose(proposal)
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 2))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 3))
    snapshots.append(snapshot_store(store))
    return _result(
        "multiple_witnesses_correcting_same_parent",
        store,
        snapshots,
        claim=(1, 2),
        committed_values=store.committed_values(1),
    )


def contradictory_witnesses_with_descendant() -> MicroResult:
    store, snapshots = _new_store()
    parent = _proposal(1, 1)
    store.propose(parent)
    snapshots.append(snapshot_store(store))
    child, _ = _derived(10, 7, (store.claim_key(parent),))
    store.derive(child, (store.claim_key(parent),))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 2))
    snapshots.append(snapshot_store(store))
    store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 3))
    snapshots.append(snapshot_store(store))
    return _result(
        "contradictory_witnesses_with_descendant",
        store,
        snapshots,
        parent=(1, 1),
        world_claims=((1, 2), (1, 3)),
        child=store.claim_key(child),
    )


def bounded_store_rejects_provenance_eviction() -> MicroResult:
    store, snapshots = _new_store()
    store.max_claims = 2
    first = _proposal(1, 1)
    second = _proposal(2, 2)
    store.propose(first)
    snapshots.append(snapshot_store(store))
    store.propose(second)
    snapshots.append(snapshot_store(store))
    before = snapshot_store(store)
    error = None
    try:
        store.propose(_proposal(3, 3))
    except MemoryError as exc:
        error = str(exc)
    after = snapshot_store(store)
    snapshots.append(after)
    return _result(
        "bounded_store_rejects_provenance_eviction",
        store,
        snapshots,
        error=error,
        unchanged=before == after,
    )


def semantic_signature(snapshot: StoreSnapshot) -> tuple[object, ...]:
    claims = tuple(
        (key, status)
        for key, (status, _) in sorted(snapshot.claims.items())
    )
    supports = tuple(
        (
            support.packet,
            support.kind,
            support.parents,
            support.enabled,
            support.effective,
        )
        for support in sorted(snapshot.supports.values(), key=lambda value: (
            value.packet,
            value.kind,
            value.parents,
        ))
    )
    return claims, supports


CASE_FUNCTIONS: tuple[Callable[[], MicroResult], ...] = (
    one_bad_support_one_valid_alternate,
    two_bad_supports,
    two_supports_sharing_one_invalid_parent,
    alternate_support_with_independent_parents,
    correct_derived_value_both_parents_corrected,
    correct_derived_value_reconstructed_from_new_parent_keys,
    derived_value_changes_after_corrected_parents,
    cascading_descendants_three_levels,
    diamond_support_graph,
    cycles_attempted_and_rejected,
    duplicate_support_insertion,
    support_removal_order_independence,
    witness_before_recomputation,
    multiple_witnesses_correcting_same_parent,
    contradictory_witnesses_with_descendant,
    bounded_store_rejects_provenance_eviction,
)


def all_micro_cases() -> tuple[MicroResult, ...]:
    return tuple(function() for function in CASE_FUNCTIONS)
