from __future__ import annotations

import json
from collections import Counter

import pytest

from scripts import run_dmc05r as dmc05r


@pytest.fixture(scope="module")
def source_cases() -> list[dict]:
    return dmc05r.load_source_cases()


@pytest.fixture(scope="module")
def variants(source_cases: list[dict]) -> list[dmc05r.Variant]:
    rows, manifest = dmc05r.build_variants(source_cases)
    assert manifest["pass"]
    return rows


def test_preregistered_config_is_narrow_and_terminal() -> None:
    config = json.loads(dmc05r.CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["status"] == "PREREGISTERED_BEFORE_IMPLEMENTATION_AND_EXECUTION"
    assert config["counterfactual"]["expected_total_variants"] == 2376
    assert config["architecture_changes_authorized"] is False
    assert config["dmc_retraining_authorized"] is False
    assert config["threshold_changes_authorized"] is False
    assert config["capacity_changes_authorized"] is False
    assert config["feature_changes_authorized"] is False
    assert config["real_language_evaluation_authorized"] is False
    assert config["training_accounting"]["dmc_unique_suite_optimizer_steps"] == 10880
    assert config["training_accounting"]["historical_wall_time"] == "TRAINING_COST_UNKNOWN"


def test_dmc05a_terminal_receipt_preserves_strongest_finding() -> None:
    receipt = json.loads(
        (dmc05r.ROOT / "experiments/dmc05a/DMC05A_TERMINAL_RECEIPT.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["status"] == "TERMINAL_FROZEN"
    assert receipt["terminal_state"] == "DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES"
    assert receipt["scientific_disposition"]["cause"] == "BENCHMARK_ORDERING_CONFOUND"
    assert receipt["strongest_finding"]["paired_set_comparisons"] == 2960
    assert receipt["strongest_finding"]["matching_set_comparisons"] == 2960
    assert receipt["training_accounting"]["unique_suite_optimizer_steps"] == 10880
    assert receipt["training_accounting"]["historical_wall_time"] == "TRAINING_COST_UNKNOWN"


def test_source_identity_and_counts(source_cases: list[dict]) -> None:
    identity = dmc05r.verify_dataset_identity(source_cases)
    assert identity["pass"], identity
    assert identity["source_case_count"] == 592
    assert {int(key): value for key, value in identity["counts_by_history_size"].items()} == dmc05r.SOURCE_COUNTS


def test_variant_counts_are_preregistered(source_cases: list[dict]) -> None:
    rows, manifest = dmc05r.build_variants(source_cases)
    assert manifest["pass"], manifest["failed_invariant_variants"]
    assert len(rows) == 2376
    assert {int(key): value for key, value in manifest["counts_by_tail"].items()} == dmc05r.EXPECTED_VARIANTS_BY_TAIL
    assert manifest["skipped_count"] == 1176


def test_safe_count_distribution_is_frozen(source_cases: list[dict]) -> None:
    distribution = Counter(
        (int(case["metadata"]["write_load"]), len(dmc05r.certified_irrelevant_rows(case)))
        for case in source_cases
    )
    assert distribution == Counter(
        {
            (32, 0): 80,
            (32, 16): 96,
            (64, 32): 80,
            (64, 48): 80,
            (128, 96): 40,
            (128, 112): 48,
            (256, 224): 40,
            (256, 240): 40,
            (1024, 992): 40,
            (1024, 1008): 48,
        }
    )


def test_every_variant_passes_all_counterfactual_invariants(
    variants: list[dmc05r.Variant],
) -> None:
    assert all(variant.invariant["pass"] for variant in variants)
    required = {
        "record_multiset_unchanged",
        "record_payloads_unchanged",
        "protected_relative_order_preserved",
        "irrelevant_relative_order_preserved",
        "trailing_tail_exact",
        "all_moved_after_last_protected",
        "target_not_moved",
        "target_and_answer_unchanged",
        "supersession_payloads_unchanged",
    }
    for variant in variants:
        assert required.issubset(variant.invariant["checks"])
        assert all(variant.invariant["checks"][name] for name in required)


def test_primary_tails_make_target_nonrecent(variants: list[dmc05r.Variant]) -> None:
    for variant in variants:
        if variant.tail_size not in dmc05r.PRIMARY_TAILS:
            continue
        target = str(variant.source_case["oracle_view"]["target_record_id"])
        final_window = list(variant.stream[-dmc05r.CAPACITY :])
        assert target not in {str(row["record_id"]) for row in final_window}
        certified = {
            str(row["record_id"])
            for row in dmc05r.certified_irrelevant_rows(variant.source_case)
        }
        assert {str(row["record_id"]) for row in final_window}.issubset(certified)


def test_tail_zero_is_byte_identical_source_order(source_cases: list[dict]) -> None:
    for case in source_cases:
        variant = dmc05r.make_variant(case, 0)
        assert variant is not None
        assert dmc05r.canonical(list(variant.stream)) == dmc05r.canonical(case["experience_stream"])


def test_certifier_excludes_oracle_scope_salience_and_dependencies(source_cases: list[dict]) -> None:
    for case in source_cases:
        safe = dmc05r.certified_irrelevant_rows(case)
        oracle = {str(row["record_id"]) for row in case["oracle_view"]["records"]}
        scoped = dmc05r.scope_entities(case)
        referenced = {
            str(row["supersedes"])
            for row in case["experience_stream"]
            if row.get("supersedes") is not None
        }
        for row in safe:
            assert str(row["record_id"]) not in oracle
            assert str(row["record_id"]) != str(case["oracle_view"]["target_record_id"])
            assert str(row["entity"]) not in scoped
            assert row.get("supersedes") is None
            assert str(row["record_id"]) not in referenced
            assert row["retention_metadata"]["salience"] != "HIGH"
            assert [float(value) for value in row["retention_features"]] == [0.0, 0.0]


def test_explicit_utility_features_match_frozen_encoder(source_cases: list[dict]) -> None:
    _, d04b = dmc05r.frozen_modules()
    from dmc02p.controller import RetentionMetadata
    from dmc03p.retention import retention_features

    audit = {
        "evaluations": 0,
        "input_fields_observed": set(),
        "forbidden_fields_observed": set(),
    }
    sampled = []
    seen = set()
    for case in source_cases:
        for row in case["experience_stream"]:
            key = (
                row["retention_metadata"]["family"],
                row["retention_metadata"]["salience"],
                tuple(row["retention_features"]),
            )
            if key not in seen:
                sampled.append(row)
                seen.add(key)
    assert sampled
    for row in sampled:
        metadata = row["retention_metadata"]
        explicit = dmc05r.explicit_utility_features(metadata, row["active_entities"], audit)
        frozen = retention_features(
            RetentionMetadata(
                family=metadata["family"],
                entity=metadata["entity"],
                field=metadata["field"],
                creation_episode=metadata["creation_episode"],
                salience=metadata["salience"],
                supersedes=metadata["supersedes"],
            ),
            row["active_entities"],
        )
        assert explicit == tuple(int(value) for value in frozen.tolist())
    assert not audit["forbidden_fields_observed"]
    assert "record_id" not in audit["input_fields_observed"]


def test_random_16_set_is_order_invariant(variants: list[dmc05r.Variant]) -> None:
    d05a, _ = dmc05r.frozen_modules()
    grouped: dict[str, set[str]] = {}
    for variant in variants:
        case = dmc05r.materialize_case(variant)
        selected = d05a.frozen_random_rows(case)
        value = dmc05r.digest(sorted(str(row["record_id"]) for row in selected))
        grouped.setdefault(str(case["case_id"]), set()).add(value)
    assert grouped
    assert all(len(values) == 1 for values in grouped.values())


def test_transparent_selector_uses_equal_information_and_hard_capacity(
    variants: list[dmc05r.Variant],
) -> None:
    representatives = []
    for tail in dmc05r.TAIL_SIZES:
        representatives.append(next(row for row in variants if row.tail_size == tail))
    expected_fields = sorted(dmc05r.ALLOWED_RETENTION_METADATA | {"active_entities"})
    for variant in representatives:
        retained, audit = dmc05r.transparent_retention(dmc05r.materialize_case(variant))
        assert len(retained) <= dmc05r.CAPACITY
        assert audit["pass"]
        assert audit["input_fields_observed"] == expected_fields
        assert not audit["forbidden_fields_observed"]
        assert audit["tie_break_fields"] == ["record_id_sha256"]


def test_exact_structured_preserves_answer_on_boundary_variants(
    variants: list[dmc05r.Variant],
) -> None:
    sample = dmc05r.nonzero_boundary_variants(variants)
    for variant in sample:
        row = dmc05r.evaluate_conventional(
            "exact_structured",
            dmc05r.materialize_case(variant),
            variant_id=variant.variant_id,
            tail_size=variant.tail_size,
            subset="TEST",
        )
        assert row["critical_recall"] == 1
        assert row["retrieval_accuracy"] == 1
        assert row["answer_accuracy"] == 1


def test_fast_dmc_retention_matches_frozen_direct_on_one_nonzero_case(
    variants: list[dmc05r.Variant],
) -> None:
    d05a, d04b = dmc05r.frozen_modules()
    variant = next(row for row in variants if row.tail_size == 16 and row.history_size == 128)
    case = dmc05r.materialize_case(variant)
    models = d05a.load_dmc(1337)
    fast, fast_audit = dmc05r.fast_dmc_retention(models, case)
    direct_audit = d04b.retention_audit()
    direct, _ = d04b.learned_retention(models["retention"], case, direct_audit)
    assert [row["record_id"] for row in fast] == [row["record_id"] for row in direct]
    assert fast_audit["logical_score_evaluations"] == direct_audit["calls"]
    assert fast_audit["pass"]


def test_surprise_dependency_is_fixed_and_nonterminal(source_cases: list[dict]) -> None:
    from dmc04p.matcher import validate_scorer_view

    rows, manifest = dmc05r.build_surprise_cases(source_cases)
    assert manifest["pass"], manifest
    assert len(rows) == 24
    assert {len(row.case["experience_stream"]) for row in rows} == {128, 256, 1024}
    assert Counter(len(row.case["experience_stream"]) for row in rows) == Counter(
        {128: 8, 256: 8, 1024: 8}
    )
    assert all(row.invariant["pass"] for row in rows)
    assert all(row.target_entity not in row.source_case["metadata"]["scope_events"][0]["entities"] for row in rows)
    assert all(row.target_entity in row.late_scope for row in rows)
    for row in rows:
        candidates = [
            {
                "write_descriptor": item["write_descriptor"],
                "creation_episode": item["creation_episode"],
            }
            for item in row.case["experience_stream"][: dmc05r.CAPACITY]
        ]
        validation = validate_scorer_view(
            {"query": row.case["neural_view"]["query"], "candidates": candidates}
        )
        assert validation["pass"]


def test_surprise_all_history_control_recovers_old_target(source_cases: list[dict]) -> None:
    rows, _ = dmc05r.build_surprise_cases(source_cases)
    for item in rows:
        result = dmc05r.evaluate_conventional(
            "exact_structured",
            item.case,
            variant_id=item.variant_id,
            tail_size=None,
            subset="SURPRISE_DEPENDENCY",
        )
        assert result["critical_recall"] == 1
        assert result["retrieval_accuracy"] == 1
        assert result["answer_accuracy"] == 1


def _metric(mean: float) -> dict:
    return {"mean": mean}


def _fake_aggregate(
    *, dmc: float, recent: float, transparent: float, transparent_resource_ratio: float = 0.5
) -> dict:
    systems = {}
    for system in dmc05r.ALL_SYSTEMS:
        capability = (
            dmc
            if system == "dmc04b"
            else recent
            if system == "recent_window_16"
            else transparent
            if system == "transparent_utility_index_16"
            else 1.0
        )
        is_dmc = system == "dmc04b"
        is_transparent = system == "transparent_utility_index_16"
        resource_scale = 1.0 if is_dmc else transparent_resource_ratio if is_transparent else 1.0
        metrics = {
            "critical_recall": _metric(capability),
            "answer_accuracy": _metric(capability),
            "persistent_records": _metric(16.0 * resource_scale),
            "persistent_serialized_bytes": _metric(9000.0 * resource_scale),
            "maximum_working_set_records": _metric(16.0 * resource_scale),
            "working_set_serialized_bytes": _metric(3000.0 * resource_scale),
            "records_inspected_query": _metric(16.0 * resource_scale),
            "online_wall_ns": _metric(1_000_000.0 * resource_scale),
            "learned_forward_calls": _metric(4.0 if is_dmc else 0.0),
            "historical_training_required": _metric(1.0 if is_dmc else 0.0),
        }
        systems[system] = {
            "subsets": {"primary": {"metrics": metrics}},
            "by_tail": {
                str(tail): {
                    "metrics": {
                        "answer_accuracy": _metric(capability),
                        "critical_recall": _metric(capability),
                    }
                }
                for tail in dmc05r.TAIL_SIZES
            },
        }
    return {"systems": systems}


def test_mechanical_verdict_precedence() -> None:
    valid = {"all": True}
    invalid = dmc05r.calculate_gates(
        _fake_aggregate(dmc=1.0, recent=0.0, transparent=1.0), {"all": False}
    )
    assert invalid["terminal_state"] == "DMC_05R_ACCOUNTING_INVALID"

    recency_failure = dmc05r.calculate_gates(
        _fake_aggregate(dmc=0.2, recent=0.0, transparent=1.0), valid
    )
    assert recency_failure["terminal_state"] == "DMC_05R_RECENCY_ONLY_FAILURE"

    selection = dmc05r.calculate_gates(
        _fake_aggregate(dmc=1.0, recent=0.0, transparent=0.8), valid
    )
    assert selection["terminal_state"] == "DMC_05R_SELECTION_ADVANTAGE"

    transparent = dmc05r.calculate_gates(
        _fake_aggregate(dmc=1.0, recent=0.0, transparent=1.0), valid
    )
    assert transparent["terminal_state"] == "DMC_05R_TRANSPARENT_INDEX_DOMINATES"

    nonrecency = dmc05r.calculate_gates(
        _fake_aggregate(
            dmc=1.0,
            recent=0.0,
            transparent=1.0,
            transparent_resource_ratio=2.0,
        ),
        valid,
    )
    assert nonrecency["terminal_state"] == "DMC_05R_NONRECENCY_RETENTION_ADVANCE"


def test_training_accounting_never_reads_zero_cost() -> None:
    accounting = dmc05r.training_accounting(2376 * 5)
    assert accounting["status"] == "TRAINING_COST_UNKNOWN"
    assert accounting["dmc04b"]["unique_suite_optimizer_steps"] == 10880
    assert accounting["dmc04b"]["historical_wall_time"] == "TRAINING_COST_UNKNOWN"
    assert accounting["scientific_run"]["optimizer_steps"] == 0
    assert accounting["scientific_run"]["training_executed"] is False


def test_preregistered_anchor_hashes_match() -> None:
    anchors = dmc05r.verify_preregistered_anchors()
    assert anchors["pass"], anchors


def test_freeze_matches_runner_and_tests() -> None:
    freeze = dmc05r.verify_freeze()
    assert freeze["pass"], freeze
