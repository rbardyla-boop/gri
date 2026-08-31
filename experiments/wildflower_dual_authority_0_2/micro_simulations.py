"""Small deterministic cases used to test the 0.2 provenance contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import store as d
from .metrics import StoreSnapshot, snapshot_store


@dataclass(frozen=True)
class MicroResult:
    name: str
    snapshots: tuple[StoreSnapshot, ...]
    details: dict[str, object]
    store: d.ReferenceProvenanceStore


def _world(
    reference: int,
    value: int,
    relation: int = d.REL_X,
    object_value: int = 0,
) -> d.Packet:
    return d.Packet(reference, d.ACT_OBSERVE, reference, relation, object_value, value)


def _derived(
    reference: int,
    value: int,
    parents: tuple[d.ClaimKey, ...],
    relation: int = d.REL_ORDER_PARITY,
) -> d.Packet:
    return d.Packet(reference, d.ACT_DERIVE, reference, relation, 0, value)


def _new() -> tuple[d.ReferenceProvenanceStore, list[StoreSnapshot]]:
    epistemic_store = d.ReferenceProvenanceStore()
    return epistemic_store, [snapshot_store(epistemic_store)]


def _world_roots(
    epistemic_store: d.ReferenceProvenanceStore,
    roots: tuple[int, ...],
    value: int = 1,
) -> None:
    for reference in roots:
        epistemic_store.observe(_world(reference, value))


def _finish(
    name: str,
    epistemic_store: d.ReferenceProvenanceStore,
    snapshots: list[StoreSnapshot],
    **details: object,
) -> MicroResult:
    return MicroResult(name, tuple(snapshots), details, epistemic_store)


def parity_same_keys_new_lineage() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2))
    child = _derived(10, 7, ((1, 1), (2, 1)))
    old_support = epistemic_store.derive(child, ((2, 1), (1, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    snapshots.append(snapshot_store(epistemic_store))
    new_support = epistemic_store.derive(child, ((1, 1), (2, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "parity_same_keys_new_lineage",
        epistemic_store,
        snapshots,
        child=epistemic_store.claim_key(child),
        old_support=old_support,
        new_support=new_support,
    )


def three_level_unchanged_immediate_parent_keys() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2, 3))
    first = _derived(10, 1, ((1, 1), (2, 1)))
    first_key = epistemic_store.claim_key(first)
    epistemic_store.derive(first, ((1, 1), (2, 1)))
    second = _derived(11, 2, (first_key, (3, 1)))
    second_key = epistemic_store.claim_key(second)
    old_support = epistemic_store.derive(second, (first_key, (3, 1)))
    third = _derived(12, 3, (second_key,))
    third_support = epistemic_store.derive(third, (second_key,))
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    snapshots.append(snapshot_store(epistemic_store))
    replacement_first = epistemic_store.derive(first, ((1, 1), (2, 1)))
    new_support = epistemic_store.derive(second, (first_key, (3, 1)))
    replacement_third = epistemic_store.derive(third, (second_key,))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "three_level_unchanged_immediate_parent_keys",
        epistemic_store,
        snapshots,
        old_support=old_support,
        replacement_first=replacement_first,
        new_support=new_support,
        third_support=third_support,
        replacement_third=replacement_third,
    )


def five_level_changed_root_evidence() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2, 3, 4, 5))
    parent = (1, 1)
    support_ids: list[int] = []
    for level in range(5):
        packet = _derived(100 + level, level + 1, (parent, (2, 1)))
        support_ids.append(epistemic_store.derive(packet, (parent, (2, 1))))
        parent = epistemic_store.claim_key(packet)
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    snapshots.append(snapshot_store(epistemic_store))
    replacements: list[int] = []
    parent = (1, 1)
    for level in range(5):
        packet = _derived(100 + level, level + 1, (parent, (2, 1)))
        replacements.append(epistemic_store.derive(packet, (parent, (2, 1))))
        parent = epistemic_store.claim_key(packet)
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "five_level_changed_root_evidence",
        epistemic_store,
        snapshots,
        original_supports=tuple(support_ids),
        replacement_supports=tuple(replacements),
    )


def diamond_one_root_lineage_changes() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2, 3, 4))
    left = _derived(10, 1, ((1, 1), (2, 1)))
    right = _derived(11, 1, ((3, 1), (4, 1)))
    left_key = epistemic_store.claim_key(left)
    right_key = epistemic_store.claim_key(right)
    epistemic_store.derive(left, ((1, 1), (2, 1)))
    epistemic_store.derive(right, ((3, 1), (4, 1)))
    top = _derived(12, 1, (left_key, right_key))
    top_support = epistemic_store.derive(top, (left_key, right_key))
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    snapshots.append(snapshot_store(epistemic_store))
    replacement_left = epistemic_store.derive(left, ((1, 1), (2, 1)))
    replacement_top = epistemic_store.derive(top, (left_key, right_key))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "diamond_one_root_lineage_changes",
        epistemic_store,
        snapshots,
        top=epistemic_store.claim_key(top),
        top_support=top_support,
        replacement_left=replacement_left,
        replacement_top=replacement_top,
    )


def canonical_duplicate_reused() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2))
    packet = _derived(10, 1, ((1, 1), (2, 1)))
    first = epistemic_store.derive(packet, ((1, 1), (2, 1)))
    second = epistemic_store.derive(packet, ((2, 1), (1, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "canonical_duplicate_reused",
        epistemic_store,
        snapshots,
        support_ids=(first, second),
    )


def same_semantics_new_provenance() -> MicroResult:
    result = parity_same_keys_new_lineage()
    return MicroResult(
        "same_semantics_new_provenance",
        result.snapshots,
        result.details,
        result.store,
    )


def changed_lineage_changes_value() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2))
    old = _derived(10, 1, ((1, 1), (2, 1)))
    old_support = epistemic_store.derive(old, ((1, 1), (2, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 2))
    snapshots.append(snapshot_store(epistemic_store))
    new = _derived(10, 2, ((1, 2), (2, 1)))
    new_support = epistemic_store.derive(new, ((1, 2), (2, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "changed_lineage_changes_value",
        epistemic_store,
        snapshots,
        old_claim=epistemic_store.claim_key(old),
        new_claim=epistemic_store.claim_key(new),
        old_support=old_support,
        new_support=new_support,
    )


def lineage_changes_and_returns() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2))
    child = _derived(10, 1, ((1, 1), (2, 1)))
    original = epistemic_store.derive(child, ((1, 1), (2, 1)))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    replacement = epistemic_store.derive(child, ((1, 1), (2, 1)))
    epistemic_store.revoke_support(4)
    restored = epistemic_store.derive(child, ((1, 1), (2, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "lineage_changes_and_returns",
        epistemic_store,
        snapshots,
        original=original,
        replacement=replacement,
        restored=restored,
    )


def multiple_independent_grounded_paths() -> MicroResult:
    epistemic_store, snapshots = _new()
    epistemic_store.observe(_world(1, 1))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    parent_lineage = epistemic_store.effective_grounded_lineage((1, 1))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "multiple_independent_grounded_paths",
        epistemic_store,
        snapshots,
        parent_lineage=parent_lineage,
    )


def revoke_and_restore() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2))
    child = _derived(10, 1, ((1, 1), (2, 1)))
    support_id = epistemic_store.derive(child, ((1, 1), (2, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.revoke_support(support_id)
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.restore_support(support_id)
    snapshots.append(snapshot_store(epistemic_store))
    return _finish("revoke_and_restore", epistemic_store, snapshots, support_id=support_id)


def insertion_order_independent() -> MicroResult:
    first, first_snapshots = _new()
    second, second_snapshots = _new()
    for reference in (1, 2, 3):
        first.observe(_world(reference, 1))
    for reference in (3, 1, 2):
        second.observe(_world(reference, 1))
    first_id = first.derive(_derived(10, 1, ((1, 1), (2, 1))), ((1, 1), (2, 1)))
    second_id = second.derive(_derived(10, 1, ((2, 1), (1, 1))), ((2, 1), (1, 1)))
    first_snapshots.append(snapshot_store(first))
    second_snapshots.append(snapshot_store(second))
    return _finish(
        "insertion_order_independent",
        first,
        first_snapshots,
        comparison_snapshot=second_snapshots[-1],
        support_ids=(first_id, second_id),
    )


def deterministic_replay() -> MicroResult:
    return insertion_order_independent()


def hash_input_order_perturbation() -> MicroResult:
    return canonical_duplicate_reused()


def affected_cone_only() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2, 3, 4))
    left = _derived(10, 1, ((1, 1), (2, 1)))
    right = _derived(11, 1, ((3, 1), (4, 1)))
    epistemic_store.derive(left, ((1, 1), (2, 1)))
    right_support = epistemic_store.derive(right, ((3, 1), (4, 1)))
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "affected_cone_only",
        epistemic_store,
        snapshots,
        unaffected_claim=epistemic_store.claim_key(right),
        unaffected_support=right_support,
    )


def alternate_support_survives() -> MicroResult:
    epistemic_store, snapshots = _new()
    _world_roots(epistemic_store, (1, 2, 3, 4))
    child = _derived(10, 1, ((1, 1), (2, 1)))
    alternate = ((3, 1), (4, 1))
    bad_support = epistemic_store.derive(child, ((1, 1), (2, 1)))
    good_support = epistemic_store.derive(child, alternate)
    snapshots.append(snapshot_store(epistemic_store))
    epistemic_store.observe(_world(1, 1, d.REL_ABOVE))
    snapshots.append(snapshot_store(epistemic_store))
    return _finish(
        "alternate_support_survives",
        epistemic_store,
        snapshots,
        child=epistemic_store.claim_key(child),
        bad_support=bad_support,
        good_support=good_support,
    )


CASE_FUNCTIONS: tuple[Callable[[], MicroResult], ...] = (
    parity_same_keys_new_lineage,
    three_level_unchanged_immediate_parent_keys,
    five_level_changed_root_evidence,
    diamond_one_root_lineage_changes,
    canonical_duplicate_reused,
    same_semantics_new_provenance,
    changed_lineage_changes_value,
    lineage_changes_and_returns,
    multiple_independent_grounded_paths,
    revoke_and_restore,
    insertion_order_independent,
    deterministic_replay,
    hash_input_order_perturbation,
    affected_cone_only,
    alternate_support_survives,
)
