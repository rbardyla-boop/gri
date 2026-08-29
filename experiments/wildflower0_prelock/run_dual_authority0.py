from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from dual_authority0 import (
    EpistemicStore,
    STATUS_COMMITTED,
    STATUS_PROVISIONAL,
    STATUS_REVOKED,
    derive_from_committed_coordinates,
    evaluator_truth,
    flatten_prediction_packets,
    flatten_truth_packets,
    materialize_prediction,
    materialize_world_witness,
)
from probe_innovation_model import InnovationModel, evaluate as eval_ungated, pre, train
from qualify_authority190 import (
    BURN,
    DECAY,
    THRESHOLD,
    WIDTH,
    eval_authority,
)
from wildflower0.nursery1 import (
    MODES,
    collect_pairs,
    select_balanced_episode_seeds,
    set_seed,
    stable_hash,
)

MODEL_SEED = 310
TRAIN_PER_MODE = 2
TEST_PER_MODE = 2
CHALLENGE_PER_MODE = 1
EPISODE_LENGTH = 420
EVAL_LENGTH = 520
CHALLENGE_LENGTH = 260
TRAIN_STEPS = 80
TRAIN_START = 600_000
TEST_START = 650_000
CHALLENGE_START = 700_000
MAX_CLAIMS = 8192
CONFIDENCE_THRESHOLD = 0.50
MIN_CONTRADICTIONS = 30
MIN_DERIVED_CONTRADICTIONS = 10
MIN_PRESERVATION_OPPORTUNITIES = 5
AUTHORIZATION_PATH = Path("DUAL_AUTHORITY_0_AUTHORIZATION.json")
FREEZE_MANIFEST_PATH = Path("DUAL_AUTHORITY_0_FREEZE_MANIFEST.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_authorization() -> dict[str, object]:
    if not AUTHORIZATION_PATH.exists():
        raise RuntimeError(
            "scored Dual-Authority-0 execution is blocked until a separate "
            "authorization-file commit exists"
        )
    authorization = json.loads(AUTHORIZATION_PATH.read_text())
    if authorization.get("model_seed") != MODEL_SEED:
        raise RuntimeError("authorization model seed mismatch")
    if authorization.get("run_count") != 1:
        raise RuntimeError("Dual-Authority-0 is one-shot")
    expected_manifest = authorization.get("freeze_manifest_sha256")
    if not isinstance(expected_manifest, str) or len(expected_manifest) != 64:
        raise RuntimeError("missing freeze-manifest digest")
    if _sha256(FREEZE_MANIFEST_PATH) != expected_manifest:
        raise RuntimeError("freeze-manifest digest mismatch")
    return authorization


def _train_candidate(
    train_selection: dict[int, tuple[int, ...]],
) -> InnovationModel:
    set_seed(MODEL_SEED)
    model = InnovationModel()
    order = [
        train_selection[mode][index]
        for index in range(TRAIN_PER_MODE)
        for mode in MODES
    ]
    for index, episode_seed in enumerate(order):
        train(
            model,
            collect_pairs(episode_seed, EPISODE_LENGTH),
            TRAIN_STEPS,
            MODEL_SEED + 10_000 + index,
        )
    return model


def _predictive_authority_one(
    model: InnovationModel,
    current: np.ndarray,
    actions: np.ndarray,
    index: int,
) -> dict[str, object]:
    """One-step frozen predictive-authority path using learner-visible arrays only."""
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
        alpha = float(np.clip((score - THRESHOLD) / WIDTH, 0.0, 1.0))

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
        prediction = (
            baseline + alpha * (learned - baseline)
        ).clamp(-1.0, 1.0)

    return {
        "prediction": prediction[0].cpu().numpy().astype(np.float32),
        "baseline": baseline[0].cpu().numpy().astype(np.float32),
        "learned": learned[0].cpu().numpy().astype(np.float32),
        "innovation_score_cells": score,
        "authority": alpha,
    }


def _predictive_qualification(
    model: InnovationModel,
    test_selection: dict[int, tuple[int, ...]],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for mode in MODES:
        for episode_seed in test_selection[mode]:
            pairs = collect_pairs(episode_seed, EVAL_LENGTH)
            row: dict[str, object] = {
                "mode": mode,
                "episode_seed": episode_seed,
            }
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
        "ungated_h1_max": float(
            np.max([row["ungated_h1_ratio"] for row in rows])
        ),
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
        "rows": rows,
        "aggregate": aggregate,
        "gates": gates,
        "passed": all(gates.values()),
    }


def run_developmental_episode(
    model: InnovationModel,
    pairs: list[object],
    episode_ordinal: int,
) -> dict[str, object]:
    """Sequential prediction -> provisional derivation -> world witness loop.

    This function receives only the ordinary learner projection from `pre`.
    Hidden mode and evaluator event flags never enter this path.
    """
    current, target, actions = pre(pairs)
    store = EpistemicStore(max_claims=MAX_CLAIMS)

    contradictions = 0
    coordinate_contradictions = 0
    derived_contradictions = 0
    wrong_pre_witness_committed = 0
    rollback_targets = 0
    rollback_successes = 0
    witness_slots = 0
    correct_durable_slots = 0
    false_durable_after_witness = 0
    direct_commit_false_durable = 0
    confidence_commit_false_durable = 0
    witness_no_dag_stale_descendants = 0
    preservation_opportunities = 0
    preservation_successes = 0
    authority_values: list[float] = []

    for index in range(BURN + 2, len(pairs) - 1):
        predictive = _predictive_authority_one(model, current, actions, index)
        authority = float(predictive["authority"])
        authority_values.append(authority)
        tick = index + 1

        prediction_bundle = materialize_prediction(
            store,
            predictive["prediction"],
            episode_ordinal,
            tick,
        )
        predicted_packets = flatten_prediction_packets(prediction_bundle)
        pre_status = {
            (packet.stable_reference, packet.value): store.status(
                packet.stable_reference,
                packet.value,
            )
            for packet in predicted_packets
        }

        truth_bundle = evaluator_truth(
            target[index],
            episode_ordinal,
            tick,
        )
        truth_packets = flatten_truth_packets(truth_bundle)
        truth_by_reference = {
            packet.stable_reference: packet
            for packet in truth_packets
        }

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

        # Independent epistemic witness: only direct coordinate observations.
        # No relation/parity truth is injected into the cognitive store.
        materialize_world_witness(
            store,
            target[index],
            episode_ordinal,
            tick,
        )

        # Preservation is measured before any post-witness recomputation:
        # a correct derived claim should become grounded through parent claims
        # even though their original prediction supports were retired.
        for packet in predicted_packets:
            actual = truth_by_reference[packet.stable_reference]
            if (
                packet.value == actual.value
                and packet.stable_reference in relation_support_by_reference
            ):
                support_id = relation_support_by_reference[packet.stable_reference]
                preservation_opportunities += 1
                if (
                    store.support_effective(support_id)
                    and store.status(packet.stable_reference, packet.value)
                    == STATUS_COMMITTED
                ):
                    preservation_successes += 1

        # Recompute correct derived facts from committed coordinate witnesses.
        derive_from_committed_coordinates(
            store,
            target[index],
            episode_ordinal,
            tick,
        )

        for packet in predicted_packets:
            actual = truth_by_reference[packet.stable_reference]
            if packet.value == actual.value:
                continue

            contradictions += 1
            direct_commit_false_durable += 1
            if packet.relation in (1, 2):
                coordinate_contradictions += 1
            else:
                derived_contradictions += 1
                witness_no_dag_stale_descendants += 1
            if authority >= CONFIDENCE_THRESHOLD:
                confidence_commit_false_durable += 1
            if (
                pre_status[(packet.stable_reference, packet.value)]
                == STATUS_COMMITTED
            ):
                wrong_pre_witness_committed += 1
            rollback_targets += 1
            if (
                store.status(packet.stable_reference, packet.value)
                == STATUS_REVOKED
            ):
                rollback_successes += 1

        for actual in truth_packets:
            witness_slots += 1
            committed = store.committed_values(actual.stable_reference)
            if committed == (actual.value,):
                correct_durable_slots += 1
            false_durable_after_witness += sum(
                value != actual.value
                for value in committed
            )

    counts = store.counts()
    rollback_recall = (
        rollback_successes / rollback_targets
        if rollback_targets
        else 0.0
    )
    durable_coverage = (
        correct_durable_slots / witness_slots
        if witness_slots
        else 0.0
    )
    preservation_rate = (
        preservation_successes / preservation_opportunities
        if preservation_opportunities
        else 0.0
    )
    return {
        "episode_ordinal": episode_ordinal,
        "contradictions": contradictions,
        "coordinate_contradictions": coordinate_contradictions,
        "derived_contradictions": derived_contradictions,
        "wrong_pre_witness_committed": wrong_pre_witness_committed,
        "rollback_targets": rollback_targets,
        "rollback_successes": rollback_successes,
        "rollback_recall": rollback_recall,
        "witness_slots": witness_slots,
        "correct_durable_slots": correct_durable_slots,
        "durable_coverage": durable_coverage,
        "false_durable_after_witness": false_durable_after_witness,
        "direct_commit_false_durable": direct_commit_false_durable,
        "confidence_commit_false_durable": confidence_commit_false_durable,
        "dag_no_witness_durable_coverage": 0.0,
        "witness_no_dag_stale_descendants": witness_no_dag_stale_descendants,
        "preservation_opportunities": preservation_opportunities,
        "preservation_successes": preservation_successes,
        "preservation_rate": preservation_rate,
        "authority_mean": float(np.mean(authority_values)),
        "authority_max": float(np.max(authority_values)),
        "active_store": counts,
        "revoked_support_count": store.revoked_support_count,
        "cascaded_support_count": store.cascaded_support_count,
        "ledger_head_sha256": store.ledger.head_sha256,
        "ledger_replay_sha256": store.ledger.replay_head(),
        "ledger_replay_passed": (
            store.ledger.head_sha256 == store.ledger.replay_head()
        ),
    }


def _developmental_challenge(
    model: InnovationModel,
    challenge_selection: dict[int, tuple[int, ...]],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    ordinal = 0
    for mode in MODES:
        for episode_seed in challenge_selection[mode]:
            row = run_developmental_episode(
                model,
                collect_pairs(
                    episode_seed,
                    CHALLENGE_LENGTH,
                    surprise=True,
                ),
                ordinal,
            )
            row["mode_evaluator_only"] = mode
            row["episode_seed_evaluator_only"] = episode_seed
            rows.append(row)
            ordinal += 1

    aggregate = {
        "contradictions": int(sum(row["contradictions"] for row in rows)),
        "coordinate_contradictions": int(
            sum(row["coordinate_contradictions"] for row in rows)
        ),
        "derived_contradictions": int(
            sum(row["derived_contradictions"] for row in rows)
        ),
        "wrong_pre_witness_committed": int(
            sum(row["wrong_pre_witness_committed"] for row in rows)
        ),
        "rollback_targets": int(sum(row["rollback_targets"] for row in rows)),
        "rollback_successes": int(
            sum(row["rollback_successes"] for row in rows)
        ),
        "witness_slots": int(sum(row["witness_slots"] for row in rows)),
        "correct_durable_slots": int(
            sum(row["correct_durable_slots"] for row in rows)
        ),
        "false_durable_after_witness": int(
            sum(row["false_durable_after_witness"] for row in rows)
        ),
        "direct_commit_false_durable": int(
            sum(row["direct_commit_false_durable"] for row in rows)
        ),
        "confidence_commit_false_durable": int(
            sum(row["confidence_commit_false_durable"] for row in rows)
        ),
        "witness_no_dag_stale_descendants": int(
            sum(row["witness_no_dag_stale_descendants"] for row in rows)
        ),
        "preservation_opportunities": int(
            sum(row["preservation_opportunities"] for row in rows)
        ),
        "preservation_successes": int(
            sum(row["preservation_successes"] for row in rows)
        ),
        "peak_claims_max": int(
            max(row["active_store"]["peak_claims"] for row in rows)
        ),
        "ledger_replay_all": all(
            row["ledger_replay_passed"] for row in rows
        ),
    }
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
    aggregate["preservation_rate"] = (
        aggregate["preservation_successes"]
        / aggregate["preservation_opportunities"]
        if aggregate["preservation_opportunities"]
        else 0.0
    )

    gates = {
        "challenge_has_enough_contradictions": (
            aggregate["contradictions"] >= MIN_CONTRADICTIONS
        ),
        "challenge_has_enough_derived_contradictions": (
            aggregate["derived_contradictions"]
            >= MIN_DERIVED_CONTRADICTIONS
        ),
        "prediction_never_self_commits_before_witness": (
            aggregate["wrong_pre_witness_committed"] == 0
        ),
        "rollback_recall_exact": aggregate["rollback_recall"] == 1.0,
        "no_false_durable_after_witness": (
            aggregate["false_durable_after_witness"] == 0
        ),
        "durable_coverage_at_least_99pct": (
            aggregate["durable_coverage"] >= 0.99
        ),
        "preservation_has_enough_opportunities": (
            aggregate["preservation_opportunities"]
            >= MIN_PRESERVATION_OPPORTUNITIES
        ),
        "alternate_support_preservation_exact": (
            aggregate["preservation_rate"] == 1.0
        ),
        "ledger_replay_exact": bool(aggregate["ledger_replay_all"]),
        "bounded_active_claims": aggregate["peak_claims_max"] <= MAX_CLAIMS,
    }
    controls = {
        "DIRECT_COMMIT_false_durable": aggregate[
            "direct_commit_false_durable"
        ],
        "CONFIDENCE_COMMIT_threshold": CONFIDENCE_THRESHOLD,
        "CONFIDENCE_COMMIT_false_durable": aggregate[
            "confidence_commit_false_durable"
        ],
        "DAG_NO_WITNESS_durable_coverage": 0.0,
        "WITNESS_NO_DAG_stale_descendants": aggregate[
            "witness_no_dag_stale_descendants"
        ],
    }
    mechanism_gates = {
        "dual_beats_direct_commit_on_false_durable": (
            aggregate["false_durable_after_witness"] == 0
            and controls["DIRECT_COMMIT_false_durable"] > 0
        ),
        "dual_beats_witness_without_dag_on_stale_descendants": (
            aggregate["rollback_recall"] == 1.0
            and controls["WITNESS_NO_DAG_stale_descendants"] > 0
        ),
        "world_witness_adds_durable_utility": (
            aggregate["durable_coverage"] >= 0.99
            and controls["DAG_NO_WITNESS_durable_coverage"] == 0.0
        ),
    }
    return {
        "rows": rows,
        "aggregate": aggregate,
        "gates": gates,
        "controls": controls,
        "mechanism_gates": mechanism_gates,
        "passed": all(gates.values()),
        "mechanism_credit_passed": all(mechanism_gates.values()),
    }


def main() -> int:
    authorization = _load_authorization()
    set_seed(MODEL_SEED)
    train_selection = select_balanced_episode_seeds(
        MODEL_SEED + 9000,
        TRAIN_PER_MODE,
        start=TRAIN_START,
    )
    test_selection = select_balanced_episode_seeds(
        MODEL_SEED + 19000,
        TEST_PER_MODE,
        start=TEST_START,
    )
    challenge_selection = select_balanced_episode_seeds(
        MODEL_SEED + 29000,
        CHALLENGE_PER_MODE,
        start=CHALLENGE_START,
    )
    model = _train_candidate(train_selection)
    predictive = _predictive_qualification(model, test_selection)
    developmental = _developmental_challenge(model, challenge_selection)

    challenge_gates = developmental["gates"]
    insufficient_challenge = not (
        challenge_gates["challenge_has_enough_contradictions"]
        and challenge_gates["challenge_has_enough_derived_contradictions"]
        and challenge_gates["preservation_has_enough_opportunities"]
    )
    if not predictive["passed"]:
        terminal_verdict = "PREDICTIVE_AUTHORITY_FAILED"
    elif insufficient_challenge:
        terminal_verdict = "INSUFFICIENT_CHALLENGE"
    elif not developmental["passed"]:
        terminal_verdict = "EPISTEMIC_AUTHORITY_FAILED"
    elif not developmental["mechanism_credit_passed"]:
        terminal_verdict = "MECHANISM_UNRESOLVED"
    else:
        terminal_verdict = "DUAL_AUTHORITY_DEMONSTRATED_WITHIN_TESTED_SCOPE"

    report = {
        "status": "WILDFLOWER_DUAL_AUTHORITY_0",
        "terminal_verdict": terminal_verdict,
        "model_seed": MODEL_SEED,
        "authorization_run_count": authorization["run_count"],
        "natural_language_in_cognitive_path": False,
        "frozen_predictive_authority": {
            "probe_innovation_model_sha256": (
                "97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1"
            ),
            "qualify_authority190_sha256": (
                "13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e"
            ),
            "threshold_cells": THRESHOLD,
            "width_cells": WIDTH,
            "decay": DECAY,
            "burn": BURN,
        },
        "fresh_design": {
            "train_per_mode": TRAIN_PER_MODE,
            "test_per_mode": TEST_PER_MODE,
            "challenge_per_mode": CHALLENGE_PER_MODE,
            "episode_length": EPISODE_LENGTH,
            "eval_length": EVAL_LENGTH,
            "challenge_length": CHALLENGE_LENGTH,
            "train_steps": TRAIN_STEPS,
            "train_start": TRAIN_START,
            "test_start": TEST_START,
            "challenge_start": CHALLENGE_START,
            "max_claims": MAX_CLAIMS,
            "confidence_control_threshold": CONFIDENCE_THRESHOLD,
        },
        "train_selection": train_selection,
        "test_selection": test_selection,
        "challenge_selection": challenge_selection,
        "predictive_authority_preservation": predictive,
        "developmental_epistemic_challenge": developmental,
        "predictive_gate_passed": predictive["passed"],
        "epistemic_gate_passed": developmental["passed"],
        "mechanism_credit_passed": developmental["mechanism_credit_passed"],
        "terminal_pass": (
            predictive["passed"]
            and developmental["passed"]
            and developmental["mechanism_credit_passed"]
        ),
        "architecture_freeze_authorized": False,
        "successor_authorized": False,
    }
    report["receipt_sha256"] = stable_hash(report)
    output = Path("artifacts/dual_authority0.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
