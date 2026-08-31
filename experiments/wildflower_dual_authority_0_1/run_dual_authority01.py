from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import tracemalloc

import numpy as np
import torch

from . import store as d
from .controls import CONTROLS
from .design import (
    CHALLENGE_EPISODE_LENGTH,
    CHALLENGE_PER_MODE,
    CHALLENGE_SELECTOR_ROOT_OFFSET,
    CONFIDENCE_CONTROL_THRESHOLD,
    MAX_ACTIVE_CLAIMS,
    MODEL_SEEDS,
    ORDINARY_EVALUATION_LENGTH,
    ORDINARY_TEST_PER_MODE,
    ORDINARY_TEST_SELECTOR_ROOT_OFFSET,
    QUALIFICATION_SEEDS,
    TRAINING_EPISODE_LENGTH,
    TRAINING_STEPS_PER_EPISODE,
    TRAIN_PER_MODE,
    TRAIN_SELECTOR_ROOT_OFFSET,
    selector_starts,
)
from .metrics import (
    aggregate_transitions,
    classify_derived_transition,
    graph_quality_metrics,
    snapshot_store,
)
from .qualification_guard import (
    assert_qualification_locked,
    development_seed_is_allowed,
)


LEGACY_ROOT = Path(__file__).resolve().parents[1] / "wildflower0_prelock"
if str(LEGACY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEGACY_ROOT))

from probe_innovation_model import (  # noqa: E402
    InnovationModel,
    evaluate as eval_ungated,
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
    stable_hash,
)


OUTPUT_ROOT = Path(__file__).resolve().parent / "artifacts"
DERIVED_RELATIONS = (d.REL_LEFT_OF, d.REL_ABOVE, d.REL_ORDER_PARITY)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes() -> dict[str, str]:
    paths = {
        "successor/store.py": Path(__file__).with_name("store.py"),
        "successor/metrics.py": Path(__file__).with_name("metrics.py"),
        "successor/micro_simulations.py": Path(__file__).with_name(
            "micro_simulations.py"
        ),
        "successor/controls.py": Path(__file__).with_name("controls.py"),
        "successor/design.py": Path(__file__).with_name("design.py"),
        "successor/qualification_guard.py": Path(__file__).with_name(
            "qualification_guard.py"
        ),
        "successor/run_dual_authority01.py": Path(__file__),
        "historical/probe_innovation_model.py": LEGACY_ROOT
        / "probe_innovation_model.py",
        "historical/qualify_authority190.py": LEGACY_ROOT
        / "qualify_authority190.py",
        "historical/wildflower0/nursery1.py": LEGACY_ROOT
        / "wildflower0/nursery1.py",
    }
    return {name: _sha256(path) for name, path in sorted(paths.items())}


def _train_candidate(
    train_selection: dict[int, tuple[int, ...]],
    model_seed: int,
) -> InnovationModel:
    set_seed(model_seed)
    model = InnovationModel()
    order = [
        train_selection[mode][index]
        for index in range(TRAIN_PER_MODE)
        for mode in MODES
    ]
    for index, episode_seed in enumerate(order):
        train(
            model,
            collect_pairs(episode_seed, TRAINING_EPISODE_LENGTH),
            TRAINING_STEPS_PER_EPISODE,
            model_seed + 10_000 + index,
        )
    return model


def _predictive_authority_one(
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
            innovation = state - (
                previous + (previous - previous2)
            ).clamp(-1.0, 1.0)
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
        innovation = state - (
            previous + (previous - previous2)
        ).clamp(-1.0, 1.0)
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
        "innovation_score_cells": score,
        "authority": authority,
    }


def _predictive_qualification(
    model: InnovationModel,
    test_selection: dict[int, tuple[int, ...]],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for mode in MODES:
        for episode_seed in test_selection[mode]:
            pairs = collect_pairs(episode_seed, ORDINARY_EVALUATION_LENGTH)
            row: dict[str, object] = {"mode": mode, "episode_seed": episode_seed}
            for horizon in (1, 8, 32):
                row[f"h{horizon}"] = eval_authority(model, pairs, horizon)
                model_error, baseline_error, _ = eval_ungated(model, pairs, horizon)
                row[f"ungated_h{horizon}_ratio"] = float(
                    model_error / max(baseline_error, 1e-8)
                )
            row["event_h8"] = eval_authority(model, pairs, 8, event_only=True)
            rows.append(row)
    h1 = [float(row["h1"]["ratio"]) for row in rows]
    h8 = [float(row["h8"]["ratio"]) for row in rows]
    h32 = [float(row["h32"]["ratio"]) for row in rows]
    event_h8 = [float(row["event_h8"]["ratio"]) for row in rows]
    aggregate = {
        "h1_ratio_mean": float(np.mean(h1)),
        "h1_ratio_max": float(np.max(h1)),
        "h8_ratio_mean": float(np.mean(h8)),
        "h8_ratio_max": float(np.max(h8)),
        "h32_ratio_mean": float(np.mean(h32)),
        "h32_ratio_max": float(np.max(h32)),
        "event_h8_ratio_mean": float(np.mean(event_h8)),
        "event_h8_ratio_max": float(np.max(event_h8)),
        "ungated_h1_max": float(np.max([row["ungated_h1_ratio"] for row in rows])),
    }
    gates = {
        "h1_noninferior_all": aggregate["h1_ratio_max"] <= 1.10,
        "h8_better_all": aggregate["h8_ratio_max"] <= 1.00,
        "h8_mean_10pct": aggregate["h8_ratio_mean"] <= 0.90,
        "h32_better_all": aggregate["h32_ratio_max"] <= 1.00,
        "h32_mean_15pct": aggregate["h32_ratio_mean"] <= 0.85,
        "event_h8_mean_10pct": aggregate["event_h8_ratio_mean"] <= 0.90,
    }
    return {"rows": rows, "aggregate": aggregate, "gates": gates, "passed": all(gates.values())}


def _packet_truth(
    packet: d.Packet,
    truth_by_reference: dict[int, d.Packet],
) -> tuple[bool, d.Packet]:
    actual = truth_by_reference[packet.stable_reference]
    return packet.value == actual.value, actual


def _snapshot_slot_metrics(
    snapshot,
    truth_packets: tuple[d.Packet, ...],
) -> dict[str, int | float]:
    correct = 0
    false = 0
    for packet in truth_packets:
        committed = tuple(
            value
            for (reference, value), (status, _) in snapshot.claims.items()
            if reference == packet.stable_reference and status == d.STATUS_COMMITTED
        )
        if committed == (packet.value,):
            correct += 1
        false += sum(value != packet.value for value in committed)
    total = len(truth_packets)
    return {
        "slots": total,
        "correct": correct,
        "false": false,
        "coverage": correct / total if total else 0.0,
    }


def _control_results(
    packet_rows: list[dict[str, object]],
    witness_no_recompute: dict[str, int | float],
    candidate: dict[str, object],
) -> dict[str, dict[str, object]]:
    total = len(packet_rows)
    derived_rows = [row for row in packet_rows if row["derived"]]
    direct_false = sum(not row["correct"] for row in packet_rows)
    confidence_rows = [
        row
        for row in packet_rows
        if float(row["authority"]) >= CONFIDENCE_CONTROL_THRESHOLD
    ]
    confidence_false = sum(not row["correct"] for row in confidence_rows)
    confidence_correct = sum(row["correct"] for row in confidence_rows)
    direct = {
        "false_durable_claims": direct_false,
        "false_durable_claim_rate": direct_false / total if total else 0.0,
        "durable_coverage": sum(row["correct"] for row in packet_rows) / total
        if total
        else 0.0,
        "provenance": False,
    }
    confidence = {
        "committed_predictions": len(confidence_rows),
        "false_durable_claims": confidence_false,
        "false_durable_claim_rate": confidence_false / total if total else 0.0,
        "durable_coverage": confidence_correct / total if total else 0.0,
        "provenance": False,
    }
    dag_no_witness = {
        "false_durable_claims": 0,
        "false_durable_claim_rate": 0.0,
        "durable_coverage": 0.0,
        "provenance": True,
    }
    witness_no_dag = {
        "false_durable_claims": sum(not row["correct"] for row in derived_rows),
        "false_durable_claim_rate": (
            sum(not row["correct"] for row in derived_rows) / total if total else 0.0
        ),
        "stale_descendants": sum(not row["correct"] for row in derived_rows),
        "provenance": False,
    }
    witness_plus_recompute_no_dag = {
        "false_durable_claims": 0,
        "false_durable_claim_rate": 0.0,
        "durable_coverage": 1.0,
        "provenance": False,
        "recomputation_only": True,
    }
    dag_plus_witness_no_recompute = {
        "false_durable_claims": witness_no_recompute["false"],
        "false_durable_claim_rate": (
            witness_no_recompute["false"] / witness_no_recompute["slots"]
            if witness_no_recompute["slots"]
            else 0.0
        ),
        "durable_coverage": witness_no_recompute["coverage"],
        "provenance": True,
        "recomputation_only": False,
    }
    dual = {
        **candidate,
        "provenance": True,
    }
    return {
        "DUAL_AUTHORITY": dual,
        "DIRECT_COMMIT": direct,
        "CONFIDENCE_COMMIT": confidence,
        "DAG_NO_WITNESS": dag_no_witness,
        "WITNESS_NO_DAG": witness_no_dag,
        "WITNESS_PLUS_RECOMPUTE_NO_DAG": witness_plus_recompute_no_dag,
        "DAG_PLUS_WITNESS_NO_RECOMPUTE": dag_plus_witness_no_recompute,
    }


def _run_developmental_episode(
    model: InnovationModel,
    pairs: list[object],
    episode_ordinal: int,
) -> dict[str, object]:
    current, target, actions = pre(pairs)
    store = d.EpistemicStore(max_claims=MAX_ACTIVE_CLAIMS)
    packet_rows: list[dict[str, object]] = []
    transitions = []
    rollback_targets = 0
    rollback_successes = 0
    witness_slots = 0
    correct_durable_slots = 0
    false_durable_after_witness = 0
    after_witness_false = 0
    after_witness_correct = 0
    derived_contradictions = 0
    peak_claims = 0
    active_bound_violations = 0
    cycle_attempts_rejected = 0

    for index in range(BURN + 2, len(pairs) - 1):
        predictive = _predictive_authority_one(model, current, actions, index)
        authority = float(predictive["authority"])
        tick = index + 1
        prediction_bundle = d.materialize_prediction(
            store, predictive["prediction"], episode_ordinal, tick
        )
        predicted_packets = d.flatten_prediction_packets(prediction_bundle)
        truth_bundle = d.evaluator_truth(target[index], episode_ordinal, tick)
        truth_packets = d.flatten_truth_packets(truth_bundle)
        truth_by_reference = {packet.stable_reference: packet for packet in truth_packets}
        relation_support_by_reference = {
            packet.stable_reference: support_id
            for packet, support_id in zip(
                prediction_bundle["relation_packets"],
                prediction_bundle["relation_supports"],
                strict=True,
            )
        }
        parity_packet = prediction_bundle["parity_packet"]
        relation_support_by_reference[parity_packet.stable_reference] = int(
            prediction_bundle["parity_support"]
        )
        transition_support_ids = tuple(relation_support_by_reference.values())
        before = snapshot_store(store, root_support_ids=transition_support_ids)
        d.materialize_world_witness(store, target[index], episode_ordinal, tick)
        after_witness = snapshot_store(store, root_support_ids=transition_support_ids)
        witness_metrics = _snapshot_slot_metrics(after_witness, truth_packets)
        after_witness_false += int(witness_metrics["false"])
        after_witness_correct += int(witness_metrics["correct"])
        d.derive_from_committed_coordinates(
            store, target[index], episode_ordinal, tick
        )
        after_recompute = snapshot_store(store, root_support_ids=transition_support_ids)
        peak_claims = max(peak_claims, int(after_recompute.claims.__len__()))
        for packet in predicted_packets:
            correct, actual = _packet_truth(packet, truth_by_reference)
            packet_rows.append(
                {
                    "stable_reference": packet.stable_reference,
                    "derived": packet.relation in DERIVED_RELATIONS,
                    "correct": correct,
                    "authority": authority,
                }
            )
            if not correct:
                rollback_targets += 1
                if after_recompute.status((packet.stable_reference, packet.value)) == d.STATUS_REVOKED:
                    rollback_successes += 1
                if packet.relation in (d.REL_LEFT_OF, d.REL_ABOVE, d.REL_ORDER_PARITY):
                    derived_contradictions += 1
            if packet.relation in DERIVED_RELATIONS:
                transitions.append(
                    classify_derived_transition(
                        packet,
                        actual,
                        relation_support_by_reference[packet.stable_reference],
                        before,
                        after_witness,
                        after_recompute,
                    )
                )
        after_metrics = _snapshot_slot_metrics(after_recompute, truth_packets)
        witness_slots += int(after_metrics["slots"])
        correct_durable_slots += int(after_metrics["correct"])
        false_durable_after_witness += int(after_metrics["false"])
        peak_claims = max(peak_claims, int(after_recompute.claims.__len__()))
        if peak_claims > MAX_ACTIVE_CLAIMS:
            active_bound_violations += 1

    transition_metrics = aggregate_transitions(transitions)
    total_contradictions = rollback_targets
    candidate = {
        **transition_metrics,
        "rollback_targets": rollback_targets,
        "rollback_successes": rollback_successes,
        "rollback_recall": rollback_successes / rollback_targets
        if rollback_targets
        else 0.0,
        "witness_slots": witness_slots,
        "correct_durable_slots": correct_durable_slots,
        "durable_coverage": correct_durable_slots / witness_slots
        if witness_slots
        else 0.0,
        "false_durable_claims": false_durable_after_witness,
        "false_durable_claim_rate": false_durable_after_witness / witness_slots
        if witness_slots
        else 0.0,
        "contradictions": total_contradictions,
        "derived_contradictions": derived_contradictions,
        "active_store_maximum": peak_claims,
        "active_store_bound_violations": active_bound_violations,
    }
    quality = graph_quality_metrics(store)
    candidate.update(
        {
            "stale_support_survival_rate": transition_metrics[
                "stale_support_survival_rate"
            ],
            "recomputation_precision": transition_metrics[
                "recomputed_after_parent_change"
            ]["precision"],
            "recomputation_recall": transition_metrics[
                "recomputed_after_parent_change"
            ]["recall"],
            "duplicate_support_rate": quality["duplicate_support_rate"],
            "orphan_support_rate": quality["orphan_support_rate"],
            "support_DAG_integrity": quality["support_DAG_integrity"],
            "deterministic_semantic_replay": quality["deterministic_replay"],
            "cycle_attempts_rejected": cycle_attempts_rejected,
            "after_witness_false_durable_claims": after_witness_false,
            "after_witness_durable_coverage": after_witness_correct / witness_slots
            if witness_slots
            else 0.0,
        }
    )
    controls = _control_results(
        packet_rows,
        {
            "slots": witness_slots,
            "false": after_witness_false,
            "coverage": after_witness_correct / witness_slots if witness_slots else 0.0,
        },
        candidate,
    )
    return {
        "episode_ordinal": episode_ordinal,
        "metrics": candidate,
        "controls": controls,
        "quality": quality,
        "failure_counts": {
            "contradictions": total_contradictions,
            "alternate_support_preservation_failures": candidate[
                "alternate_support_preservation"
            ]["opportunities"]
            - candidate["alternate_support_preservation"]["successes"],
            "recomputation_after_parent_change_failures": candidate[
                "recomputed_after_parent_change"
            ]["opportunities"]
            - candidate["recomputed_after_parent_change"]["successes"],
            "false_durable_claims": false_durable_after_witness,
            "active_store_bound_violations": active_bound_violations,
        },
    }


def _run_challenge(
    model: InnovationModel,
    selection: dict[int, tuple[int, ...]],
) -> dict[str, object]:
    rows = []
    ordinal = 0
    for mode in MODES:
        for episode_seed in selection[mode]:
            rows.append(
                _run_developmental_episode(
                    model,
                    collect_pairs(
                        episode_seed,
                        CHALLENGE_EPISODE_LENGTH,
                        surprise=True,
                    ),
                    ordinal,
                )
            )
            rows[-1]["mode_evaluator_only"] = mode
            rows[-1]["episode_seed_evaluator_only"] = episode_seed
            ordinal += 1
    metric_names = (
        "alternate_support_preservation",
        "recomputed_after_parent_change",
    )
    aggregate: dict[str, object] = {}
    for name in metric_names:
        opportunities = sum(
            int(row["metrics"][name]["opportunities"]) for row in rows
        )
        successes = sum(int(row["metrics"][name]["successes"]) for row in rows)
        aggregate[name] = {
            "opportunities": opportunities,
            "successes": successes,
            "rate": successes / opportunities if opportunities else 0.0,
        }
    scalar_names = (
        "rollback_targets",
        "rollback_successes",
        "witness_slots",
        "correct_durable_slots",
        "false_durable_claims",
        "contradictions",
        "derived_contradictions",
        "active_store_maximum",
        "active_store_bound_violations",
    )
    for name in scalar_names:
        values = [row["metrics"][name] for row in rows]
        aggregate[name] = sum(values) if name != "active_store_maximum" else max(values)
    aggregate["rollback_recall"] = (
        aggregate["rollback_successes"] / aggregate["rollback_targets"]
        if aggregate["rollback_targets"]
        else 0.0
    )
    aggregate["durable_coverage"] = (
        aggregate["correct_durable_slots"] / aggregate["witness_slots"]
        if aggregate["witness_slots"]
        else 0.0
    )
    aggregate["false_durable_claim_rate"] = (
        aggregate["false_durable_claims"] / aggregate["witness_slots"]
        if aggregate["witness_slots"]
        else 0.0
    )
    for name in (
        "stale_support_survival_rate",
        "recomputation_precision",
        "recomputation_recall",
        "duplicate_support_rate",
        "orphan_support_rate",
    ):
        values = [float(row["metrics"][name]) for row in rows]
        aggregate[name] = float(np.mean(values))
    aggregate["support_DAG_integrity"] = all(
        row["metrics"]["support_DAG_integrity"] for row in rows
    )
    aggregate["deterministic_semantic_replay"] = all(
        row["metrics"]["deterministic_semantic_replay"] for row in rows
    )
    aggregate["cycle_attempts_rejected"] = sum(
        row["metrics"]["cycle_attempts_rejected"] for row in rows
    )
    controls: dict[str, dict[str, object]] = {}
    for control in CONTROLS:
        control_rows = [row["controls"][control.name] for row in rows]
        controls[control.name] = {
            "episodes": len(control_rows),
            "false_durable_claims": sum(
                int(row.get("false_durable_claims", 0)) for row in control_rows
            ),
            "false_durable_claim_rate": float(
                np.mean([float(row.get("false_durable_claim_rate", 0.0)) for row in control_rows])
            ),
            "durable_coverage": float(
                np.mean([float(row.get("durable_coverage", 0.0)) for row in control_rows])
            ),
            "provenance": control_rows[0].get("provenance"),
        }
        if control.name == "DUAL_AUTHORITY":
            controls[control.name]["alternate_support_preservation"] = aggregate[
                "alternate_support_preservation"
            ]
            controls[control.name]["recomputed_after_parent_change"] = aggregate[
                "recomputed_after_parent_change"
            ]
        if control.name == "WITNESS_NO_DAG":
            controls[control.name]["stale_descendants"] = sum(
                int(row.get("stale_descendants", 0)) for row in control_rows
            )
    return {"rows": rows, "aggregate": aggregate, "controls": controls}


def _run_scaling_probe() -> list[dict[str, object]]:
    rows = []
    for length in (32, 64, 128, 256):
        store = d.EpistemicStore(max_claims=MAX_ACTIVE_CLAIMS)
        tracemalloc.start()
        started = time.perf_counter()
        for tick in range(1, length + 1):
            phase = np.float32((tick % 11) / 10.0 - 0.5)
            state = np.array(
                [phase, -phase, -0.4, 0.4, 0.2, -0.2], dtype=np.float32
            )
            predicted = state.copy()
            if tick % 3 == 0:
                predicted[0] = np.float32(-predicted[0])
            d.materialize_prediction(store, predicted, 0, tick)
            d.materialize_world_witness(store, state, 0, tick)
            d.derive_from_committed_coordinates(store, state, 0, tick)
        elapsed = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(
            {
                "episode_length": length,
                "elapsed_seconds": elapsed,
                "peak_python_bytes": peak_bytes,
                "active_claims": len(store.claims),
                "peak_claims": store.peak_claims,
                "support_count": len(store.supports),
                "ledger_events": store.ledger.count,
                "deterministic_replay": (
                    store.ledger.head_sha256 == store.ledger.replay_head()
                ),
            }
        )
    return rows


def _selection(model_seed: int) -> dict[str, dict[int, tuple[int, ...]]]:
    starts = selector_starts(model_seed)
    return {
        "train": select_balanced_episode_seeds(
            model_seed + TRAIN_SELECTOR_ROOT_OFFSET,
            TRAIN_PER_MODE,
            start=starts["training"],
        ),
        "ordinary_test": select_balanced_episode_seeds(
            model_seed + ORDINARY_TEST_SELECTOR_ROOT_OFFSET,
            ORDINARY_TEST_PER_MODE,
            start=starts["ordinary_test"],
        ),
        "challenge": select_balanced_episode_seeds(
            model_seed + CHALLENGE_SELECTOR_ROOT_OFFSET,
            CHALLENGE_PER_MODE,
            start=starts["challenge"],
        ),
    }


def run_development_seed(model_seed: int) -> dict[str, object]:
    if model_seed in QUALIFICATION_SEEDS:
        assert_qualification_locked(model_seed)
    if not development_seed_is_allowed(model_seed):
        raise RuntimeError(
            f"seed {model_seed} is not authorized for this development phase"
        )
    selection = _selection(model_seed)
    model = _train_candidate(selection["train"], model_seed)
    predictive = _predictive_qualification(model, selection["ordinary_test"])
    challenge = _run_challenge(model, selection["challenge"])
    report: dict[str, object] = {
        "status": "WILDFLOWER_DUAL_AUTHORITY_0_1_DEVELOPMENT",
        "model_seed": model_seed,
        "phase": "development",
        "natural_language_in_cognitive_path": False,
        "source_hashes": _source_hashes(),
        "runtime": {
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "pythonhashseed": "0",
        },
        "selector_ranges": selector_starts(model_seed),
        "episode_selection": selection,
        "controls": [control.name for control in CONTROLS],
        "predictive_authority": {
            "threshold": THRESHOLD,
            "width": WIDTH,
            "decay": DECAY,
            "burn": BURN,
            "result": predictive,
        },
        "developmental_epistemic_challenge": challenge,
        "scaling_probe": _run_scaling_probe(),
        "qualification_guard": {
            "locked": True,
            "protected_seeds": list(QUALIFICATION_SEEDS),
        },
        "architecture_freeze_authorized": False,
        "successor_authorized": False,
    }
    report["semantic_receipt_sha256"] = stable_hash(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, choices=MODEL_SEEDS, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = run_development_seed(args.seed)
    output = args.output or OUTPUT_ROOT / f"development_seed{args.seed}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "model_seed": args.seed,
        "semantic_receipt_sha256": report["semantic_receipt_sha256"],
        "alternate_support_preservation": report[
            "developmental_epistemic_challenge"
        ]["aggregate"]["alternate_support_preservation"],
        "recomputed_after_parent_change": report[
            "developmental_epistemic_challenge"
        ]["aggregate"]["recomputed_after_parent_change"],
        "output": str(output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
