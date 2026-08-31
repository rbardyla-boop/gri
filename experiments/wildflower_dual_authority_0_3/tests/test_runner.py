from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from experiments.wildflower_dual_authority_0_3 import store as d
from experiments.wildflower_dual_authority_0_3.controls import (
    CONTROL_SPECS,
    RecordedTransition,
    StreamClaim,
    score_recorded_stream,
)
from experiments.wildflower_dual_authority_0_3 import run_dual_authority03 as runner


def _packet(
    reference: int,
    value: int,
    act: int,
    relation: int = d.REL_X,
) -> d.Packet:
    return d.Packet(reference, act, reference, relation, 0, value)


def _recomputation_stream() -> tuple[RecordedTransition, ...]:
    wrong_left = StreamClaim(_packet(1, 0, d.ACT_PROPOSE))
    wrong_right = StreamClaim(_packet(2, 0, d.ACT_PROPOSE))
    wrong_child = StreamClaim(
        _packet(10, 0, d.ACT_DERIVE, d.REL_ORDER_PARITY),
        ((1, 0), (2, 0)),
    )
    correct_left = StreamClaim(_packet(1, 1, d.ACT_PROPOSE))
    correct_right = StreamClaim(_packet(2, 1, d.ACT_PROPOSE))
    correct_child = StreamClaim(
        _packet(10, 1, d.ACT_DERIVE, d.REL_ORDER_PARITY),
        ((1, 1), (2, 1)),
    )
    return (
        RecordedTransition(
            tick=0,
            predictions=(wrong_left, wrong_right, wrong_child),
            witnesses=(),
            recomputed=(),
            authority=1.0,
            truth_packets=(),
        ),
        RecordedTransition(
            tick=1,
            predictions=(),
            witnesses=(
                _packet(1, 1, d.ACT_OBSERVE),
                _packet(2, 1, d.ACT_OBSERVE),
            ),
            recomputed=(correct_left, correct_right, correct_child),
            authority=1.0,
            truth_packets=(
                _packet(1, 1, d.ACT_OBSERVE),
                _packet(2, 1, d.ACT_OBSERVE),
                _packet(10, 1, d.ACT_OBSERVE, d.REL_ORDER_PARITY),
            ),
            recomputation_targets=(correct_child,),
        ),
    )


def test_only_seed_340_is_authorized_for_execution() -> None:
    runner._assert_seed_authorized(340)


def test_other_registered_seeds_are_rejected_by_runner() -> None:
    for seed in (341, 342):
        with pytest.raises(RuntimeError):
            runner._assert_seed_authorized(seed)
    for seed in (350, 351):
        with pytest.raises(RuntimeError, match="locked"):
            runner._assert_seed_authorized(seed)


def test_historical_and_unknown_seeds_are_rejected() -> None:
    for seed in (311, 312, 313, 314, 315, 999):
        with pytest.raises(ValueError):
            runner._assert_seed_authorized(seed)


def test_selector_payload_is_exact_and_disjoint() -> None:
    selection = runner._selection(340)
    payload = runner._selector_payload(340, selection)
    assert payload["starts"] == {
        "training": 3_000_000,
        "ordinary_test": 3_050_000,
        "challenge": 3_100_000,
    }
    assert payload["ranges"] == {
        "training": (3_000_000, 3_049_999),
        "ordinary_test": (3_050_000, 3_099_999),
        "challenge": (3_100_000, 3_149_999),
    }
    assert set(selection) == {"training", "ordinary_test", "challenge"}


def test_selected_episode_seeds_are_generated_from_preregistered_ranges() -> None:
    selection = runner._selection(340)
    roots = {
        "training": (340 + runner.design.TRAIN_SELECTOR_ROOT_OFFSET, 3_000_000),
        "ordinary_test": (
            340 + runner.design.ORDINARY_TEST_SELECTOR_ROOT_OFFSET,
            3_050_000,
        ),
        "challenge": (340 + runner.design.CHALLENGE_SELECTOR_ROOT_OFFSET, 3_100_000),
    }
    for name, (root, start) in roots.items():
        end = start + runner.design.SELECTOR_RANGE_WIDTH
        for seeds in selection[name].values():
            assert all(root * 100_000 + start <= seed < root * 100_000 + end for seed in seeds)


def test_truth_sidecar_is_absent_from_mechanism_frame() -> None:
    frame = _recomputation_stream()[0]
    mechanism_frame = frame.mechanism_frame
    assert not hasattr(mechanism_frame, "truth_packets")
    assert not hasattr(mechanism_frame, "preservation_targets")
    assert not hasattr(mechanism_frame, "recomputation_targets")


def test_predictive_function_has_no_truth_input() -> None:
    assert tuple(inspect.signature(runner._predictive_one).parameters) == (
        "model",
        "current",
        "actions",
        "index",
    )


def test_r1_mixed_key_lookup_reproduces_and_repairs_exact_crash() -> None:
    stable_reference = 2_000_000_961
    recomputed = StreamClaim(_packet(stable_reference, 1, d.ACT_DERIVE))
    recomputed_by_reference: dict[int, StreamClaim] = {
        recomputed.packet.stable_reference: recomputed
    }
    transition_claim: d.ClaimKey = (stable_reference, 1)

    with pytest.raises(KeyError):
        _ = recomputed_by_reference[transition_claim]
    assert recomputed_by_reference[transition_claim[0]] is recomputed


def test_stable_reference_mapping_preserves_existing_slot_behavior() -> None:
    stable_reference = 2_000_000_961
    first = StreamClaim(_packet(stable_reference, 0, d.ACT_DERIVE))
    second = StreamClaim(_packet(stable_reference, 1, d.ACT_DERIVE))
    recomputed_by_reference: dict[int, StreamClaim] = {
        claim.packet.stable_reference: claim for claim in (first, second)
    }
    assert recomputed_by_reference[stable_reference] is second
    assert recomputed_by_reference[(stable_reference, 1)[0]] is second


def test_runner_reports_all_seven_independent_controls() -> None:
    scores = score_recorded_stream(_recomputation_stream())
    assert tuple(scores) == tuple(spec.name for spec in CONTROL_SPECS)
    assert set(scores) == {
        "DUAL_AUTHORITY",
        "DIRECT_COMMIT",
        "CONFIDENCE_COMMIT",
        "DAG_NO_WITNESS",
        "WITNESS_NO_DAG",
        "WITNESS_PLUS_RECOMPUTE_NO_DAG",
        "DAG_PLUS_WITNESS_NO_RECOMPUTE",
    }
    assert scores["DUAL_AUTHORITY"].provenance_query_capability
    assert not scores["WITNESS_PLUS_RECOMPUTE_NO_DAG"].provenance_query_capability


def test_real_flat_control_is_not_given_fake_metric_b_provenance() -> None:
    scores = score_recorded_stream(_recomputation_stream())
    assert scores["DUAL_AUTHORITY"].metric_b_successes == 1
    assert scores["DUAL_AUTHORITY"].metric_b_false_positive_reconstructions == 0
    assert scores["WITNESS_PLUS_RECOMPUTE_NO_DAG"].metric_b_successes == 0
    assert scores["WITNESS_PLUS_RECOMPUTE_NO_DAG"].metric_b_false_positive_reconstructions == 1


def test_exact_semantic_and_lineage_duplicate_reuses_support_id() -> None:
    epistemic_store = d.ReferenceProvenanceStore()
    epistemic_store.observe(_packet(1, 1, d.ACT_OBSERVE))
    epistemic_store.observe(_packet(2, 1, d.ACT_OBSERVE))
    packet = _packet(10, 1, d.ACT_DERIVE, d.REL_ORDER_PARITY)
    first = epistemic_store.derive(packet, ((1, 1), (2, 1)))
    second = epistemic_store.derive(packet, ((2, 1), (1, 1)))
    assert first == second
    assert epistemic_store.engineering_metrics()["canonical_support_reuses"] == 1


def test_same_semantics_with_changed_lineage_gets_new_support() -> None:
    epistemic_store = d.ReferenceProvenanceStore()
    epistemic_store.observe(_packet(1, 1, d.ACT_OBSERVE))
    epistemic_store.observe(_packet(2, 1, d.ACT_OBSERVE))
    packet = _packet(10, 1, d.ACT_DERIVE, d.REL_ORDER_PARITY)
    first = epistemic_store.derive(packet, ((1, 1), (2, 1)))
    epistemic_store.observe(_packet(1, 1, d.ACT_OBSERVE, d.REL_ABOVE))
    second = epistemic_store.derive(packet, ((1, 1), (2, 1)))
    assert first != second
    assert epistemic_store.supports[first].parents == epistemic_store.supports[second].parents
    assert epistemic_store.supports[first].lineage_fingerprint != epistemic_store.supports[second].lineage_fingerprint


def test_dual_scaling_harness_contains_all_preregistered_sizes() -> None:
    rows = runner._dual_scaling_rows()
    assert [row["retained_events"] for row in rows] == [100, 1_000, 10_000, 100_000]
    assert all(row["correction_work"] >= 0 for row in rows)


def test_incremental_challenge_matches_reference_semantics() -> None:
    pairs = runner.collect_pairs(424242, 24, surprise=True)
    model = runner.InnovationModel()
    reference = runner._run_challenge_episode(
        model,
        pairs,
        mode=0,
        episode_seed=424242,
        episode_ordinal=0,
        store_factory=d.ReferenceProvenanceStore,
    )
    incremental = runner._run_challenge_episode(
        model,
        pairs,
        mode=0,
        episode_seed=424242,
        episode_ordinal=0,
    )
    reference_frames, reference_transitions, reference_metrics, _ = reference
    incremental_frames, incremental_transitions, incremental_metrics, _ = incremental
    assert reference_frames == incremental_frames
    assert reference_transitions == incremental_transitions
    metric_keys = {
        "alternate_support_preservation",
        "recomputed_after_parent_change",
        "semantic_duplicate_events",
        "same_semantics_new_provenance_events",
        "stale_support_survival_rate",
    }
    assert {
        key: reference_metrics[key] for key in metric_keys
    } == {key: incremental_metrics[key] for key in metric_keys}
    assert reference_metrics["support_inventory"] == incremental_metrics["support_inventory"]
    assert reference_metrics["graph_quality"] == incremental_metrics["graph_quality"]
    for field in (
        "support_insert_attempts",
        "canonical_support_creations",
        "canonical_support_reuses",
        "provenance_changes",
        "semantic_duplicates_reused",
        "active_supports",
        "historical_events",
    ):
        assert reference_metrics["engineering"][field] == incremental_metrics[
            "engineering"
        ][field]
    assert incremental_metrics["engineering"]["lineage_cache_hits"] > 0


def test_engineering_profile_controls_use_no_scientific_selectors() -> None:
    profile = runner.run_engineering_profile(("controls",))
    assert profile["mode"] == "ENGINEERING_PROFILE_ONLY"
    assert profile["engineering_seed"] == runner.PROFILE_ENGINEERING_SEED
    assert profile["scientific_selectors_used"] is False
    assert "selectors" not in profile
    assert set(profile["controls"]["scores"]) == {
        spec.name for spec in CONTROL_SPECS
    }
    assert "metric_a_b_scoring" in profile["phase_profile"]


def test_engineering_profile_scaling_reports_all_four_sizes() -> None:
    profile = runner.run_engineering_profile(("scaling",))
    assert [
        row["retained_events"]
        for row in profile["scaling"]["flat_recompute_everything"]
    ] == [100, 1_000, 10_000, 100_000]
    assert [
        row["retained_events"]
        for row in profile["scaling"]["dual_authority_affected_cone"]
    ] == [100, 1_000, 10_000, 100_000]


def test_runner_canonical_serialization_rejects_nonfinite_values() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="nonfinite"):
            runner._canonical_json_bytes({"value": value})


def test_runner_canonical_serialization_is_order_independent() -> None:
    first = runner._canonical_json_bytes({"b": [2, 1], "a": {"z": 0}})
    second = runner._canonical_json_bytes({"a": {"z": 0}, "b": [2, 1]})
    assert first == second


def test_semantic_receipt_excludes_operational_variability() -> None:
    first = {
        "semantic_receipt_sha256": "discarded",
        "runtime": {"wall_seconds": 1.0, "started_at": "one", "stable": 7},
        "controls": {"DUAL_AUTHORITY": {"runtime_seconds": 2.0, "stable": 8}},
        "scaling_adversary": {"dual": [{"elapsed_seconds": 3.0, "stable": 9}]},
    }
    second = {
        "scaling_adversary": {"dual": [{"stable": 9, "elapsed_seconds": 99.0}]},
        "controls": {"DUAL_AUTHORITY": {"stable": 8, "runtime_seconds": 88.0}},
        "runtime": {"stable": 7, "started_at": "two", "wall_seconds": 77.0},
        "semantic_receipt_sha256": "different",
    }
    assert runner.semantic_receipt_sha256(first) == runner.semantic_receipt_sha256(second)


def test_atomic_writer_is_fail_closed_before_replacing_output(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    with pytest.raises(ValueError, match="missing fields"):
        runner._atomic_write_json(output, {"not": "a result"})
    assert not output.exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_source_hash_guard_detects_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_source_hashes", lambda: {"source": "changed"})
    with pytest.raises(RuntimeError, match="source hash"):
        runner._assert_source_hashes_stable({"source": "initial"})


def test_help_is_available_without_running_a_seed() -> None:
    with pytest.raises(SystemExit) as exit_info:
        runner.main(["--help"])
    assert exit_info.value.code == 0
