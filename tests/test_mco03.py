from __future__ import annotations

import json

import numpy as np

from scripts import run_mco02 as mco02
from scripts import run_mco03 as mco03


def test_keyed_schema_binds_every_record_id() -> None:
    record_ids = ["r_0123456789abcdef", "r_fedcba9876543210"]
    schema = mco03.keyed_schema(record_ids)
    assert list(schema["properties"]) == record_ids
    assert schema["required"] == record_ids
    assert schema["additionalProperties"] is False
    assert mco03.parse_keyed(
        json.dumps(
            {
                record_ids[0]: "depends_on",
                record_ids[1]: "failure_threshold",
            }
        ),
        record_ids,
    ) == {
        record_ids[0]: "depends_on",
        record_ids[1]: "failure_threshold",
    }
    assert mco03.parse_keyed(
        json.dumps({record_ids[0]: "depends_on"}), record_ids
    ) is None


def test_single_parser_is_strict() -> None:
    assert mco03.parse_single('{"relation":"renamed_to"}') == "renamed_to"
    assert mco03.parse_single('{"relation":"other"}') is None
    assert mco03.parse_single('{"relation":"renamed_to","extra":1}') is None


def test_transparent_compiler_recovers_all_renderer_templates() -> None:
    public, oracle = mco02.build_language_history(2702, 1_000)
    expected = {row["record_id"]: row["relation"] for row in oracle["records"]}
    observed = {
        row["record_id"]: mco03.transparent_relation(row["text"])
        for row in public["records"]
    }
    assert observed == expected


def test_engineering_fixture_is_disjoint_from_scientific_population() -> None:
    assert mco03.ENGINEERING_SEED not in mco02.SEEDS
    public, _ = mco02.build_language_history(
        mco03.ENGINEERING_SEED, mco03.ENGINEERING_RECORDS
    )
    scientific_ids = {
        public_history["history_id"] for public_history, _ in mco02.load_corpus()
    }
    assert public["history_id"] not in scientific_ids


def test_scoring_reports_critical_relation_accuracy() -> None:
    public, oracle = mco02.build_language_history(2703, 100)
    predictions = {row["record_id"]: row["relation"] for row in oracle["records"]}
    metrics = mco03.score_predictions(public, oracle, predictions)
    assert metrics["relation_accuracy"] == 1.0
    assert metrics["critical_relation_accuracy"] == 1.0
    assert metrics["unresolved_records"] == 0


def test_preregistration_freezes_selected_candidate_and_nulls() -> None:
    config = json.loads(mco03.CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["status"] == "PREREGISTERED_BEFORE_SCIENTIFIC_INFERENCE"
    assert config["scientific_population"]["records"] == 32_200
    assert config["scientific_population"]["queries"] == 64
    assert config["learned_extractor"] == {
        "model": "llama3.1:8b",
        "interface": "single",
        "batch_size": 1,
    }
    assert config["models"]["embedding"]["name"] == "embeddinggemma:300m"
    assert "transparent_compiler" in config["variants"]
    assert "entity_hybrid_rag" in config["variants"]
    assert config["acceptance_criteria"]["minimum_critical_relation_accuracy"] == 0.99
    assert config["prior_terminal_state"]["dmc_historical_optimizer_steps"] == 10880
    assert config["prior_terminal_state"]["dmc_historical_training_label"] == (
        "TRAINING_COST_UNKNOWN"
    )


def test_perfect_predictions_materialize_indexable_structure() -> None:
    public, oracle = mco02.build_language_history(2704, 100)
    predictions = {row["record_id"]: row["relation"] for row in oracle["records"]}
    records = mco03.materialize_records(public, predictions)
    assert records == oracle["records"]
    assert mco03.indexing_check(records)["pass"]


def test_stability_selection_is_deterministic_and_stratified() -> None:
    public, oracle = mco02.build_language_history(2705, 1_000)
    left = mco03.select_stability_records(public, oracle)
    right = mco03.select_stability_records(public, oracle)
    assert left == right
    assert 100 <= len(left) <= 150
    relations = {
        oracle["rendering_metadata"][row["record_id"]]["relation"] for row in left
    }
    assert relations == set(mco03.ALLOWED_RELATIONS)


def test_compiler_prediction_preserves_exact_ordered_provenance() -> None:
    public, oracle = mco02.build_language_history(2706, 100)
    oracle_queries = {row["query_id"]: row for row in oracle["queries"]}
    for query in public["queries"]:
        traversal = mco02.traverse_extracted(oracle["records"], query)
        prediction = mco03.compiler_prediction(traversal, query)
        expected = oracle_queries[query["query_id"]]["expected"]
        assert mco03.answer_exact(prediction, expected)
        assert prediction["path_record_ids"] == expected["path_record_ids"]


def test_entity_hybrid_rag_uses_public_subject_expansion_within_cap() -> None:
    public, oracle = mco02.build_language_history(2707, 100)
    rng = np.random.default_rng(2707)
    embeddings = rng.normal(size=(100, 16)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    index = mco03.HybridRagIndex(public["records"], embeddings)
    query = public["queries"][0]
    selected = index.retrieve(
        variant="entity_hybrid_rag",
        question=query["question"],
        root_entity=query["root_entity"],
        query_embedding=embeddings[0],
    )
    assert 0 < len(selected) <= mco03.RAG_CAPACITY
    scaffolds = [mco02.parse_scaffold(row["text"]) for row in selected]
    assert any(row["subject"] == query["root_entity"] for row in scaffolds)
    expected_ids = set(oracle["queries"][0]["expected"]["path_record_ids"])
    assert expected_ids.intersection(row["record_id"] for row in selected)


def test_transparent_dominance_has_precedence_after_valid_learned_mechanism() -> None:
    criteria = json.loads(mco03.CONFIG_PATH.read_text(encoding="utf-8"))[
        "acceptance_criteria"
    ]
    extraction = {
        "learned": {
            "relation_accuracy": 1.0,
            "critical_relation_accuracy": 1.0,
            "minimum_history_relation_accuracy": 1.0,
            "unresolved_records": 0,
            "usage": {"model_calls": 100, "expensive_token_units": 1000},
        },
        "transparent": {
            "relation_accuracy": 1.0,
            "model_calls": 0,
            "expensive_token_units": 0,
        },
    }
    load = {
        "packet_answer_accuracy": 1.0,
        "packet_provenance_accuracy": 1.0,
    }
    planner_variant = {
        "packet_answer_accuracy": 1.0,
        "packet_provenance_accuracy": 1.0,
        "packet_critical_recall": 1.0,
        "model_answer_accuracy": 1.0,
        "model_generated_provenance_accuracy": 1.0,
        "by_history_size": {str(size): load for size in mco02.HISTORY_SIZES},
    }
    planner = {
        "variants": {
            "learned_single": planner_variant,
            "transparent_compiler": planner_variant,
        }
    }
    rag_variant = {
        "model_answer_accuracy": 0.0,
        "model_generated_provenance_accuracy": 0.0,
        "retrieval_recall": 0.0,
    }
    outcome, gates = mco03.evaluate_mco03_verdict(
        extraction=extraction,
        planner=planner,
        rag={"variants": {"dense_rag": rag_variant}},
        stability={
            "raw_content_stability": criteria["minimum_raw_response_stability"],
            "semantic_relation_stability": criteria[
                "minimum_semantic_relation_stability"
            ],
        },
        integrity_pass=True,
    )
    assert gates["learned_extraction_quality"]
    assert gates["transparent_compiler_dominates"]
    assert outcome == "MCO_03_TRANSPARENT_COMPILER_DOMINATES"
