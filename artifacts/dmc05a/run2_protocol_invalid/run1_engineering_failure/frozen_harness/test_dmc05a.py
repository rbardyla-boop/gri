from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/run_dmc05a.py"
SPEC = importlib.util.spec_from_file_location("run_dmc05a", SOURCE)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(record_id: str, a: int, b: int, episode: int, value: str, *, supersedes: str | None = None) -> dict:
    return {
        "active_entities": [],
        "creation_episode": episode,
        "entity": f"entity_{a}",
        "field": "value",
        "record_id": record_id,
        "retention_features": [0.0, 0.0],
        "retention_metadata": {
            "creation_episode": episode,
            "entity": f"entity_{a}",
            "family": "test",
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
    return {
        "case_id": "mini",
        "family": "test",
        "experience_stream": stream,
        "metadata": {"write_load": len(stream), "physical_memory_budget": 16},
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
    assert current["maximum_working_set_records"] == 1


def test_recent_window_and_frozen_fifo_are_distinct() -> None:
    stream = [row(f"d{i}", 0, 0, i, "RED") for i in range(16)]
    target = row("target", 1, 2, 16, "BLUE")
    mini = case([*stream, target], "target", "BLUE")
    recent = MODULE.conventional_case("recent_window_16", mini)
    frozen_fifo = MODULE.conventional_case("frozen_fifo_16", mini)
    assert recent["retrieval_accuracy"] == 1
    assert frozen_fifo["retrieval_accuracy"] == 0


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
