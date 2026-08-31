from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from . import store


ClaimKey = store.ClaimKey


@dataclass(frozen=True)
class SupportSnapshot:
    support_id: int
    packet: tuple[int, int, int, int, int, int]
    kind: int
    semantic_parent_claim_keys: tuple[ClaimKey, ...]
    parent_lineage_fingerprint: str
    enabled: bool
    effective: bool
    grounded: bool

    @property
    def parents(self) -> tuple[ClaimKey, ...]:
        return self.semantic_parent_claim_keys

    @property
    def lineage_fingerprint(self) -> str:
        return self.parent_lineage_fingerprint


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
        return store.STATUS_REVOKED if claim is None else claim[0]


@dataclass(frozen=True)
class DerivedTransition:
    claim: ClaimKey
    original_support_id: int
    correct_before_witness: bool
    invalidated_lineage_support_ids: tuple[int, ...]
    original_support_effective_after_witness: bool
    parent_keys_changed: bool
    preservation_opportunity: bool
    preservation_success: bool
    recomputation_opportunity: bool
    recomputation_success: bool
    reconstructed_support_ids: tuple[int, ...]
    provenance_changed: bool
    semantic_duplicate: bool
    same_semantics_new_provenance: bool
    stale_support_survived: bool


def snapshot_store(
    epistemic_store: store.ReferenceProvenanceStore,
    root_support_ids: Iterable[int] | None = None,
) -> StoreSnapshot:
    selected_claim_keys: set[ClaimKey] | None = None
    if root_support_ids is None:
        selected_support_ids = set(epistemic_store.supports)
    else:
        selected_support_ids = {int(value) for value in root_support_ids}
        pending = list(selected_support_ids)
        selected_claim_keys = set()
        while pending:
            support_id = pending.pop()
            support = epistemic_store.supports[support_id]
            selected_claim_keys.add(epistemic_store.claim_key(support.packet))
            for parent in support.parents:
                selected_claim_keys.add(parent)
                claim = epistemic_store.claims.get(parent)
                if claim is None:
                    continue
                for parent_support_id in claim.support_ids:
                    if parent_support_id not in selected_support_ids:
                        selected_support_ids.add(parent_support_id)
                        pending.append(parent_support_id)
        for key in selected_claim_keys:
            claim = epistemic_store.claims.get(key)
            if claim is not None:
                selected_support_ids.update(claim.support_ids)
    claims = {
        key: (claim.status, tuple(claim.support_ids))
        for key, claim in sorted(epistemic_store.claims.items())
        if selected_claim_keys is None or key in selected_claim_keys
    }
    supports = {
        support_id: SupportSnapshot(
            support_id=support_id,
            packet=support.packet.numeric_tuple(),
            kind=support.kind,
            semantic_parent_claim_keys=support.parents,
            parent_lineage_fingerprint=support.lineage_fingerprint,
            enabled=support.enabled,
            effective=epistemic_store.support_effective(support_id),
            grounded=epistemic_store.support_grounded(support_id),
        )
        for support_id, support in sorted(epistemic_store.supports.items())
        if support_id in selected_support_ids
    }
    return StoreSnapshot(claims, supports, epistemic_store.ledger.head_sha256)


def support_lineage(snapshot: StoreSnapshot, support_id: int) -> frozenset[int]:
    if support_id not in snapshot.supports:
        raise KeyError(f"unknown support {support_id}")
    result: set[int] = set()
    pending = [support_id]
    while pending:
        current = pending.pop()
        if current in result:
            continue
        support = snapshot.supports[current]
        result.add(current)
        if support.kind == store.SUPPORT_DERIVED:
            pending.extend(
                parent_support_id
                for parent in support.parents
                for parent_support_id in snapshot.support_ids_for_claim(parent)
            )
    return frozenset(result)


def _parent_has_world_path(snapshot: StoreSnapshot, key: ClaimKey) -> bool:
    return any(
        snapshot.supports[support_id].kind == store.SUPPORT_WORLD
        and snapshot.supports[support_id].enabled
        and snapshot.supports[support_id].effective
        and snapshot.supports[support_id].grounded
        for support_id in snapshot.support_ids_for_claim(key)
    )


def _support_is_grounded(snapshot: StoreSnapshot, support_id: int) -> bool:
    support = snapshot.supports[support_id]
    return support.enabled and support.effective and support.grounded


def _support_is_effective(snapshot: StoreSnapshot, support_id: int) -> bool:
    support = snapshot.supports[support_id]
    return support.enabled and support.effective


def _claim_has_grounded_support(snapshot: StoreSnapshot, key: ClaimKey) -> bool:
    return any(
        _support_is_grounded(snapshot, support_id)
        for support_id in snapshot.support_ids_for_claim(key)
    )


def classify_derived_transition(
    packet: store.Packet,
    truth: store.Packet,
    original_support_id: int,
    before_witness: StoreSnapshot,
    after_witness: StoreSnapshot,
    after_recompute: StoreSnapshot,
) -> DerivedTransition:
    if packet.act != store.ACT_DERIVE:
        raise ValueError("transition packet must be derived")
    if packet.stable_reference != truth.stable_reference:
        raise ValueError("prediction/truth stable-reference mismatch")
    claim = (packet.stable_reference, packet.value)
    original = before_witness.supports[original_support_id]
    lineage = support_lineage(before_witness, original_support_id)
    invalidated = tuple(
        sorted(
            support_id
            for support_id in lineage
            if (
                _support_is_effective(before_witness, support_id)
                and not _support_is_effective(after_witness, support_id)
            )
            or (
                _support_is_grounded(before_witness, support_id)
                and not _support_is_grounded(after_witness, support_id)
            )
        )
    )
    original_after = _support_is_grounded(after_witness, original_support_id)
    parent_keys_changed = any(
        before_witness.status(parent) != after_witness.status(parent)
        for parent in original.parents
    )
    correct_before = packet.value == truth.value
    alternate_grounded_support = any(
        support_id != original_support_id
        and support_id in before_witness.support_ids_for_claim(claim)
        and _support_is_grounded(before_witness, support_id)
        and _support_is_grounded(after_witness, support_id)
        for support_id in after_witness.support_ids_for_claim(claim)
    )
    preservation_opportunity = (
        correct_before
        and bool(invalidated)
        and alternate_grounded_support
    )
    preservation_success = (
        preservation_opportunity and after_witness.status(claim) == store.STATUS_COMMITTED
    )
    reconstructed = tuple(
        sorted(
            support_id
            for support_id in after_recompute.support_ids_for_claim(claim)
            if support_id not in before_witness.support_ids_for_claim(claim)
            and after_recompute.supports[support_id].kind == store.SUPPORT_DERIVED
            and after_recompute.supports[support_id].effective
            and after_recompute.supports[support_id].grounded
        )
    )
    corrected_evidence_available = bool(reconstructed) or all(
        _claim_has_grounded_support(after_recompute, parent)
        for parent in original.parents
    )
    recomputation_opportunity = (
        correct_before
        and bool(invalidated)
        and not original_after
        and corrected_evidence_available
    )
    reconstructed_fingerprints = {
        after_recompute.supports[support_id].lineage_fingerprint
        for support_id in reconstructed
    }
    provenance_changed = any(
        fingerprint != original.lineage_fingerprint
        for fingerprint in reconstructed_fingerprints
    )
    recomputation_success = (
        recomputation_opportunity
        and bool(reconstructed)
        and after_recompute.status(claim) == store.STATUS_COMMITTED
        and provenance_changed
    )
    semantic_duplicate = any(
        after_recompute.supports[support_id].lineage_fingerprint
        == original.lineage_fingerprint
        and after_recompute.supports[support_id].parents == original.parents
        for support_id in reconstructed
    )
    same_semantics_new_provenance = bool(reconstructed) and any(
        after_recompute.supports[support_id].parents == original.parents
        and after_recompute.supports[support_id].lineage_fingerprint
        != original.lineage_fingerprint
        for support_id in reconstructed
    )
    return DerivedTransition(
        claim=claim,
        original_support_id=original_support_id,
        correct_before_witness=correct_before,
        invalidated_lineage_support_ids=invalidated,
        original_support_effective_after_witness=original_after,
        parent_keys_changed=parent_keys_changed,
        preservation_opportunity=preservation_opportunity,
        preservation_success=preservation_success,
        recomputation_opportunity=recomputation_opportunity,
        recomputation_success=recomputation_success,
        reconstructed_support_ids=reconstructed,
        provenance_changed=provenance_changed,
        semantic_duplicate=semantic_duplicate,
        same_semantics_new_provenance=same_semantics_new_provenance,
        stale_support_survived=parent_keys_changed and original_after,
    )


def aggregate_transitions(transitions: Iterable[DerivedTransition]) -> dict[str, object]:
    rows = tuple(transitions)
    a_opportunities = sum(row.preservation_opportunity for row in rows)
    a_successes = sum(row.preservation_success for row in rows)
    b_opportunities = sum(row.recomputation_opportunity for row in rows)
    b_successes = sum(row.recomputation_success for row in rows)
    reconstructed = sum(bool(row.reconstructed_support_ids) for row in rows)
    duplicate_events = sum(row.semantic_duplicate for row in rows)
    provenance_changes = sum(row.same_semantics_new_provenance for row in rows)
    return {
        "alternate_support_preservation": {
            "opportunities": a_opportunities,
            "successes": a_successes,
            "rate": a_successes / a_opportunities if a_opportunities else 1.0,
        },
        "recomputed_after_parent_change": {
            "opportunities": b_opportunities,
            "successes": b_successes,
            "failures": b_opportunities - b_successes,
            "true_positives": b_successes,
            "false_positives": reconstructed - b_successes,
            "false_negatives": b_opportunities - b_successes,
            "global_precision": b_successes / reconstructed if reconstructed else 1.0,
            "global_recall": b_successes / b_opportunities if b_opportunities else 1.0,
            "reconstructed_support_transitions": reconstructed,
        },
        "semantic_duplicate_events": duplicate_events,
        "same_semantics_new_provenance_events": provenance_changes,
        "stale_support_survival_rate": (
            sum(row.stale_support_survived for row in rows)
            / sum(row.parent_keys_changed for row in rows)
            if any(row.parent_keys_changed for row in rows)
            else 0.0
        ),
    }


def graph_quality_metrics(epistemic_store: store.ReferenceProvenanceStore) -> dict[str, object]:
    supports = tuple(epistemic_store.supports.values())
    orphaned = [
        support
        for support in supports
        if support.kind == store.SUPPORT_DERIVED
        and any(parent not in epistemic_store.claims for parent in support.parents)
    ]
    return {
        "active_store_bound": len(epistemic_store.claims) <= epistemic_store.max_claims,
        "active_support_count": sum(support.enabled for support in supports),
        "canonical_support_count": len(supports),
        "historical_event_count": len(epistemic_store.event_history),
        "support_DAG_integrity": not orphaned,
        "orphan_support_rate": len(orphaned) / len(supports) if supports else 0.0,
        "semantic_duplicate_reuses": epistemic_store.semantic_duplicates_reused,
        "provenance_changes": epistemic_store.provenance_changes,
        "deterministic_replay": (
            epistemic_store.ledger.head_sha256 == epistemic_store.ledger.replay_head()
        ),
    }
