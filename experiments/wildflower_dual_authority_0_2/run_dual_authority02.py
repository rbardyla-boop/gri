"""Fail-closed Dual-Authority-0.2 scientific runner.

This module is intentionally executable only for an explicitly authorized
development seed. It carries forward the historical numeric predictor and
Nursery, while the epistemic challenge and controls use the 0.2 interfaces.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import tracemalloc
from typing import Iterator

import numpy as np
import torch

from . import design, store as d
from .controls import (
    CONTROL_SPECS,
    RecordedTransition,
    StreamClaim,
    score_recorded_stream,
)
from .metrics import (
    aggregate_transitions,
    classify_derived_transition,
    graph_quality_metrics,
    snapshot_store,
)
from .predictive_trace import PredictiveTrace, PredictiveTraceRow
from .qualification_guard import (
    assert_qualification_locked,
    assert_seed_is_registered,
    development_seed_is_allowed,
)
from .recorded_stream import canonical_stream_bytes
from .scaling import benchmark_recompute_everything


LEGACY_ROOT = Path(__file__).resolve().parents[1] / "wildflower0_prelock"
if str(LEGACY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEGACY_ROOT))

from probe_innovation_model import (  # noqa: E402
    InnovationModel,
    evaluate as evaluate_ungated,
    pre,
    train,
)
from qualify_authority190 import (  # noqa: E402
    BURN,
    DECAY,
    THRESHOLD,
    WIDTH,
    eval_authority,
)
from wildflower0.nursery1 import (  # noqa: E402
    MODES,
    collect_pairs,
    select_balanced_episode_seeds,
    set_seed,
)


AUTHORIZED_DEVELOPMENT_SEED = 320
PROFILE_ENGINEERING_SEED = 424242
OUTPUT_ROOT = Path(__file__).resolve().parent / "artifacts"
StableReference = int
ClaimValue = int
ClaimKey = tuple[StableReference, ClaimValue]
PROFILE_PHASE_CHOICES = ("pipeline", "epistemic", "controls", "scaling")
PROFILE_PHASES = (
    "nursery_data_generation",
    "model_training",
    "ordinary_predictive_evaluation",
    "predictive_trace_generation",
    "challenge_prediction_materialization",
    "witness_application",
    "provenance_recomputation",
    "transition_stream_serialization",
    "dual_authority_replay",
    "control_replay_direct_commit",
    "control_replay_confidence_commit",
    "control_replay_dag_no_witness",
    "control_replay_witness_no_dag",
    "control_replay_witness_plus_recompute_no_dag",
    "control_replay_dag_plus_witness_no_recompute",
    "metric_a_b_scoring",
    "canonical_support_accounting",
    "safety_scoring",
    "scaling_flat_100",
    "scaling_flat_1000",
    "scaling_flat_10000",
    "scaling_flat_100000",
    "scaling_dual_100",
    "scaling_dual_1000",
    "scaling_dual_10000",
    "scaling_dual_100000",
    "diagnostic_output_serialization",
    "semantic_receipt_generation",
    "json_canonicalization",
    "artifact_validation",
)
CONTROL_PHASE_NAMES = {
    "DUAL_AUTHORITY": "dual_authority_replay",
    "DIRECT_COMMIT": "control_replay_direct_commit",
    "CONFIDENCE_COMMIT": "control_replay_confidence_commit",
    "DAG_NO_WITNESS": "control_replay_dag_no_witness",
    "WITNESS_NO_DAG": "control_replay_witness_no_dag",
    "WITNESS_PLUS_RECOMPUTE_NO_DAG": "control_replay_witness_plus_recompute_no_dag",
    "DAG_PLUS_WITNESS_NO_RECOMPUTE": "control_replay_dag_plus_witness_no_recompute",
}
DERIVED_RELATIONS = (d.REL_LEFT_OF, d.REL_ABOVE, d.REL_ORDER_PARITY)
PAIR_OBJECTS = ((0, 1), (0, 2), (1, 2))
RECEIPT_EXCLUSIONS = (
    "runtime.started_at",
    "runtime.finished_at",
    "runtime.wall_seconds",
    "runtime.cpu_seconds",
    "runtime.peak_rss_bytes",
    "runtime.peak_python_bytes",
    "runtime.phase_profile",
    "controls.*.runtime_seconds",
    "controls.*.metric_scoring_seconds",
    "scaling_adversary.*.elapsed_seconds",
)


@dataclass
class _PhaseStats:
    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0
    calls: int = 0
    iterations: int = 0
    claims_processed: int = 0
    supports_processed: int = 0
    events_processed: int = 0
    peak_active_claims: int = 0
    peak_active_supports: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "wall_seconds": self.wall_seconds,
            "cpu_seconds": self.cpu_seconds,
            "calls": self.calls,
            "iterations": self.iterations,
            "claims_processed": self.claims_processed,
            "supports_processed": self.supports_processed,
            "events_processed": self.events_processed,
            "peak_active_claims": self.peak_active_claims,
            "peak_active_supports": self.peak_active_supports,
        }


@dataclass
class PhaseRecorder:
    """Low-overhead engineering telemetry; never changes scientific state."""

    _phases: dict[str, _PhaseStats] = field(default_factory=dict)
    _store_totals: dict[tuple[str, int], tuple[int, int, int]] = field(
        default_factory=dict
    )

    def _get(self, name: str) -> _PhaseStats:
        return self._phases.setdefault(name, _PhaseStats())

    @contextmanager
    def measure(self, name: str, iterations: int = 0) -> Iterator[None]:
        stats = self._get(name)
        stats.calls += 1
        stats.iterations += int(iterations)
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        try:
            yield
        finally:
            stats.wall_seconds += time.perf_counter() - wall_start
            stats.cpu_seconds += time.process_time() - cpu_start

    def add(
        self,
        name: str,
        *,
        wall_seconds: float = 0.0,
        cpu_seconds: float = 0.0,
        calls: int = 1,
        iterations: int = 0,
        claims_processed: int = 0,
        supports_processed: int = 0,
        events_processed: int = 0,
        peak_active_claims: int = 0,
        peak_active_supports: int = 0,
    ) -> None:
        stats = self._get(name)
        stats.wall_seconds += float(wall_seconds)
        stats.cpu_seconds += float(cpu_seconds)
        stats.calls += int(calls)
        stats.iterations += int(iterations)
        stats.claims_processed += int(claims_processed)
        stats.supports_processed += int(supports_processed)
        stats.events_processed += int(events_processed)
        stats.peak_active_claims = max(stats.peak_active_claims, int(peak_active_claims))
        stats.peak_active_supports = max(
            stats.peak_active_supports, int(peak_active_supports)
        )

    def sample_store(self, name: str, epistemic_store: object) -> None:
        counts = epistemic_store.counts()
        engineering = epistemic_store.engineering_metrics()
        store_key = (name, id(epistemic_store))
        previous_claims, previous_supports, previous_events = self._store_totals.get(
            store_key, (0, 0, 0)
        )
        current_claims = int(engineering.get("claims_visited", 0))
        current_supports = int(engineering.get("supports_visited", 0))
        current_events = int(counts["historical_events"])
        self._store_totals[store_key] = (
            current_claims,
            current_supports,
            current_events,
        )
        self.add(
            name,
            calls=0,
            claims_processed=current_claims - previous_claims,
            supports_processed=current_supports - previous_supports,
            events_processed=current_events - previous_events,
            peak_active_claims=counts["claims"],
            peak_active_supports=counts["active_supports"],
        )

    def as_dict(self) -> dict[str, dict[str, object]]:
        return {
            name: self._phases[name].as_dict()
            for name in sorted(self._phases)
        }


def _phase_context(
    phase: PhaseRecorder | None,
    name: str,
    iterations: int = 0,
) -> object:
    return phase.measure(name, iterations) if phase is not None else nullcontext()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes() -> dict[str, str]:
    paths = {
        f"successor/{path.relative_to(Path(__file__).parent)}": path
        for path in Path(__file__).parent.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    paths.update(
        {
            "historical/probe_innovation_model.py": LEGACY_ROOT
            / "probe_innovation_model.py",
            "historical/qualify_authority190.py": LEGACY_ROOT
            / "qualify_authority190.py",
            "historical/wildflower0/nursery1.py": LEGACY_ROOT
            / "wildflower0"
            / "nursery1.py",
        }
    )
    return {name: _sha256(path) for name, path in sorted(paths.items())}


def _assert_source_hashes_stable(initial: dict[str, str]) -> None:
    final = _source_hashes()
    if final != initial:
        raise RuntimeError("source hash mismatch during scientific run")


def _finite(value: object, path: str = "result") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"nonfinite numeric value at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _finite(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _finite(child, f"{path}[{index}]")


def _canonical_json_bytes(value: object) -> bytes:
    _finite(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _as_proposal(packet: d.Packet) -> d.Packet:
    return d.Packet(
        packet.stable_reference,
        d.ACT_PROPOSE,
        packet.subject,
        packet.relation,
        packet.object,
        packet.value,
    )


def _quantize_state(state: np.ndarray) -> np.ndarray:
    array = np.asarray(state, dtype=np.float64)
    if array.shape != (6,) or not np.isfinite(array).all():
        raise ValueError("object state must be six finite values")
    return np.rint((np.clip(array, -1.0, 1.0) + 1.0) * 5.5).astype(np.int64)


def _entity_code(episode: int, tick: int, object_index: int) -> int:
    return 1 + episode * 1_000_000 + tick * 16 + object_index


def _coordinate_slot(episode: int, tick: int, object_index: int, axis: int) -> int:
    return (
        1_000_000_000
        + episode * 10_000_000
        + tick * 64
        + object_index * 2
        + axis
        + 1
    )


def _relation_slot(
    episode: int,
    tick: int,
    relation: int,
    left_object: int,
    right_object: int,
) -> int:
    pair_index = PAIR_OBJECTS.index((left_object, right_object))
    return (
        2_000_000_000
        + episode * 10_000_000
        + tick * 64
        + pair_index * 2
        + (0 if relation == d.REL_LEFT_OF else 1)
        + 1
    )


def _parity_slot(episode: int, tick: int) -> int:
    return 3_000_000_000 + episode * 10_000_000 + tick + 1


def _coordinate_packet(
    cells: np.ndarray,
    episode: int,
    tick: int,
    object_index: int,
    axis: int,
    act: int,
) -> d.Packet:
    return d.Packet(
        _coordinate_slot(episode, tick, object_index, axis),
        act,
        _entity_code(episode, tick, object_index),
        d.REL_X if axis == 0 else d.REL_Y,
        0,
        int(cells[object_index * 2 + axis]),
    )


def _relation_value(
    cells: np.ndarray,
    left_object: int,
    right_object: int,
    relation: int,
) -> int:
    axis = 0 if relation == d.REL_LEFT_OF else 1
    return int(cells[left_object * 2 + axis] < cells[right_object * 2 + axis])


def _relation_packet(
    cells: np.ndarray,
    episode: int,
    tick: int,
    left_object: int,
    right_object: int,
    relation: int,
    act: int,
) -> d.Packet:
    return d.Packet(
        _relation_slot(episode, tick, relation, left_object, right_object),
        act,
        _entity_code(episode, tick, left_object),
        relation,
        _entity_code(episode, tick, right_object),
        _relation_value(cells, left_object, right_object, relation),
    )


def _parity_packet(
    cells: np.ndarray,
    episode: int,
    tick: int,
    act: int,
) -> d.Packet:
    relations = tuple(
        _relation_packet(cells, episode, tick, left, right, relation, act)
        for relation in (d.REL_LEFT_OF, d.REL_ABOVE)
        for left, right in PAIR_OBJECTS
    )
    return d.Packet(
        _parity_slot(episode, tick),
        act,
        _entity_code(episode, tick, 0),
        d.REL_ORDER_PARITY,
        _entity_code(episode, tick, 2),
        int(sum(packet.value for packet in relations) % 2),
    )


def _materialize_prediction(
    epistemic_store: d.ReferenceProvenanceStore,
    state: np.ndarray,
    episode: int,
    tick: int,
) -> dict[str, object]:
    cells = _quantize_state(state)
    coordinate_packets: list[d.Packet] = []
    coordinate_claims: dict[tuple[int, int], d.ClaimKey] = {}
    for object_index in range(3):
        for axis in (0, 1):
            packet = _coordinate_packet(
                cells, episode, tick, object_index, axis, d.ACT_PROPOSE
            )
            epistemic_store.propose(packet)
            coordinate_packets.append(packet)
            coordinate_claims[(object_index, axis)] = epistemic_store.claim_key(packet)

    relation_packets: list[d.Packet] = []
    relation_claims: list[d.ClaimKey] = []
    relation_parents: list[tuple[d.ClaimKey, ...]] = []
    relation_supports: list[int] = []
    for relation in (d.REL_LEFT_OF, d.REL_ABOVE):
        axis = 0 if relation == d.REL_LEFT_OF else 1
        for left, right in PAIR_OBJECTS:
            packet = _relation_packet(
                cells, episode, tick, left, right, relation, d.ACT_DERIVE
            )
            parents = (
                coordinate_claims[(left, axis)],
                coordinate_claims[(right, axis)],
            )
            support_id = epistemic_store.derive(packet, parents)
            relation_packets.append(packet)
            relation_claims.append(epistemic_store.claim_key(packet))
            relation_parents.append(parents)
            relation_supports.append(support_id)
    parity = _parity_packet(cells, episode, tick, d.ACT_DERIVE)
    parity_support = epistemic_store.derive(parity, tuple(relation_claims))
    return {
        "coordinate_packets": tuple(coordinate_packets),
        "coordinate_claims": coordinate_claims,
        "relation_packets": tuple(relation_packets),
        "relation_claims": tuple(relation_claims),
        "relation_parents": tuple(relation_parents),
        "relation_supports": tuple(relation_supports),
        "parity_packet": parity,
        "parity_support": parity_support,
    }


def _truth_bundle(state: np.ndarray, episode: int, tick: int) -> dict[str, object]:
    cells = _quantize_state(state)
    coordinates = tuple(
        _coordinate_packet(cells, episode, tick, object_index, axis, d.ACT_OBSERVE)
        for object_index in range(3)
        for axis in (0, 1)
    )
    relations = tuple(
        _relation_packet(cells, episode, tick, left, right, relation, d.ACT_OBSERVE)
        for relation in (d.REL_LEFT_OF, d.REL_ABOVE)
        for left, right in PAIR_OBJECTS
    )
    return {
        "coordinate_packets": coordinates,
        "relation_packets": relations,
        "parity_packet": _parity_packet(cells, episode, tick, d.ACT_OBSERVE),
    }


def _materialize_world_witness(
    epistemic_store: d.ReferenceProvenanceStore,
    truth: dict[str, object],
) -> None:
    for packet in truth["coordinate_packets"]:
        epistemic_store.observe(packet)


def _derive_from_committed_coordinates(
    epistemic_store: d.ReferenceProvenanceStore,
    truth: dict[str, object],
    episode: int,
    tick: int,
) -> dict[str, object]:
    coordinate_claims: dict[tuple[int, int], d.ClaimKey] = {}
    for packet in truth["coordinate_packets"]:
        object_index = (packet.subject - (1 + episode * 1_000_000 + tick * 16))
        object_index %= 16
        object_index = int(object_index)
        axis = 0 if packet.relation == d.REL_X else 1
        key = epistemic_store.claim_key(packet)
        if epistemic_store.status(*key) != d.STATUS_COMMITTED:
            raise RuntimeError("derived inference requires committed coordinate parents")
        coordinate_claims[(object_index, axis)] = key

    relation_packets: list[d.Packet] = []
    relation_claims: list[d.ClaimKey] = []
    relation_parents: list[tuple[d.ClaimKey, ...]] = []
    relation_supports: list[int] = []
    for relation in (d.REL_LEFT_OF, d.REL_ABOVE):
        axis = 0 if relation == d.REL_LEFT_OF else 1
        for left, right in PAIR_OBJECTS:
            truth_packet = next(
                packet
                for packet in truth["relation_packets"]
                if packet.relation == relation
                and packet.subject == _entity_code(episode, tick, left)
                and packet.object == _entity_code(episode, tick, right)
            )
            packet = d.Packet(
                truth_packet.stable_reference,
                d.ACT_DERIVE,
                truth_packet.subject,
                truth_packet.relation,
                truth_packet.object,
                truth_packet.value,
            )
            parents = (
                coordinate_claims[(left, axis)],
                coordinate_claims[(right, axis)],
            )
            support_id = epistemic_store.derive(packet, parents)
            relation_packets.append(packet)
            relation_claims.append(epistemic_store.claim_key(packet))
            relation_parents.append(parents)
            relation_supports.append(support_id)
    truth_parity = truth["parity_packet"]
    parity = d.Packet(
        truth_parity.stable_reference,
        d.ACT_DERIVE,
        truth_parity.subject,
        truth_parity.relation,
        truth_parity.object,
        truth_parity.value,
    )
    parity_support = epistemic_store.derive(parity, tuple(relation_claims))
    return {
        "coordinate_packets": tuple(
            _as_proposal(packet) for packet in truth["coordinate_packets"]
        ),
        "coordinate_claims": coordinate_claims,
        "relation_packets": tuple(relation_packets),
        "relation_claims": tuple(relation_claims),
        "relation_parents": tuple(relation_parents),
        "relation_supports": tuple(relation_supports),
        "parity_packet": parity,
        "parity_support": parity_support,
    }


def _prediction_stream_claims(bundle: dict[str, object]) -> tuple[StreamClaim, ...]:
    coordinates = tuple(StreamClaim(packet) for packet in bundle["coordinate_packets"])
    relations = tuple(
        StreamClaim(packet, parents)
        for packet, parents in zip(
            bundle["relation_packets"], bundle["relation_parents"], strict=True
        )
    )
    parity = StreamClaim(bundle["parity_packet"], tuple(bundle["relation_claims"]))
    return coordinates + relations + (parity,)


def _truth_stream_packets(bundle: dict[str, object]) -> tuple[d.Packet, ...]:
    return (
        tuple(bundle["coordinate_packets"])
        + tuple(bundle["relation_packets"])
        + (bundle["parity_packet"],)
    )


def _predictive_one(
    model: InnovationModel,
    current: np.ndarray,
    actions: np.ndarray,
    index: int,
) -> dict[str, object]:
    if index < BURN + 2:
        raise ValueError("insufficient burn history")
    hidden = torch.zeros((1, 64), dtype=torch.float32)
    history: list[float] = []
    with torch.no_grad():
        for observed_index in range(index - BURN, index):
            state = torch.tensor(current[observed_index][None])
            previous = torch.tensor(current[observed_index - 1][None])
            velocity = state - previous
            previous2 = torch.tensor(current[observed_index - 2][None])
            innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
            _, hidden, _, _ = model.step(
                state,
                velocity,
                torch.tensor([actions[observed_index]]),
                innovation,
                hidden,
            )
            history.append(float(innovation.abs().mean() * 5.5))
        weights = np.geomspace(0.35, 1.0, len(history))
        score = float(np.dot(weights, history) / weights.sum())
        authority = float(np.clip((score - THRESHOLD) / WIDTH, 0.0, 1.0))
        state = torch.tensor(current[index][None])
        previous = torch.tensor(current[index - 1][None])
        velocity = state - previous
        previous2 = torch.tensor(current[index - 2][None])
        innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
        learned, _, _, _ = model.step(
            state,
            velocity,
            torch.tensor([actions[index]]),
            innovation,
            hidden,
        )
        baseline = (state + velocity).clamp(-1.0, 1.0)
        prediction = (baseline + authority * (learned - baseline)).clamp(-1.0, 1.0)
    return {
        "prediction": prediction[0].cpu().numpy().astype(np.float32),
        "baseline": baseline[0].cpu().numpy().astype(np.float32),
        "learned": learned[0].cpu().numpy().astype(np.float32),
        "innovation_score": score,
        "authority": authority,
    }


def _h8_prediction(
    model: InnovationModel,
    current: np.ndarray,
    actions: np.ndarray,
    index: int,
) -> tuple[float, ...]:
    hidden = torch.zeros((1, 64), dtype=torch.float32)
    history: list[float] = []
    with torch.no_grad():
        for observed_index in range(index - BURN, index):
            state = torch.tensor(current[observed_index][None])
            previous = torch.tensor(current[observed_index - 1][None])
            velocity = state - previous
            previous2 = torch.tensor(current[observed_index - 2][None])
            innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
            _, hidden, _, _ = model.step(
                state,
                velocity,
                torch.tensor([actions[observed_index]]),
                innovation,
                hidden,
            )
            history.append(float(innovation.abs().mean() * 5.5))
        weights = np.geomspace(0.35, 1.0, len(history))
        authority = float(
            np.clip((np.dot(weights, history) / weights.sum() - THRESHOLD) / WIDTH, 0.0, 1.0)
        )
        state = torch.tensor(current[index][None])
        previous = torch.tensor(current[index - 1][None])
        velocity = state - previous
        previous2 = torch.tensor(current[index - 2][None])
        innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
        base_state = state.clone()
        base_velocity = velocity.clone()
        local_authority = authority
        trajectory: list[float] = []
        for offset in range(8):
            learned, hidden, _, _ = model.step(
                state,
                velocity,
                torch.tensor([actions[index + offset]]),
                innovation,
                hidden,
            )
            baseline = (base_state + base_velocity).clamp(-1.0, 1.0)
            prediction = (
                baseline + local_authority * (learned - baseline)
            ).clamp(-1.0, 1.0)
            trajectory.extend(float(value) for value in prediction[0].cpu().numpy())
            velocity = prediction - state
            state = prediction
            innovation = innovation * 0.90
            base_velocity = baseline - base_state
            base_state = baseline
            local_authority *= DECAY
    return tuple(trajectory)


def _predictive_episode(
    model: InnovationModel,
    pairs: list[object],
    mode: int,
    episode_seed: int,
    phase: PhaseRecorder | None = None,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    current, target, actions = pre(pairs)
    trace = PredictiveTrace()
    trace_iterations = max(len(pairs) - (BURN + 10), 0)
    with _phase_context(phase, "predictive_trace_generation", trace_iterations):
        for index in range(BURN + 2, len(pairs) - 8):
            one = _predictive_one(model, current, actions, index)
            target_now = target[index]
            baseline = one["baseline"]
            learned = one["learned"]
            prediction = one["prediction"]
            events = [
                index + offset
                for offset in range(8)
                if pairs[index + offset].rule_event
                or pairs[index + offset].collision
                or pairs[index + offset].boundary
            ]
            trace.append(
                PredictiveTraceRow(
                    episode_seed=episode_seed,
                    mode=mode,
                    step=index,
                    innovation_score=float(one["innovation_score"]),
                    authority=float(one["authority"]),
                    null_error=float(np.abs(baseline - target_now).mean() * 5.5),
                    ungated_learned_error=float(
                        np.abs(learned - target_now).mean() * 5.5
                    ),
                    gated_error=float(np.abs(prediction - target_now).mean() * 5.5),
                    h8_prediction=_h8_prediction(model, current, actions, index),
                    event_location=min(events) if events else None,
                )
            )
    with _phase_context(phase, "ordinary_predictive_evaluation", 4):
        h1 = eval_authority(model, pairs, 1)
        h8 = eval_authority(model, pairs, 8)
        h32 = eval_authority(model, pairs, 32)
        event_h8 = eval_authority(model, pairs, 8, event_only=True)
        ungated: dict[str, float] = {}
        for horizon in (1, 8, 32):
            model_error, baseline_error, _ = evaluate_ungated(model, pairs, horizon)
            ungated[f"h{horizon}_ratio"] = float(
                model_error / max(baseline_error, 1e-8)
            )
    trace_rows = tuple(
        {
            "episode_seed_evaluator_only": row.episode_seed,
            "mode_evaluator_only": row.mode,
            "step": row.step,
            "innovation_score": row.innovation_score,
            "authority": row.authority,
            "null_error": row.null_error,
            "ungated_learned_error": row.ungated_learned_error,
            "gated_error": row.gated_error,
            "h8_prediction": list(row.h8_prediction),
            "event_location_evaluator_only": row.event_location,
        }
        for row in trace.rows
    )
    innovation = [row.innovation_score for row in trace.rows]
    authority = [row.authority for row in trace.rows]
    stats = {
        "innovation_score_mean": float(np.mean(innovation)),
        "innovation_score_min": float(np.min(innovation)),
        "innovation_score_max": float(np.max(innovation)),
        "authority_mean": float(np.mean(authority)),
        "authority_min": float(np.min(authority)),
        "authority_max": float(np.max(authority)),
        "null_error_mean": float(np.mean([row.null_error for row in trace.rows])),
        "ungated_learned_error_mean": float(
            np.mean([row.ungated_learned_error for row in trace.rows])
        ),
        "gated_error_mean": float(np.mean([row.gated_error for row in trace.rows])),
    }
    row = {
        "mode_evaluator_only": mode,
        "episode_seed_evaluator_only": episode_seed,
        "h1_ratio": float(h1["ratio"]),
        "h8_ratio": float(h8["ratio"]),
        "h32_ratio": float(h32["ratio"]),
        "event_h8_ratio": float(event_h8["ratio"]),
        "ungated_learned_null_ratios": ungated,
        "innovation_authority_statistics": stats,
        "trace_rows": len(trace_rows),
    }
    return row, trace_rows


def _predictive_qualification(
    model: InnovationModel,
    selection: dict[int, tuple[int, ...]],
    phase: PhaseRecorder | None = None,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    rows: list[dict[str, object]] = []
    trace_rows: list[dict[str, object]] = []
    for mode in MODES:
        for episode_seed in selection[mode]:
            with _phase_context(
                phase, "nursery_data_generation", design.ORDINARY_EVALUATION_LENGTH
            ):
                pairs = collect_pairs(episode_seed, design.ORDINARY_EVALUATION_LENGTH)
            row, episode_trace = _predictive_episode(
                model,
                pairs,
                mode,
                episode_seed,
                phase,
            )
            rows.append(row)
            trace_rows.extend(episode_trace)
    aggregate = {
        "h1_ratio_mean": float(np.mean([row["h1_ratio"] for row in rows])),
        "h1_ratio_max": float(np.max([row["h1_ratio"] for row in rows])),
        "h8_ratio_mean": float(np.mean([row["h8_ratio"] for row in rows])),
        "h8_ratio_max": float(np.max([row["h8_ratio"] for row in rows])),
        "h32_ratio_mean": float(np.mean([row["h32_ratio"] for row in rows])),
        "h32_ratio_max": float(np.max([row["h32_ratio"] for row in rows])),
        "event_h8_ratio_mean": float(
            np.mean([row["event_h8_ratio"] for row in rows])
        ),
        "event_h8_ratio_max": float(np.max([row["event_h8_ratio"] for row in rows])),
    }
    gates = {
        "h1_noninferior_all": aggregate["h1_ratio_max"] <= 1.10,
        "h8_better_all": aggregate["h8_ratio_max"] <= 1.00,
        "h8_mean_10pct": aggregate["h8_ratio_mean"] <= 0.90,
        "h32_better_all": aggregate["h32_ratio_max"] <= 1.00,
        "h32_mean_15pct": aggregate["h32_ratio_mean"] <= 0.85,
        "event_h8_mean_10pct": aggregate["event_h8_ratio_mean"] <= 0.90,
    }
    return {
        "episodes": rows,
        "aggregate": aggregate,
        "gates": gates,
        "passed": all(gates.values()),
    }, tuple(trace_rows)


def _support_inventory(epistemic_store: d.ReferenceProvenanceStore) -> list[dict[str, object]]:
    return [
        {
            "support_id": support_id,
            "packet": list(support.packet.numeric_tuple()),
            "kind": support.kind,
            "semantic_parent_claim_keys": [list(parent) for parent in support.parents],
            "parent_lineage_fingerprint": support.lineage_fingerprint,
            "enabled": support.enabled,
            "effective": epistemic_store.support_effective(support_id),
            "grounded": epistemic_store.support_grounded(support_id),
        }
        for support_id, support in sorted(epistemic_store.supports.items())
    ]


def _run_challenge_episode(
    model: InnovationModel,
    pairs: list[object],
    mode: int,
    episode_seed: int,
    episode_ordinal: int,
    *,
    store_factory: type[d.ReferenceProvenanceStore] = d.IncrementalProvenanceStore,
    phase: PhaseRecorder | None = None,
) -> tuple[
    tuple[RecordedTransition, ...],
    tuple[object, ...],
    dict[str, object],
    tuple[dict[str, object], ...],
]:
    current, target, actions = pre(pairs)
    oracle = store_factory(max_claims=design.MAX_ACTIVE_CLAIMS)
    frames: list[RecordedTransition] = []
    transitions: list[object] = []
    for index in range(BURN + 2, len(pairs) - 1):
        predictive = _predictive_one(model, current, actions, index)
        prediction = predictive["prediction"]
        with _phase_context(phase, "challenge_prediction_materialization", 1):
            prediction_bundle = _materialize_prediction(
                oracle, prediction, episode_ordinal, index + 1
            )
        if phase is not None:
            phase.sample_store("challenge_prediction_materialization", oracle)
        truth_bundle = _truth_bundle(target[index], episode_ordinal, index + 1)
        support_ids = tuple(prediction_bundle["relation_supports"]) + (
            prediction_bundle["parity_support"],
        )
        with _phase_context(phase, "witness_application", 1):
            before = snapshot_store(oracle, root_support_ids=support_ids)
            _materialize_world_witness(oracle, truth_bundle)
            after_witness = snapshot_store(oracle, root_support_ids=support_ids)
        if phase is not None:
            phase.sample_store("witness_application", oracle)
        with _phase_context(phase, "provenance_recomputation", 1):
            recompute_bundle = _derive_from_committed_coordinates(
                oracle, truth_bundle, episode_ordinal, index + 1
            )
            after_recompute = snapshot_store(oracle, root_support_ids=support_ids)
        if phase is not None:
            phase.sample_store("provenance_recomputation", oracle)
        predictions = _prediction_stream_claims(prediction_bundle)
        recomputed = _prediction_stream_claims(recompute_bundle)
        truth_packets = _truth_stream_packets(truth_bundle)
        derived_predictions = predictions[6:]
        derived_support_ids = support_ids
        recomputed_by_reference: dict[StableReference, StreamClaim] = {
            claim.packet.stable_reference: claim for claim in recomputed
        }
        preservation_targets: list[StreamClaim] = []
        recomputation_targets: list[StreamClaim] = []
        truth_by_reference: dict[StableReference, d.Packet] = {
            packet.stable_reference: packet for packet in truth_packets
        }
        with _phase_context(phase, "metric_a_b_scoring", len(derived_predictions)):
            for packet, support_id in zip(
                (claim.packet for claim in derived_predictions),
                derived_support_ids,
                strict=True,
            ):
                transition = classify_derived_transition(
                    packet,
                    truth_by_reference[packet.stable_reference],
                    support_id,
                    before,
                    after_witness,
                    after_recompute,
                )
                transitions.append(transition)
                if transition.preservation_opportunity:
                    preservation_targets.append(StreamClaim(packet))
                if transition.recomputation_opportunity:
                    recomputation_targets.append(
                        recomputed_by_reference[transition.claim[0]]
                    )
        frames.append(
            RecordedTransition(
                tick=index + 1,
                predictions=predictions,
                witnesses=tuple(truth_bundle["coordinate_packets"]),
                recomputed=recomputed,
                authority=float(predictive["authority"]),
                truth_packets=truth_packets,
                preservation_targets=tuple(preservation_targets),
                recomputation_targets=tuple(recomputation_targets),
            )
        )
    transitions_tuple = tuple(transitions)
    episode_metrics = aggregate_transitions(transitions_tuple)
    episode_metrics["mode_evaluator_only"] = mode
    episode_metrics["episode_seed_evaluator_only"] = episode_seed
    with _phase_context(phase, "canonical_support_accounting", len(oracle.supports)):
        episode_metrics["support_inventory"] = _support_inventory(oracle)
        episode_metrics["engineering"] = oracle.engineering_metrics()
        episode_metrics["graph_quality"] = graph_quality_metrics(oracle)
    return tuple(frames), transitions_tuple, episode_metrics, ()


def _control_score(score: object) -> dict[str, object]:
    corrections = max(int(score.correction_events), 1)
    durable_opportunities = int(score.durable_slots)
    return {
        "false_durable_claims": score.false_durable_claims,
        "false_durable_claim_opportunities": durable_opportunities,
        "false_durable_claim_rate": (
            score.false_durable_claims / durable_opportunities
            if durable_opportunities
            else 0.0
        ),
        "durable_coverage": score.durable_coverage,
        "stale_descendants": score.stale_descendants,
        "rollback_opportunities": score.rollback_targets,
        "rollback_successes": score.rollback_successes,
        "rollback_recall": score.rollback_recall,
        "metric_a": {
            "opportunities": score.metric_a_opportunities,
            "successes": score.metric_a_successes,
            "rate": score.metric_a_rate,
        },
        "metric_b": {
            "opportunities": score.metric_b_opportunities,
            "true_positives": score.metric_b_successes,
            "false_positives": score.metric_b_false_positive_reconstructions,
            "false_negatives": score.metric_b_false_negatives,
            "global_precision": score.metric_b_precision,
            "global_recall": score.metric_b_recall,
        },
        "provenance_query_capability": score.provenance_query_capability,
        "supports_touched_total": score.supports_touched_per_correction,
        "supports_touched_per_correction": (
            score.supports_touched_per_correction / corrections
        ),
        "history_reconsidered_total": score.historical_state_reconsidered_per_witness,
        "history_reconsidered_per_witness": (
            score.historical_state_reconsidered_per_witness / corrections
        ),
        "active_supports": score.active_support_count,
        "stream_length": score.stream_length,
        "state_mutation_events": score.state_mutation_events,
        "history_reconsideration_events": score.history_reconsideration_events,
        "runtime_seconds": score.runtime_seconds,
        "metric_scoring_seconds": score.metric_scoring_seconds,
        "memory_proxy": score.memory_growth,
    }


def _record_control_phases(
    phase: PhaseRecorder | None,
    controls: dict[str, object],
) -> None:
    if phase is None:
        return
    metric_wall_seconds = 0.0
    metric_iterations = 0
    for name, score in controls.items():
        metric_wall_seconds += float(score.metric_scoring_seconds)
        metric_iterations += int(score.metric_a_opportunities) + int(
            score.metric_b_opportunities
        )
        phase.add(
            CONTROL_PHASE_NAMES[name],
            wall_seconds=max(
                float(score.runtime_seconds) - float(score.metric_scoring_seconds),
                0.0,
            ),
            iterations=int(score.runtime_steps),
            supports_processed=int(score.supports_touched_per_correction),
            events_processed=int(score.historical_state_reconsidered_per_witness),
            peak_active_supports=int(score.active_support_count),
        )
    phase.add(
        "metric_a_b_scoring",
        wall_seconds=metric_wall_seconds,
        iterations=metric_iterations,
    )


def _engineering_profile_stream(
    frame_count: int = 64,
) -> tuple[RecordedTransition, ...]:
    """Small deterministic stream used only by ``--profile-only``."""
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    frames: list[RecordedTransition] = []
    for tick in range(frame_count):
        left = d.Packet(4_100_001, d.ACT_PROPOSE, 1, d.REL_X, 0, 0)
        right = d.Packet(4_100_002, d.ACT_PROPOSE, 2, d.REL_X, 0, 0)
        child = StreamClaim(
            d.Packet(4_100_010, d.ACT_DERIVE, 1, d.REL_ORDER_PARITY, 2, 0),
            ((4_100_001, 0), (4_100_002, 0)),
        )
        corrected_left = d.Packet(4_100_001, d.ACT_OBSERVE, 1, d.REL_X, 0, 1)
        corrected_right = d.Packet(4_100_002, d.ACT_OBSERVE, 2, d.REL_X, 0, 1)
        corrected_child = StreamClaim(
            d.Packet(4_100_010, d.ACT_DERIVE, 1, d.REL_ORDER_PARITY, 2, 0),
            ((4_100_001, 1), (4_100_002, 1)),
        )
        frames.append(
            RecordedTransition(
                tick=tick,
                predictions=(
                    StreamClaim(left),
                    StreamClaim(right),
                    child,
                ),
                witnesses=(corrected_left, corrected_right),
                recomputed=(corrected_child,),
                authority=1.0,
                truth_packets=(corrected_left, corrected_right),
                preservation_targets=(),
                recomputation_targets=(corrected_child,),
            )
        )
    return tuple(frames)


def _dual_scaling_rows(phase: PhaseRecorder | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for history_size in (100, 1_000, 10_000, 100_000):
        epistemic_store = d.IncrementalProvenanceStore(
            max_claims=design.MAX_ACTIVE_CLAIMS
        )
        epistemic_store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 1))
        child = epistemic_store.derive(
            d.Packet(2, d.ACT_DERIVE, 2, d.REL_LEFT_OF, 0, 1), ((1, 1),)
        )
        for _ in range(history_size):
            epistemic_store.observe(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 1))
        before = epistemic_store.engineering_metrics()
        started = time.perf_counter()
        with _phase_context(phase, f"scaling_dual_{history_size}", 1):
            epistemic_store.revoke_support(child)
        elapsed = time.perf_counter() - started
        after = epistemic_store.engineering_metrics()
        row = {
            "retained_events": history_size,
            "correction_work": (
                after["dirty_claims_processed"]
                - before["dirty_claims_processed"]
                + after["dirty_supports_processed"]
                - before["dirty_supports_processed"]
            ),
            "supports_visited": after["supports_visited"]
            - before["supports_visited"],
            "claims_visited": after["claims_visited"] - before["claims_visited"],
            "elapsed_seconds": elapsed,
            "memory_proxy": len(epistemic_store.event_history),
        }
        if phase is not None:
            phase.add(
                f"scaling_dual_{history_size}",
                calls=0,
                claims_processed=row["claims_visited"],
                supports_processed=row["supports_visited"],
                events_processed=history_size,
                peak_active_claims=epistemic_store.counts()["claims"],
                peak_active_supports=epistemic_store.counts()["active_supports"],
            )
        rows.append(row)
    return rows


def _selection(model_seed: int) -> dict[str, dict[int, tuple[int, ...]]]:
    starts = design.selector_starts(model_seed)
    return {
        "training": select_balanced_episode_seeds(
            model_seed + design.TRAIN_SELECTOR_ROOT_OFFSET,
            design.TRAIN_PER_MODE,
            start=starts["training"],
        ),
        "ordinary_test": select_balanced_episode_seeds(
            model_seed + design.ORDINARY_TEST_SELECTOR_ROOT_OFFSET,
            design.ORDINARY_TEST_PER_MODE,
            start=starts["ordinary_test"],
        ),
        "challenge": select_balanced_episode_seeds(
            model_seed + design.CHALLENGE_SELECTOR_ROOT_OFFSET,
            design.CHALLENGE_PER_MODE,
            start=starts["challenge"],
        ),
    }


def _selector_payload(
    model_seed: int,
    selection: dict[str, dict[int, tuple[int, ...]]],
) -> dict[str, object]:
    return {
        "starts": design.selector_starts(model_seed),
        "ranges": design.selector_ranges()[model_seed],
        "selected_episode_seeds": selection,
    }


def _assert_seed_authorized(model_seed: int) -> None:
    assert_seed_is_registered(model_seed)
    if model_seed in design.QUALIFICATION_SEEDS:
        assert_qualification_locked(model_seed)
    if model_seed != AUTHORIZED_DEVELOPMENT_SEED:
        raise RuntimeError(
            f"only seed {AUTHORIZED_DEVELOPMENT_SEED} is authorized for this run"
        )
    if not development_seed_is_allowed(model_seed):
        raise RuntimeError(f"seed {model_seed} is not authorized for development")


def _train_candidate(
    selection: dict[int, tuple[int, ...]],
    model_seed: int,
    phase: PhaseRecorder | None = None,
) -> InnovationModel:
    set_seed(model_seed)
    model = InnovationModel()
    order = [
        selection[mode][index]
        for index in range(design.TRAIN_PER_MODE)
        for mode in MODES
    ]
    for index, episode_seed in enumerate(order):
        with _phase_context(
            phase, "nursery_data_generation", design.TRAINING_EPISODE_LENGTH
        ):
            pairs = collect_pairs(episode_seed, design.TRAINING_EPISODE_LENGTH)
        with _phase_context(
            phase, "model_training", design.TRAINING_STEPS_PER_EPISODE
        ):
            train(
                model,
                pairs,
                design.TRAINING_STEPS_PER_EPISODE,
                model_seed + 10_000 + index,
            )
    return model


def _receipt_payload(result: dict[str, object]) -> dict[str, object]:
    payload = json.loads(json.dumps(result))
    payload.pop("semantic_receipt_sha256", None)
    runtime = payload.get("runtime", {})
    for runtime_field in (
        "started_at",
        "finished_at",
        "wall_seconds",
        "cpu_seconds",
        "peak_rss_bytes",
        "peak_python_bytes",
        "phase_profile",
    ):
        runtime.pop(runtime_field, None)
    for control in payload.get("controls", {}).values():
        control.pop("runtime_seconds", None)
        control.pop("metric_scoring_seconds", None)
    for section in payload.get("scaling_adversary", {}).values():
        if isinstance(section, list):
            for row in section:
                row.pop("elapsed_seconds", None)
    return payload


def semantic_receipt_sha256(
    result: dict[str, object], phase: PhaseRecorder | None = None
) -> str:
    with _phase_context(phase, "json_canonicalization", 2):
        first_payload = _canonical_json_bytes(_receipt_payload(result))
        second_payload = _canonical_json_bytes(_receipt_payload(result))
    with _phase_context(phase, "semantic_receipt_generation", 2):
        first = hashlib.sha256(first_payload).hexdigest()
        second = hashlib.sha256(second_payload).hexdigest()
    if first != second:
        raise RuntimeError("semantic receipt generation was nondeterministic")
    return first


def run_engineering_profile(
    selected_phases: tuple[str, ...] = PROFILE_PHASE_CHOICES,
) -> dict[str, object]:
    """Run deterministic engineering workloads without scientific selectors."""
    phases = tuple(dict.fromkeys(selected_phases))
    unknown = set(phases).difference(PROFILE_PHASE_CHOICES)
    if unknown:
        raise ValueError(f"unknown engineering profile phase(s): {sorted(unknown)}")
    if not phases:
        phases = PROFILE_PHASE_CHOICES

    phase = PhaseRecorder()
    profile: dict[str, object] = {
        "mode": "ENGINEERING_PROFILE_ONLY",
        "engineering_seed": PROFILE_ENGINEERING_SEED,
        "selected_sections": list(phases),
        "scientific_selectors_used": False,
    }
    challenge_frames: list[RecordedTransition] = []
    profile_trace_rows: list[dict[str, object]] = []
    profile_metric_transitions: list[object] = []

    if "pipeline" in phases:
        training_selection = {
            mode: tuple(
                PROFILE_ENGINEERING_SEED + 10_000 + index * 100 + mode
                for index in range(design.TRAIN_PER_MODE)
            )
            for mode in MODES
        }
        ordinary_selection = {
            mode: tuple(
                PROFILE_ENGINEERING_SEED + 20_000 + index * 100 + mode
                for index in range(design.ORDINARY_TEST_PER_MODE)
            )
            for mode in MODES
        }
        model = _train_candidate(
            training_selection, PROFILE_ENGINEERING_SEED, phase
        )
        _, ordinary_trace = _predictive_qualification(
            model, ordinary_selection, phase
        )
        profile_trace_rows.extend(ordinary_trace)
        for ordinal, mode in enumerate(MODES):
            episode_seed = PROFILE_ENGINEERING_SEED + 30_000 + mode
            with _phase_context(
                phase,
                "nursery_data_generation",
                design.CHALLENGE_EPISODE_LENGTH,
            ):
                pairs = collect_pairs(
                    episode_seed,
                    design.CHALLENGE_EPISODE_LENGTH,
                    surprise=True,
                )
            frames, transitions, _, _ = _run_challenge_episode(
                model,
                pairs,
                mode,
                episode_seed,
                ordinal,
                phase=phase,
            )
            challenge_frames.extend(frames)
            profile_metric_transitions.extend(transitions)
        profile["pipeline"] = {
            "training_episodes": design.TRAIN_PER_MODE * len(MODES),
            "ordinary_episodes": design.ORDINARY_TEST_PER_MODE * len(MODES),
            "challenge_episodes": len(MODES),
            "training_length": design.TRAINING_EPISODE_LENGTH,
            "ordinary_length": design.ORDINARY_EVALUATION_LENGTH,
            "challenge_length": design.CHALLENGE_EPISODE_LENGTH,
            "recorded_transitions": len(challenge_frames),
        }
    elif "epistemic" in phases:
        model = InnovationModel()
        for ordinal, mode in enumerate(MODES):
            episode_seed = PROFILE_ENGINEERING_SEED + 40_000 + mode
            with _phase_context(
                phase,
                "nursery_data_generation",
                design.CHALLENGE_EPISODE_LENGTH,
            ):
                pairs = collect_pairs(
                    episode_seed,
                    design.CHALLENGE_EPISODE_LENGTH,
                    surprise=True,
                )
            frames, transitions, _, _ = _run_challenge_episode(
                model,
                pairs,
                mode,
                episode_seed,
                ordinal,
                phase=phase,
            )
            challenge_frames.extend(frames)
            profile_metric_transitions.extend(transitions)
        profile["epistemic"] = {
            "challenge_episodes": len(MODES),
            "challenge_length": design.CHALLENGE_EPISODE_LENGTH,
            "recorded_transitions": len(challenge_frames),
        }

    if challenge_frames:
        with _phase_context(
            phase, "transition_stream_serialization", len(challenge_frames)
        ):
            profile_stream_bytes = canonical_stream_bytes(challenge_frames)
        with _phase_context(
            phase, "diagnostic_output_serialization", len(profile_trace_rows)
        ):
            profile["output_sizes"] = {
                "predictive_trace_rows": len(profile_trace_rows),
                "predictive_trace_canonical_bytes": len(
                    _canonical_json_bytes(profile_trace_rows)
                ),
                "recorded_transition_count": len(challenge_frames),
                "recorded_transition_canonical_bytes": len(profile_stream_bytes),
                "metric_transition_count": len(profile_metric_transitions),
                "metric_transition_canonical_bytes": len(
                    _canonical_json_bytes(
                        [
                            transition.__dict__
                            for transition in profile_metric_transitions
                        ]
                    )
                ),
            }

    if "controls" in phases:
        if not challenge_frames:
            challenge_frames = list(_engineering_profile_stream())
        with _phase_context(
            phase, "transition_stream_serialization", len(challenge_frames)
        ):
            stream_digest = hashlib.sha256(
                canonical_stream_bytes(challenge_frames)
            ).hexdigest()
        controls = score_recorded_stream(challenge_frames)
        _record_control_phases(phase, controls)
        profile["controls"] = {
            "stream_sha256": stream_digest,
            "recorded_transitions": len(challenge_frames),
            "scores": {
                name: _control_score(score) for name, score in controls.items()
            },
        }
        with _phase_context(phase, "safety_scoring", len(challenge_frames)):
            profile["safety"] = {
                "stream_length": len(challenge_frames),
                "independent_control_states": len(controls),
                "all_control_scores_finite": all(
                    math.isfinite(float(score.runtime_seconds))
                    for score in controls.values()
                ),
            }

    if "scaling" in phases:
        flat_rows = benchmark_recompute_everything()
        flat_profile = []
        for row in flat_rows:
            phase.add(
                f"scaling_flat_{row.history_events}",
                wall_seconds=row.elapsed_seconds,
                iterations=row.correction_work,
                events_processed=row.retained_events,
            )
            flat_profile.append(
                {
                    "retained_events": row.history_events,
                    "correction_work": row.correction_work,
                    "elapsed_seconds": row.elapsed_seconds,
                    "memory_proxy": row.retained_events,
                }
            )
        profile["scaling"] = {
            "flat_recompute_everything": flat_profile,
            "dual_authority_affected_cone": _dual_scaling_rows(phase),
        }

    receipt_payload = dict(profile)
    receipt_payload.pop("semantic_receipt_sha256", None)
    receipt_payload.pop("phase_profile", None)
    with _phase_context(phase, "json_canonicalization", 2):
        first_payload = _canonical_json_bytes(receipt_payload)
        second_payload = _canonical_json_bytes(receipt_payload)
    with _phase_context(phase, "semantic_receipt_generation", 2):
        first = hashlib.sha256(first_payload).hexdigest()
        second = hashlib.sha256(second_payload).hexdigest()
    if first != second:
        raise RuntimeError("engineering profile receipt was nondeterministic")
    profile["semantic_receipt_sha256"] = first
    profile["phase_profile"] = phase.as_dict()
    with _phase_context(phase, "artifact_validation", 1):
        _finite(profile)
        json.loads(_canonical_json_bytes(profile))
    profile["phase_profile"] = phase.as_dict()
    return profile


def _validate_result(result: dict[str, object]) -> None:
    required = {
        "experiment",
        "version",
        "model_seed",
        "selectors",
        "runtime",
        "source_hashes",
        "predictive_authority",
        "predictive_trace",
        "epistemic_challenge",
        "canonical_support_accounting",
        "controls",
        "scaling_adversary",
        "safety",
        "deterministic_replay",
        "active_store_bound",
        "language_cognitive_path",
        "semantic_receipt_sha256",
    }
    missing = required.difference(result)
    if missing:
        raise ValueError(f"result missing fields: {sorted(missing)}")
    if result["model_seed"] != AUTHORIZED_DEVELOPMENT_SEED:
        raise ValueError("result seed is not the authorized development seed")
    if set(result["controls"]) != {spec.name for spec in CONTROL_SPECS}:
        raise ValueError("result does not contain exactly the seven controls")
    if result["language_cognitive_path"] is not False:
        raise ValueError("natural language entered the cognitive path")
    receipt = result["semantic_receipt_sha256"]
    if not isinstance(receipt, str) or len(receipt) != 64:
        raise ValueError("malformed semantic receipt")
    for value in result["source_hashes"].values():
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError("malformed source hash")
    for episode in result["epistemic_challenge"]["episodes"]:
        for support in episode["support_inventory"]:
            if len(support["parent_lineage_fingerprint"]) != 64:
                raise ValueError("malformed lineage fingerprint")
    _finite(result)
    if semantic_receipt_sha256(result) != receipt:
        raise ValueError("semantic receipt mismatch")


def _atomic_write_json(path: Path, result: dict[str, object]) -> None:
    _validate_result(result)
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def run_development_seed(model_seed: int) -> dict[str, object]:
    _assert_seed_authorized(model_seed)
    if not design.selectors_are_disjoint_from_0_1():
        raise RuntimeError("selector ranges overlap the 0.1 range")

    source_hashes = _source_hashes()
    started_at = datetime.now(timezone.utc).isoformat()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    phase = PhaseRecorder()
    tracemalloc.start()
    try:
        selection = _selection(model_seed)
        model = _train_candidate(selection["training"], model_seed, phase)
        predictive, ordinary_trace = _predictive_qualification(
            model, selection["ordinary_test"], phase
        )
        challenge_episodes: list[dict[str, object]] = []
        challenge_frames: list[RecordedTransition] = []
        all_transitions: list[object] = []
        challenge_trace: list[dict[str, object]] = []
        ordinal = 0
        for mode in MODES:
            for episode_seed in selection["challenge"][mode]:
                with _phase_context(
                    phase,
                    "nursery_data_generation",
                    design.CHALLENGE_EPISODE_LENGTH,
                ):
                    challenge_pairs = collect_pairs(
                        episode_seed,
                        design.CHALLENGE_EPISODE_LENGTH,
                        surprise=True,
                    )
                frames, transitions, episode_metrics, episode_trace = _run_challenge_episode(
                    model,
                    challenge_pairs,
                    mode,
                    episode_seed,
                    ordinal,
                    phase=phase,
                )
                challenge_frames.extend(frames)
                all_transitions.extend(transitions)
                challenge_episodes.append(episode_metrics)
                challenge_trace.extend(episode_trace)
                ordinal += 1
        controls = score_recorded_stream(challenge_frames)
        _record_control_phases(phase, controls)
        control_result = {
            name: _control_score(score) for name, score in controls.items()
        }
        dual = control_result["DUAL_AUTHORITY"]
        transition_metrics = aggregate_transitions(all_transitions)
        flat_rows = benchmark_recompute_everything()
        scaling_flat = []
        for row in flat_rows:
            phase.add(
                f"scaling_flat_{row.history_events}",
                wall_seconds=row.elapsed_seconds,
                iterations=row.correction_work,
                events_processed=row.retained_events,
            )
            scaling_flat.append(
                {
                    "retained_events": row.history_events,
                    "correction_work": row.correction_work,
                    "elapsed_seconds": row.elapsed_seconds,
                    "memory_proxy": row.retained_events,
                }
            )
        scaling_dual = _dual_scaling_rows(phase)
        all_trace = ordinary_trace + tuple(challenge_trace)
        graph_rows = [episode["graph_quality"] for episode in challenge_episodes]
        canonical = {
            "support_insert_attempts": sum(
                episode["engineering"].get("support_insert_attempts", 0)
                for episode in challenge_episodes
            ),
            "canonical_support_creations": sum(
                episode["engineering"].get("canonical_support_creations", 0)
                for episode in challenge_episodes
            ),
            "canonical_support_reuses": sum(
                episode["engineering"].get("canonical_support_reuses", 0)
                for episode in challenge_episodes
            ),
            "semantic_duplicates_reused": sum(
                episode["engineering"].get("semantic_duplicates_reused", 0)
                for episode in challenge_episodes
            ),
            "provenance_changes": sum(
                episode["engineering"].get("provenance_changes", 0)
                for episode in challenge_episodes
            ),
            "active_support_count_max": max(
                int(episode["graph_quality"]["active_support_count"])
                for episode in challenge_episodes
            ),
            "historical_event_count": sum(
                int(episode["graph_quality"]["historical_event_count"])
                for episode in challenge_episodes
            ),
            "duplicate_support_rate": 0.0,
        }
        with _phase_context(phase, "safety_scoring", len(all_transitions)):
            safety = {
                "false_durable_claims": dual["false_durable_claims"],
                "false_durable_claim_opportunities": dual[
                    "false_durable_claim_opportunities"
                ],
                "false_durable_claim_rate": dual["false_durable_claim_rate"],
                "rollback_opportunities": dual["rollback_opportunities"],
                "rollback_successes": dual["rollback_successes"],
                "rollback_recall": dual["rollback_recall"],
                "stale_support_survival_rate": transition_metrics[
                    "stale_support_survival_rate"
                ],
                "orphan_support_rate": max(
                    float(row["orphan_support_rate"]) for row in graph_rows
                ),
                "support_DAG_integrity": all(
                    row["support_DAG_integrity"] for row in graph_rows
                ),
                "active_store_bound": all(
                    row["active_store_bound"] for row in graph_rows
                ),
                "deterministic_replay": all(
                    row["deterministic_replay"] for row in graph_rows
                ),
            }
        with _phase_context(
            phase, "transition_stream_serialization", len(challenge_frames)
        ):
            stream_bytes = canonical_stream_bytes(challenge_frames)
            stream_sha256 = hashlib.sha256(stream_bytes).hexdigest()
        with _phase_context(
            phase, "diagnostic_output_serialization", len(all_trace)
        ):
            output_sizes = {
                "predictive_trace_rows": len(all_trace),
                "predictive_trace_canonical_bytes": len(
                    _canonical_json_bytes(list(all_trace))
                ),
                "recorded_transition_count": len(challenge_frames),
                "recorded_transition_canonical_bytes": len(stream_bytes),
                "metric_transition_count": len(all_transitions),
                "metric_transition_canonical_bytes": len(
                    _canonical_json_bytes(
                        [transition.__dict__ for transition in all_transitions]
                    )
                ),
                "control_diagnostics_canonical_bytes": len(
                    _canonical_json_bytes(control_result)
                ),
                "canonical_support_history_count": sum(
                    len(episode["support_inventory"])
                    for episode in challenge_episodes
                ),
                "canonical_support_history_canonical_bytes": len(
                    _canonical_json_bytes(
                        [
                            episode["support_inventory"]
                            for episode in challenge_episodes
                        ]
                    )
                ),
            }
        runtime = {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_seconds": time.perf_counter() - wall_start,
            "cpu_seconds": time.process_time() - cpu_start,
            "peak_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "peak_python_bytes": int(tracemalloc.get_traced_memory()[1]),
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "phase_profile": phase.as_dict(),
            "control_stream_shared": True,
            "exact_command": (
                "PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "
                "python -m experiments.wildflower_dual_authority_0_2.run_dual_authority02 "
                f"--seed {model_seed}"
            ),
        }
        _assert_source_hashes_stable(source_hashes)
        result: dict[str, object] = {
            "experiment": "WILDFLOWER Dual-Authority",
            "version": "0.2",
            "status": "DEVELOPMENT_RUN",
            "model_seed": model_seed,
            "selectors": _selector_payload(model_seed, selection),
            "runtime": runtime,
            "source_hashes": source_hashes,
            "predictive_authority": predictive,
            "predictive_trace": list(all_trace),
            "epistemic_challenge": {
                "recorded_transition_count": len(challenge_frames),
                "recorded_transition_stream_sha256": stream_sha256,
                "episodes": challenge_episodes,
                "aggregate": transition_metrics,
            },
            "canonical_support_accounting": canonical,
            "controls": control_result,
            "output_sizes": output_sizes,
            "scaling_adversary": {
                "flat_recompute_everything": scaling_flat,
                "dual_authority_affected_cone": scaling_dual,
            },
            "safety": safety,
            "deterministic_replay": safety["deterministic_replay"],
            "active_store_bound": safety["active_store_bound"],
            "language_cognitive_path": False,
            "architecture_freeze_authorized": False,
            "qualification_authorized": False,
            "successor_authorized": False,
            "semantic_receipt_exclusions": list(RECEIPT_EXCLUSIONS),
            "semantic_receipt_sha256": "",
        }
        result["semantic_receipt_sha256"] = semantic_receipt_sha256(result, phase)
        runtime["phase_profile"] = phase.as_dict()
        with _phase_context(phase, "artifact_validation", 1):
            _validate_result(result)
        runtime["phase_profile"] = phase.as_dict()
        return result
    finally:
        tracemalloc.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--profile-only",
        action="store_true",
        help="run only deterministic engineering workloads; never a scientific seed",
    )
    parser.add_argument(
        "--profile-phase",
        action="append",
        choices=PROFILE_PHASE_CHOICES,
        help="restrict --profile-only to one or more engineering sections",
    )
    args = parser.parse_args(argv)
    if args.profile_only:
        if args.seed is not None:
            parser.error("--profile-only cannot be combined with --seed")
        result = run_engineering_profile(tuple(args.profile_phase or ()))
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.seed is None:
        parser.error("--seed is required unless --profile-only is used")
    result = run_development_seed(args.seed)
    output = args.output or OUTPUT_ROOT / f"development_seed{args.seed}.json"
    _atomic_write_json(output, result)
    print(
        json.dumps(
            {
                "model_seed": result["model_seed"],
                "semantic_receipt_sha256": result["semantic_receipt_sha256"],
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
