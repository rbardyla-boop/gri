from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core import digest, file_sha256, read_json


STATUS_VERIFIED = "VERIFIED_FROM_LOG"
STATUS_PARTIAL = "PARTIAL"
STATUS_MISSING = "MISSING"
STATUS_NOT_ESTABLISHED = "NOT_ESTABLISHED"


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != {} and value != []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _evidence(status: str, detail: Any = None) -> dict[str, Any]:
    row: dict[str, Any] = {"status": status}
    if detail is not None:
        row["detail"] = detail
    return row


def audit_inspect_log(
    log_path: str | Path,
    run_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Audit a JSON representation of an Inspect AI EvalLog.

    The log should come from an Inspect JSON log or from `inspect log dump`.
    A JSON run config may optionally be supplied from
    `inspect log export-config --format json`.

    This function intentionally distinguishes facts *logged by Inspect* from
    claims that require external evidence. In particular, dataset content
    identity, holdout isolation, preregistration, and training-data
    contamination are never inferred from ordinary EvalLog metadata alone.
    """

    log_path = Path(log_path).resolve()
    log = read_json(log_path)
    if not isinstance(log, dict):
        raise ValueError("Inspect log JSON must be an object")

    eval_spec = _dict(log.get("eval"))
    dataset = _dict(eval_spec.get("dataset"))
    results = _dict(log.get("results"))
    stats = _dict(log.get("stats"))
    samples = _list(log.get("samples"))
    config_updates = _list(log.get("config_updates"))
    log_updates = _list(log.get("log_updates"))

    required_shape = {
        "status": isinstance(log.get("status"), str),
        "eval": isinstance(log.get("eval"), dict),
        "eval.task": isinstance(eval_spec.get("task"), str),
        "eval.model": isinstance(eval_spec.get("model"), str),
    }
    shape_ok = all(required_shape.values())

    status = str(log.get("status", ""))
    successful = status == "success"
    invalidated = bool(log.get("invalidated", False))

    total_samples = results.get("total_samples")
    completed_samples = results.get("completed_samples")
    result_counts_available = isinstance(total_samples, int) and isinstance(completed_samples, int)
    complete_results = (
        result_counts_available
        and int(total_samples) >= 0
        and int(completed_samples) == int(total_samples)
    )

    sample_count = len(samples) if samples else None
    targets_present = bool(samples) and all(
        isinstance(sample, dict) and "target" in sample for sample in samples
    )
    score_records_present = bool(samples) and all(
        isinstance(sample, dict) and _present(sample.get("scores")) for sample in samples
    )

    dataset_metadata_fields = {
        key: dataset.get(key)
        for key in ("name", "location", "samples", "sample_ids", "shuffled")
        if key in dataset
    }
    dataset_metadata_present = bool(dataset_metadata_fields)

    revision = eval_spec.get("revision")
    packages = _dict(eval_spec.get("packages"))
    model_config_fields = {
        "model": eval_spec.get("model"),
        "model_generate_config": eval_spec.get("model_generate_config"),
        "model_args": eval_spec.get("model_args"),
        "model_roles": eval_spec.get("model_roles"),
    }
    model_config_present = isinstance(eval_spec.get("model"), str)

    run_config: Any = None
    run_config_evidence: dict[str, Any]
    if run_config_path is not None:
        config_path = Path(run_config_path).resolve()
        run_config = read_json(config_path)
        if not isinstance(run_config, dict):
            raise ValueError("Inspect run config JSON must be an object")
        run_config_evidence = _evidence(
            STATUS_VERIFIED,
            {
                "path": str(config_path),
                "sha256": file_sha256(config_path),
                "note": "configuration artifact present; this audit does not claim it was replayed",
            },
        )
    else:
        run_config_evidence = _evidence(
            STATUS_MISSING,
            "no exported run config supplied to Gauntlet",
        )

    concerns: list[str] = []
    if not shape_ok:
        concerns.append("LOG_SCHEMA_INCOMPLETE")
    if not successful:
        concerns.append("EVAL_NOT_SUCCESSFUL")
    if invalidated:
        concerns.append("INVALIDATED_SAMPLES_PRESENT")
    if config_updates:
        concerns.append("MID_RUN_CONFIG_UPDATES_PRESENT")
    if result_counts_available and not complete_results:
        concerns.append("INCOMPLETE_RESULT_COUNT")
    if not results:
        concerns.append("RESULTS_MISSING")

    evidence = {
        "log_integrity": _evidence(
            STATUS_VERIFIED,
            {
                "sha256": file_sha256(log_path),
                "bytes": log_path.stat().st_size,
            },
        ),
        "inspect_log_shape": _evidence(
            STATUS_VERIFIED if shape_ok else STATUS_PARTIAL,
            required_shape,
        ),
        "successful_completion": _evidence(
            STATUS_VERIFIED if successful else STATUS_PARTIAL,
            status or None,
        ),
        "task_identity": _evidence(
            STATUS_VERIFIED if _present(eval_spec.get("task_id")) else STATUS_PARTIAL,
            {
                "task": eval_spec.get("task"),
                "task_id": eval_spec.get("task_id"),
                "task_version": eval_spec.get("task_version"),
                "task_file": eval_spec.get("task_file"),
                "eval_id": eval_spec.get("eval_id"),
                "run_id": eval_spec.get("run_id"),
            },
        ),
        "model_configuration": _evidence(
            STATUS_VERIFIED if model_config_present else STATUS_MISSING,
            model_config_fields,
        ),
        "model_binary_identity": _evidence(
            STATUS_NOT_ESTABLISHED,
            "ordinary Inspect model metadata names/configures the model but does not by itself prove immutable provider weights or a local model blob hash",
        ),
        "dataset_metadata": _evidence(
            STATUS_VERIFIED if dataset_metadata_present else STATUS_MISSING,
            dataset_metadata_fields or None,
        ),
        "dataset_content_identity": _evidence(
            STATUS_NOT_ESTABLISHED,
            "dataset name/location/sample IDs are not a cryptographic content manifest",
        ),
        "source_revision": _evidence(
            STATUS_VERIFIED if _present(revision) else STATUS_MISSING,
            revision,
        ),
        "package_versions": _evidence(
            STATUS_VERIFIED if packages else STATUS_MISSING,
            packages or None,
        ),
        "run_config_artifact": run_config_evidence,
        "results_complete": _evidence(
            STATUS_VERIFIED if complete_results else STATUS_PARTIAL,
            {
                "total_samples": total_samples,
                "completed_samples": completed_samples,
                "sample_records_in_supplied_log": sample_count,
            },
        ),
        "sample_targets_logged": _evidence(
            STATUS_VERIFIED if targets_present else STATUS_MISSING,
            targets_present,
        ),
        "sample_scores_logged": _evidence(
            STATUS_VERIFIED if score_records_present else STATUS_MISSING,
            score_records_present,
        ),
        "model_usage_logged": _evidence(
            STATUS_VERIFIED if _present(stats.get("model_usage")) else STATUS_MISSING,
            stats.get("model_usage"),
        ),
        "mid_run_config_stability": _evidence(
            STATUS_VERIFIED if not config_updates else STATUS_PARTIAL,
            {"config_updates": len(config_updates)},
        ),
        "post_eval_metadata_history": _evidence(
            STATUS_VERIFIED,
            {"log_updates": len(log_updates)},
        ),
        "holdout_isolation": _evidence(
            STATUS_NOT_ESTABLISHED,
            "targets being present in a finished log does not prove they were inaccessible to the evaluated agent during execution",
        ),
        "preregistration": _evidence(
            STATUS_NOT_ESTABLISHED,
            "an EvalLog records what ran; it does not prove thresholds and hypotheses were frozen before results were observed",
        ),
        "training_data_contamination": _evidence(
            STATUS_NOT_ESTABLISHED,
            "not inferable from the run log",
        ),
        "independent_replay": _evidence(
            STATUS_NOT_ESTABLISHED,
            "run configuration can support replay, but no replay receipt was supplied to this foreign-log audit",
        ),
    }

    strong_logged = shape_ok and successful and complete_results and not invalidated and not config_updates
    classification = "FOREIGN_LOG_STRUCTURALLY_STRONG" if strong_logged else "FOREIGN_LOG_WITH_INTEGRITY_CONCERNS"
    if run_config_path is None and classification == "FOREIGN_LOG_STRUCTURALLY_STRONG":
        classification = "FOREIGN_LOG_PARTIAL_EVIDENCE"

    audit: dict[str, Any] = {
        "schema_version": 1,
        "adapter": "inspect_ai_json",
        "evidence_class": "FOREIGN_LOG_AUDIT",
        "classification": classification,
        "log_sha256": file_sha256(log_path),
        "run_config_sha256": file_sha256(Path(run_config_path).resolve()) if run_config_path is not None else None,
        "concerns": concerns,
        "evidence": evidence,
        "boundary": {
            "claim_admissibility": "NOT_ESTABLISHED",
            "reason": "foreign framework metadata can establish parts of run identity and completeness, but not Gauntlet freeze timing, holdout isolation, dataset content identity, model-weight identity, or independent replay",
        },
    }
    audit["audit_sha256"] = digest(audit)
    return audit
