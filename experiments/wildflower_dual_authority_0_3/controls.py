from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterable, Protocol

from . import store


CONFIDENCE_THRESHOLD = 0.50


@dataclass(frozen=True)
class ControlSpec:
    name: str
    witnessing: bool
    dependency_tracking: bool
    grounded_recomputation: bool


CONTROL_SPECS = (
    ControlSpec("DUAL_AUTHORITY", True, True, True),
    ControlSpec("DIRECT_COMMIT", False, False, False),
    ControlSpec("CONFIDENCE_COMMIT", False, False, False),
    ControlSpec("DAG_NO_WITNESS", False, True, False),
    ControlSpec("WITNESS_NO_DAG", True, False, False),
    ControlSpec("WITNESS_PLUS_RECOMPUTE_NO_DAG", True, False, True),
    ControlSpec("DAG_PLUS_WITNESS_NO_RECOMPUTE", True, True, False),
)


@dataclass(frozen=True)
class StreamClaim:
    packet: store.Packet
    semantic_parents: tuple[store.ClaimKey, ...] = ()


@dataclass(frozen=True)
class MechanismFrame:
    """The only stream data a mechanism is allowed to consume."""

    tick: int
    predictions: tuple[StreamClaim, ...]
    witnesses: tuple[store.Packet, ...]
    recomputed: tuple[StreamClaim, ...]
    authority: float


@dataclass(frozen=True)
class RecordedTransition:
    """Mechanism input plus a quarantined evaluator-only truth sidecar."""

    tick: int
    predictions: tuple[StreamClaim, ...]
    witnesses: tuple[store.Packet, ...]
    recomputed: tuple[StreamClaim, ...]
    authority: float
    truth_packets: tuple[store.Packet, ...]
    preservation_targets: tuple[StreamClaim, ...] = ()
    recomputation_targets: tuple[StreamClaim, ...] = ()

    @property
    def mechanism_frame(self) -> MechanismFrame:
        return MechanismFrame(
            tick=self.tick,
            predictions=self.predictions,
            witnesses=self.witnesses,
            recomputed=self.recomputed,
            authority=self.authority,
        )


@dataclass
class ControlScore:
    name: str
    false_durable_claims: int = 0
    durable_slots: int = 0
    correct_durable_slots: int = 0
    stale_descendants: int = 0
    rollback_targets: int = 0
    rollback_successes: int = 0
    metric_a_opportunities: int = 0
    metric_a_successes: int = 0
    metric_b_opportunities: int = 0
    metric_b_successes: int = 0
    metric_b_reconstructed_supports: int = 0
    metric_b_false_positive_reconstructions: int = 0
    correction_events: int = 0
    provenance_query_capability: bool = False
    supports_touched_per_correction: int = 0
    historical_state_reconsidered_per_witness: int = 0
    active_support_count: int = 0
    runtime_steps: int = 0
    memory_growth: int = 0
    runtime_seconds: float = 0.0
    metric_scoring_seconds: float = 0.0
    stream_length: int = 0
    state_mutation_events: int = 0
    history_reconsideration_events: int = 0

    @property
    def durable_coverage(self) -> float:
        return (
            self.correct_durable_slots / self.durable_slots
            if self.durable_slots
            else 0.0
        )

    @property
    def rollback_recall(self) -> float:
        return (
            self.rollback_successes / self.rollback_targets
            if self.rollback_targets
            else 0.0
        )

    @property
    def metric_a_rate(self) -> float:
        return (
            self.metric_a_successes / self.metric_a_opportunities
            if self.metric_a_opportunities
            else 1.0
        )

    @property
    def metric_b_precision(self) -> float:
        return (
            self.metric_b_successes
            / (self.metric_b_successes + self.metric_b_false_positive_reconstructions)
            if self.metric_b_successes + self.metric_b_false_positive_reconstructions
            else 1.0
        )

    @property
    def metric_b_recall(self) -> float:
        return (
            self.metric_b_successes / self.metric_b_opportunities
            if self.metric_b_opportunities
            else 1.0
        )

    @property
    def metric_b_false_negatives(self) -> int:
        return self.metric_b_opportunities - self.metric_b_successes


class Mechanism(Protocol):
    name: str

    def consume(self, frame: MechanismFrame) -> None: ...

    def committed_values(self, stable_reference: int) -> tuple[int, ...]: ...

    def support_count(self) -> int: ...

    def supports_touched(self) -> int: ...

    def historical_state_reconsidered(self) -> int: ...

    def state_mutations(self) -> int: ...

    def has_grounded_provenance(self, stable_reference: int, value: int) -> bool: ...

    @property
    def provenance_query_capability(self) -> bool: ...


class _SimpleMechanism:
    def __init__(self, name: str, threshold: float | None = None) -> None:
        self.name = name
        self.threshold = threshold
        self.committed: dict[store.ClaimKey, set[int]] = {}
        self._values_by_reference: dict[int, set[int]] = {}
        self._supports = 0
        self._touched = 0
        self._reconsidered = 0
        self.provenance_query_capability = False

    def _commit(self, claim: StreamClaim) -> None:
        key = (claim.packet.stable_reference, claim.packet.value)
        self.committed.setdefault(key, set()).add(claim.packet.value)
        self._values_by_reference.setdefault(claim.packet.stable_reference, set()).add(
            claim.packet.value
        )
        self._supports += 1

    def consume(self, frame: MechanismFrame) -> None:
        for claim in frame.predictions:
            if self.threshold is None or frame.authority >= self.threshold:
                self._commit(claim)

    def committed_values(self, stable_reference: int) -> tuple[int, ...]:
        return tuple(sorted(self._values_by_reference.get(stable_reference, ())))

    def support_count(self) -> int:
        return self._supports

    def supports_touched(self) -> int:
        return self._touched

    def historical_state_reconsidered(self) -> int:
        return self._reconsidered

    def state_mutations(self) -> int:
        return self._supports

    def has_grounded_provenance(self, stable_reference: int, value: int) -> bool:
        del stable_reference, value
        return False


class _FlatWitnessMechanism:
    """Witness and optional recompute without a dependency graph or lineage."""

    def __init__(self, spec: ControlSpec) -> None:
        self.name = spec.name
        self.spec = spec
        self.committed: dict[int, set[int]] = {}
        self._support_events = 0
        self._touched = 0
        self._reconsidered = 0
        self.provenance_query_capability = False

    def _commit(self, claim: StreamClaim, replace: bool = False) -> None:
        if replace:
            self.committed[claim.packet.stable_reference] = set()
        self.committed.setdefault(claim.packet.stable_reference, set()).add(
            claim.packet.value
        )
        self._support_events += 1

    def _witness(self, packet: store.Packet) -> None:
        values = self.committed.get(packet.stable_reference)
        if values is None:
            return
        before = len(values)
        values.difference_update({value for value in values if value != packet.value})
        self._touched += before
        self._reconsidered += before

    def consume(self, frame: MechanismFrame) -> None:
        for claim in frame.predictions:
            self._commit(claim)
        for packet in frame.witnesses:
            self._witness(packet)
        if self.spec.grounded_recomputation:
            for claim in frame.recomputed:
                self._commit(claim, replace=True)

    def committed_values(self, stable_reference: int) -> tuple[int, ...]:
        return tuple(sorted(self.committed.get(stable_reference, ())))

    def support_count(self) -> int:
        return self._support_events

    def supports_touched(self) -> int:
        return self._touched

    def historical_state_reconsidered(self) -> int:
        return self._reconsidered

    def state_mutations(self) -> int:
        return self._support_events

    def has_grounded_provenance(self, stable_reference: int, value: int) -> bool:
        del stable_reference, value
        return False


class _StoreMechanism:
    def __init__(self, spec: ControlSpec, max_claims: int) -> None:
        self.name = spec.name
        self.spec = spec
        self.store = store.IncrementalProvenanceStore(max_claims=max_claims)
        self._touched = 0
        self._reconsidered = 0
        self._mutations = 0
        self.provenance_query_capability = spec.dependency_tracking

    def _insert(self, claim: StreamClaim) -> None:
        self._mutations += 1
        if claim.packet.act == store.ACT_DERIVE:
            self.store.derive(claim.packet, claim.semantic_parents)
        else:
            self.store.propose(claim.packet)

    def consume(self, frame: MechanismFrame) -> None:
        for claim in frame.predictions:
            self._insert(claim)
        if self.spec.witnessing:
            for packet in frame.witnesses:
                before = self.store.counts()["active_supports"]
                self.store.observe(packet)
                self._mutations += 1
                self._touched += abs(self.store.counts()["active_supports"] - before)
                self._reconsidered += self.store.revoked_support_total
        if self.spec.grounded_recomputation:
            for claim in frame.recomputed:
                self._insert(claim)

    def committed_values(self, stable_reference: int) -> tuple[int, ...]:
        return self.store.committed_values(stable_reference)

    def support_count(self) -> int:
        return self.store.counts()["active_supports"]

    def supports_touched(self) -> int:
        return self._touched

    def historical_state_reconsidered(self) -> int:
        return self._reconsidered

    def state_mutations(self) -> int:
        return self._mutations

    def has_grounded_provenance(self, stable_reference: int, value: int) -> bool:
        claim = self.store.claims.get((stable_reference, value))
        return bool(
            claim
            and claim.status == store.STATUS_COMMITTED
            and any(
                support.kind == store.SUPPORT_DERIVED
                and self.store.support_grounded(support_id)
                for support_id in claim.support_ids
                for support in (self.store.supports[support_id],)
            )
        )


def _make_mechanism(spec: ControlSpec, max_claims: int = 8192) -> Mechanism:
    if spec.name == "DIRECT_COMMIT":
        return _SimpleMechanism(spec.name)
    if spec.name == "CONFIDENCE_COMMIT":
        return _SimpleMechanism(spec.name, CONFIDENCE_THRESHOLD)
    if not spec.dependency_tracking:
        return _FlatWitnessMechanism(spec)
    return _StoreMechanism(spec, max_claims)


def _metric_counts(
    mechanism: Mechanism,
    frame: RecordedTransition,
    score: ControlScore,
    derived_references: set[int],
) -> None:
    truth_by_reference = {packet.stable_reference: packet for packet in frame.truth_packets}
    derived_references.update(
        claim.packet.stable_reference
        for claim in frame.predictions
        if claim.packet.act == store.ACT_DERIVE
    )
    for truth in frame.truth_packets:
        committed = mechanism.committed_values(truth.stable_reference)
        score.durable_slots += 1
        if committed == (truth.value,):
            score.correct_durable_slots += 1
        score.false_durable_claims += sum(value != truth.value for value in committed)
        if truth.stable_reference in derived_references and any(
            value != truth.value for value in committed
        ):
            score.stale_descendants += 1
    for claim in frame.predictions:
        truth = truth_by_reference.get(claim.packet.stable_reference)
        if truth is None or claim.packet.value == truth.value:
            continue
        score.rollback_targets += 1
        if claim.packet.value not in mechanism.committed_values(claim.packet.stable_reference):
            score.rollback_successes += 1
    for target in frame.preservation_targets:
        score.metric_a_opportunities += 1
        if mechanism.committed_values(target.packet.stable_reference) == (
            target.packet.value,
        ):
            score.metric_a_successes += 1
    for target in frame.recomputation_targets:
        score.metric_b_opportunities += 1
        exact = mechanism.committed_values(target.packet.stable_reference) == (
            target.packet.value,
        )
        provenance = mechanism.has_grounded_provenance(
            target.packet.stable_reference, target.packet.value
        )
        if provenance:
            score.metric_b_reconstructed_supports += 1
            if exact:
                score.metric_b_successes += 1
            else:
                score.metric_b_false_positive_reconstructions += 1
        elif exact:
            score.metric_b_false_positive_reconstructions += 1


def score_recorded_stream(
    frames: Iterable[RecordedTransition],
) -> dict[str, ControlScore]:
    """Run each control as an independent state machine over identical frames.

    Truth packets are consumed only by this scorer after ``consume`` returns;
    no mechanism receives evaluator-only truth while mutating its state.
    """
    frames = tuple(frames)
    stream_claim_keys = {
        (packet.stable_reference, packet.value)
        for frame in frames
        for packet in frame.witnesses
    }
    stream_claim_keys.update(
        (claim.packet.stable_reference, claim.packet.value)
        for frame in frames
        for claim in frame.predictions + frame.recomputed
    )
    replay_max_claims = max(8192, len(stream_claim_keys))
    mechanisms = {
        spec.name: _make_mechanism(spec, replay_max_claims) for spec in CONTROL_SPECS
    }
    scores = {name: ControlScore(name=name) for name in mechanisms}
    derived_references = {name: set() for name in mechanisms}
    for frame in frames:
        for name, mechanism in mechanisms.items():
            started = time.perf_counter()
            mechanism.consume(frame.mechanism_frame)
            score = scores[name]
            metric_started = time.perf_counter()
            _metric_counts(mechanism, frame, score, derived_references[name])
            score.metric_scoring_seconds += time.perf_counter() - metric_started
            score.runtime_steps += 1
            score.runtime_seconds += time.perf_counter() - started
            score.correction_events += bool(frame.witnesses)
            score.active_support_count = mechanism.support_count()
            score.supports_touched_per_correction = mechanism.supports_touched()
            score.historical_state_reconsidered_per_witness = (
                mechanism.historical_state_reconsidered()
            )
            score.provenance_query_capability = mechanism.provenance_query_capability
            score.memory_growth = mechanism.support_count()
            score.state_mutation_events = mechanism.state_mutations()
            score.history_reconsideration_events = (
                mechanism.historical_state_reconsidered()
            )
            score.stream_length = len(frames)
    for score in scores.values():
        score.stream_length = len(frames)
    return scores
