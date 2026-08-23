from __future__ import annotations

import importlib.util
import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/run_dmc05a.py"
SPEC = importlib.util.spec_from_file_location("run_dmc05a", SOURCE)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(
    record_id: str,
    a: int,
    b: int,
    episode: int,
    value: str,
    *,
    supersedes: str | None = None,
    entity: str | None = None,
    active_entities: list[str] | None = None,
) -> dict:
    entity = entity or f"entity_{a}"
    active_entities = [entity] if active_entities is None else active_entities
    return {
        "active_entities": active_entities,
        "creation_episode": episode,
        "entity": entity,
        "field": "value",
        "record_id": record_id,
        "retention_features": [0.0, 0.0],
        "retention_metadata": {
            "creation_episode": episode,
            "entity": entity,
            "family": "mission_set",
            "field": "value",
            "salience": "LOW",
            "supersedes": supersedes,
        },
        "supersedes": supersedes,
        "value": value,
        "version": "current",
        "write_descriptor": {
            "attribute_order": ["A", "B"],
            "tokens": [f"write_A_token_{a}", f"write_B_token_{b}"],
        },
    }


def case(stream: list[dict], target: str, answer: str, *, mode: str = "current", as_of: int | None = None) -> dict:
    active = sorted({entity for item in stream for entity in item["active_entities"]})
    return {
        "case_id": "mini",
        "family": "test",
        "experience_stream": stream,
        "metadata": {
            "write_load": len(stream),
            "physical_memory_budget": 16,
            "scope_events": [{"kind": "mission_set", "entities": active}],
        },
        "neural_view": {
            "query": {
                "mode": mode,
                "as_of_episode": as_of,
                "query_descriptor": {
                    "attribute_order": ["B", "A"],
                    "tokens": ["query_B_token_2", "query_A_token_1"],
                    "noise_token_count": 0,
                },
            }
        },
        "oracle_view": {"target_record_id": target, "answer": answer},
    }


def test_preregistered_config_is_exact() -> None:
    config = json.loads((ROOT / "experiments/dmc05a/DMC05A_CONFIG.json").read_text(encoding="utf-8"))
    assert config["status"] == "PREREGISTERED_BEFORE_EXECUTION"
    assert config["case_filter"]["history_sizes"] == [32, 64, 128, 256, 1024]
    assert config["case_filter"]["expected_total_cases"] == 592
    assert config["capacity"] == 16
    assert config["architecture_changes_authorized"] is False
    assert config["training_authorized"] is False


def test_normalized_descriptors_do_not_need_oracle_fields() -> None:
    item = row("r", 1, 2, 3, "RED")
    mini = case([item], "r", "RED")
    assert MODULE.write_key(item) == (1, 2)
    assert MODULE.query_key(mini) == (1, 2)
    assert "oracle_view" not in MODULE.compact_entry(item)


def test_exact_structured_resolves_current_and_history() -> None:
    old = row("old", 1, 2, 1, "RED")
    new = row("new", 1, 2, 9, "BLUE", supersedes="old")
    current = MODULE.conventional_case("exact_structured", case([old, new], "new", "BLUE"))
    history = MODULE.conventional_case("exact_structured", case([old, new], "old", "RED", mode="history", as_of=1))
    assert current["retrieval_accuracy"] == 1
    assert current["answer_accuracy"] == 1
    assert history["retrieval_accuracy"] == 1
    assert history["answer_accuracy"] == 1
    assert current["maximum_working_set_records"] == 2


def test_recent_window_and_frozen_fifo_are_distinct() -> None:
    stream = [row(f"d{i}", 0, 0, i, "RED") for i in range(16)]
    target = row("target", 1, 2, 16, "BLUE")
    mini = case([*stream, target], "target", "BLUE")
    recent = MODULE.conventional_case("recent_window_16", mini)
    frozen_fifo = MODULE.conventional_case("frozen_fifo_16", mini)
    assert recent["retrieval_accuracy"] == 1
    assert frozen_fifo["retrieval_accuracy"] == 0


def test_strong_conventional_baselines_filter_authorized_utility_aliases() -> None:
    target = row("target", 1, 2, 10, "BLUE", entity="mission", active_entities=["mission"])
    alias = row("alias", 1, 2, 99, "RED", entity="noise", active_entities=["mission"])
    mini = case([target, alias], "target", "BLUE")
    for system in ("full_history_scan", "exact_structured", "conventional_retrieval"):
        result = MODULE.conventional_case(system, mini)
        assert result["critical_recall"] == 1
        assert result["retrieval_accuracy"] == 1
        assert result["answer_accuracy"] == 1
        if system != "full_history_scan":
            assert result["maximum_working_set_records"] <= 16


def test_conventional_utility_firewall_rejects_extra_fields() -> None:
    metadata = dict(row("r", 1, 2, 1, "RED")["retention_metadata"])
    metadata["target_record_id"] = "r"
    with pytest.raises(ValueError, match="non-frozen metadata fields"):
        MODULE.conventional_utility_eligible(metadata, frozenset({"entity_1"}))


def test_exact_critical_recall_is_measured_at_retrieved_bucket() -> None:
    useful = row("useful", 1, 2, 10, "BLUE", entity="mission", active_entities=["mission"])
    persisted_but_ineligible = row("target", 1, 2, 99, "RED", entity="noise", active_entities=["mission"])
    result = MODULE.conventional_case(
        "exact_structured",
        case([useful, persisted_but_ineligible], "target", "RED"),
    )
    assert result["persistent_records"] == 2
    assert result["critical_recall"] == 0
    assert result["retrieval_accuracy"] == 0


def test_recent_window_persists_only_compact_query_fields() -> None:
    stream = [row(f"r{i}", i % 8, (i + 1) % 8, i, "RED") for i in range(20)]
    result = MODULE.conventional_case("recent_window_16", case(stream, "r19", "RED"))
    assert result["persistent_records"] == 16
    assert result["persistent_serialized_bytes"] < MODULE.canonical_bytes(stream[-16:])


def test_training_accounting_reconstructs_nonzero_cost() -> None:
    accounting = MODULE.training_accounting(592)
    assert accounting["status"] == "TRAINING_COST_UNKNOWN"
    assert accounting["components"]["decoder_dmc01_seed1337"]["optimizer_steps"] == 880
    assert accounting["components"]["retention_dmc03_per_seed"]["optimizer_steps"] == 1840
    assert accounting["components"]["retrieval_dmc04r2_per_seed"]["optimizer_steps"] == 160
    assert accounting["training_inclusive_amortization"]["dmc04b"]["unique_suite_optimizer_steps"] == 10880


def test_dataset_identity_matches_frozen_scaling_grid() -> None:
    identity = MODULE.dataset_identity()
    assert identity["pass"], identity
    assert identity["selected_total"] == 592
    assert identity["selected_counts"] == {"32": 176, "64": 160, "128": 88, "256": 80, "1024": 88}


def test_strong_conventional_systems_solve_every_frozen_structured_case() -> None:
    checked = 0
    for frozen_case in MODULE.iter_cases():
        for system in ("full_history_scan", "recent_window_16", "exact_structured", "conventional_retrieval"):
            result = MODULE.conventional_case(system, frozen_case)
            assert result["critical_recall"] == 1, (system, frozen_case["case_id"])
            assert result["retrieval_accuracy"] == 1, (system, frozen_case["case_id"])
            assert result["answer_accuracy"] == 1, (system, frozen_case["case_id"])
            if system != "full_history_scan":
                assert result["maximum_working_set_records"] <= 16
        checked += 1
    assert checked == 592


def test_batched_retrieval_matches_frozen_retrieval_at_legal_capacity() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_dmc04b

    real_case = next(MODULE.iter_cases())
    models = MODULE.load_dmc(1337)
    value_vectors = MODULE.hidden_map(real_case)
    candidates = [
        run_dmc04b.candidate_from_row(item, value_vectors)
        for item in real_case["experience_stream"][:16]
    ]
    frozen_audit = run_dmc04b.retrieval_audit()
    batched_audit = run_dmc04b.retrieval_audit()
    frozen = run_dmc04b.learned_retrieve(models["retriever"], real_case, candidates, frozen_audit)
    batched = MODULE.learned_retrieve_complete_history(
        models["retriever"],
        real_case,
        candidates,
        batched_audit,
        run_dmc04b,
        models["torch"],
    )
    assert frozen is not None and batched is not None
    assert frozen["record_id"] == batched["record_id"]
    assert frozen_audit["calls"] == batched_audit["calls"] == 1
    assert not batched_audit["forbidden_fields_observed"]


def test_complete_history_retrieval_uses_legal_batches_and_global_resolver() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_dmc04b

    real_case = next(MODULE.iter_cases())
    assert len(real_case["experience_stream"]) == 32
    models = MODULE.load_dmc(1337)
    value_vectors = MODULE.hidden_map(real_case)
    candidates = [
        run_dmc04b.candidate_from_row(item, value_vectors)
        for item in real_case["experience_stream"]
    ]
    audit = run_dmc04b.retrieval_audit()
    selected = MODULE.learned_retrieve_complete_history(
        models["retriever"],
        real_case,
        candidates,
        audit,
        run_dmc04b,
        models["torch"],
    )
    query_descriptor = real_case["neural_view"]["query"]["query_descriptor"]
    with models["torch"].no_grad():
        direct_scores = models["retriever"](
            query_descriptor,
            [item["write_descriptor"] for item in candidates],
        )
    direct = MODULE.resolve_learned_scores(real_case, candidates, direct_scores)
    assert selected is not None
    assert direct is not None
    assert selected["record_id"] == direct["record_id"]
    assert audit["calls"] == 2
    assert audit["candidate_count_max"] == 16
    assert audit["all_candidates_scored"] is True
    assert not audit["forbidden_fields_observed"]


def test_external_replay_output_path_is_accepted(tmp_path: Path) -> None:
    external = (tmp_path / "receipt.json").resolve()
    try:
        external.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise AssertionError("pytest temporary directory unexpectedly lies inside repository")
    assert MODULE.receipt_path_for(external) == str(external)
    assert MODULE.receipt_path_for(ROOT / "artifacts/dmc05a/raw/example.json") == "artifacts/dmc05a/raw/example.json"


def test_verdict_checks_recent_window_for_conventional_dominance() -> None:
    aggregate = json.loads(
        (ROOT / "artifacts/dmc05a/run2_protocol_invalid/aggregate.json").read_text(encoding="utf-8")
    )
    aggregate = copy.deepcopy(aggregate)
    for size in MODULE.HISTORY_SIZES:
        recent = aggregate["systems"]["recent_window_16"]["by_history_size"][str(size)]
        dmc = aggregate["systems"]["dmc04b"]["by_history_size"][str(size)]
        recent["persistent_serialized_bytes"]["mean"] = dmc["persistent_serialized_bytes"]["mean"] - 1
        recent["working_set_serialized_bytes"]["mean"] = dmc["working_set_serialized_bytes"]["mean"] - 1
        recent["ingestion_wall_ns"]["mean"] = dmc["ingestion_wall_ns"]["mean"] / 100
        recent["query_wall_ns"]["mean"] = dmc["query_wall_ns"]["mean"] / 100
    result = MODULE.calculate_gates(aggregate, {"synthetic_integrity": True})
    assert result["terminal_state"] == "DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES"
    assert result["bounded_advantage"] is False
    assert "recent_window_16" in result["conventional_dominators"]
