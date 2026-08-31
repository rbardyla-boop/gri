from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from collections import defaultdict, deque
from typing import Iterable

import numpy as np

# Packet ACT codes. Runtime packets contain integers only.
ACT_PROPOSE = 1
ACT_OBSERVE = 2
ACT_DERIVE = 3

# Relation codes.
REL_X = 1
REL_Y = 2
REL_LEFT_OF = 3
REL_ABOVE = 4
REL_ORDER_PARITY = 5

# Support kinds.
SUPPORT_PROPOSAL = 1
SUPPORT_WORLD = 2
SUPPORT_DERIVED = 3

# Claim states.
STATUS_PROVISIONAL = 1
STATUS_COMMITTED = 2
STATUS_REVOKED = 3
STATUS_CONFLICTED = 4

# Numeric transition-ledger event codes.
LEDGER_ADD = 1
LEDGER_REVOKE = 2
LEDGER_STATUS = 3
LEDGER_RESTORE = 4

GRID_MAX = 11
ClaimKey = tuple[int, int]


@dataclass(frozen=True)
class Packet:
    stable_reference: int
    act: int
    subject: int
    relation: int
    object: int
    value: int

    def validate(self) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (
                self.stable_reference,
                self.act,
                self.subject,
                self.relation,
                self.object,
                self.value,
            )
        ):
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
    parents: tuple[ClaimKey, ...] = ()
    enabled: bool = True

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


@dataclass
class Claim:
    stable_reference: int
    value: int
    support_ids: list[int] = field(default_factory=list)
    status: int = STATUS_PROVISIONAL


class NumericLedger:
    """Append-only numeric transition ledger with deterministic replay."""

    def __init__(self) -> None:
        self._head = bytes(32)
        self._events: list[tuple[int, ...]] = []

    def append(self, *fields: int) -> None:
        event = tuple(int(value) for value in fields)
        raw = json.dumps(event, separators=(",", ":")).encode("ascii")
        self._head = hashlib.sha256(self._head + raw).digest()
        self._events.append(event)

    @property
    def head_sha256(self) -> str:
        return self._head.hex()

    @property
    def count(self) -> int:
        return len(self._events)

    def replay_head(self) -> str:
        head = bytes(32)
        for event in self._events:
            raw = json.dumps(event, separators=(",", ":")).encode("ascii")
            head = hashlib.sha256(head + raw).digest()
        return head.hex()


def _uvarint(value: int) -> bytes:
    if value < 0:
        raise ValueError("uvarint requires non-negative integer")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_uvarint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("truncated varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, offset
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _zigzag(value: int) -> int:
    return value * 2 if value >= 0 else (-value * 2) - 1


def _unzigzag(value: int) -> int:
    return value // 2 if value % 2 == 0 else -(value // 2) - 1


def encode_packet(packet: Packet) -> bytes:
    """In-band stable reference + unsigned varints + ZigZag VALUE."""
    fields = packet.numeric_tuple()
    encoded = bytearray()
    for value in fields[:-1]:
        encoded.extend(_uvarint(value))
    encoded.extend(_uvarint(_zigzag(fields[-1])))
    return bytes(encoded)


def decode_packet(data: bytes) -> Packet:
    values: list[int] = []
    offset = 0
    for _ in range(5):
        value, offset = _read_uvarint(data, offset)
        values.append(value)
    signed, offset = _read_uvarint(data, offset)
    if offset != len(data):
        raise ValueError("trailing packet bytes")
    packet = Packet(*values, _unzigzag(signed))
    packet.validate()
    return packet


class ReferenceEpistemicStore:
    """Reversible claim/support DAG with a separate durability authority.

    Prediction-derived claims may propagate while provisional. A claim becomes
    durable only when an active support path is rooted in direct world
    observation. Direct observation of a stable slot disables conflicting
    non-world supports. Descendants then become unsupported automatically
    unless an alternate active parent support remains.
    """

    def __init__(self, max_claims: int = 8192) -> None:
        if max_claims <= 0:
            raise ValueError("max_claims must be positive")
        self.max_claims = int(max_claims)
        self.supports: dict[int, Support] = {}
        self.claims: dict[ClaimKey, Claim] = {}
        self.children: dict[ClaimKey, set[int]] = {}
        self._next_support_id = 1
        self.ledger = NumericLedger()
        self.peak_claims = 0
        self.revoked_support_count = 0
        self.cascaded_support_count = 0
        self.conflicted_slot_count = 0
        self._engineering = defaultdict(int)

    def reset_engineering_metrics(self) -> None:
        self._engineering.clear()

    def engineering_metrics(self) -> dict[str, int]:
        return dict(self._engineering)

    def _count_engineering(self, name: str, amount: int = 1) -> None:
        self._engineering[name] += amount

    @staticmethod
    def claim_key(packet: Packet) -> ClaimKey:
        return (packet.stable_reference, packet.value)

    def _ensure_capacity(self, key: ClaimKey) -> None:
        if key not in self.claims and len(self.claims) >= self.max_claims:
            raise MemoryError("epistemic active-claim bound exceeded")

    def _add_support(
        self,
        packet: Packet,
        kind: int,
        parents: Iterable[ClaimKey] = (),
    ) -> int:
        self._count_engineering("support_insertions")
        packet.validate()
        parent_tuple = tuple((int(ref), int(value)) for ref, value in parents)
        support_id = self._next_support_id
        support = Support(support_id, packet, kind, parent_tuple, True)
        support.validate()
        for parent in parent_tuple:
            if parent not in self.claims:
                raise KeyError(f"missing parent claim {parent}")
        key = self.claim_key(packet)
        if kind == SUPPORT_DERIVED and any(
            self._claim_depends_on(parent, key) for parent in parent_tuple
        ):
            raise ValueError("support cycle detected")
        self._ensure_capacity(key)
        claim = self.claims.setdefault(key, Claim(packet.stable_reference, packet.value))
        claim.support_ids.append(support_id)
        self.supports[support_id] = support
        for parent in parent_tuple:
            self.children.setdefault(parent, set()).add(support_id)
        self._next_support_id += 1
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
        )
        self._refresh_all_statuses()
        self.peak_claims = max(self.peak_claims, len(self.claims))
        return support_id

    def _claim_depends_on(
        self,
        start: ClaimKey,
        target: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        """Return whether a claim's existing supports depend on ``target``."""
        self._count_engineering("recursive_calls")
        self._count_engineering("claims_visited")
        if start == target:
            return True
        if start in trail:
            raise ValueError("support cycle detected")
        claim = self.claims.get(start)
        if claim is None:
            return False
        next_trail = trail | {start}
        for support_id in claim.support_ids:
            support = self.supports[support_id]
            if support.kind == SUPPORT_DERIVED and any(
                self._claim_depends_on(parent, target, next_trail)
                for parent in support.parents
            ):
                return True
        return False

    def propose(self, packet: Packet) -> int:
        if packet.act != ACT_PROPOSE:
            raise ValueError("proposal packet must use ACT_PROPOSE")
        return self._add_support(packet, SUPPORT_PROPOSAL)

    def derive(self, packet: Packet, parents: Iterable[ClaimKey]) -> int:
        if packet.act != ACT_DERIVE:
            raise ValueError("derived packet must use ACT_DERIVE")
        return self._add_support(packet, SUPPORT_DERIVED, parents)

    def observe(self, packet: Packet) -> int:
        if packet.act != ACT_OBSERVE:
            raise ValueError("world packet must use ACT_OBSERVE")
        packet.validate()
        conflicting_world = False
        to_disable: list[int] = []
        for (stable_reference, _), claim in self.claims.items():
            if stable_reference != packet.stable_reference:
                continue
            for support_id in claim.support_ids:
                support = self.supports[support_id]
                if not support.enabled:
                    continue
                if support.kind == SUPPORT_WORLD and support.packet.value != packet.value:
                    conflicting_world = True
                elif support.kind != SUPPORT_WORLD:
                    to_disable.append(support_id)

        # Add the independent witness first, then retire all prediction/derivation
        # supports for this exact observed slot. Matching claims stay alive through
        # the new world support; conflicting claims lose their non-world support.
        support_id = self._add_support(packet, SUPPORT_WORLD)
        for prior_support_id in to_disable:
            self.revoke_support(prior_support_id)
        if conflicting_world:
            self.conflicted_slot_count += 1
            self._refresh_all_statuses()
        return support_id

    def _claim_has_effective_support(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        if key in trail:
            raise ValueError("support cycle detected")
        claim = self.claims.get(key)
        if claim is None:
            return False
        return any(
            self._support_effective(support_id, trail | {key})
            for support_id in claim.support_ids
        )

    def _support_effective(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        self._count_engineering("recursive_calls")
        self._count_engineering("supports_visited")
        support = self.supports[support_id]
        if not support.enabled:
            return False
        if support.kind != SUPPORT_DERIVED:
            return True
        return all(
            self._claim_has_effective_support(parent, trail)
            for parent in support.parents
        )

    def _claim_grounded(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        if key in trail:
            raise ValueError("support cycle detected")
        claim = self.claims.get(key)
        if claim is None:
            return False
        return any(
            self._support_grounded(support_id, trail | {key})
            for support_id in claim.support_ids
        )

    def _support_grounded(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        self._count_engineering("recursive_calls")
        self._count_engineering("supports_visited")
        support = self.supports[support_id]
        if not self._support_effective(support_id):
            return False
        if support.kind == SUPPORT_WORLD:
            return True
        if support.kind == SUPPORT_PROPOSAL:
            return False
        return all(self._claim_grounded(parent, trail) for parent in support.parents)

    def _effective_map(self) -> dict[int, bool]:
        self._count_engineering("before_after_map_builds")
        self._count_engineering("supports_visited", len(self.supports))
        return {
            support_id: self._support_effective(support_id)
            for support_id in self.supports
        }

    def _refresh_all_statuses(self) -> None:
        self._count_engineering("status_refresh_calls")
        self._count_engineering("claims_visited", len(self.claims))
        slot_world_values: dict[int, set[int]] = {}
        for key, claim in self.claims.items():
            reference, value = key
            if any(
                self.supports[support_id].enabled
                and self.supports[support_id].kind == SUPPORT_WORLD
                for support_id in claim.support_ids
            ):
                slot_world_values.setdefault(reference, set()).add(value)

        for key in sorted(self.claims):
            claim = self.claims[key]
            old = claim.status
            reference, _ = key
            effective = [
                support_id
                for support_id in claim.support_ids
                if self._support_effective(support_id)
            ]
            if not effective:
                claim.status = STATUS_REVOKED
            elif len(slot_world_values.get(reference, set())) > 1:
                claim.status = STATUS_CONFLICTED
            elif self._claim_grounded(key):
                claim.status = STATUS_COMMITTED
            else:
                claim.status = STATUS_PROVISIONAL
            if claim.status != old:
                self.ledger.append(
                    LEDGER_STATUS,
                    claim.stable_reference,
                    claim.value,
                    old,
                    claim.status,
                )

    def revoke_support(self, support_id: int) -> None:
        self._count_engineering("support_revocations")
        support = self.supports[support_id]
        if not support.enabled:
            return
        before_effective = self._effective_map()
        support.enabled = False
        self.revoked_support_count += 1
        self.ledger.append(LEDGER_REVOKE, support_id)
        self._refresh_all_statuses()
        after_effective = self._effective_map()
        self.cascaded_support_count += sum(
            before_effective[child_id]
            and not after_effective[child_id]
            and child_id != support_id
            for child_id in before_effective
        )

    def restore_support(self, support_id: int) -> None:
        support = self.supports[support_id]
        if support.enabled:
            return
        support.enabled = True
        self.ledger.append(LEDGER_RESTORE, support_id)
        self._refresh_all_statuses()

    def status(self, stable_reference: int, value: int) -> int:
        claim = self.claims.get((stable_reference, value))
        return STATUS_REVOKED if claim is None else claim.status

    def committed_values(self, stable_reference: int) -> tuple[int, ...]:
        return tuple(
            sorted(
                value
                for (reference, value), claim in self.claims.items()
                if reference == stable_reference and claim.status == STATUS_COMMITTED
            )
        )

    def support_effective(self, support_id: int) -> bool:
        return self._support_effective(support_id)

    def counts(self) -> dict[str, int]:
        values = [claim.status for claim in self.claims.values()]
        return {
            "claims": len(values),
            "provisional": sum(value == STATUS_PROVISIONAL for value in values),
            "committed": sum(value == STATUS_COMMITTED for value in values),
            "revoked": sum(value == STATUS_REVOKED for value in values),
            "conflicted": sum(value == STATUS_CONFLICTED for value in values),
            "peak_claims": self.peak_claims,
            "ledger_events": self.ledger.count,
        }


class IncrementalEpistemicStore(ReferenceEpistemicStore):
    """Incrementally maintained equivalent of :class:`ReferenceEpistemicStore`.

    The reference store intentionally recomputes every claim after each
    mutation. This implementation keeps effective/grounded support state and
    propagates only through reverse dependency edges whose inputs changed.
    ``ReferenceEpistemicStore`` remains available for differential testing.
    """

    def __init__(self, max_claims: int = 8192) -> None:
        super().__init__(max_claims=max_claims)
        self.support_to_claim: dict[int, ClaimKey] = {}
        self._claims_by_reference: dict[int, set[ClaimKey]] = defaultdict(set)
        self._support_effective_cache: dict[int, bool] = {}
        self._support_grounded_cache: dict[int, bool] = {}
        self._claim_effective_cache: dict[ClaimKey, bool] = {}
        self._claim_grounded_cache: dict[ClaimKey, bool] = {}

    def _queue_metric(self, name: str, amount: int = 1) -> None:
        self._count_engineering(name, amount)

    def _claim_depends_on(
        self,
        start: ClaimKey,
        target: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        """Iterative cycle check used by derived-support insertion."""
        del trail
        pending = [start]
        visited: set[ClaimKey] = set()
        while pending:
            key = pending.pop()
            if key == target:
                return True
            if key in visited:
                continue
            visited.add(key)
            self._queue_metric("claims_visited")
            claim = self.claims.get(key)
            if claim is None:
                continue
            for support_id in claim.support_ids:
                support = self.supports[support_id]
                if support.kind == SUPPORT_DERIVED:
                    pending.extend(support.parents)
        return False

    def _enqueue_support(
        self,
        queue: deque[tuple[int, object]],
        queued_supports: set[int],
        support_id: int,
    ) -> None:
        if support_id not in queued_supports:
            queue.append((0, support_id))
            queued_supports.add(support_id)
            self._queue_metric("dirty_queue_enqueues")

    def _enqueue_claim(
        self,
        queue: deque[tuple[int, object]],
        queued_claims: set[ClaimKey],
        key: ClaimKey,
    ) -> None:
        if key in self.claims and key not in queued_claims:
            queue.append((1, key))
            queued_claims.add(key)
            self._queue_metric("dirty_queue_enqueues")

    def _world_values(self, reference: int) -> set[int]:
        return {
            key[1]
            for key in self._claims_by_reference.get(reference, ())
            for support_id in self.claims[key].support_ids
            if self.supports[support_id].enabled
            and self.supports[support_id].kind == SUPPORT_WORLD
        }

    def _status_for_key(self, key: ClaimKey, world_values: set[int]) -> int:
        if not self._claim_effective_cache.get(key, False):
            return STATUS_REVOKED
        if len(world_values) > 1:
            return STATUS_CONFLICTED
        if self._claim_grounded_cache.get(key, False):
            return STATUS_COMMITTED
        return STATUS_PROVISIONAL

    def _propagate(
        self,
        *,
        initial_support_ids: Iterable[int] = (),
        initial_claims: Iterable[ClaimKey] = (),
        slot_references: Iterable[int] = (),
    ) -> None:
        """Recompute a deterministic dirty worklist until it reaches a fixpoint."""
        queue: deque[tuple[int, object]] = deque()
        queued_supports: set[int] = set()
        queued_claims: set[ClaimKey] = set()
        for support_id in sorted(set(initial_support_ids)):
            self._enqueue_support(queue, queued_supports, support_id)
        for key in sorted(set(initial_claims)):
            self._enqueue_claim(queue, queued_claims, key)
        for reference in sorted(set(slot_references)):
            for key in sorted(self._claims_by_reference.get(reference, ())):
                self._enqueue_claim(queue, queued_claims, key)

        while queue:
            item_kind, item = queue.popleft()
            if item_kind == 0:
                support_id = int(item)
                queued_supports.remove(support_id)
                support = self.supports[support_id]
                self._queue_metric("dirty_supports_processed")
                self._queue_metric("supports_visited")
                if not support.enabled:
                    effective = False
                    grounded = False
                elif support.kind == SUPPORT_DERIVED:
                    effective = all(
                        self._claim_effective_cache.get(parent, False)
                        for parent in support.parents
                    )
                    grounded = effective and all(
                        self._claim_grounded_cache.get(parent, False)
                        for parent in support.parents
                    )
                else:
                    effective = True
                    grounded = support.kind == SUPPORT_WORLD
                old_effective = self._support_effective_cache.get(support_id, False)
                old_grounded = self._support_grounded_cache.get(support_id, False)
                self._queue_metric("cache_hits" if support_id in self._support_effective_cache else "cache_misses")
                self._support_effective_cache[support_id] = effective
                self._support_grounded_cache[support_id] = grounded
                if effective != old_effective or grounded != old_grounded:
                    self._enqueue_claim(
                        queue,
                        queued_claims,
                        self.support_to_claim[support_id],
                    )
                continue

            key = item
            if not isinstance(key, tuple):
                raise TypeError("dirty claim key must be a tuple")
            queued_claims.remove(key)
            self._queue_metric("dirty_claims_processed")
            self._queue_metric("claims_visited")
            claim = self.claims[key]
            old_effective = self._claim_effective_cache.get(key, False)
            old_grounded = self._claim_grounded_cache.get(key, False)
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
            if effective != old_effective or grounded != old_grounded:
                for child_support_id in sorted(self.children.get(key, ())):
                    self._enqueue_support(
                        queue, queued_supports, child_support_id
                    )
            world_values = self._world_values(key[0])
            old_status = claim.status
            claim.status = self._status_for_key(key, world_values)
            if claim.status != old_status:
                self.ledger.append(
                    LEDGER_STATUS,
                    claim.stable_reference,
                    claim.value,
                    old_status,
                    claim.status,
                )

    def _add_support(
        self,
        packet: Packet,
        kind: int,
        parents: Iterable[ClaimKey] = (),
    ) -> int:
        self._count_engineering("support_insertions")
        packet.validate()
        parent_tuple = tuple((int(ref), int(value)) for ref, value in parents)
        support_id = self._next_support_id
        support = Support(support_id, packet, kind, parent_tuple, True)
        support.validate()
        for parent in parent_tuple:
            if parent not in self.claims:
                raise KeyError(f"missing parent claim {parent}")
        key = self.claim_key(packet)
        if kind == SUPPORT_DERIVED and any(
            self._claim_depends_on(parent, key) for parent in parent_tuple
        ):
            raise ValueError("support cycle detected")
        self._ensure_capacity(key)
        claim = self.claims.setdefault(key, Claim(packet.stable_reference, packet.value))
        claim.support_ids.append(support_id)
        self.supports[support_id] = support
        self.support_to_claim[support_id] = key
        self._claims_by_reference[packet.stable_reference].add(key)
        for parent in parent_tuple:
            self.children.setdefault(parent, set()).add(support_id)
        self._next_support_id += 1
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
        )
        self._propagate(
            initial_support_ids=(support_id,),
            initial_claims=(key,),
            slot_references=(packet.stable_reference,)
            if kind == SUPPORT_WORLD
            else (),
        )
        self.peak_claims = max(self.peak_claims, len(self.claims))
        return support_id

    def observe(self, packet: Packet) -> int:
        if packet.act != ACT_OBSERVE:
            raise ValueError("world packet must use ACT_OBSERVE")
        packet.validate()
        conflicting_world = False
        to_disable: list[int] = []
        for key in sorted(self._claims_by_reference.get(packet.stable_reference, ())):
            claim = self.claims[key]
            for support_id in claim.support_ids:
                support = self.supports[support_id]
                if not support.enabled:
                    continue
                if support.kind == SUPPORT_WORLD and support.packet.value != packet.value:
                    conflicting_world = True
                elif support.kind != SUPPORT_WORLD:
                    to_disable.append(support_id)
        support_id = self._add_support(packet, SUPPORT_WORLD)
        for prior_support_id in sorted(to_disable):
            self.revoke_support(prior_support_id)
        if conflicting_world:
            self.conflicted_slot_count += 1
            self._propagate(
                initial_claims=self._claims_by_reference.get(
                    packet.stable_reference, ()
                ),
                slot_references=(packet.stable_reference,),
            )
        return support_id

    def _descendant_support_cone(self, root: ClaimKey) -> set[int]:
        pending = [root]
        seen_claims: set[ClaimKey] = set()
        result: set[int] = set()
        while pending:
            key = pending.pop()
            if key in seen_claims:
                continue
            seen_claims.add(key)
            self._queue_metric("descendant_claims_visited")
            for support_id in sorted(self.children.get(key, ())):
                result.add(support_id)
                child_key = self.support_to_claim[support_id]
                pending.append(child_key)
        self._queue_metric("descendant_traversals")
        return result

    def revoke_support(self, support_id: int) -> None:
        self._count_engineering("support_revocations")
        support = self.supports[support_id]
        if not support.enabled:
            return
        affected_supports = self._descendant_support_cone(
            self.support_to_claim[support_id]
        )
        affected_supports.add(support_id)
        before_effective = {
            child_id: self._support_effective_cache.get(child_id, False)
            for child_id in affected_supports
        }
        support.enabled = False
        self.revoked_support_count += 1
        self.ledger.append(LEDGER_REVOKE, support_id)
        target_key = self.support_to_claim[support_id]
        self._propagate(
            initial_support_ids=(support_id,),
            initial_claims=(target_key,),
            slot_references=(support.packet.stable_reference,)
            if support.kind == SUPPORT_WORLD
            else (),
        )
        self.cascaded_support_count += sum(
            before_effective[child_id]
            and not self._support_effective_cache.get(child_id, False)
            and child_id != support_id
            for child_id in affected_supports
        )

    def restore_support(self, support_id: int) -> None:
        support = self.supports[support_id]
        if support.enabled:
            return
        support.enabled = True
        self.ledger.append(LEDGER_RESTORE, support_id)
        target_key = self.support_to_claim[support_id]
        self._propagate(
            initial_support_ids=(support_id,),
            initial_claims=(target_key,),
            slot_references=(support.packet.stable_reference,)
            if support.kind == SUPPORT_WORLD
            else (),
        )

    def _refresh_all_statuses(self) -> None:
        self._count_engineering("status_refresh_calls")
        self._propagate(
            initial_support_ids=self.supports,
            initial_claims=self.claims,
            slot_references=self._claims_by_reference,
        )

    def _claim_has_effective_support(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._claim_effective_cache.get(key, False)

    def _support_effective(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._support_effective_cache.get(support_id, False)

    def _claim_grounded(
        self,
        key: ClaimKey,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._claim_grounded_cache.get(key, False)

    def _support_grounded(
        self,
        support_id: int,
        trail: frozenset[ClaimKey] = frozenset(),
    ) -> bool:
        del trail
        return self._support_grounded_cache.get(support_id, False)

    def _effective_map(self) -> dict[int, bool]:
        self._count_engineering("before_after_map_builds")
        self._count_engineering("supports_visited", len(self._support_effective_cache))
        return dict(self._support_effective_cache)


# Existing successor callers use the optimized implementation. The explicit
# names above make differential tests and engineering benchmarks unambiguous.
EpistemicStore = IncrementalEpistemicStore


def quantize_state(state: np.ndarray) -> np.ndarray:
    array = np.asarray(state, dtype=np.float64)
    if array.shape != (6,):
        raise ValueError("expected six-coordinate object state")
    if not np.isfinite(array).all():
        raise ValueError("object state must be finite")
    scaled = np.rint((np.clip(array, -1.0, 1.0) + 1.0) * (GRID_MAX / 2.0))
    return scaled.astype(np.int64)


def entity_code(episode_ordinal: int, tick: int, object_index: int) -> int:
    if episode_ordinal < 0 or tick < 0 or not 0 <= object_index < 3:
        raise ValueError("invalid entity coordinates")
    return 1 + episode_ordinal * 1_000_000 + tick * 16 + object_index


def coordinate_slot(
    episode_ordinal: int,
    tick: int,
    object_index: int,
    axis: int,
) -> int:
    if axis not in (0, 1):
        raise ValueError("axis must be 0 or 1")
    return (
        1_000_000_000
        + episode_ordinal * 10_000_000
        + tick * 64
        + object_index * 2
        + axis
        + 1
    )


def relation_slot(
    episode_ordinal: int,
    tick: int,
    relation: int,
    left_object: int,
    right_object: int,
) -> int:
    if relation not in (REL_LEFT_OF, REL_ABOVE):
        raise ValueError("unsupported pair relation")
    pair_index = {(0, 1): 0, (0, 2): 1, (1, 2): 2}[(left_object, right_object)]
    relation_index = 0 if relation == REL_LEFT_OF else 1
    return (
        2_000_000_000
        + episode_ordinal * 10_000_000
        + tick * 64
        + pair_index * 2
        + relation_index
        + 1
    )


def parity_slot(episode_ordinal: int, tick: int) -> int:
    return 3_000_000_000 + episode_ordinal * 10_000_000 + tick + 1


def _coord_packet(
    state_cells: np.ndarray,
    episode_ordinal: int,
    tick: int,
    object_index: int,
    axis: int,
    act: int,
) -> Packet:
    relation = REL_X if axis == 0 else REL_Y
    return Packet(
        stable_reference=coordinate_slot(episode_ordinal, tick, object_index, axis),
        act=act,
        subject=entity_code(episode_ordinal, tick, object_index),
        relation=relation,
        object=0,
        value=int(state_cells[object_index * 2 + axis]),
    )


def _relation_value(
    state_cells: np.ndarray,
    left_object: int,
    right_object: int,
    relation: int,
) -> int:
    axis = 0 if relation == REL_LEFT_OF else 1
    left_value = int(state_cells[left_object * 2 + axis])
    right_value = int(state_cells[right_object * 2 + axis])
    return int(left_value < right_value)


def _relation_packet(
    state_cells: np.ndarray,
    episode_ordinal: int,
    tick: int,
    left_object: int,
    right_object: int,
    relation: int,
    act: int,
) -> Packet:
    return Packet(
        stable_reference=relation_slot(
            episode_ordinal,
            tick,
            relation,
            left_object,
            right_object,
        ),
        act=act,
        subject=entity_code(episode_ordinal, tick, left_object),
        relation=relation,
        object=entity_code(episode_ordinal, tick, right_object),
        value=_relation_value(state_cells, left_object, right_object, relation),
    )


def materialize_prediction(
    store: EpistemicStore,
    state: np.ndarray,
    episode_ordinal: int,
    tick: int,
) -> dict[str, object]:
    cells = quantize_state(state)
    coordinate_claims: dict[tuple[int, int], ClaimKey] = {}
    coordinate_packets: list[Packet] = []
    for object_index in range(3):
        for axis in (0, 1):
            packet = _coord_packet(
                cells,
                episode_ordinal,
                tick,
                object_index,
                axis,
                ACT_PROPOSE,
            )
            store.propose(packet)
            coordinate_packets.append(packet)
            coordinate_claims[(object_index, axis)] = store.claim_key(packet)

    relation_claims: list[ClaimKey] = []
    relation_supports: list[int] = []
    relation_packets: list[Packet] = []
    for relation in (REL_LEFT_OF, REL_ABOVE):
        axis = 0 if relation == REL_LEFT_OF else 1
        for left_object, right_object in ((0, 1), (0, 2), (1, 2)):
            packet = _relation_packet(
                cells,
                episode_ordinal,
                tick,
                left_object,
                right_object,
                relation,
                ACT_DERIVE,
            )
            support_id = store.derive(
                packet,
                (
                    coordinate_claims[(left_object, axis)],
                    coordinate_claims[(right_object, axis)],
                ),
            )
            relation_packets.append(packet)
            relation_claims.append(store.claim_key(packet))
            relation_supports.append(support_id)

    parity = Packet(
        stable_reference=parity_slot(episode_ordinal, tick),
        act=ACT_DERIVE,
        subject=entity_code(episode_ordinal, tick, 0),
        relation=REL_ORDER_PARITY,
        object=entity_code(episode_ordinal, tick, 2),
        value=int(sum(packet.value for packet in relation_packets) % 2),
    )
    parity_support = store.derive(parity, tuple(relation_claims))
    return {
        "coordinate_packets": tuple(coordinate_packets),
        "relation_packets": tuple(relation_packets),
        "parity_packet": parity,
        "coordinate_claims": coordinate_claims,
        "relation_claims": tuple(relation_claims),
        "relation_supports": tuple(relation_supports),
        "parity_support": parity_support,
    }


def _truth_packets(
    state: np.ndarray,
    episode_ordinal: int,
    tick: int,
    coordinate_act: int,
    derived_act: int,
) -> dict[str, object]:
    cells = quantize_state(state)
    coordinates: list[Packet] = []
    relations: list[Packet] = []
    for object_index in range(3):
        for axis in (0, 1):
            coordinates.append(
                _coord_packet(
                    cells,
                    episode_ordinal,
                    tick,
                    object_index,
                    axis,
                    coordinate_act,
                )
            )
    for relation in (REL_LEFT_OF, REL_ABOVE):
        for left_object, right_object in ((0, 1), (0, 2), (1, 2)):
            relations.append(
                _relation_packet(
                    cells,
                    episode_ordinal,
                    tick,
                    left_object,
                    right_object,
                    relation,
                    derived_act,
                )
            )
    parity = Packet(
        stable_reference=parity_slot(episode_ordinal, tick),
        act=derived_act,
        subject=entity_code(episode_ordinal, tick, 0),
        relation=REL_ORDER_PARITY,
        object=entity_code(episode_ordinal, tick, 2),
        value=int(sum(packet.value for packet in relations) % 2),
    )
    return {
        "coordinate_packets": tuple(coordinates),
        "relation_packets": tuple(relations),
        "parity_packet": parity,
    }


def evaluator_truth(
    state: np.ndarray,
    episode_ordinal: int,
    tick: int,
) -> dict[str, object]:
    """Evaluator-only truth projection; it is never passed to the learner."""
    return _truth_packets(
        state,
        episode_ordinal,
        tick,
        ACT_OBSERVE,
        ACT_OBSERVE,
    )


def materialize_world_witness(
    store: EpistemicStore,
    state: np.ndarray,
    episode_ordinal: int,
    tick: int,
) -> dict[str, object]:
    """Admit only direct coordinate observations as independent witnesses."""
    truth = _truth_packets(
        state,
        episode_ordinal,
        tick,
        ACT_OBSERVE,
        ACT_OBSERVE,
    )
    coordinates = tuple(truth["coordinate_packets"])
    for packet in coordinates:
        store.observe(packet)
    return {"coordinate_packets": coordinates}


def derive_from_committed_coordinates(
    store: EpistemicStore,
    state: np.ndarray,
    episode_ordinal: int,
    tick: int,
) -> dict[str, object]:
    """Recompute derived machine facts from the newly witnessed coordinates."""
    cells = quantize_state(state)
    coordinate_claims: dict[tuple[int, int], ClaimKey] = {}
    for object_index in range(3):
        for axis in (0, 1):
            packet = _coord_packet(
                cells,
                episode_ordinal,
                tick,
                object_index,
                axis,
                ACT_OBSERVE,
            )
            key = store.claim_key(packet)
            if store.status(*key) != STATUS_COMMITTED:
                raise RuntimeError("derived inference requires committed coordinate parents")
            coordinate_claims[(object_index, axis)] = key

    relation_claims: list[ClaimKey] = []
    relation_packets: list[Packet] = []
    relation_supports: list[int] = []
    for relation in (REL_LEFT_OF, REL_ABOVE):
        axis = 0 if relation == REL_LEFT_OF else 1
        for left_object, right_object in ((0, 1), (0, 2), (1, 2)):
            packet = _relation_packet(
                cells,
                episode_ordinal,
                tick,
                left_object,
                right_object,
                relation,
                ACT_DERIVE,
            )
            support_id = store.derive(
                packet,
                (
                    coordinate_claims[(left_object, axis)],
                    coordinate_claims[(right_object, axis)],
                ),
            )
            relation_packets.append(packet)
            relation_claims.append(store.claim_key(packet))
            relation_supports.append(support_id)

    parity = Packet(
        stable_reference=parity_slot(episode_ordinal, tick),
        act=ACT_DERIVE,
        subject=entity_code(episode_ordinal, tick, 0),
        relation=REL_ORDER_PARITY,
        object=entity_code(episode_ordinal, tick, 2),
        value=int(sum(packet.value for packet in relation_packets) % 2),
    )
    parity_support = store.derive(parity, tuple(relation_claims))
    return {
        "relation_packets": tuple(relation_packets),
        "parity_packet": parity,
        "relation_supports": tuple(relation_supports),
        "parity_support": parity_support,
    }


def flatten_prediction_packets(bundle: dict[str, object]) -> tuple[Packet, ...]:
    coordinates = tuple(bundle["coordinate_packets"])
    relations = tuple(bundle["relation_packets"])
    parity = bundle["parity_packet"]
    if not isinstance(parity, Packet):
        raise TypeError("invalid parity packet")
    return coordinates + relations + (parity,)


def flatten_truth_packets(bundle: dict[str, object]) -> tuple[Packet, ...]:
    coordinates = tuple(bundle["coordinate_packets"])
    relations = tuple(bundle["relation_packets"])
    parity = bundle["parity_packet"]
    if not isinstance(parity, Packet):
        raise TypeError("invalid parity packet")
    return coordinates + relations + (parity,)


def flatten_witness_packets(bundle: dict[str, object]) -> tuple[Packet, ...]:
    return tuple(bundle["coordinate_packets"])


def false_durable_count(
    store: EpistemicStore,
    truth_packets: Iterable[Packet],
) -> int:
    false_count = 0
    for packet in truth_packets:
        committed = store.committed_values(packet.stable_reference)
        false_count += sum(value != packet.value for value in committed)
    return false_count
