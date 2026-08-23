from __future__ import annotations

import json
from collections import Counter

import pytest

from scripts import run_mco01 as mco01


@pytest.fixture(scope="module")
def small_history() -> dict:
    return mco01.build_history(2601, 100)


@pytest.fixture(scope="module")
def dataset_check() -> dict:
    return mco01.verify_dataset(deep=True)


def test_dmc_branch_is_terminal_and_mco01_is_the_only_successor() -> None:
    receipt = json.loads(mco01.TERMINAL_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["status"] == "TERMINAL_BRANCH_STOP"
    assert receipt["scientific_chain"][-1]["verdict"] == (
        "DMC_05R_TRANSPARENT_INDEX_DOMINATES"
    )
    assert receipt["terminal_interpretation"]["architecture_advantage"] is False
    assert receipt["terminal_interpretation"]["authorized_successor"] == (
        "MCO-01 — STORE ALL, THINK SMALL"
    )
    assert receipt["training_cost_accounting"][
        "reconstructed_historical_optimizer_steps"
    ] == 10880
    assert receipt["training_cost_accounting"]["label"] == "TRAINING_COST_UNKNOWN"


def test_config_was_preregistered_without_retention_or_language_work() -> None:
    config = json.loads(mco01.CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["status"] == "PREREGISTERED_BEFORE_DATASET_GENERATION"
    assert config["dataset"]["expected_history_count"] == 20
    assert config["dataset"]["expected_query_count"] == 160
    assert config["dataset"]["expected_total_event_records"] == 555500
    assert config["frozen_scope"]["learned_retention"] is False
    assert config["frozen_scope"]["utility_labels_at_ingestion"] is False
    assert config["frozen_scope"]["language_model_inference"] is False
    assert config["frozen_scope"]["tokenizer_accounting"] is False
    assert config["frozen_scope"]["active_record_cap"] == 16
    assert config["systems"] == [
        {"id": "full_history_oracle", "stored_records": "all", "active_records": "all"},
        {"id": "recent_16", "stored_records": 16, "active_records": 16},
        {
            "id": "exact_structured_lookup",
            "stored_records": "all",
            "active_records_max": 16,
        },
        {
            "id": "conventional_one_shot_retrieval",
            "stored_records": "all",
            "active_records_max": 16,
            "retrieval_rounds": 1,
        },
        {
            "id": "iterative_need_retrieval",
            "stored_records": "all",
            "active_records_max": 16,
            "interface": "NEED(subject, relation)",
        },
    ]


def test_generation_is_deterministic_and_integrity_clean(small_history: dict) -> None:
    replay = mco01.build_history(2601, 100)
    assert mco01.digest(small_history) == mco01.digest(replay)
    check = mco01.verify_history(small_history)
    assert check["pass"], check
    assert check["record_count"] == 100
    assert check["query_count"] == 8
    assert check["hop_counts"] == {"2": 2, "3": 2, "4": 2, "5": 2}
    assert set(check["family_counts"]) == {
        "contradiction",
        "correction",
        "delayed_dependency",
        "distractor_hard",
        "rename",
        "supersession",
    }


def test_records_expose_no_labels_or_case_identifiers(small_history: dict) -> None:
    for row in small_history["records"]:
        assert frozenset(row) == mco01.RECORD_FIELDS
        assert not (frozenset(row) & mco01.FORBIDDEN_RECORD_FIELDS)
        payload = mco01.canonical(row)
        assert "query_id" not in payload
        assert "chain_id" not in payload
        assert "utility" not in payload
        assert "answer" not in payload


def test_every_path_defeats_contiguous_fifo_and_recency_windows(
    small_history: dict,
) -> None:
    record_ids = [row["record_id"] for row in small_history["records"]]
    positions = {record_id: index for index, record_id in enumerate(record_ids)}
    for query in small_history["queries"]:
        path = query["expected"]["path_record_ids"]
        path_positions = [positions[record_id] for record_id in path]
        assert max(path_positions) - min(path_positions) > mco01.CAPACITY
        assert not set(path).issubset(record_ids[: mco01.CAPACITY])
        assert not set(path).issubset(record_ids[-mco01.CAPACITY :])


def test_update_resolution_uses_supersession_then_source_priority(
    small_history: dict,
) -> None:
    index = mco01.index_records(small_history["records"])
    by_id = {row["record_id"]: row for row in small_history["records"]}
    observed = 0
    for query in small_history["queries"]:
        for winner_id in query["expected"]["updated_record_ids"]:
            winner = by_id[winner_id]
            bucket = index[(winner["subject"], winner["relation"])]
            assert len(bucket) >= 2
            assert mco01.winning_record(bucket)["record_id"] == winner_id
            observed += 1
    assert observed > 0


def test_public_query_withholds_hops_families_and_expected_answer(
    small_history: dict,
) -> None:
    visible = mco01.public_query(small_history["queries"][0])
    assert set(visible) == {"root_entity", "deployment_temperature"}
    assert "expected" not in visible
    assert "dependency_hops" not in visible
    assert "families" not in visible


def test_exact_and_iterative_recover_all_small_history_queries_under_cap(
    small_history: dict,
) -> None:
    context = mco01.make_context(small_history["records"])
    for query in small_history["queries"]:
        public = mco01.public_query(query)
        for system in ("exact_structured_lookup", "iterative_need_retrieval"):
            outcome = mco01.SYSTEM_FUNCTIONS[system](context, public)
            row = mco01.score_outcome(
                history=small_history,
                query=query,
                system=system,
                outcome=outcome,
                wall_time_seconds=0.0,
            )
            assert row["answer_accuracy"] == 1.0
            assert row["critical_recall"] == 1.0
            assert row["dependency_chain_accuracy"] == 1.0
            assert row["temporal_update_accuracy"] == 1.0
            assert row["provenance_accuracy"] == 1.0
            assert row["maximum_active_records"] <= mco01.CAPACITY


def test_one_shot_is_one_round_and_deterministic(small_history: dict) -> None:
    context = mco01.make_context(small_history["records"])
    for query in small_history["queries"]:
        public = mco01.public_query(query)
        left = mco01.system_conventional_one_shot(context, public)
        right = mco01.system_conventional_one_shot(context, public)
        assert left["retrieval_rounds"] == 1
        assert left["maximum_active_records"] == 16
        assert left["retrieved_record_ids"] == right["retrieved_record_ids"]
        assert left["prediction"] == right["prediction"]


def test_frozen_dataset_identity_and_deep_integrity(dataset_check: dict) -> None:
    assert dataset_check["pass"], dataset_check["errors"]
    assert len(dataset_check["file_checks"]) == 20
    assert len(dataset_check["deep_checks"]) == 20
    assert all(row["pass"] for row in dataset_check["file_checks"])
    assert all(row["pass"] for row in dataset_check["deep_checks"])


def test_frozen_dataset_population_and_placement_quartiles() -> None:
    manifest = json.loads(
        mco01.DATASET_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert manifest["history_count"] == 20
    assert manifest["query_count"] == 160
    assert manifest["record_count"] == 555500
    assert manifest["integrity"]["pass"]
    assert manifest["integrity"]["hop_counts"] == {
        "2": 40,
        "3": 40,
        "4": 40,
        "5": 40,
    }
    for load, placement in manifest["integrity"]["placement_quartiles"].items():
        assert int(load) in mco01.HISTORY_SIZES
        assert placement["pass"]
        assert all(0.10 <= value <= 0.40 for value in placement["shares"].values())


def test_dataset_has_exact_seed_load_coverage() -> None:
    manifest = json.loads(
        mco01.DATASET_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    coverage = Counter((row["history_size"], row["seed"]) for row in manifest["files"])
    assert coverage == Counter(
        {(size, seed): 1 for size in mco01.HISTORY_SIZES for seed in mco01.SEEDS}
    )


def test_freeze_hashes_match_before_scientific_execution() -> None:
    check = mco01.verify_freeze()
    assert check["pass"], check


def test_verdict_logic_credits_iterative_acquisition_materially() -> None:
    def summary(answer: float, active: int) -> dict:
        return {
            "n": 40,
            "answer_accuracy": answer,
            "critical_recall": answer,
            "dependency_chain_accuracy": answer,
            "temporal_update_accuracy": answer,
            "provenance_accuracy": answer,
            "maximum_active_records": active,
            "mean_active_records": float(active),
            "records_retrieved_per_question": float(active),
            "retrieval_rounds": 1.0,
            "external_bytes": 1.0,
            "external_reads": 1.0,
            "external_index_probes": 1.0,
        }

    systems = {
        "full_history_oracle": summary(1.0, 100),
        "recent_16": summary(0.0, 16),
        "exact_structured_lookup": summary(1.0, 5),
        "conventional_one_shot_retrieval": summary(0.25, 16),
        "iterative_need_retrieval": summary(1.0, 8),
    }
    aggregate = {
        "overall": systems,
        "by_history_size": {
            str(size): systems for size in mco01.HISTORY_SIZES
        },
        "by_dependency_hops": {
            str(hops): systems for hops in (2, 3, 4, 5)
        },
    }
    verdict, gates = mco01.evaluate_verdict(aggregate, True)
    assert verdict == "MCO_01_ITERATIVE_ACQUISITION_ADVANCES"
    assert gates["exact_bounded_quality"]["pass"]
    assert gates["iterative_bounded_quality"]["pass"]
    assert not gates["one_shot_bounded_quality"]["pass"]
