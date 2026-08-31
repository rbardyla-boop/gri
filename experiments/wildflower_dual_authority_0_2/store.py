from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import hashlib
import itertools
import json
from typing import Iterable


ACT_PROPOSE = 1
ACT_OBSERVE = 2
ACT_DERIVE = 3

REL_X = 1
REL_Y = 2
REL_LEFT_OF = 3
REL_ABOVE = 4
REL_ORDER_PARITY = 5

SUPPORT_PROPOSAL = 1
SUPPORT_WORLD = 2
SUPPORT_DERIVED = 3

STATUS_PROVISIONAL = 1
STATUS_COMMITTED = 2
STATUS_REVOKED = 3
STATUS_CONFLICTED = 4

LEDGER_ADD = 1
LEDGER_REVOKE = 2
LEDGER_STATUS = 3
LEDGER_RESTORE = 4

ClaimKey = tuple[int, int]
LineageFingerprint = str


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def canonical_hash(value: object) -> str:
    """Hash machine-native canonical data, never object identity or prose."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


NO_GROUNDED_LINEAGE = canonical_hash(("no-grounded-lineage",))


@dataclass(frozen=True)
class Packet:
    stable_reference: int
    act: int
    subject: int
    relation: int
    object: int
    value: int

    def validate(self) -> None:
        fields = (
            self.stable_reference,
            self.act,
            self.subject,
            self.relation,
            self.object,
            self.value,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in fields):
            raise TypeError("packet fields must be integers")
        if self.stable_reference <= 0:
            raise ValueError("stable_reference must be positive")
        if self.act not in (ACT_PROPOSE, ACT_OBSERVE, ACT_DERIVE):
            raise ValueError("unknown ACT code")
        if self.subject < 0 or self.relation <= 0 or self.object < 0:
            raise ValueError("invalid unsigned packet field")

    def numeric_tuple(self) -> tuple[int, int, int, int, int, int]:
        self.validate()
        return (
            self.stable_reference,
            self.act,
            self.subject,
            self.relation,
            self.object,
            self.value,
        )


@dataclass
class Support:
    support_id: int
    packet: Packet
    kind: int
    semantic_parent_claim_keys: tuple[ClaimKey, ...] = ()
    parent_lineage_fingerprint: LineageFingerprint = NO_GROUNDED_LINEAGE
    enabled: bool = True

    @property
    def parents(self) -> tuple[ClaimKey, ...]:
        """Compatibility spelling; these remain semantic claim keys."""
        return self.semantic_parent_claim_keys

    @property
    def lineage_fingerprint(self) -> LineageFingerprint:
        return self.parent_lineage_fingerprint

    def validate(self) -> None:
        self.packet.validate()
        if self.support_id <= 0:
            raise ValueError("support_id must be positive")
        if self.kind not in (SUPPORT_PROPOSAL, SUPPORT_WORLD, SUPPORT_DERIVED):
            raise ValueError("unknown support kind")
        if self.kind == SUPPORT_DERIVED and not self.parents:
            raise ValueError("derived support requires parents")
        if self.kind != SUPPORT_DERIVED and self.parents:
            raise ValueError("only derived support may carry parents")
        if len(self.lineage_fingerprint) != 64:
            raise ValueError("lineage fingerprint must be a SHA-256 hex digest")


@dataclass
class Claim:
    stable_reference: int
    value: int
    support_ids: list[int] = field(default_factory=list)
    status: int = STATUS_PROVISIONAL


@dataclass(frozen=True)
class EventOccurrence:
    event: str
    support_id: int
    packet: tuple[int, int, int, int, int, int]
    kind: int
    semantic_parents: tuple[ClaimKey, ...]
    lineage_fingerprint: LineageFingerprint


class NumericLedger:
    """Append-only numeric ledger with deterministic replay hashing."""

    def __init__(self) -> None:
        self._events: list[tuple[int, ...]] = []
        self._head = bytes(32)

    def append(self, *fields: int) -> None:
        event = tuple(int(field) for field in fields)
        self._events.append(event)
        self._head = hashlib.sha256(self._head + _canonical_bytes(event)).digest()

    @property
    def count(self) -> int:
        return len(self._events)

    @property
    def head_sha256(self) -> str:
        return self._head.hex()

    def replay_head(self) -> str:
        head = bytes(32)
        for event in self._events:
            head = hashlib.sha256(head + _canonical_bytes(event)).digest()
        return head.hex()


class ReferenceProvenanceStore:
    """Semantic oracle that refreshes the full graph after each mutation."""

    def __init__(self, max_claims: int = 8192) -> None:
        if max_claims <= 0:
            raise ValueError("max_claims must be positive")
        self.max_claims = int(max_claims)
        self.supports: dict[int, Support] = {}
        self.claims: dict[ClaimKey, Claim] = {}
        self._claim_keys_by_reference: dict[int, list[ClaimKey]] = defaultdict(list)
        self.children: dict[ClaimKey, set[int]] = {}
        self._active_world_values: dict[int, set[int]] = defaultdict(set)
        self._support_ids_by_reference: dict[int, set[int]] = defaultdict(set)
        self._canonical: dict[tuple[object, ...], int] = {}
        self._semantic_lineages: dict[tuple[object, ...], set[str]] = defaultdict(set)
        self._next_support_id = 1
        self.ledger = NumericLedger()
        self.event_history: list[EventOccurrence] = []
        self.support_insert_attempts = 0
        self.canonical_support_creations = 0
        self.canonical_support_reuses = 0
        self.provenance_changes = 0
        self.semantic_duplicates_reused = 0
        self.peak_claims = 0
        self.revoked_support_count = 0
        self.cascaded_support_count = 0
        self.conflicted_slot_count = 0
        self.revoked_support_total = 0
        self.lineage_fingerprint_calculations = 0
        self.grounded_lineage_traversals = 0
        self.lineage_hash_bytes = 0
        self.lineage_parent_count = 0
        self.grounded_lineage_path_total = 0
        self.max_grounded_lineage_paths = 0
        self.lineage_cache_hits = 0
        self.lineage_cache_misses = 0

    @staticmethod
    def claim_key(packet: Packet) -> ClaimKey:
        return packet.stable_reference, packet.value

    @staticmethod
    def _semantic_key(
        packet: Packet,
        kind: int,
        parents: tuple[ClaimKey, ...],
    ) -> tuple[object, ...]:
        return packet.numeric_tuple(), int(kind), parents

    def _canonical_key(
        self,
        packet: Packet,
        kind: int,
        parents: tuple[ClaimKey, ...],
        lineage_fingerprint: str,
    ) -> tuple[object, ...]:
        return self._semantic_key(packet, kind, parents) + (lineage_fingerprint,)

    def _ensure_capacity(self, key: ClaimKey) -> None:
        if key not in self.claims and len(self.claims) >= self.max_claims:
            raise MemoryError("epistemic active-claim bound exceeded")

    def _claim_depends_on(
        self,
        start: ClaimKey,
        target: ClaimKey,
    ) -> bool:
        pending = [start]
        visited: set[ClaimKey] = set()
        while pending:
            key = pending.pop()
            if key == target:
                return True
            if key in visited:
                continue
            visited.add(key)
            claim = self.claims.get(key)
            if claim is None:
                continue
            for support_id in claim.support_ids:
                support = self.supports[support_id]
                if support.kind == SUPPORT_DERIVED:
                    pending.extend(support.parents)
        return False

    def _support_effective(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        support = self.supports[support_id]
        if not support.enabled:
            return False
        if support.kind != SUPPORT_DERIVED:
            return True
        return all(self._claim_has_effective_support(parent, trail) for parent in support.parents)

    def _claim_has_effective_support(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        if key in trail:
            raise ValueError("support cycle detected")
        claim = self.claims.get(key)
        return bool(
            claim
            and any(
                self._support_effective(support_id, trail | {key})
                for support_id in claim.support_ids
            )
        )

    def _support_grounded(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        support = self.supports[support_id]
        if not self._support_effective(support_id):
            return False
        if support.kind == SUPPORT_WORLD:
            return True
        if support.kind == SUPPORT_PROPOSAL:
            return False
        return (
            all(self._claim_grounded(parent, trail) for parent in support.parents)
            and support.lineage_fingerprint
            == self.lineage_fingerprint_for_parents(support.parents)
        )

    def _claim_grounded(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        if key in trail:
            raise ValueError("support cycle detected")
        claim = self.claims.get(key)
        return bool(
            claim
            and any(
                self._support_grounded(support_id, trail | {key})
                for support_id in claim.support_ids
            )
        )

    def _grounded_path_fingerprints_for_support(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> frozenset[str]:
        support = self.supports[support_id]
        if not self._support_grounded(support_id, trail):
            return frozenset()
        if support.kind == SUPPORT_WORLD:
            return frozenset({canonical_hash(("world", support.packet.numeric_tuple()))})
        if support.kind == SUPPORT_PROPOSAL:
            return frozenset()
        parent_paths = [
            self._grounded_path_fingerprints_for_claim(parent, trail)
            for parent in support.parents
        ]
        if any(not paths for paths in parent_paths):
            return frozenset()
        return frozenset(
            canonical_hash(("derived-path", tuple(sorted(path_tuple))))
            for path_tuple in itertools.product(*parent_paths)
        )

    def _grounded_path_fingerprints_for_claim(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> frozenset[str]:
        if key in trail:
            raise ValueError("support cycle detected")
        claim = self.claims.get(key)
        if claim is None:
            return frozenset()
        result: set[str] = set()
        for support_id in claim.support_ids:
            result.update(
                self._grounded_path_fingerprints_for_support(
                    support_id, trail | {key}
                )
            )
        return frozenset(result)

    def effective_grounded_lineage(self, key: ClaimKey) -> tuple[str, ...]:
        self.grounded_lineage_traversals += 1
        lineage = tuple(sorted(self._grounded_path_fingerprints_for_claim(key)))
        self.max_grounded_lineage_paths = max(
            self.max_grounded_lineage_paths, len(lineage)
        )
        self.grounded_lineage_path_total += len(lineage)
        return lineage

    def lineage_fingerprint_for_parents(
        self,
        parents: Iterable[ClaimKey],
    ) -> LineageFingerprint:
        parent_tuple = tuple(parents)
        parent_paths = [
            list(self.effective_grounded_lineage(parent)) for parent in parent_tuple
        ]
        payload = (
            "parent-lineage",
            tuple(
                sorted(
                    (parent, tuple(sorted(paths)))
                    for parent, paths in zip(parent_tuple, parent_paths, strict=True)
                )
            ),
        )
        encoded = _canonical_bytes(payload)
        self.lineage_fingerprint_calculations += 1
        self.lineage_hash_bytes += len(encoded)
        self.lineage_parent_count += len(parent_tuple)
        return hashlib.sha256(encoded).hexdigest()

    def _record_event(
        self,
        event: str,
        support: Support,
    ) -> None:
        self.event_history.append(
            EventOccurrence(
                event=event,
                support_id=support.support_id,
                packet=support.packet.numeric_tuple(),
                kind=support.kind,
                semantic_parents=support.parents,
                lineage_fingerprint=support.lineage_fingerprint,
            )
        )

    def _refresh_after_support_change(self, support_id: int) -> None:
        self._refresh_all_statuses()

    def _refresh_after_slot_change(self, stable_reference: int) -> None:
        self._refresh_all_statuses()

    def _add_support(
        self,
        packet: Packet,
        kind: int,
        parents: Iterable[ClaimKey] = (),
        lineage_fingerprint: LineageFingerprint = NO_GROUNDED_LINEAGE,
    ) -> int:
        self.support_insert_attempts += 1
        packet.validate()
        parent_tuple = tuple(
            sorted((int(ref), int(value)) for ref, value in parents)
        )
        key = self.claim_key(packet)
        for parent in parent_tuple:
            if parent not in self.claims:
                raise KeyError(f"missing parent claim {parent}")
        if kind == SUPPORT_DERIVED and any(
            self._claim_depends_on(parent, key) for parent in parent_tuple
        ):
            raise ValueError("support cycle detected")
        semantic_key = self._semantic_key(packet, kind, parent_tuple)
        canonical_key = self._canonical_key(
            packet, kind, parent_tuple, lineage_fingerprint
        )
        existing_id = self._canonical.get(canonical_key)
        if existing_id is not None:
            support = self.supports[existing_id]
            self.canonical_support_reuses += 1
            if kind == SUPPORT_DERIVED:
                self.semantic_duplicates_reused += 1
            if not support.enabled:
                support.enabled = True
                self._index_world_support(support)
                self.ledger.append(LEDGER_RESTORE, existing_id)
            self._record_event("canonical_reuse", support)
            self._refresh_after_support_change(existing_id)
            return existing_id
        if kind == SUPPORT_DERIVED and self._semantic_lineages[semantic_key]:
            self.provenance_changes += 1
        self._ensure_capacity(key)
        support_id = self._next_support_id
        support = Support(
            support_id=support_id,
            packet=packet,
            kind=kind,
            semantic_parent_claim_keys=parent_tuple,
            parent_lineage_fingerprint=lineage_fingerprint,
            enabled=True,
        )
        support.validate()
        claim = self.claims.get(key)
        if claim is None:
            claim = Claim(packet.stable_reference, packet.value)
            self.claims[key] = claim
            self._claim_keys_by_reference[packet.stable_reference].append(key)
        claim.support_ids.append(support_id)
        if claim.status == STATUS_REVOKED:
            self.revoked_support_total += 1
        self.supports[support_id] = support
        self._canonical[canonical_key] = support_id
        self._semantic_lineages[semantic_key].add(lineage_fingerprint)
        self._support_ids_by_reference[packet.stable_reference].add(support_id)
        self._index_world_support(support)
        for parent in parent_tuple:
            self.children.setdefault(parent, set()).add(support_id)
        self._next_support_id += 1
        self.canonical_support_creations += 1
        self._record_event("canonical_create", support)
        lineage_int = int(lineage_fingerprint, 16)
        flattened_parents = tuple(value for pair in parent_tuple for value in pair)
        self.ledger.append(
            LEDGER_ADD,
            support_id,
            kind,
            packet.stable_reference,
            packet.act,
            packet.subject,
            packet.relation,
            packet.object,
            packet.value,
            len(parent_tuple),
            *flattened_parents,
            lineage_int,
        )
        self._refresh_after_support_change(support_id)
        self.peak_claims = max(self.peak_claims, len(self.claims))
        return support_id

    def propose(self, packet: Packet) -> int:
        if packet.act != ACT_PROPOSE:
            raise ValueError("proposal packet must use ACT_PROPOSE")
        return self._add_support(packet, SUPPORT_PROPOSAL)

    def derive(
        self,
        packet: Packet,
        parents: Iterable[ClaimKey],
    ) -> int:
        if packet.act != ACT_DERIVE:
            raise ValueError("derived packet must use ACT_DERIVE")
        parent_tuple = tuple(parents)
        lineage = self.lineage_fingerprint_for_parents(parent_tuple)
        return self._add_support(packet, SUPPORT_DERIVED, parent_tuple, lineage)

    def observe(self, packet: Packet) -> int:
        if packet.act != ACT_OBSERVE:
            raise ValueError("world packet must use ACT_OBSERVE")
        packet.validate()
        conflicting_world = False
        to_disable: list[int] = []
        for support_id in sorted(
            self._support_ids_by_reference.get(packet.stable_reference, ())
        ):
            support = self.supports[support_id]
            if not support.enabled:
                continue
            if support.kind == SUPPORT_WORLD and support.packet.value != packet.value:
                conflicting_world = True
            elif support.kind != SUPPORT_WORLD:
                to_disable.append(support_id)
        support_id = self._add_support(
            packet,
            SUPPORT_WORLD,
            lineage_fingerprint=canonical_hash(("world", packet.numeric_tuple())),
        )
        for prior_support_id in sorted(set(to_disable)):
            self.revoke_support(prior_support_id)
        if conflicting_world:
            self.conflicted_slot_count += 1
            self._refresh_after_slot_change(packet.stable_reference)
        return support_id

    def _index_world_support(self, support: Support) -> None:
        if support.kind == SUPPORT_WORLD and support.enabled:
            self._active_world_values[support.packet.stable_reference].add(
                support.packet.value
            )

    def _unindex_world_support(self, support: Support) -> None:
        if support.kind != SUPPORT_WORLD:
            return
        values = self._active_world_values.get(support.packet.stable_reference)
        if values is None:
            return
        if not any(
            other is not support
            and other.enabled
            and other.kind == SUPPORT_WORLD
            and other.packet.stable_reference == support.packet.stable_reference
            and other.packet.value == support.packet.value
            for other in self.supports.values()
        ):
            values.discard(support.packet.value)
        if not values:
            self._active_world_values.pop(support.packet.stable_reference, None)

    def revoke_support(self, support_id: int) -> None:
        support = self.supports[support_id]
        if not support.enabled:
            return
        self._unindex_world_support(support)
        support.enabled = False
        self.revoked_support_count += 1
        self.ledger.append(LEDGER_REVOKE, support_id)
        self._refresh_all_statuses()

    def restore_support(self, support_id: int) -> None:
        support = self.supports[support_id]
        if support.enabled:
            return
        support.enabled = True
        self._index_world_support(support)
        self.ledger.append(LEDGER_RESTORE, support_id)
        self._refresh_all_statuses()

    def _refresh_all_statuses(self) -> None:
        world_values: dict[int, set[int]] = {}
        for key, claim in self.claims.items():
            for support_id in claim.support_ids:
                support = self.supports[support_id]
                if support.enabled and support.kind == SUPPORT_WORLD:
                    world_values.setdefault(key[0], set()).add(key[1])
        for key in sorted(self.claims):
            claim = self.claims[key]
            old = claim.status
            if not self._claim_has_effective_support(key):
                claim.status = STATUS_REVOKED
            elif len(world_values.get(key[0], set())) > 1:
                claim.status = STATUS_CONFLICTED
            elif self._claim_grounded(key):
                claim.status = STATUS_COMMITTED
            else:
                claim.status = STATUS_PROVISIONAL
            if claim.status != old:
                if old == STATUS_REVOKED:
                    self.revoked_support_total -= len(claim.support_ids)
                elif claim.status == STATUS_REVOKED:
                    self.revoked_support_total += len(claim.support_ids)
                self.ledger.append(LEDGER_STATUS, key[0], key[1], old, claim.status)

    def support_effective(self, support_id: int) -> bool:
        return self._support_effective(support_id)

    def support_grounded(self, support_id: int) -> bool:
        return self._support_grounded(support_id)

    def committed_values(self, stable_reference: int) -> tuple[int, ...]:
        return tuple(
            key[1]
            for key in self._claim_keys_by_reference.get(stable_reference, ())
            if self.claims[key].status == STATUS_COMMITTED
        )

    def status(self, stable_reference: int, value: int) -> int:
        claim = self.claims.get((stable_reference, value))
        return STATUS_REVOKED if claim is None else claim.status

    def counts(self) -> dict[str, int]:
        statuses = [claim.status for claim in self.claims.values()]
        return {
            "claims": len(statuses),
            "provisional": statuses.count(STATUS_PROVISIONAL),
            "committed": statuses.count(STATUS_COMMITTED),
            "revoked": statuses.count(STATUS_REVOKED),
            "conflicted": statuses.count(STATUS_CONFLICTED),
            "active_supports": sum(support.enabled for support in self.supports.values()),
            "canonical_supports": len(self.supports),
            "historical_events": len(self.event_history),
            "revoked_support_total": self.revoked_support_total,
            "peak_claims": self.peak_claims,
            "ledger_events": self.ledger.count,
        }

    def engineering_metrics(self) -> dict[str, int]:
        return {
            "support_insert_attempts": self.support_insert_attempts,
            "canonical_support_creations": self.canonical_support_creations,
            "canonical_support_reuses": self.canonical_support_reuses,
            "provenance_changes": self.provenance_changes,
            "semantic_duplicates_reused": self.semantic_duplicates_reused,
            "active_supports": sum(support.enabled for support in self.supports.values()),
            "historical_events": len(self.event_history),
            "lineage_fingerprint_calculations": self.lineage_fingerprint_calculations,
            "grounded_lineage_traversals": self.grounded_lineage_traversals,
            "lineage_hash_bytes": self.lineage_hash_bytes,
            "lineage_parent_count": self.lineage_parent_count,
            "grounded_lineage_path_total": self.grounded_lineage_path_total,
            "max_grounded_lineage_paths": self.max_grounded_lineage_paths,
            "lineage_cache_hits": self.lineage_cache_hits,
            "lineage_cache_misses": self.lineage_cache_misses,
        }


class IncrementalProvenanceStore(ReferenceProvenanceStore):
    """Dirty-cone implementation with the reference store as semantic oracle."""

    def __init__(self, max_claims: int = 8192) -> None:
        super().__init__(max_claims=max_claims)
        self._support_effective_cache: dict[int, bool] = {}
        self._support_grounded_cache: dict[int, bool] = {}
        self._claim_effective_cache: dict[ClaimKey, bool] = {}
        self._claim_grounded_cache: dict[ClaimKey, bool] = {}
        self._claim_lineage_cache: dict[ClaimKey, tuple[str, ...]] = {}
        self.dirty_claims_processed = 0
        self.dirty_supports_processed = 0
        self.claims_visited = 0
        self.supports_visited = 0

    def effective_grounded_lineage(self, key: ClaimKey) -> tuple[str, ...]:
        if key in self._claim_lineage_cache:
            self.lineage_cache_hits += 1
            return self._claim_lineage_cache[key]
        self.lineage_cache_misses += 1
        lineage = super().effective_grounded_lineage(key)
        self._claim_lineage_cache[key] = lineage
        return lineage

    def _enqueue_support(
        self,
        queue: deque[tuple[int, object]],
        support_ids: set[int],
        support_id: int,
    ) -> None:
        if support_id not in support_ids:
            support_ids.add(support_id)
            queue.append((0, support_id))

    def _enqueue_claim(
        self,
        queue: deque[tuple[int, object]],
        claim_keys: set[ClaimKey],
        key: ClaimKey,
        initial_statuses: dict[ClaimKey, int] | None = None,
    ) -> None:
        if key in self.claims and key not in claim_keys:
            if initial_statuses is not None:
                initial_statuses.setdefault(key, self.claims[key].status)
            claim_keys.add(key)
            queue.append((1, key))

    def _propagate(
        self,
        initial_support_ids: Iterable[int] = (),
        initial_claims: Iterable[ClaimKey] = (),
        slot_references: Iterable[int] = (),
    ) -> None:
        queue: deque[tuple[int, object]] = deque()
        queued_supports: set[int] = set()
        queued_claims: set[ClaimKey] = set()
        initial_statuses: dict[ClaimKey, int] = {}
        for support_id in sorted(set(initial_support_ids)):
            self._enqueue_support(queue, queued_supports, support_id)
        for key in sorted(set(initial_claims)):
            self._enqueue_claim(queue, queued_claims, key, initial_statuses)
        for reference in sorted(set(slot_references)):
            for key in sorted(self.claims):
                if key[0] == reference:
                    self._enqueue_claim(queue, queued_claims, key, initial_statuses)

        while queue:
            kind, item = queue.popleft()
            if kind == 0:
                support_id = int(item)
                queued_supports.remove(support_id)
                support = self.supports[support_id]
                self.dirty_supports_processed += 1
                self.supports_visited += 1
                if not support.enabled:
                    effective = grounded = False
                elif support.kind == SUPPORT_DERIVED:
                    effective = all(
                        self._claim_effective_cache.get(parent, False)
                        for parent in support.parents
                    )
                    grounded = effective and all(
                        self._claim_grounded_cache.get(parent, False)
                        for parent in support.parents
                    )
                    grounded = grounded and (
                        support.lineage_fingerprint
                        == self.lineage_fingerprint_for_parents(support.parents)
                    )
                else:
                    effective = True
                    grounded = support.kind == SUPPORT_WORLD
                old_effective = self._support_effective_cache.get(support_id, False)
                old_grounded = self._support_grounded_cache.get(support_id, False)
                self._support_effective_cache[support_id] = effective
                self._support_grounded_cache[support_id] = grounded
                if effective != old_effective or grounded != old_grounded:
                    self._enqueue_claim(
                        queue,
                        queued_claims,
                        self.claim_key(support.packet),
                        initial_statuses,
                    )
                continue
            key = item
            if not isinstance(key, tuple):
                raise TypeError("dirty claim key must be a tuple")
            queued_claims.remove(key)
            self.dirty_claims_processed += 1
            self.claims_visited += 1
            claim = self.claims[key]
            old_effective = self._claim_effective_cache.get(key, False)
            old_grounded = self._claim_grounded_cache.get(key, False)
            old_lineage = self._claim_lineage_cache.get(key, ())
            effective = any(
                self._support_effective_cache.get(support_id, False)
                for support_id in claim.support_ids
            )
            grounded = any(
                self._support_grounded_cache.get(support_id, False)
                for support_id in claim.support_ids
            )
            self._claim_effective_cache[key] = effective
            self._claim_grounded_cache[key] = grounded
            self._claim_lineage_cache.pop(key, None)
            lineage = self.effective_grounded_lineage(key)
            self._claim_lineage_cache[key] = lineage
            if (
                effective != old_effective
                or grounded != old_grounded
                or lineage != old_lineage
            ):
                for child_support_id in sorted(self.children.get(key, ())):
                    self._enqueue_support(queue, queued_supports, child_support_id)
            world_values = self._active_world_values.get(key[0], ())
            old_status = claim.status
            if not effective:
                claim.status = STATUS_REVOKED
            elif len(world_values) > 1:
                claim.status = STATUS_CONFLICTED
            elif grounded:
                claim.status = STATUS_COMMITTED
            else:
                claim.status = STATUS_PROVISIONAL
            if old_status == STATUS_REVOKED and claim.status != STATUS_REVOKED:
                self.revoked_support_total -= len(claim.support_ids)
            elif old_status != STATUS_REVOKED and claim.status == STATUS_REVOKED:
                self.revoked_support_total += len(claim.support_ids)

        for key in sorted(initial_statuses):
            old_status = initial_statuses[key]
            new_status = self.claims[key].status
            if new_status != old_status:
                self.ledger.append(
                    LEDGER_STATUS,
                    key[0],
                    key[1],
                    old_status,
                    new_status,
                )

    def _refresh_all_statuses(self) -> None:
        self._propagate(
            initial_support_ids=self.supports,
            initial_claims=self.claims,
            slot_references=(),
        )

    def _refresh_after_support_change(self, support_id: int) -> None:
        self._propagate(
            initial_support_ids=(support_id,),
            initial_claims=(self.claim_key(self.supports[support_id].packet),),
        )

    def _refresh_after_slot_change(self, stable_reference: int) -> None:
        self._propagate(slot_references=(stable_reference,))

    def _support_effective(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._support_effective_cache.get(support_id, False)

    def _claim_has_effective_support(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._claim_effective_cache.get(key, False)

    def _support_grounded(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._support_grounded_cache.get(support_id, False)

    def _claim_grounded(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._claim_grounded_cache.get(key, False)

    def revoke_support(self, support_id: int) -> None:
        support = self.supports[support_id]
        if not support.enabled:
            return
        self._unindex_world_support(support)
        support.enabled = False
        self.revoked_support_count += 1
        self.ledger.append(LEDGER_REVOKE, support_id)
        if support.kind == SUPPORT_WORLD:
            self._propagate(
                initial_support_ids=(support_id,),
                slot_references=(support.packet.stable_reference,),
            )
        else:
            self._propagate(
                initial_support_ids=(support_id,),
                initial_claims=(self.claim_key(support.packet),),
            )

    def restore_support(self, support_id: int) -> None:
        support = self.supports[support_id]
        if support.enabled:
            return
        support.enabled = True
        self._index_world_support(support)
        self.ledger.append(LEDGER_RESTORE, support_id)
        if support.kind == SUPPORT_WORLD:
            self._propagate(
                initial_support_ids=(support_id,),
                slot_references=(support.packet.stable_reference,),
            )
        else:
            self._propagate(
                initial_support_ids=(support_id,),
                initial_claims=(self.claim_key(support.packet),),
            )

    def engineering_metrics(self) -> dict[str, int]:
        result = super().engineering_metrics()
        result.update(
            {
                "dirty_claims_processed": self.dirty_claims_processed,
                "dirty_supports_processed": self.dirty_supports_processed,
                "claims_visited": self.claims_visited,
                "supports_visited": self.supports_visited,
                "lineage_cache_hits": self.lineage_cache_hits,
                "lineage_cache_misses": self.lineage_cache_misses,
            }
        )
        return result


EpistemicStore = IncrementalProvenanceStore
ProvenanceStore = IncrementalProvenanceStore


def _coord_packet(
    reference: int,
    value: int,
    act: int = ACT_PROPOSE,
) -> Packet:
    return Packet(reference, act, reference, REL_X, 0, value)
