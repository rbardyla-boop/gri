from __future__ import annotations

import random

import pytest

from experiments.wildflower_dual_authority_0_1 import store as d
from experiments.wildflower_dual_authority_0_1.micro_simulations import CASE_FUNCTIONS
from experiments.wildflower_dual_authority_0_1.metrics import (
    _graph_is_acyclic,
    snapshot_store,
)


def semantic_state(store: d.ReferenceEpistemicStore) -> tuple[object, ...]:
    claims = tuple(
        (key, claim.status, tuple(claim.support_ids))
        for key, claim in sorted(store.claims.items())
    )
    supports = tuple(
        (
            support_id,
            support.packet.numeric_tuple(),
            support.kind,
            support.parents,
            support.enabled,
            store.support_effective(support_id),
            store._support_grounded(support_id),
        )
        for support_id, support in sorted(store.supports.items())
    )
    children = tuple(
        (key, tuple(sorted(support_ids)))
        for key, support_ids in sorted(store.children.items())
    )
    return claims, supports, children


def proposal(reference: int, value: int) -> d.Packet:
    return d.Packet(reference, d.ACT_PROPOSE, reference, d.REL_X, 0, value)


def world(reference: int, value: int) -> d.Packet:
    return d.Packet(reference, d.ACT_OBSERVE, reference, d.REL_X, 0, value)


def derived(reference: int, value: int) -> d.Packet:
    return d.Packet(reference, d.ACT_DERIVE, reference, d.REL_LEFT_OF, 0, value)


def assert_equivalent(
    reference: d.ReferenceEpistemicStore,
    incremental: d.IncrementalEpistemicStore,
) -> None:
    assert semantic_state(reference) == semantic_state(incremental)


def snapshot_semantic_state(snapshot) -> tuple[object, ...]:
    claims = tuple(
        (key, status, support_ids)
        for key, (status, support_ids) in sorted(snapshot.claims.items())
    )
    supports = tuple(
        (
            support_id,
            support.packet,
            support.kind,
            support.parents,
            support.enabled,
            support.effective,
        )
        for support_id, support in sorted(snapshot.supports.items())
    )
    return claims, supports


def test_micro_style_mutations_match_reference_after_every_mutation() -> None:
    reference = d.ReferenceEpistemicStore()
    incremental = d.IncrementalEpistemicStore()
    assert_equivalent(reference, incremental)

    operations: list[tuple[str, object]] = []
    for ref, value in ((1, 1), (2, 1), (3, 2), (4, 2)):
        operations.append(("propose", proposal(ref, value)))
    operations.extend(
        (
            ("derive", (derived(10, 7), ((1, 1), (2, 1)))),
            ("derive", (derived(10, 7), ((3, 2), (4, 2)))),
            ("observe", world(1, 9)),
            ("observe", world(2, 9)),
            ("observe", world(3, 2)),
            ("observe", world(4, 2)),
        )
    )
    for kind, payload in operations:
        if kind == "propose":
            reference.propose(payload)
            incremental.propose(payload)
        elif kind == "derive":
            packet, parents = payload
            reference.derive(packet, parents)
            incremental.derive(packet, parents)
        else:
            reference.observe(payload)
            incremental.observe(payload)
        assert_equivalent(reference, incremental)

    reference.revoke_support(5)
    incremental.revoke_support(5)
    assert_equivalent(reference, incremental)
    reference.restore_support(5)
    incremental.restore_support(5)
    assert_equivalent(reference, incremental)


def test_all_deterministic_micro_cases_match_reference(monkeypatch) -> None:
    results: dict[str, tuple[object, ...]] = {}
    for store_type in (d.ReferenceEpistemicStore, d.IncrementalEpistemicStore):
        monkeypatch.setattr(d, "EpistemicStore", store_type)
        for case_function in CASE_FUNCTIONS:
            result = case_function()
            state = (
                semantic_state(result.store)
                if result.store is not None
                else snapshot_semantic_state(result.snapshots[-1])
            )
            results.setdefault(result.name, state)
            assert results[result.name] == state

def test_random_engineering_mutations_match_after_every_mutation() -> None:
    reference = d.ReferenceEpistemicStore(max_claims=512)
    incremental = d.IncrementalEpistemicStore(max_claims=512)
    rng = random.Random(90210)
    claims: list[d.ClaimKey] = []
    references: list[int] = []
    known_support_ids: list[int] = []
    disabled_support_ids: list[int] = []
    assert_equivalent(reference, incremental)

    for index in range(180):
        choices = ["propose"]
        if claims:
            choices.append("observe")
        if len(claims) >= 2:
            choices.append("derive")
        if known_support_ids:
            choices.append("revoke")
        if disabled_support_ids:
            choices.append("restore")
        operation = rng.choice(choices)
        if operation == "propose":
            packet = proposal(20_000 + index, (index % 7) - 3)
            reference.propose(packet)
            incremental.propose(packet)
            claims.append((packet.stable_reference, packet.value))
            references.append(packet.stable_reference)
            known_support_ids.append(len(known_support_ids) + 1)
        elif operation == "derive":
            parents = tuple(rng.sample(claims, 2))
            packet = derived(30_000 + index, index % 11)
            reference.derive(packet, parents)
            incremental.derive(packet, parents)
            claims.append((packet.stable_reference, packet.value))
            references.append(packet.stable_reference)
            known_support_ids.append(len(known_support_ids) + 1)
        elif operation == "observe":
            reference_id = rng.choice(references)
            packet = world(reference_id, rng.randrange(-3, 4))
            reference.observe(packet)
            incremental.observe(packet)
            known_support_ids.append(len(known_support_ids) + 1)
        elif operation == "revoke":
            support_id = rng.choice(known_support_ids)
            if support_id in disabled_support_ids:
                continue
            reference.revoke_support(support_id)
            incremental.revoke_support(support_id)
            disabled_support_ids.append(support_id)
        else:
            support_id = rng.choice(disabled_support_ids)
            reference.restore_support(support_id)
            incremental.restore_support(support_id)
            disabled_support_ids.remove(support_id)
        assert_equivalent(reference, incremental)


def test_deep_chain_is_iterative_and_preserves_grounding() -> None:
    store = d.IncrementalEpistemicStore(max_claims=2_000)
    root = proposal(1, 1)
    store.propose(root)
    parent = store.claim_key(root)
    for index in range(1, 1_000):
        packet = derived(100_000 + index, index)
        store.derive(packet, (parent,))
        parent = store.claim_key(packet)
    store.observe(world(1, 1))
    assert store.status(*parent) == d.STATUS_COMMITTED
    assert store.counts()["claims"] == 1_000
    assert store.ledger.head_sha256 == store.ledger.replay_head()
    snapshot = snapshot_store(store)
    assert _graph_is_acyclic(snapshot)


def test_wide_fanout_and_duplicate_dirty_notifications_are_local() -> None:
    reference = d.ReferenceEpistemicStore(max_claims=2_000)
    incremental = d.IncrementalEpistemicStore(max_claims=2_000)
    root = proposal(1, 1)
    reference.propose(root)
    incremental.propose(root)
    parent = (1, 1)
    for index in range(1, 1_000):
        packet = derived(200_000 + index, index)
        reference.derive(packet, (parent,))
        incremental.derive(packet, (parent,))
    assert_equivalent(reference, incremental)
    reference.observe(world(1, 1))
    incremental.observe(world(1, 1))
    incremental._propagate(
        initial_support_ids=(1, 1, 1),
        initial_claims=((1, 1), (1, 1)),
    )
    assert_equivalent(reference, incremental)

    incremental.reset_engineering_metrics()
    isolated = proposal(900_000, 1)
    incremental.propose(isolated)
    counters = incremental.engineering_metrics()
    assert counters["dirty_claims_processed"] == 1
    assert counters["dirty_supports_processed"] == 1
    assert counters["claims_visited"] < len(incremental.claims)
    assert counters["supports_visited"] < len(incremental.supports)


def test_noop_witness_and_bounded_capacity_match() -> None:
    reference = d.ReferenceEpistemicStore(max_claims=2)
    incremental = d.IncrementalEpistemicStore(max_claims=2)
    packet = proposal(1, 1)
    reference.propose(packet)
    incremental.propose(packet)
    reference.observe(world(1, 1))
    incremental.observe(world(1, 1))
    reference.observe(world(1, 1))
    incremental.observe(world(1, 1))
    assert_equivalent(reference, incremental)
    reference.propose(proposal(2, 2))
    incremental.propose(proposal(2, 2))
    before = semantic_state(incremental)
    with pytest.raises(MemoryError):
        reference.propose(proposal(3, 2))
    with pytest.raises(MemoryError):
        incremental.propose(proposal(3, 2))
    assert semantic_state(reference) == before
    assert semantic_state(incremental) == before
