from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .store import (
    ACT_DERIVE,
    STATUS_COMMITTED,
    STATUS_REVOKED,
    SUPPORT_DERIVED,
    SUPPORT_WORLD,
    EpistemicStore,
    Packet,
)

ClaimKey = tuple[int, int]


@dataclass(frozen=True)
class SupportSnapshot:
    support_id: int
    packet: tuple[int, int, int, int, int, int]
    kind: int
    parents: tuple[ClaimKey, ...]
    enabled: bool
    effective: bool


@dataclass(frozen=True)
class StoreSnapshot:
    claims: dict[ClaimKey, tuple[int, tuple[int, ...]]]
    supports: dict[int, SupportSnapshot]
    ledger_head_sha256: str

    def support_ids_for_claim(self, key: ClaimKey) -> tuple[int, ...]:
        claim = self.claims.get(key)
        return () if claim is None else claim[1]

    def status(self, key: ClaimKey) -> int:
        claim = self.claims.get(key)
        return STATUS_REVOKED if claim is None else claim[0]


@dataclass(frozen=True)
class DerivedTransition:
    claim: ClaimKey
    original_support_id: int
    correct_before_witness: bool
    invalidated_lineage_support_ids: tuple[int, ...]
    original_support_effective_after_witness: bool
    parent_keys_world_valid: bool
    alternate_parent_world_paths: bool
    preservation_opportunity: bool
    preservation_success: bool
    parent_keys_changed: bool
    recomputation_opportunity: bool
    recomputation_success: bool
    reconstructed_support_ids: tuple[int, ...]
    stale_support_survived: bool


def snapshot_store(
    store: EpistemicStore,
    root_support_ids: Iterable[int] | None = None,
) -> StoreSnapshot:
    """Snapshot all state or only a closed support region.

    Full snapshots are appropriate for final quality checks. Transition metrics
    use the closed region rooted at the current derived supports so historical
    store growth does not make instrumentation quadratic.
    """
    selected_claim_keys: set[ClaimKey] | None = None
    if root_support_ids is None:
        selected_support_ids = set(store.supports)
    else:
        selected_support_ids = set(int(support_id) for support_id in root_support_ids)
        pending = list(selected_support_ids)
        selected_claim_keys = set()
        while pending:
            support_id = pending.pop()
            support = store.supports[support_id]
            selected_claim_keys.add((support.packet.stable_reference, support.packet.value))
            for parent in support.parents:
                selected_claim_keys.add(parent)
                claim = store.claims.get(parent)
                if claim is None:
                    continue
                for parent_support_id in claim.support_ids:
                    if parent_support_id not in selected_support_ids:
                        selected_support_ids.add(parent_support_id)
                        pending.append(parent_support_id)
        for key in selected_claim_keys:
            claim = store.claims.get(key)
            if claim is not None:
                selected_support_ids.update(claim.support_ids)
    claims = {
        key: (claim.status, tuple(claim.support_ids))
        for key, claim in sorted(store.claims.items())
        if selected_claim_keys is None or key in selected_claim_keys
    }
    supports = {
        support_id: SupportSnapshot(
            support_id=support_id,
            packet=store.supports[support_id].packet.numeric_tuple(),
            kind=store.supports[support_id].kind,
            parents=store.supports[support_id].parents,
            enabled=store.supports[support_id].enabled,
            effective=store.support_effective(support_id),
        )
        for support_id in sorted(selected_support_ids)
    }
    return StoreSnapshot(claims, supports, store.ledger.head_sha256)


def support_lineage(snapshot: StoreSnapshot, support_id: int) -> frozenset[int]:
    """Return a support and every support that backs its parent claims."""
    if support_id not in snapshot.supports:
        raise KeyError(f"unknown support {support_id}")
    visiting: set[int] = set()
    result: set[int] = set()
    pending: list[tuple[int, bool]] = [(support_id, False)]
    while pending:
        current, exiting = pending.pop()
        if exiting:
            visiting.remove(current)
            continue
        if current in visiting:
            raise ValueError("support cycle detected")
        if current in result:
            continue
        support = snapshot.supports[current]
        visiting.add(current)
        result.add(current)
        pending.append((current, True))
        if support.kind == SUPPORT_DERIVED:
            parent_supports = [
                parent_support
                for parent in support.parents
                for parent_support in snapshot.support_ids_for_claim(parent)
            ]
            pending.extend((parent_support, False) for parent_support in reversed(parent_supports))
    return frozenset(result)


def _parent_has_world_path(snapshot: StoreSnapshot, key: ClaimKey) -> bool:
    return any(
        snapshot.supports[support_id].kind == SUPPORT_WORLD
        and snapshot.supports[support_id].enabled
        and snapshot.supports[support_id].effective
        for support_id in snapshot.support_ids_for_claim(key)
    )


def classify_derived_transition(
    packet: Packet,
    truth: Packet,
    original_support_id: int,
    before_witness: StoreSnapshot,
    after_witness: StoreSnapshot,
    after_recompute: StoreSnapshot,
) -> DerivedTransition:
    """Separate continuity of support from reconstruction after parent change."""
    if packet.act != ACT_DERIVE:
        raise ValueError("preservation metrics require a derived packet")
    if packet.stable_reference != truth.stable_reference:
        raise ValueError("prediction/truth stable-reference mismatch")

    claim = (packet.stable_reference, packet.value)
    original = before_witness.supports[original_support_id]
    invalidated = tuple(
        sorted(
            support_id
            for support_id in support_lineage(before_witness, original_support_id)
            if support_id != original_support_id
            and before_witness.supports[support_id].effective
            and not after_witness.supports[support_id].effective
        )
    )
    original_after = after_witness.supports[original_support_id].effective
    parent_keys_world_valid = all(
        after_witness.status(parent) == STATUS_COMMITTED
        for parent in original.parents
    )
    alternate_parent_world_paths = all(
        _parent_has_world_path(after_witness, parent)
        for parent in original.parents
    )
    correct_before = packet.value == truth.value
    preservation_opportunity = (
        correct_before
        and bool(invalidated)
        and original_after
        and parent_keys_world_valid
        and alternate_parent_world_paths
    )
    preservation_success = (
        preservation_opportunity
        and after_witness.status(claim) == STATUS_COMMITTED
    )
    parent_keys_changed = any(
        after_witness.status(parent) != STATUS_COMMITTED
        for parent in original.parents
    )
    recomputed_support_ids = tuple(
        sorted(
            support_id
            for support_id in after_recompute.support_ids_for_claim(claim)
            if support_id not in before_witness.support_ids_for_claim(claim)
            and after_recompute.supports[support_id].kind == SUPPORT_DERIVED
            and after_recompute.supports[support_id].effective
        )
    )
    recomputation_opportunity = (
        correct_before
        and parent_keys_changed
        and not original_after
    )
    recomputation_success = (
        recomputation_opportunity
        and bool(recomputed_support_ids)
        and after_recompute.status(claim) == STATUS_COMMITTED
        and any(
            after_recompute.supports[support_id].parents != original.parents
            for support_id in recomputed_support_ids
        )
    )
    return DerivedTransition(
        claim=claim,
        original_support_id=original_support_id,
        correct_before_witness=correct_before,
        invalidated_lineage_support_ids=invalidated,
        original_support_effective_after_witness=original_after,
        parent_keys_world_valid=parent_keys_world_valid,
        alternate_parent_world_paths=alternate_parent_world_paths,
        preservation_opportunity=preservation_opportunity,
        preservation_success=preservation_success,
        parent_keys_changed=parent_keys_changed,
        recomputation_opportunity=recomputation_opportunity,
        recomputation_success=recomputation_success,
        reconstructed_support_ids=recomputed_support_ids,
        stale_support_survived=parent_keys_changed and original_after,
    )


def aggregate_transitions(
    transitions: Iterable[DerivedTransition],
) -> dict[str, object]:
    rows = tuple(transitions)
    preservation_opportunities = sum(
        row.preservation_opportunity for row in rows
    )
    preservation_successes = sum(row.preservation_success for row in rows)
    recomputation_opportunities = sum(
        row.recomputation_opportunity for row in rows
    )
    recomputation_successes = sum(row.recomputation_success for row in rows)
    reconstructed_supports = sum(
        bool(row.reconstructed_support_ids) for row in rows
    )
    stale_candidates = sum(row.parent_keys_changed for row in rows)
    stale_survivors = sum(row.stale_support_survived for row in rows)
    return {
        "alternate_support_preservation": {
            "opportunities": preservation_opportunities,
            "successes": preservation_successes,
            "rate": (
                preservation_successes / preservation_opportunities
                if preservation_opportunities
                else 1.0
            ),
        },
        "recomputed_after_parent_change": {
            "opportunities": recomputation_opportunities,
            "successes": recomputation_successes,
            "rate": (
                recomputation_successes / recomputation_opportunities
                if recomputation_opportunities
                else 1.0
            ),
            "precision": (
                recomputation_successes / reconstructed_supports
                if reconstructed_supports
                else 1.0
            ),
            "recall": (
                recomputation_successes / recomputation_opportunities
                if recomputation_opportunities
                else 1.0
            ),
        },
        "stale_support_survival_rate": (
            stale_survivors / stale_candidates if stale_candidates else 0.0
        ),
    }


def _graph_is_acyclic(snapshot: StoreSnapshot) -> bool:
    states: dict[ClaimKey, int] = {}
    for root in sorted(snapshot.claims):
        if states.get(root, 0) == 2:
            continue
        pending: list[tuple[ClaimKey, bool]] = [(root, False)]
        while pending:
            key, exiting = pending.pop()
            state = states.get(key, 0)
            if exiting:
                states[key] = 2
                continue
            if state == 1:
                return False
            if state == 2:
                continue
            states[key] = 1
            pending.append((key, True))
            parents = [
                parent
                for support_id in snapshot.support_ids_for_claim(key)
                if snapshot.supports[support_id].kind == SUPPORT_DERIVED
                for parent in snapshot.supports[support_id].parents
            ]
            pending.extend((parent, False) for parent in reversed(sorted(parents)))
    return True


def graph_quality_metrics(
    store: EpistemicStore,
    *,
    before_witness: StoreSnapshot | None = None,
    after_witness: StoreSnapshot | None = None,
    truth_packets: Iterable[Packet] = (),
) -> dict[str, object]:
    snapshot = snapshot_store(store)
    derived_supports = [
        support
        for support in snapshot.supports.values()
        if support.kind == SUPPORT_DERIVED and support.enabled
    ]
    orphaned = [
        support
        for support in derived_supports
        if any(parent not in snapshot.claims for parent in support.parents)
    ]
    signatures = [
        (support.packet, support.kind, support.parents)
        for support in snapshot.supports.values()
    ]
    duplicate_count = len(signatures) - len(set(signatures))
    false_durable = 0
    truth_rows = tuple(truth_packets)
    for packet in truth_rows:
        false_durable += sum(
            value != packet.value for value in store.committed_values(packet.stable_reference)
        )
    result: dict[str, object] = {
        "false_durable_claim_rate": (
            false_durable / len(truth_rows) if truth_rows else 0.0
        ),
        "duplicate_support_rate": (
            duplicate_count / len(signatures) if signatures else 0.0
        ),
        "orphan_support_rate": (
            len(orphaned) / len(derived_supports) if derived_supports else 0.0
        ),
        "support_DAG_integrity": _graph_is_acyclic(snapshot)
        and not orphaned,
        "active_store_bound": len(snapshot.claims) <= store.max_claims,
        "deterministic_replay": (
            store.ledger.head_sha256 == store.ledger.replay_head()
        ),
    }
    if before_witness is not None and after_witness is not None:
        stale_candidates = [
            support_id
            for support_id, support in before_witness.supports.items()
            if support.kind == SUPPORT_DERIVED
            and support.effective
            and any(
                after_witness.status(parent) != STATUS_COMMITTED
                for parent in support.parents
            )
        ]
        stale_survivors = [
            support_id
            for support_id in stale_candidates
            if after_witness.supports[support_id].effective
        ]
        result["stale_support_survival_rate"] = (
            len(stale_survivors) / len(stale_candidates)
            if stale_candidates
            else 0.0
        )
    return result
