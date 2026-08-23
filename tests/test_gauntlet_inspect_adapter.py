from __future__ import annotations

import json
from pathlib import Path

from gauntlet.adapters.inspect_ai import audit_inspect_log


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _inspect_log() -> dict:
    return {
        "version": 2,
        "status": "success",
        "eval": {
            "eval_id": "eval-1",
            "run_id": "run-1",
            "task": "demo_task",
            "task_id": "demo.py@demo_task#abc/model/xyz",
            "task_version": 1,
            "task_file": "demo.py",
            "dataset": {
                "name": "demo",
                "location": "data/demo.jsonl",
                "samples": 2,
                "sample_ids": ["a", "b"],
                "shuffled": False,
            },
            "model": "mockllm/model",
            "model_generate_config": {"temperature": 0},
            "model_args": {},
            "model_roles": None,
            "revision": {"type": "git", "origin": "repo", "commit": "a" * 40},
            "packages": {"inspect_ai": "0.3.999"},
        },
        "plan": {"steps": []},
        "results": {
            "total_samples": 2,
            "completed_samples": 2,
            "scores": [],
        },
        "stats": {
            "model_usage": {"mockllm/model": {"input_tokens": 10, "output_tokens": 4}}
        },
        "invalidated": False,
        "config_updates": [],
        "log_updates": [],
        "samples": [
            {"id": "a", "epoch": 1, "target": "yes", "scores": {"acc": {"value": 1}}},
            {"id": "b", "epoch": 1, "target": "no", "scores": {"acc": {"value": 1}}},
        ],
    }


def test_foreign_inspect_log_is_useful_but_not_promoted_to_admissible_claim(tmp_path: Path) -> None:
    log = tmp_path / "inspect.json"
    _write_json(log, _inspect_log())
    audited = audit_inspect_log(log)
    assert audited["evidence_class"] == "FOREIGN_LOG_AUDIT"
    assert audited["classification"] == "FOREIGN_LOG_PARTIAL_EVIDENCE"
    assert audited["concerns"] == []
    assert audited["evidence"]["successful_completion"]["status"] == "VERIFIED_FROM_LOG"
    assert audited["evidence"]["results_complete"]["status"] == "VERIFIED_FROM_LOG"
    assert audited["evidence"]["dataset_metadata"]["status"] == "VERIFIED_FROM_LOG"
    assert audited["evidence"]["dataset_content_identity"]["status"] == "NOT_ESTABLISHED"
    assert audited["evidence"]["holdout_isolation"]["status"] == "NOT_ESTABLISHED"
    assert audited["evidence"]["preregistration"]["status"] == "NOT_ESTABLISHED"
    assert audited["evidence"]["training_data_contamination"]["status"] == "NOT_ESTABLISHED"
    assert audited["boundary"]["claim_admissibility"] == "NOT_ESTABLISHED"


def test_exported_run_config_improves_artifact_coverage_but_does_not_claim_replay(tmp_path: Path) -> None:
    log = tmp_path / "inspect.json"
    config = tmp_path / "run.json"
    _write_json(log, _inspect_log())
    _write_json(config, {"tasks": ["demo_task"], "model": "mockllm/model"})
    audited = audit_inspect_log(log, config)
    assert audited["classification"] == "FOREIGN_LOG_STRUCTURALLY_STRONG"
    assert audited["evidence"]["run_config_artifact"]["status"] == "VERIFIED_FROM_LOG"
    assert "does not claim it was replayed" in audited["evidence"]["run_config_artifact"]["detail"]["note"]
    assert audited["evidence"]["independent_replay"]["status"] == "NOT_ESTABLISHED"
    assert audited["boundary"]["claim_admissibility"] == "NOT_ESTABLISHED"


def test_mid_run_config_update_is_surface_as_integrity_concern(tmp_path: Path) -> None:
    value = _inspect_log()
    value["config_updates"] = [{"field": "temperature", "value": 1}]
    log = tmp_path / "inspect.json"
    _write_json(log, value)
    audited = audit_inspect_log(log)
    assert audited["classification"] == "FOREIGN_LOG_WITH_INTEGRITY_CONCERNS"
    assert "MID_RUN_CONFIG_UPDATES_PRESENT" in audited["concerns"]
    assert audited["evidence"]["mid_run_config_stability"]["status"] == "PARTIAL"


def test_incomplete_or_invalidated_run_is_not_structurally_strong(tmp_path: Path) -> None:
    value = _inspect_log()
    value["invalidated"] = True
    value["results"]["completed_samples"] = 1
    log = tmp_path / "inspect.json"
    _write_json(log, value)
    audited = audit_inspect_log(log)
    assert audited["classification"] == "FOREIGN_LOG_WITH_INTEGRITY_CONCERNS"
    assert "INVALIDATED_SAMPLES_PRESENT" in audited["concerns"]
    assert "INCOMPLETE_RESULT_COUNT" in audited["concerns"]
    assert audited["evidence"]["results_complete"]["status"] == "PARTIAL"
