"""Read-only diagnostic replay for the completed seed-311 development run.

This module deliberately does not call ``main`` and therefore never writes the
frozen development result.  It replays only seed 311, captures the transition
snapshots and support-creation phases, and writes a separate diagnostic trace.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from . import run_dual_authority01 as runner
from . import store
from .metrics import StoreSnapshot, support_lineage


SEED = 311
ARTIFACT = Path(__file__).with_name("artifacts") / "development_seed311.json"
TRACE_OUTPUT = Path(__file__).with_name("artifacts") / "seed311_autopsy_trace.json"
EXPECTED_ARTIFACT_SHA256 = (
    "b51de9e7e7221c23226f95507fea4464446445fc9279d5e99398049c81e78c58"
)

_phase = "outside"
_scope = "outside"
_episode_ordinal: int | None = None
_transitions: list[dict[str, Any]] = []
_insertions: list[dict[str, Any]] = []
_prediction_stream: dict[tuple[int, int], dict[str, Any]] = {}
_authority_rows: list[dict[str, Any]] = []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packet_tuple(packet: Any) -> list[int]:
    return [int(value) for value in packet.numeric_tuple()]


def _claim_key(key: tuple[int, int]) -> list[int]:
    return [int(key[0]), int(key[1])]


def _decode_reference(reference: int) -> tuple[int, int] | None:
    for base in (1_000_000_000, 2_000_000_000, 3_000_000_000):
        if not base <= int(reference) < base + 1_000_000_000:
            continue
        offset = int(reference) - base - 1
        if offset < 0:
            continue
        episode = offset // 10_000_000
        remainder = offset % 10_000_000
        if base == 3_000_000_000:
            return episode, remainder
        return episode, remainder // 64
    return None


def _support_record(snapshot: StoreSnapshot, support_id: int) -> dict[str, Any]:
    support = snapshot.supports[support_id]
    return {
        "support_id": int(support_id),
        "packet": [int(value) for value in support.packet],
        "kind": int(support.kind),
        "parents": [_claim_key(parent) for parent in support.parents],
        "enabled": bool(support.enabled),
        "effective": bool(support.effective),
    }


def _support_ids_for_claim(snapshot: StoreSnapshot, claim: tuple[int, int]) -> list[int]:
    return [int(value) for value in snapshot.support_ids_for_claim(claim)]


def _claim_view(
    snapshots: dict[str, StoreSnapshot],
    claim: tuple[int, int],
) -> dict[str, Any]:
    result: dict[str, Any] = {"claim": _claim_key(claim)}
    for name, snapshot in snapshots.items():
        support_ids = _support_ids_for_claim(snapshot, claim)
        result[name] = {
            "status": int(snapshot.status(claim)),
            "support_ids": support_ids,
            "supports": [
                _support_record(snapshot, support_id) for support_id in support_ids
            ],
        }
    return result


def _descendant_supports(
    snapshot: StoreSnapshot,
    root: tuple[int, int],
) -> list[int]:
    children: dict[tuple[int, int], list[int]] = defaultdict(list)
    support_claims: dict[int, tuple[int, int]] = {}
    for support_id, support in snapshot.supports.items():
        support_claims[support_id] = (int(support.packet[0]), int(support.packet[5]))
        for parent in support.parents:
            children[parent].append(support_id)

    pending = [root]
    visited_claims: set[tuple[int, int]] = set()
    descendants: set[int] = set()
    while pending:
        claim = pending.pop()
        if claim in visited_claims:
            continue
        visited_claims.add(claim)
        for support_id in children.get(claim, ()):
            if support_id in descendants:
                continue
            descendants.add(support_id)
            pending.append(support_claims[support_id])
    return sorted(descendants)


def _transition_record(
    transition: Any,
    before: StoreSnapshot,
    after_witness: StoreSnapshot,
    after_recompute: StoreSnapshot,
) -> dict[str, Any]:
    claim = tuple(transition.claim)
    snapshots = {
        "before_witness": before,
        "after_witness": after_witness,
        "after_recompute": after_recompute,
    }
    original = before.supports[transition.original_support_id]
    lineage = sorted(support_lineage(before, transition.original_support_id))
    parent_views = [
        _claim_view(snapshots, tuple(parent)) for parent in original.parents
    ]
    lineage_views: dict[str, list[dict[str, Any]]] = {}
    for name, snapshot in snapshots.items():
        lineage_views[name] = [
            _support_record(snapshot, support_id)
            for support_id in lineage
            if support_id in snapshot.supports
        ]
    return {
        "episode_ordinal": _episode_ordinal,
        "tick": _decode_reference(claim[0])[1] if _decode_reference(claim[0]) else None,
        "claim": _claim_key(claim),
        "original_support_id": int(transition.original_support_id),
        "original_support": _support_record(before, transition.original_support_id),
        "correct_before_witness": bool(transition.correct_before_witness),
        "invalidated_lineage_support_ids": [
            int(value) for value in transition.invalidated_lineage_support_ids
        ],
        "original_support_effective_after_witness": bool(
            transition.original_support_effective_after_witness
        ),
        "parent_keys_world_valid": bool(transition.parent_keys_world_valid),
        "alternate_parent_world_paths": bool(transition.alternate_parent_world_paths),
        "preservation_opportunity": bool(transition.preservation_opportunity),
        "preservation_success": bool(transition.preservation_success),
        "parent_keys_changed": bool(transition.parent_keys_changed),
        "recomputation_opportunity": bool(transition.recomputation_opportunity),
        "recomputation_success": bool(transition.recomputation_success),
        "reconstructed_support_ids": [
            int(value) for value in transition.reconstructed_support_ids
        ],
        "stale_support_survived": bool(transition.stale_support_survived),
        "claim_views": {
            name: _claim_view(snapshots, claim)[name]
            for name in snapshots
        },
        "parent_views": parent_views,
        "lineage_supports": lineage_views,
        "descendant_support_ids": {
            name: _descendant_supports(snapshot, claim)
            for name, snapshot in snapshots.items()
        },
    }


def _with_phase(
    phase: str,
    function: Callable[..., Any],
) -> Callable[..., Any]:
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        global _phase
        previous = _phase
        _phase = phase
        try:
            return function(*args, **kwargs)
        finally:
            _phase = previous

    return wrapped


def _install_hooks() -> dict[str, Any]:
    originals: dict[str, Any] = {
        "add_support": store.IncrementalEpistemicStore._add_support,
        "materialize_prediction": store.materialize_prediction,
        "materialize_world_witness": store.materialize_world_witness,
        "derive_from_committed_coordinates": store.derive_from_committed_coordinates,
        "classify": runner.classify_derived_transition,
        "episode": runner._run_developmental_episode,
        "predictive": runner._predictive_authority_one,
        "truth": store.evaluator_truth,
        "challenge": runner._run_challenge,
        "scaling": runner._run_scaling_probe,
    }

    def add_support(
        self: Any,
        packet: Any,
        kind: int,
        parents: Any = (),
    ) -> int:
        parent_tuple = tuple(parents)
        support_id = originals["add_support"](self, packet, kind, parent_tuple)
        decoded = _decode_reference(packet.stable_reference)
        if (
            decoded is not None
            and _scope == "challenge"
            and _phase in {"prediction", "witness", "recompute"}
        ):
            _insertions.append(
                {
                    "episode_ordinal": int(decoded[0]),
                    "tick": int(decoded[1]),
                    "support_id": int(support_id),
                    "packet": _packet_tuple(packet),
                    "kind": int(kind),
                    "parents": [_claim_key(parent) for parent in parent_tuple],
                    "phase": _phase,
                }
            )
        return support_id

    def classify(*args: Any, **kwargs: Any) -> Any:
        transition = originals["classify"](*args, **kwargs)
        _transitions.append(
            _transition_record(
                transition,
                args[3],
                args[4],
                args[5],
            )
        )
        return transition

    def episode(*args: Any, **kwargs: Any) -> Any:
        global _episode_ordinal
        previous = _episode_ordinal
        _episode_ordinal = int(args[2]) if len(args) > 2 else int(kwargs["episode_ordinal"])
        try:
            return originals["episode"](*args, **kwargs)
        finally:
            _episode_ordinal = previous

    def predictive(*args: Any, **kwargs: Any) -> Any:
        result = originals["predictive"](*args, **kwargs)
        if _episode_ordinal is not None:
            index = int(args[3]) if len(args) > 3 else int(kwargs["index"])
            _authority_rows.append(
                {
                    "episode_ordinal": _episode_ordinal,
                    "index": index,
                    "tick": index + 1,
                    "authority": float(result["authority"]),
                    "innovation_score_cells": float(result["innovation_score_cells"]),
                }
            )
        return result

    def prediction(*args: Any, **kwargs: Any) -> Any:
        global _phase
        previous = _phase
        _phase = "prediction"
        try:
            result = originals["materialize_prediction"](*args, **kwargs)
        finally:
            _phase = previous
        if _episode_ordinal is not None:
            tick = int(args[3]) if len(args) > 3 else int(kwargs["tick"])
            key = (_episode_ordinal, tick)
            _prediction_stream.setdefault(key, {})["predicted_packets"] = [
                _packet_tuple(packet)
                for packet in store.flatten_prediction_packets(result)
            ]
        return result

    def challenge(*args: Any, **kwargs: Any) -> Any:
        global _scope
        previous = _scope
        _scope = "challenge"
        try:
            return originals["challenge"](*args, **kwargs)
        finally:
            _scope = previous

    def scaling(*args: Any, **kwargs: Any) -> Any:
        global _scope
        previous = _scope
        _scope = "scaling"
        try:
            return originals["scaling"](*args, **kwargs)
        finally:
            _scope = previous

    def truth(*args: Any, **kwargs: Any) -> Any:
        result = originals["truth"](*args, **kwargs)
        if _episode_ordinal is not None:
            tick = int(args[2]) if len(args) > 2 else int(kwargs["tick"])
            key = (_episode_ordinal, tick)
            _prediction_stream.setdefault(key, {})["truth_packets"] = [
                _packet_tuple(packet) for packet in store.flatten_truth_packets(result)
            ]
        return result

    store.IncrementalEpistemicStore._add_support = add_support
    store.materialize_prediction = prediction
    store.materialize_world_witness = _with_phase(
        "witness", originals["materialize_world_witness"]
    )
    store.derive_from_committed_coordinates = _with_phase(
        "recompute", originals["derive_from_committed_coordinates"]
    )
    runner.classify_derived_transition = classify
    runner._run_developmental_episode = episode
    runner._predictive_authority_one = predictive
    store.evaluator_truth = truth
    runner._run_challenge = challenge
    runner._run_scaling_probe = scaling
    return originals


def _restore_hooks(originals: dict[str, Any]) -> None:
    store.IncrementalEpistemicStore._add_support = originals["add_support"]
    store.materialize_prediction = originals["materialize_prediction"]
    store.materialize_world_witness = originals["materialize_world_witness"]
    store.derive_from_committed_coordinates = originals[
        "derive_from_committed_coordinates"
    ]
    runner.classify_derived_transition = originals["classify"]
    runner._run_developmental_episode = originals["episode"]
    runner._predictive_authority_one = originals["predictive"]
    store.evaluator_truth = originals["truth"]
    runner._run_challenge = originals["challenge"]
    runner._run_scaling_probe = originals["scaling"]


def _duplicate_audit() -> dict[str, Any]:
    by_episode: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for insertion in _insertions:
        by_episode[int(insertion["episode_ordinal"])].append(insertion)
    rows: list[dict[str, Any]] = []
    all_duplicates: list[dict[str, Any]] = []
    for episode, insertions in sorted(by_episode.items()):
        seen: dict[tuple[Any, ...], dict[str, Any]] = {}
        duplicates: list[dict[str, Any]] = []
        for insertion in insertions:
            signature = (
                tuple(insertion["packet"]),
                int(insertion["kind"]),
                tuple(tuple(parent) for parent in insertion["parents"]),
            )
            first = seen.get(signature)
            if first is not None:
                duplicate = {
                    "episode_ordinal": episode,
                    "signature": {
                        "packet": insertion["packet"],
                        "kind": insertion["kind"],
                        "parents": insertion["parents"],
                    },
                    "first_phase": first["phase"],
                    "duplicate_phase": insertion["phase"],
                    "first_support_id": first["support_id"],
                    "duplicate_support_id": insertion["support_id"],
                }
                duplicates.append(duplicate)
                all_duplicates.append(duplicate)
            else:
                seen[signature] = insertion
        rows.append(
            {
                "episode_ordinal": episode,
                "support_insertions": len(insertions),
                "unique_signatures": len(seen),
                "exact_duplicate_supports": len(duplicates),
                "duplicate_rate": len(duplicates) / len(insertions)
                if insertions
                else 0.0,
                "duplicates_by_phase": {
                    phase: sum(item["duplicate_phase"] == phase for item in duplicates)
                    for phase in ("prediction", "witness", "recompute")
                },
            }
        )
    return {
        "episodes": rows,
        "total_exact_duplicate_supports": len(all_duplicates),
        "duplicates_by_phase": {
            phase: sum(item["duplicate_phase"] == phase for item in all_duplicates)
            for phase in ("prediction", "witness", "recompute")
        },
        "duplicate_examples": all_duplicates[:20],
    }


def _transition_summary() -> dict[str, Any]:
    b_opportunities = [row for row in _transitions if row["recomputation_opportunity"]]
    b_successes = [row for row in b_opportunities if row["recomputation_success"]]
    b_failures = [row for row in b_opportunities if not row["recomputation_success"]]
    reconstructed = [row for row in _transitions if row["reconstructed_support_ids"]]
    return {
        "transition_count": len(_transitions),
        "metric_a_opportunities": sum(
            row["preservation_opportunity"] for row in _transitions
        ),
        "metric_a_successes": sum(row["preservation_success"] for row in _transitions),
        "metric_b_opportunities": len(b_opportunities),
        "metric_b_successes": len(b_successes),
        "metric_b_failures": len(b_failures),
        "metric_b_failure_classes": {
            "no_reconstructed_support": sum(
                not row["reconstructed_support_ids"] for row in b_failures
            ),
            "reconstructed_but_claim_not_committed": sum(
                bool(row["reconstructed_support_ids"])
                and row["claim_views"]["after_recompute"]["status"] != 2
                for row in b_failures
            ),
            "reconstructed_and_committed_but_parent_signature_unchanged": sum(
                bool(row["reconstructed_support_ids"])
                and row["claim_views"]["after_recompute"]["status"] == 2
                and not any(
                    support["parents"] != row["original_support"]["parents"]
                    for support in row["claim_views"]["after_recompute"]["supports"]
                    if support["support_id"] in row["reconstructed_support_ids"]
                )
                for row in b_failures
            ),
        },
        "reconstruction_precision_boolean_denominator": len(reconstructed),
        "reconstruction_true_positives": len(b_successes),
        "reconstruction_false_positives": len(reconstructed) - len(b_successes),
        "global_precision": len(b_successes) / len(reconstructed)
        if reconstructed
        else 1.0,
        "metric_b_failure_rows": b_failures,
    }


def _first_difference(left: Any, right: Any, path: str = "$") -> dict[str, Any] | None:
    if type(left) is not type(right):
        return {"path": path, "left": repr(left), "right": repr(right)}
    if isinstance(left, dict):
        if set(left) != set(right):
            return {
                "path": path,
                "left_keys": sorted(left),
                "right_keys": sorted(right),
            }
        for key in sorted(left):
            difference = _first_difference(left[key], right[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path, "left_length": len(left), "right_length": len(right)}
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            difference = _first_difference(left_item, right_item, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if left != right:
        return {"path": path, "left": repr(left), "right": repr(right)}
    return None


def _canonical_without_volatile_fields(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            str(key): _canonical_without_volatile_fields(value)
            for key, value in data.items()
            if key not in {"runtime", "scaling_probe", "semantic_receipt_sha256"}
        }
    if isinstance(data, list):
        return [_canonical_without_volatile_fields(value) for value in data]
    return data


def run() -> dict[str, Any]:
    artifact_before = _sha256(ARTIFACT)
    if artifact_before != EXPECTED_ARTIFACT_SHA256:
        raise RuntimeError(
            f"frozen artifact hash changed before replay: {artifact_before}"
        )
    frozen = json.loads(ARTIFACT.read_text())
    originals = _install_hooks()
    try:
        replay = runner.run_development_seed(SEED)
    finally:
        _restore_hooks(originals)
    artifact_after = _sha256(ARTIFACT)
    if artifact_after != artifact_before:
        raise RuntimeError("diagnostic replay changed the frozen artifact")
    receipt_matches = replay["semantic_receipt_sha256"] == frozen[
        "semantic_receipt_sha256"
    ]
    replay_scientific = _canonical_without_volatile_fields(replay)
    frozen_scientific = _canonical_without_volatile_fields(frozen)
    scientific_fields_match = replay_scientific == frozen_scientific

    output = {
        "status": "SEED311_DIAGNOSTIC_REPLAY",
        "seed": SEED,
        "frozen_artifact": str(ARTIFACT),
        "frozen_artifact_sha256_before": artifact_before,
        "frozen_artifact_sha256_after": artifact_after,
        "frozen_semantic_receipt_sha256": frozen["semantic_receipt_sha256"],
        "replay_semantic_receipt_sha256": replay["semantic_receipt_sha256"],
        "replay_matches_frozen_receipt": receipt_matches,
        "replay_matches_frozen_scientific_fields": scientific_fields_match,
        "receipt_includes_volatile_runtime_and_scaling_fields": True,
        "replay_first_difference": None
        if receipt_matches
        else _first_difference(replay, frozen),
        "scientific_first_difference": None
        if scientific_fields_match
        else _first_difference(replay_scientific, frozen_scientific),
        "authority_rows": _authority_rows,
        "prediction_stream": [
            {
                "episode_ordinal": key[0],
                "tick": key[1],
                **value,
            }
            for key, value in sorted(_prediction_stream.items())
        ],
        "transition_summary": _transition_summary(),
        "duplicate_audit": _duplicate_audit(),
        "transitions": _transitions,
        "support_insertions": _insertions,
    }
    TRACE_OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return output


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {
                "output": str(TRACE_OUTPUT),
                "frozen_artifact_sha256": result["frozen_artifact_sha256_after"],
                "receipt": result["replay_semantic_receipt_sha256"],
                "transitions": result["transition_summary"]["transition_count"],
                "metric_b_failures": result["transition_summary"]["metric_b_failures"],
            },
            sort_keys=True,
        )
    )
