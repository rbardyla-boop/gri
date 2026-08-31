from __future__ import annotations

import hashlib
import json
import random

import pytest

from experiments.wildflower_dual_authority_0_1.micro_simulations import (
    CASE_FUNCTIONS as LEGACY_CASE_FUNCTIONS,
)
from experiments.wildflower_dual_authority_0_3 import store as d
from experiments.wildflower_dual_authority_0_3.metrics import classify_derived_transition
from experiments.wildflower_dual_authority_0_3.micro_simulations import (
    CASE_FUNCTIONS,
    affected_cone_only,
    alternate_support_survives,
    canonical_duplicate_reused,
    diamond_one_root_lineage_changes,
    five_level_changed_root_evidence,
    insertion_order_independent,
    lineage_changes_and_returns,
    multiple_independent_grounded_paths,
    parity_same_keys_new_lineage,
    revoke_and_restore,
    same_semantics_new_provenance,
    three_level_unchanged_immediate_parent_keys,
)


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


def _packet(
    reference: int,
    value: int,
    act: int = d.ACT_PROPOSE,
    relation: int = d.REL_X,
    object_value: int = 0,
) -> d.Packet:
    return d.Packet(reference, act, reference, relation, object_value, value)


def _run_operations(
    epistemic_store: d.ReferenceProvenanceStore,
) -> None:
    epistemic_store.observe(_packet(1, 1, d.ACT_OBSERVE))
    epistemic_store.observe(_packet(2, 1, d.ACT_OBSERVE))
    epistemic_store.derive(
        _packet(10, 1, d.ACT_DERIVE, d.REL_ORDER_PARITY, 2),
        ((1, 1), (2, 1)),
    )
    epistemic_store.observe(_packet(1, 1, d.ACT_OBSERVE, d.REL_ABOVE))
    epistemic_store.derive(
        _packet(10, 1, d.ACT_DERIVE, d.REL_ORDER_PARITY, 2),
        ((2, 1), (1, 1)),
    )


def test_parity_preserves_semantic_parents_but_changes_lineage() -> None:
    result = parity_same_keys_new_lineage()
    old_id = result.details["old_support"]
    new_id = result.details["new_support"]
    assert old_id != new_id
    assert result.store.supports[old_id].parents == result.store.supports[new_id].parents
    assert (
        result.store.supports[old_id].lineage_fingerprint
        != result.store.supports[new_id].lineage_fingerprint
    )
    assert result.store.support_grounded(old_id) is False
    assert result.store.support_grounded(new_id) is True
    assert result.store.status(*result.details["child"]) == d.STATUS_COMMITTED


def test_metric_b_accepts_same_parent_keys_when_lineage_changes() -> None:
    result = parity_same_keys_new_lineage()
    transition = classify_derived_transition(
        result.store.supports[result.details["old_support"]].packet,
        _packet(10, 7, d.ACT_OBSERVE, d.REL_ORDER_PARITY),
        result.details["old_support"],
        result.snapshots[1],
        result.snapshots[2],
        result.snapshots[3],
    )
    assert transition.recomputation_opportunity
    assert transition.recomputation_success
    assert transition.parent_keys_changed is False
    assert transition.same_semantics_new_provenance


def test_metric_a_requires_an_already_existing_alternate_path() -> None:
    result = alternate_support_survives()
    transition = classify_derived_transition(
        result.store.supports[result.details["bad_support"]].packet,
        _packet(10, 1, d.ACT_OBSERVE, d.REL_ORDER_PARITY),
        result.details["bad_support"],
        result.snapshots[1],
        result.snapshots[2],
        result.snapshots[2],
    )
    assert transition.preservation_opportunity
    assert transition.preservation_success


@pytest.mark.parametrize(
    "case_function",
    CASE_FUNCTIONS,
    ids=lambda function: function.__name__,
)
def test_each_hostile_case_is_deterministic(case_function) -> None:
    first = case_function()
    second = case_function()
    assert first.snapshots == second.snapshots
    assert first.details.keys() == second.details.keys()


def test_three_and_five_level_transitive_repair_reaches_commitment() -> None:
    three = three_level_unchanged_immediate_parent_keys()
    five = five_level_changed_root_evidence()
    assert three.store.status(12, 3) == d.STATUS_COMMITTED
    assert five.store.status(104, 5) == d.STATUS_COMMITTED
    assert three.details["new_support"] != three.details["old_support"]
    assert five.details["original_supports"] != five.details["replacement_supports"]


def test_diamond_only_affected_branch_changes() -> None:
    result = diamond_one_root_lineage_changes()
    assert result.store.status(*result.details["top"]) == d.STATUS_COMMITTED
    assert result.store.support_grounded(result.details["replacement_top"])
    right_key = (11, 1)
    assert result.store.status(*right_key) == d.STATUS_COMMITTED


def test_same_semantics_same_lineage_reuses_canonical_identity() -> None:
    result = canonical_duplicate_reused()
    first, second = result.details["support_ids"]
    assert first == second
    metrics = result.store.engineering_metrics()
    assert metrics["canonical_support_reuses"] == 1
    assert metrics["semantic_duplicates_reused"] == 1
    assert metrics["canonical_support_creations"] == 3
    assert result.store.counts()["active_supports"] == 3
    assert result.store.counts()["historical_events"] == 4


def test_same_semantics_different_lineage_is_not_a_duplicate() -> None:
    result = same_semantics_new_provenance()
    old_id = result.details["old_support"]
    new_id = result.details["new_support"]
    assert old_id != new_id
    assert result.store.supports[old_id].parents == result.store.supports[new_id].parents
    assert result.store.supports[old_id].lineage_fingerprint != (
        result.store.supports[new_id].lineage_fingerprint
    )
    assert result.store.engineering_metrics()["provenance_changes"] == 1


def test_lineage_return_reuses_original_canonical_support() -> None:
    result = lineage_changes_and_returns()
    assert result.details["original"] == result.details["restored"]
    assert result.details["replacement"] != result.details["original"]


def test_multiple_grounded_paths_are_sorted_and_machine_native() -> None:
    result = multiple_independent_grounded_paths()
    paths = result.details["parent_lineage"]
    assert len(paths) == 2
    assert paths == tuple(sorted(paths))
    assert all(len(path) == 64 for path in paths)
    assert all(character in "0123456789abcdef" for path in paths for character in path)


def test_revoke_and_restore_preserves_identity_and_replay() -> None:
    result = revoke_and_restore()
    support_id = result.details["support_id"]
    assert result.snapshots[2].supports[support_id].enabled is False
    assert result.snapshots[3].supports[support_id].enabled is True
    assert result.store.ledger.head_sha256 == result.store.ledger.replay_head()


def test_insertion_order_does_not_change_semantic_lineage() -> None:
    result = insertion_order_independent()
    first = result.snapshots[-1]
    second = result.details["comparison_snapshot"]
    first_rows = sorted(
        (item.packet, item.kind, item.semantic_parent_claim_keys, item.parent_lineage_fingerprint)
        for item in first.supports.values()
    )
    second_rows = sorted(
        (item.packet, item.kind, item.semantic_parent_claim_keys, item.parent_lineage_fingerprint)
        for item in second.supports.values()
    )
    assert first_rows == second_rows


def test_deterministic_replay_and_input_order_perturbation() -> None:
    first = parity_same_keys_new_lineage()
    second = parity_same_keys_new_lineage()
    assert first.store.ledger.head_sha256 == second.store.ledger.head_sha256
    assert first.store.supports[first.details["old_support"]].lineage_fingerprint == (
        second.store.supports[second.details["old_support"]].lineage_fingerprint
    )
    duplicate = canonical_duplicate_reused()
    assert duplicate.details["support_ids"][0] == duplicate.details["support_ids"][1]


def test_affected_cone_does_not_visit_unrelated_branch() -> None:
    result = affected_cone_only()
    unrelated = result.details["unaffected_support"]
    assert result.store.support_grounded(unrelated)
    assert result.store.status(*result.details["unaffected_claim"]) == d.STATUS_COMMITTED

    incremental = d.IncrementalProvenanceStore()
    incremental.observe(_packet(1, 1, d.ACT_OBSERVE))
    incremental.observe(_packet(2, 1, d.ACT_OBSERVE))
    incremental.observe(_packet(3, 1, d.ACT_OBSERVE))
    incremental.observe(_packet(4, 1, d.ACT_OBSERVE))
    incremental.derive(_packet(10, 1, d.ACT_DERIVE), ((1, 1), (2, 1)))
    incremental.derive(_packet(11, 1, d.ACT_DERIVE), ((3, 1), (4, 1)))
    before = incremental.engineering_metrics()
    incremental.observe(_packet(1, 1, d.ACT_OBSERVE, d.REL_ABOVE))
    delta = incremental.engineering_metrics()
    assert delta["supports_visited"] - before["supports_visited"] < len(
        incremental.supports
    )


def test_alternate_support_survives_other_lineage_change() -> None:
    result = alternate_support_survives()
    child = result.details["child"]
    bad = result.details["bad_support"]
    good = result.details["good_support"]
    assert result.store.status(*child) == d.STATUS_COMMITTED
    assert result.store.support_grounded(bad) is False
    assert result.store.support_grounded(good) is True


def test_reference_and_incremental_match_after_every_mutation() -> None:
    reference = d.ReferenceProvenanceStore()
    incremental = d.IncrementalProvenanceStore()
    operations = (
        ("observe", _packet(1, 1, d.ACT_OBSERVE)),
        ("observe", _packet(2, 1, d.ACT_OBSERVE)),
        ("derive", (_packet(10, 1, d.ACT_DERIVE), ((1, 1), (2, 1)))),
        ("observe", _packet(1, 1, d.ACT_OBSERVE, d.REL_ABOVE)),
        ("derive", (_packet(10, 1, d.ACT_DERIVE), ((2, 1), (1, 1)))),
        ("revoke_support", 4),
        ("restore_support", 4),
    )
    for operation, payload in operations:
        if isinstance(payload, tuple):
            packet, parents = payload
            getattr(reference, operation)(packet, parents)
            getattr(incremental, operation)(packet, parents)
        else:
            getattr(reference, operation)(payload)
            getattr(incremental, operation)(payload)
        assert _signature(reference) == _signature(incremental)


def test_old_0_1_reference_cases_still_execute_without_importing_successor() -> None:
    assert len(LEGACY_CASE_FUNCTIONS) >= 16
    for case_function in LEGACY_CASE_FUNCTIONS:
        result = case_function()
        assert result.snapshots


def test_lineage_hash_is_not_based_on_python_object_identity() -> None:
    result = parity_same_keys_new_lineage()
    payload = {
        "parents": result.store.supports[result.details["new_support"]].parents,
        "lineage": result.store.supports[result.details["new_support"]].lineage_fingerprint,
    }
    assert hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_random_small_mutation_sequence_matches_reference() -> None:
    reference = d.ReferenceProvenanceStore(max_claims=512)
    incremental = d.IncrementalProvenanceStore(max_claims=512)
    rng = random.Random(2026020)
    roots: list[d.ClaimKey] = []
    for index in range(45):
        packet = _packet(20_000 + index, index % 5, d.ACT_OBSERVE)
        reference.observe(packet)
        incremental.observe(packet)
        roots.append((packet.stable_reference, packet.value))
        assert _signature(reference) == _signature(incremental)
        if index >= 2 and rng.random() < 0.7:
            parents = tuple(sorted(rng.sample(roots, 2)))
            derived = _packet(30_000 + index, index % 7, d.ACT_DERIVE)
            reference.derive(derived, parents)
            incremental.derive(derived, parents)
            assert _signature(reference) == _signature(incremental)
