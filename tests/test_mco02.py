from __future__ import annotations

import json
from collections import Counter

import pytest

from scripts import run_mco02 as mco02


@pytest.fixture(scope="module")
def language_history() -> tuple[dict, dict]:
    return mco02.build_language_history(2601, 100)


def test_mco01_is_permanently_frozen_with_narrow_credit() -> None:
    receipt = json.loads(mco02.MCO01_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["status"] == "PERMANENTLY_FROZEN"
    assert receipt["verdict"] == "MCO_01_ITERATIVE_ACQUISITION_ADVANCES"
    assert receipt["authorized_successor"] == "MCO-02 — LANGUAGE / INFERENCE BOUNDARY"
    assert "natural-language robustness" in receipt["credit_denied"]
    assert "world-changing impact" in receipt["credit_denied"]
    assert receipt["training_accounting"]["dmc_historical_optimizer_steps_preserved"] == 10880
    assert receipt["training_accounting"]["dmc_historical_training_label"] == (
        "TRAINING_COST_UNKNOWN"
    )


def test_mco02_preregistration_freezes_model_population_and_cost_boundary() -> None:
    config = json.loads(mco02.CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["status"] == (
        "PREREGISTERED_BEFORE_LANGUAGE_CORPUS_AND_SCIENTIFIC_INFERENCE"
    )
    assert config["semantic_worlds"]["expected_histories"] == 8
    assert config["semantic_worlds"]["expected_queries"] == 64
    assert config["semantic_worlds"]["expected_semantic_records"] == 32200
    assert config["model"]["name"] == "llama3.1:8b"
    assert config["model"]["blob_sha256"] == mco02.MODEL_BLOB_SHA256
    assert config["model"]["native_context_length"] == 131072
    assert config["model"]["deployed_full_context_limit"] == 32768
    assert config["model"]["bounded_context_limit"] == 8192
    assert config["shared_extraction"]["relation_batch_size"] == 12
    amendment = config["pre_scientific_engineering_amendments"][0]
    assert amendment["id"] == "MCO02-ENG-01"
    assert amendment["scientific_runs_before_amendment"] == 0
    assert "acceptance thresholds" in amendment["unchanged"]
    assert config["amortization"]["query_counts"] == [1, 2, 8, 32, 128]
    assert config["amortization"]["output_token_weight"] == 4
    assert config["world_impact_claim"]["status_before_mco02"] == (
        "UNFALSIFIABLE_HERE_AND_NOT_ESTABLISHED"
    )


def test_renderer_is_deterministic_and_semantics_preserving(
    language_history: tuple[dict, dict],
) -> None:
    public, oracle = language_history
    replay_public, replay_oracle = mco02.build_language_history(2601, 100)
    assert mco02.digest(public) == mco02.digest(replay_public)
    assert mco02.digest(oracle) == mco02.digest(replay_oracle)
    check = mco02.verify_language_history(public, oracle)
    assert check["pass"], check
    assert check["local_pronoun_records"] > 0
    assert check["irrelevant_narrative_records"] > 0
    assert set(check["semantic_check"]["hop_counts"]) == {"2", "3", "4", "5"}


def test_public_language_has_no_canonical_relations_or_labels(
    language_history: tuple[dict, dict],
) -> None:
    public, _ = language_history
    for row in public["records"]:
        lowered = row["text"].lower()
        assert row["record_id"] in row["text"]
        for marker in mco02.FORBIDDEN_LANGUAGE_MARKERS:
            assert marker.lower() not in lowered


def test_scaffold_recovers_every_nonrelation_field(
    language_history: tuple[dict, dict],
) -> None:
    public, oracle = language_history
    expected = {row["record_id"]: row for row in oracle["records"]}
    for row in public["records"]:
        parsed = mco02.parse_scaffold(row["text"])
        semantic = expected[row["record_id"]]
        assert parsed["relation"] is None
        assert {key: value for key, value in parsed.items() if key != "relation"} == {
            key: value for key, value in semantic.items() if key != "relation"
        }


def test_extraction_receives_only_the_semantic_sentence(
    language_history: tuple[dict, dict],
) -> None:
    public, oracle = language_history
    for row in public["records"]:
        clause = mco02.semantic_clause(row["text"])
        metadata = oracle["rendering_metadata"][row["record_id"]]
        relation = metadata["relation"]
        template = {
            "depends_on": mco02.DEPENDENCY_TEMPLATES,
            "renamed_to": mco02.RENAME_TEMPLATES,
            "failure_threshold": mco02.THRESHOLD_TEMPLATES,
        }[relation][metadata["template_index"]]
        semantic = next(
            item for item in oracle["records"] if item["record_id"] == row["record_id"]
        )
        expected = template.format(subject=semantic["subject"], object=semantic["object"])
        assert clause == expected
        assert "Record " not in clause
        assert "states:" not in clause


def test_reasoning_prompts_freeze_signed_comparison_and_completion_rules() -> None:
    assert "same transparent integer comparison" in mco02.FINAL_REASONING_SYSTEM_PROMPT
    assert "required JSON schema" in mco02.NEED_SYSTEM_PROMPT
    parsed = mco02.parse_answer(
        json.dumps(
            {
                "status": "ANSWER",
                "terminal_entity": "e_0123456789abcdef",
                "failure_threshold": -11,
                "path_record_ids": ["r_0123456789abcdef"],
            }
        )
    )
    assert mco02.derive_inspection(
        parsed, {"deployment_temperature": -6}
    )["requires_inspection"] is False


def test_all_language_templates_are_exercised(language_history: tuple[dict, dict]) -> None:
    _, oracle = language_history
    coverage = Counter(
        (metadata["relation"], metadata["template_index"])
        for metadata in oracle["rendering_metadata"].values()
    )
    for relation in ("depends_on", "renamed_to", "failure_threshold"):
        assert len({index for (observed, index), count in coverage.items() if observed == relation and count}) >= 4


def test_relation_and_answer_parsers_are_strict() -> None:
    relation_json = json.dumps(
        {"relations": ["depends_on", "renamed_to", "failure_threshold"]}
    )
    assert mco02.parse_relation_json(relation_json, 3) == [
        "depends_on",
        "renamed_to",
        "failure_threshold",
    ]
    assert mco02.parse_relation_json('{"relations":["depends_on"]}', 3) is None
    assert mco02.relation_format_schema(3)["properties"]["relations"]["minItems"] == 3
    parsed = mco02.parse_answer(
        json.dumps(
            {
                "status": "ANSWER",
                "terminal_entity": "e_0123456789abcdef",
                "failure_threshold": -18,
                "path_record_ids": [
                    "r_0123456789abcdef",
                    "r_fedcba9876543210",
                ],
            }
        )
    )
    assert parsed["complete"]
    assert parsed["failure_threshold"] == -18
    assert parsed["requires_inspection"] is None
    evidence = [
        "[Record r_0123456789abcdef; source AUTHORITY; event 1] "
        "subject=e_0123456789abcdef; relation=failure_threshold; object=-18; "
        "operation=assert; supersedes=None"
    ]
    schema = mco02.final_format_schema(evidence)
    assert schema["properties"]["status"]["enum"] == ["ANSWER"]
    assert schema["properties"]["terminal_entity"]["enum"] == [
        "e_0123456789abcdef"
    ]


def test_exact_planner_reconstructs_every_query_from_perfect_structure(
    language_history: tuple[dict, dict],
) -> None:
    public, oracle = language_history
    oracle_queries = {row["query_id"]: row for row in oracle["queries"]}
    for query in public["queries"]:
        traversal = mco02.traverse_extracted(oracle["records"], query)
        assert traversal["complete"]
        expected = oracle_queries[query["query_id"]]["expected"]["path_record_ids"]
        assert [row["record_id"] for row in traversal["path"]] == expected
        assert len(traversal["path"]) <= mco02.CAPACITY


def test_rag_is_deterministic_and_bounded(language_history: tuple[dict, dict]) -> None:
    public, _ = language_history
    index = mco02.ConventionalRagIndex(public["records"])
    left, reads_left = index.retrieve(public["queries"][0]["question"])
    right, reads_right = index.retrieve(public["queries"][0]["question"])
    assert [row["record_id"] for row in left] == [row["record_id"] for row in right]
    assert len(left) == 16
    assert reads_left == reads_right == 100
    assert index.persistent_bytes > 0


def test_full_context_feasibility_is_explicit_not_scored(
    language_history: tuple[dict, dict],
) -> None:
    public, oracle = language_history
    query = public["queries"][0]
    oracle_query = oracle["queries"][0]
    outcome = mco02.infeasible_full_context_outcome(40000)
    row = mco02.score_query_result(
        system="full_context",
        public=public,
        public_query=query,
        oracle_query=oracle_query,
        oracle_records=oracle["records"],
        outcome=outcome,
        ingestion=mco02.empty_usage(),
        extraction=None,
        persistent_records=100,
        persistent_bytes=1,
        feasible=False,
    )
    assert row["status"] == "FULL_CONTEXT_INFEASIBLE"
    assert row["answer_accuracy"] is None
    assert row["failure_class"] is None


def test_failure_attribution_uses_earliest_cause(
    language_history: tuple[dict, dict],
) -> None:
    public, oracle = language_history
    query = public["queries"][0]
    oracle_query = oracle["queries"][0]
    wrong_records = [dict(row) for row in oracle["records"]]
    target = oracle_query["expected"]["path_record_ids"][0]
    for row in wrong_records:
        if row["record_id"] == target:
            row["relation"] = "renamed_to" if row["relation"] != "renamed_to" else "depends_on"
    extraction = {
        "records": wrong_records,
        "metrics": {"extraction_precision": 0.99, "extraction_recall": 0.99},
        "indexing": {"pass": True},
        "shared_extraction_sha256": mco02.digest(wrong_records),
    }
    outcome = {
        "prediction": mco02.parse_answer("UNKNOWN"),
        "raw_output_sha256": mco02.digest("UNKNOWN"),
        "usage": mco02.empty_usage(),
        "call_ids": [],
        "visible_record_ids": [],
        "retrieved_record_ids": [],
        "maximum_model_visible_records": 0,
        "maximum_model_visible_tokens": 10,
        "retrieval_rounds": 1,
        "external_reads": 1,
        "index_probes": 1,
        "acquisition_failure": "empty-need-result",
    }
    row = mco02.score_query_result(
        system="iterative_need_retrieval",
        public=public,
        public_query=query,
        oracle_query=oracle_query,
        oracle_records=oracle["records"],
        outcome=outcome,
        ingestion=mco02.empty_usage(),
        extraction=extraction,
        persistent_records=100,
        persistent_bytes=1,
    )
    assert row["failure_class"] == "LANGUAGE_EXTRACTION_FAILURE"


def test_expensive_token_units_and_amortization_are_mechanical() -> None:
    assert mco02.expensive_token_units(100, 10) == 140
    assert mco02.expensive_token_units(100, 10, 1) == 110
    rows = []
    for query_index in range(2):
        rows.append(
            {
                "history_id": "h",
                "status": "SCORED",
                "ingestion_input_tokens": 1000,
                "ingestion_output_tokens": 100,
                "ingestion_model_calls": 2,
                "query_input_tokens": 100,
                "query_output_tokens": 10,
                "query_model_calls": 1,
            }
        )
    amortized = mco02.amortization_for_rows(rows)
    assert amortized["query_horizons"]["1"]["mean_expensive_token_units"] == 1540
    assert amortized["query_horizons"]["2"]["mean_expensive_token_units"] == 1680


def test_model_identity_matches_frozen_local_blob() -> None:
    identity = mco02.model_identity()
    assert identity["pass"], identity
    assert identity["blob_sha256"] == mco02.MODEL_BLOB_SHA256
    assert identity["native_context_length"] == 131072
    assert identity["tokenizer_pretokenizer"] == "llama-bpe"


def test_frozen_corpus_identity_and_integrity() -> None:
    check = mco02.verify_corpus(deep=True)
    assert check["pass"], check["errors"]
    assert len(check["file_checks"]) == 8
    assert len(check["deep_checks"]) == 8


def test_freeze_hashes_match_before_scientific_inference() -> None:
    check = mco02.verify_freeze()
    assert check["pass"], check
