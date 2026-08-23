#!/usr/bin/env python3
from __future__ import annotations

"""DMC-05A conventional-memory null and cost-scaling evidence runner."""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "experiments/dmc05a"
CONFIG_PATH = EXPERIMENT_ROOT / "DMC05A_CONFIG.json"
CONTRACT_PATH = EXPERIMENT_ROOT / "DMC05A_CONTRACT.md"
FREEZE_PATH = EXPERIMENT_ROOT / "DMC05A_FREEZE.json"
RUN2_AMENDMENT_PATH = EXPERIMENT_ROOT / "DMC05A_RUN2_AMENDMENT.md"
RUN3_AMENDMENT_PATH = EXPERIMENT_ROOT / "DMC05A_RUN3_PROTOCOL_CORRECTION.md"
OUT = ROOT / "artifacts/dmc05a"
RAW_OUT = OUT / "raw"

HISTORY_SIZES = (32, 64, 128, 256, 1024)
EXPECTED_COUNTS = {32: 176, 64: 160, 128: 88, 256: 80, 1024: 88}
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
CAPACITY = 16
RANDOM_CONTROL_SEED = 20260202
DETERMINISTIC_SYSTEMS = (
    "full_history_scan",
    "recent_window_16",
    "frozen_fifo_16",
    "random_16",
    "exact_structured",
    "conventional_retrieval",
)
DMC_SYSTEMS = ("dmc04b", "dmc_retrieval_all_history")
ALL_SYSTEMS = DETERMINISTIC_SYSTEMS + DMC_SYSTEMS
BOUNDED_CONVENTIONAL_SYSTEMS = (
    "recent_window_16",
    "frozen_fifo_16",
    "random_16",
    "exact_structured",
    "conventional_retrieval",
)

DMC04B_ANCHORS = {
    "scripts/run_dmc04b.py": "3185434b9546236f93b3e75b47f5f11c88e7e33d89985a2c545c36c0fa90cbec",
    "artifacts/dmc04b/DMC04B_VERDICT.json": "f62724ca065b166fbc00741f5097a24b85c36e1b232cfc67f6cccbb79c3ba902",
    "artifacts/dmc04b/aggregate.json": "ffcceabec39c9953ec4617aecabd461ed1c6933a34612df08871424d79adb7ab",
    "artifacts/dmc04ba/dataset_manifest.json": "ee4afa55326205030a8600b079a0a484b6bfa39312d6127a80633e00c93274fc",
}

WRITE_TOKEN = re.compile(r"^write_([AB])_token_([0-7])$")
QUERY_TOKEN = re.compile(r"^query_([AB])_token_([0-7])$")

COUNT_METRICS = (
    "persistent_records",
    "persistent_serialized_bytes",
    "records_inspected_ingestion",
    "records_inspected_query",
    "retrieval_candidate_records",
    "retrieved_records",
    "persistent_write_operations",
    "declared_update_operations",
    "retention_discard_operations",
    "retrieval_index_operations",
    "maximum_working_set_records",
    "working_set_serialized_bytes",
    "retention_score_evaluations",
    "retention_model_forward_calls",
    "retrieval_model_forward_calls",
    "decoder_model_forward_calls",
)
TIME_METRICS = ("ingestion_wall_ns", "query_wall_ns")
CAPABILITY_METRICS = ("critical_recall", "retrieval_accuracy", "answer_accuracy")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(value: Any) -> int:
    return len(canonical(value).encode("utf-8"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def descriptor_key(descriptor: dict[str, Any], pattern: re.Pattern[str]) -> tuple[int, int]:
    found: dict[str, int] = {}
    for token in descriptor["tokens"]:
        match = pattern.match(token)
        if match:
            found[match.group(1)] = int(match.group(2))
    if set(found) != {"A", "B"}:
        raise ValueError("descriptor does not contain one normalized A and B address")
    return found["A"], found["B"]


def write_key(row: dict[str, Any]) -> tuple[int, int]:
    return descriptor_key(row["write_descriptor"], WRITE_TOKEN)


def query_key(case: dict[str, Any]) -> tuple[int, int]:
    return descriptor_key(case["neural_view"]["query"]["query_descriptor"], QUERY_TOKEN)


def compact_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": list(write_key(row)),
        "creation_episode": int(row["creation_episode"]),
        "record_id": str(row["record_id"]),
        "value": str(row["value"]),
    }


def structured_entry(row: dict[str, Any], *, utility_eligible: bool) -> dict[str, Any]:
    """Compact conventional record with every field needed by a competent index."""

    metadata = row["retention_metadata"]
    return {
        "record_id": str(row["record_id"]),
        "key": list(write_key(row)),
        "entity": str(metadata["entity"]),
        "field": str(metadata["field"]),
        "creation_episode": int(metadata["creation_episode"]),
        "supersedes": metadata["supersedes"],
        "version": str(row["version"]),
        "value": str(row["value"]),
        "utility_eligible": bool(utility_eligible),
    }


def final_active_scope(case: dict[str, Any]) -> frozenset[str]:
    events = case["metadata"].get("scope_events", [])
    return frozenset(events[-1]["entities"]) if events else frozenset()


def conventional_utility_eligible(metadata: dict[str, Any], active_scope: frozenset[str]) -> bool:
    """Exact transparent counterpart of the two authorized retention features."""

    allowed = {"family", "entity", "field", "creation_episode", "salience", "supersedes"}
    if set(metadata) != allowed:
        raise ValueError("conventional utility policy received non-frozen metadata fields")
    family = str(metadata["family"])
    if family in {"mission_set", "supersession", "utility_change"}:
        return str(metadata["entity"]) in active_scope
    if family in {"salience", "distractor_flood"}:
        return metadata["salience"] == "HIGH"
    raise ValueError(f"unknown conventional utility family: {family}")


def conventional_entries(case: dict[str, Any]) -> list[dict[str, Any]]:
    scope = final_active_scope(case)
    return [
        structured_entry(
            row,
            utility_eligible=conventional_utility_eligible(dict(row["retention_metadata"]), scope),
        )
        for row in case["experience_stream"]
    ]


def exact_select(entries: Iterable[dict[str, Any]], key: tuple[int, int], mode: str, as_of: int | None) -> dict[str, Any] | None:
    matches = [
        row
        for row in entries
        if tuple(row["key"]) == key
        and (mode == "current" or int(row["creation_episode"]) <= int(as_of))
    ]
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda row: (
            -int(row["creation_episode"]),
            hashlib.sha256(str(row["record_id"]).encode("utf-8")).hexdigest(),
        ),
    )[0]


def declared_update_count(stream: list[dict[str, Any]]) -> int:
    return sum(int(row.get("supersedes") is not None) for row in stream)


def frozen_random_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        case["experience_stream"],
        key=lambda row: digest([RANDOM_CONTROL_SEED, case["case_id"], row["record_id"]]),
    )[:CAPACITY]


def dataset_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "artifacts/dmc04ba/dataset_manifest.json").read_text(encoding="utf-8"))


def iter_cases() -> Iterable[dict[str, Any]]:
    manifest = dataset_manifest()
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / manifest[split]["path"]
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                case = json.loads(line)
                if int(case["metadata"]["write_load"]) in HISTORY_SIZES:
                    yield case


def dataset_identity() -> dict[str, Any]:
    manifest = dataset_manifest()
    rows: dict[str, Any] = {}
    counts: dict[int, int] = defaultdict(int)
    errors: list[str] = []
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / manifest[split]["path"]
        observed = file_sha256(path)
        expected = manifest[split]["sha256"]
        split_count = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                case = json.loads(line)
                load = int(case["metadata"]["write_load"])
                if load in HISTORY_SIZES:
                    counts[load] += 1
                    split_count += 1
                    if len(case["experience_stream"]) != load:
                        errors.append(f"{case['case_id']}:stream-load")
                    if int(case["metadata"]["physical_memory_budget"]) != CAPACITY:
                        errors.append(f"{case['case_id']}:capacity")
        rows[split] = {
            "path": str(path.relative_to(ROOT)),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "selected_case_count": split_count,
        }
        if observed != expected:
            errors.append(f"{split}:hash")
    actual = {int(key): int(value) for key, value in counts.items()}
    if actual != EXPECTED_COUNTS:
        errors.append("case-counts")
    return {
        "pass": not errors,
        "selected_counts": {str(key): actual.get(key, 0) for key in HISTORY_SIZES},
        "expected_counts": {str(key): EXPECTED_COUNTS[key] for key in HISTORY_SIZES},
        "selected_total": sum(actual.values()),
        "rows": rows,
        "errors": errors,
    }


def conventional_case(system: str, case: dict[str, Any]) -> dict[str, Any]:
    stream = case["experience_stream"]
    target_id = str(case["oracle_view"]["target_record_id"])
    expected_answer = str(case["oracle_view"]["answer"])
    qkey = query_key(case)
    query = case["neural_view"]["query"]
    mode = str(query["mode"])
    as_of = query["as_of_episode"]
    load = len(stream)
    updates = declared_update_count(stream)

    ingestion_start = time.perf_counter_ns()
    if system == "full_history_scan":
        state: Any = conventional_entries(case)
        persistent_payload = state
        discarded = 0
    elif system == "recent_window_16":
        window: deque[dict[str, Any]] = deque(maxlen=CAPACITY)
        for row in stream:
            window.append(compact_entry(row))
        state = list(window)
        persistent_payload = state
        discarded = max(0, load - len(state))
    elif system == "frozen_fifo_16":
        state = []
        for row in stream:
            if len(state) < CAPACITY:
                state.append(compact_entry(row))
        persistent_payload = state
        discarded = max(0, load - len(state))
    elif system == "random_16":
        state = [compact_entry(row) for row in frozen_random_rows(case)]
        persistent_payload = state
        discarded = max(0, load - len(state))
    elif system == "exact_structured":
        entries = conventional_entries(case)
        records = {str(entry["record_id"]): entry for entry in entries}
        index: dict[str, list[str]] = defaultdict(list)
        for entry in entries:
            if entry["utility_eligible"]:
                index[f"{entry['key'][0]}:{entry['key'][1]}"].append(str(entry["record_id"]))
        state = {
            "records": dict(sorted(records.items())),
            "eligible_address_index": dict(sorted(index.items())),
        }
        persistent_payload = state
        discarded = 0
    elif system == "conventional_retrieval":
        entries = conventional_entries(case)
        records = {str(entry["record_id"]): entry for entry in entries}
        state = {
            "records": dict(sorted(records.items())),
            "utility_index": [str(entry["record_id"]) for entry in entries if entry["utility_eligible"]],
        }
        persistent_payload = state
        discarded = 0
    else:
        raise ValueError(system)
    ingestion_wall_ns = time.perf_counter_ns() - ingestion_start

    query_start = time.perf_counter_ns()
    selected: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    query_inspected: int
    retrieval_operations: int
    if system == "full_history_scan":
        candidates = list(state)
        selected = exact_select(
            [row for row in candidates if row["utility_eligible"]],
            qkey,
            mode,
            as_of,
        )
        query_inspected = len(candidates)
        retrieval_operations = len(candidates)
        working_payload: Any = candidates
        critical_ids = {str(row["record_id"]) for row in candidates}
    elif system in {"recent_window_16", "frozen_fifo_16", "random_16"}:
        candidates = list(state)
        selected = exact_select(candidates, qkey, mode, as_of)
        query_inspected = len(candidates)
        retrieval_operations = len(candidates)
        working_payload = candidates
        critical_ids = {str(row["record_id"]) for row in candidates}
    elif system == "exact_structured":
        record_ids = state["eligible_address_index"].get(f"{qkey[0]}:{qkey[1]}", [])
        bucket = [state["records"][record_id] for record_id in record_ids]
        selected = exact_select(bucket, qkey, mode, as_of)
        candidates = bucket
        query_inspected = len(bucket)
        retrieval_operations = 1 + len(bucket)
        working_payload = candidates
        critical_ids = {str(row["record_id"]) for row in candidates}
    else:
        eligible = [state["records"][record_id] for record_id in state["utility_index"]]
        scored = []
        for row in eligible:
            key = tuple(row["key"])
            score = int(key[0] == qkey[0]) + int(key[1] == qkey[1])
            scored.append((score, hashlib.sha256(str(row["record_id"]).encode("utf-8")).hexdigest(), row))
        candidates = [row for _, _, row in sorted(scored, key=lambda item: (-item[0], item[1]))[:CAPACITY]]
        selected = exact_select(candidates, qkey, mode, as_of)
        query_inspected = len(eligible)
        retrieval_operations = 1 + len(eligible)
        working_payload = candidates
        critical_ids = {str(row["record_id"]) for row in candidates}
    query_wall_ns = time.perf_counter_ns() - query_start

    selected_id = None if selected is None else str(selected["record_id"])
    predicted = None if selected is None else str(selected["value"])
    persistent_records = load if system in {"full_history_scan", "exact_structured", "conventional_retrieval"} else len(state)
    working_records = load if system == "full_history_scan" else len(working_payload)
    persistent_ids = (
        set(state["records"])
        if system in {"exact_structured", "conventional_retrieval"}
        else {str(row["record_id"]) for row in state}
    )
    return {
        "case_id": case["case_id"],
        "history_size": load,
        "selected_record_id": selected_id,
        "target_record_id": target_id,
        "critical_recall": int(target_id in critical_ids),
        "retrieval_accuracy": int(selected_id == target_id),
        "answer_accuracy": int(predicted == expected_answer),
        "persistent_records": persistent_records,
        "persistent_serialized_bytes": canonical_bytes(persistent_payload),
        "records_inspected_ingestion": load,
        "records_inspected_query": query_inspected,
        "retrieval_candidate_records": len(candidates),
        "retrieved_records": int(selected is not None),
        "persistent_write_operations": load,
        "declared_update_operations": updates,
        "retention_discard_operations": discarded,
        "retrieval_index_operations": retrieval_operations,
        "maximum_working_set_records": working_records,
        "working_set_serialized_bytes": canonical_bytes(working_payload),
        "ingestion_wall_ns": ingestion_wall_ns,
        "query_wall_ns": query_wall_ns,
        "retention_score_evaluations": 0,
        "retention_model_forward_calls": 0,
        "retrieval_model_forward_calls": 0,
        "decoder_model_forward_calls": 0,
        "model_visible_records": working_records,
        "model_visible_tokens": "NOT_APPLICABLE_SYNTHETIC_RECORDS",
        "persistent_record_ids_sha256": digest(sorted(persistent_ids)),
    }


class CountingRetentionModel:
    def __init__(self, model: Any) -> None:
        self.model = model
        self.forward_calls = 0

    def __call__(self, features: Any) -> Any:
        self.forward_calls += 1
        return self.model(features)


def load_dmc(seed: int) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    import torch
    from dmc01.memory import build_paired_controllers
    from dmc03p.retention import AffineRetentionScorer
    from dmc04p.matcher import FactorizedAssociativeMatcher

    retention_path = ROOT / f"artifacts/dmc03/checkpoints/retention_seed{seed}_final.pt"
    retrieval_path = ROOT / f"artifacts/dmc04r2/checkpoints/retrieval_seed{seed}_final.pt"
    decoder_path = ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
    retention_manifest = json.loads((ROOT / "artifacts/dmc03/SHA256SUMS.json").read_text(encoding="utf-8"))
    retrieval_manifest = json.loads((ROOT / "artifacts/dmc04r2/SHA256SUMS.json").read_text(encoding="utf-8"))
    if file_sha256(retention_path) != retention_manifest[f"checkpoints/retention_seed{seed}_final.pt"]:
        raise ValueError("retention checkpoint hash mismatch")
    if file_sha256(retrieval_path) != retrieval_manifest[f"checkpoints/retrieval_seed{seed}_final.pt"]:
        raise ValueError("retrieval checkpoint hash mismatch")
    if file_sha256(decoder_path) != "4d7dd38a53216b6c010fbfbea27c5e382b572ba229db7fadaf9dd125c99b35a6":
        raise ValueError("decoder checkpoint hash mismatch")

    retention_payload = torch.load(retention_path, map_location="cpu", weights_only=False)
    retention = AffineRetentionScorer()
    retention.load_state_dict(retention_payload["scorer_state_dict"], strict=True)
    retention.eval()
    for parameter in retention.parameters():
        parameter.requires_grad_(False)

    retrieval_payload = torch.load(retrieval_path, map_location="cpu", weights_only=False)
    retriever = FactorizedAssociativeMatcher(seed=seed)
    retriever.load_state_dict(retrieval_payload["model_state_dict"], strict=True)
    retriever.eval()
    for parameter in retriever.parameters():
        parameter.requires_grad_(False)

    decoder_payload = torch.load(decoder_path, map_location="cpu", weights_only=False)
    decoder, _ = build_paired_controllers(1337)
    decoder.load_state_dict(decoder_payload["model_state_dict"], strict=True)
    decoder.eval()
    for parameter in decoder.parameters():
        parameter.requires_grad_(False)

    return {
        "torch": torch,
        "retention": CountingRetentionModel(retention),
        "retriever": retriever,
        "decoder": decoder,
        "checkpoint_hashes": {
            "retention": file_sha256(retention_path),
            "retrieval": file_sha256(retrieval_path),
            "decoder": file_sha256(decoder_path),
        },
    }


def hidden_map(case: dict[str, Any]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for memory, record in zip(case["neural_view"]["memory"], case["oracle_view"]["records"]):
        value = str(record["answer"])
        vector = [float(item) for item in memory["hidden_value"]]
        if value in result and result[value] != vector:
            raise ValueError("hidden map is not value-consistent")
        result[value] = vector
    if len(result) != 8:
        raise ValueError("hidden map lacks the frozen eight-value basis")
    return result


def resolve_learned_scores(case: dict[str, Any], candidates: list[dict[str, Any]], scores: Any) -> dict[str, Any] | None:
    """Apply the frozen DMC-04B global descriptor-group and temporal resolver."""

    if getattr(scores, "ndim", None) != 1 or int(scores.shape[0]) != len(candidates):
        raise ValueError("batched retrieval score shape mismatch")
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(candidates):
        groups[canonical(row["write_descriptor"])].append(index)
    grouped = list(groups.values())
    group_order = sorted(
        range(len(grouped)),
        key=lambda index: (
            -float(scores[grouped[index][0]].item()),
            min(
                hashlib.sha256(str(candidates[item]["record_id"]).encode("utf-8")).hexdigest()
                for item in grouped[index]
            ),
        ),
    )
    selected_group = grouped[group_order[0]]
    query = case["neural_view"]["query"]
    if query["mode"] == "history":
        eligible = [
            index
            for index in selected_group
            if candidates[index]["creation_episode"] <= query["as_of_episode"]
        ]
    else:
        eligible = list(selected_group)
    if not eligible:
        return None
    selected = sorted(
        eligible,
        key=lambda index: (
            -candidates[index]["creation_episode"],
            hashlib.sha256(str(candidates[index]["record_id"]).encode("utf-8")).hexdigest(),
        ),
    )[0]
    return candidates[selected]


def learned_retrieve_complete_history(
    model: Any,
    case: dict[str, Any],
    candidates: list[dict[str, Any]],
    audit: dict[str, Any],
    module: Any,
    torch_module: Any,
) -> dict[str, Any] | None:
    """Score all history through legal frozen-capacity calls, then resolve globally."""

    if not candidates:
        return None
    score_parts = []
    for start in range(0, len(candidates), CAPACITY):
        score_parts.append(module.learned_scores(model, case, candidates[start : start + CAPACITY], audit))
    scores = torch_module.cat(score_parts)
    if int(scores.shape[0]) != len(candidates):
        raise ValueError("all-history scorer did not score every candidate exactly once")
    return resolve_learned_scores(case, candidates, scores)


def dmc_case(system: str, case: dict[str, Any], models: dict[str, Any], module: Any) -> dict[str, Any]:
    stream = case["experience_stream"]
    load = len(stream)
    target_id = str(case["oracle_view"]["target_record_id"])
    expected_answer = str(case["oracle_view"]["answer"])
    updates = declared_update_count(stream)
    value_vectors = hidden_map(case)
    retention = models["retention"]

    ingestion_start = time.perf_counter_ns()
    before_forward = retention.forward_calls
    if system == "dmc04b":
        audit = module.retention_audit()
        retained, _ = module.learned_retention(retention, case, audit)
        retention_score_evaluations = int(audit["calls"])
    elif system == "dmc_retrieval_all_history":
        retained = list(stream)
        retention_score_evaluations = 0
    else:
        raise ValueError(system)
    ingestion_wall_ns = time.perf_counter_ns() - ingestion_start
    retention_forward_calls = retention.forward_calls - before_forward

    query_start = time.perf_counter_ns()
    candidates = [module.candidate_from_row(row, value_vectors) for row in retained]
    retrieval_audit = module.retrieval_audit()
    if system == "dmc_retrieval_all_history":
        selected = learned_retrieve_complete_history(
            models["retriever"],
            case,
            candidates,
            retrieval_audit,
            module,
            models["torch"],
        )
    else:
        selected = module.learned_retrieve(models["retriever"], case, candidates, retrieval_audit)
    predicted = None if selected is None else module.decode_row(models["decoder"], case, selected)
    query_wall_ns = time.perf_counter_ns() - query_start

    scorer_payload = {
        "query": case["neural_view"]["query"],
        "candidates": [
            {
                "write_descriptor": row["write_descriptor"],
                "creation_episode": row["creation_episode"],
            }
            for row in retained
        ],
        "selected_hidden_value": None if selected is None else selected["hidden_value"],
    }
    selected_id = None if selected is None else str(selected["record_id"])
    ids = {str(row["record_id"]) for row in retained}
    return {
        "case_id": case["case_id"],
        "history_size": load,
        "selected_record_id": selected_id,
        "target_record_id": target_id,
        "critical_recall": int(target_id in ids),
        "retrieval_accuracy": int(selected_id == target_id),
        "answer_accuracy": int(predicted == expected_answer),
        "persistent_records": len(retained),
        "persistent_serialized_bytes": canonical_bytes(retained),
        "records_inspected_ingestion": load,
        "records_inspected_query": len(candidates),
        "retrieval_candidate_records": len(candidates),
        "retrieved_records": int(selected is not None),
        "persistent_write_operations": load,
        "declared_update_operations": updates,
        "retention_discard_operations": max(0, load - len(retained)),
        "retrieval_index_operations": len(candidates),
        "maximum_working_set_records": len(candidates),
        "working_set_serialized_bytes": canonical_bytes(scorer_payload),
        "ingestion_wall_ns": ingestion_wall_ns,
        "query_wall_ns": query_wall_ns,
        "retention_score_evaluations": retention_score_evaluations,
        "retention_model_forward_calls": retention_forward_calls,
        "retrieval_model_forward_calls": int(retrieval_audit["calls"]),
        "decoder_model_forward_calls": int(selected is not None),
        "model_visible_records": len(candidates),
        "model_visible_tokens": "NOT_APPLICABLE_SYNTHETIC_RECORDS",
        "retrieval_firewall_pass": not retrieval_audit["forbidden_fields_observed"],
        "persistent_record_ids_sha256": digest(sorted(ids)),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"case_count": len(rows)}
    for metric in CAPABILITY_METRICS:
        result[metric] = statistics.mean(float(row[metric]) for row in rows)
    for metric in COUNT_METRICS + ("model_visible_records",):
        values = [float(row[metric]) for row in rows]
        result[metric] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "max": max(values),
            "total": sum(values),
        }
    for metric in TIME_METRICS:
        values = [float(row[metric]) for row in rows]
        result[metric] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": percentile(values, 0.95),
            "max": max(values),
            "total": sum(values),
        }
    result["model_visible_tokens"] = "NOT_APPLICABLE_SYNTHETIC_RECORDS"
    return result


def replay_projection(worker: dict[str, Any]) -> dict[str, Any]:
    projection = {
        "system": worker["system"],
        "seed": worker["seed"],
        "case_count": worker["case_count"],
        "decisions_sha256": worker["decisions_sha256"],
        "by_history_size": {},
    }
    for size, row in worker["by_history_size"].items():
        projection["by_history_size"][size] = {
            key: value
            for key, value in row.items()
            if key not in TIME_METRICS
        }
    return projection


def run_worker(system: str, seed: int | None) -> dict[str, Any]:
    worker_start = time.perf_counter_ns()
    if system not in ALL_SYSTEMS:
        raise ValueError(f"unknown system: {system}")
    if system in DMC_SYSTEMS and seed not in EVIDENCE_SEEDS:
        raise ValueError("DMC worker requires an evidence seed")
    if system in DETERMINISTIC_SYSTEMS and seed is not None:
        raise ValueError("deterministic worker must not receive a seed")

    models = None
    module = None
    checkpoint_hashes: dict[str, str] = {}
    if system in DMC_SYSTEMS:
        models = load_dmc(int(seed))
        checkpoint_hashes = dict(models["checkpoint_hashes"])
        import run_dmc04b as module  # type: ignore[no-redef]

    rows: list[dict[str, Any]] = []
    for case in iter_cases():
        if system in DMC_SYSTEMS:
            row = dmc_case(system, case, models, module)
        else:
            row = conventional_case(system, case)
        rows.append(row)
    counts = {size: sum(int(row["history_size"] == size) for row in rows) for size in HISTORY_SIZES}
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"worker case counts mismatch: {counts}")
    if any(row["model_visible_tokens"] != "NOT_APPLICABLE_SYNTHETIC_RECORDS" for row in rows):
        raise ValueError("synthetic token accounting was not explicit")
    if system in DMC_SYSTEMS and any(not row.get("retrieval_firewall_pass", False) for row in rows):
        raise ValueError("DMC retrieval firewall failed")

    decisions = [
        {
            "case_id": row["case_id"],
            "selected_record_id": row["selected_record_id"],
            "target_record_id": row["target_record_id"],
            "critical_recall": row["critical_recall"],
            "retrieval_accuracy": row["retrieval_accuracy"],
            "answer_accuracy": row["answer_accuracy"],
        }
        for row in rows
    ]
    result = {
        "unit": "DMC-05A-WORKER",
        "system": system,
        "seed": seed,
        "case_count": len(rows),
        "case_counts": {str(key): value for key, value in counts.items()},
        "by_history_size": {
            str(size): summarize_rows([row for row in rows if row["history_size"] == size])
            for size in HISTORY_SIZES
        },
        "overall": summarize_rows(rows),
        "decisions_sha256": digest(decisions),
        "cases_sha256": digest(rows),
        "checkpoint_hashes": checkpoint_hashes,
        "model_visible_tokens": "NOT_APPLICABLE_SYNTHETIC_RECORDS",
        "worker_wall_ns": time.perf_counter_ns() - worker_start,
        "worker_peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "cases": rows,
    }
    result["replay_projection_sha256"] = digest(replay_projection(result))
    return result


def verify_manifest(root: Path) -> dict[str, Any]:
    path = root / "SHA256SUMS.json"
    if not path.exists():
        return {"pass": False, "errors": ["missing manifest"]}
    expected = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    for relative, value in expected.items():
        candidate = root / relative
        if not candidate.exists():
            errors.append(f"missing:{relative}")
        elif file_sha256(candidate) != value:
            errors.append(f"hash:{relative}")
    actual = {
        str(candidate.relative_to(root))
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.name != "SHA256SUMS.json"
    }
    errors.extend(f"unexpected:{relative}" for relative in sorted(actual - set(expected)))
    return {"pass": not errors, "entries": len(expected), "errors": errors}


def training_accounting(evaluated_queries_per_seed: int) -> dict[str, Any]:
    dmc01_config = json.loads((ROOT / "artifacts/dmc01/DMC01_CONFIG.json").read_text(encoding="utf-8"))
    dmc03_config = json.loads((ROOT / "artifacts/dmc03/DMC03_CONFIG.json").read_text(encoding="utf-8"))
    dmc03_examples = json.loads((ROOT / "artifacts/dmc03/training_example_identity.json").read_text(encoding="utf-8"))
    dmc04_config = json.loads((ROOT / "artifacts/dmc04r2/DMC04R2_CONFIG.json").read_text(encoding="utf-8"))

    dmc01_cases = 176
    dmc01_epochs = int(dmc01_config["training"]["epochs"])
    dmc01_batch = int(dmc01_config["training"]["batch_size"])
    dmc01_steps = dmc01_epochs * math.ceil(dmc01_cases / dmc01_batch)

    dmc03_count = int(dmc03_examples["examples"])
    dmc03_epochs = int(dmc03_config["training"]["epochs"])
    dmc03_batch = int(dmc03_config["training"]["batch_size"])
    dmc03_steps_per_seed = dmc03_epochs * math.ceil(dmc03_count / dmc03_batch)

    retrieval_rows = {}
    retrieval_steps_per_seed = []
    retrieval_presentations_per_seed = []
    for seed in EVIDENCE_SEEDS:
        payload = json.loads((ROOT / f"artifacts/dmc04r2/retrieval_seed{seed}_train.json").read_text(encoding="utf-8"))
        steps = sum(int(row["batch_count"]) for row in payload["order_rows"])
        presentations = sum(int(row["case_count"]) for row in payload["order_rows"])
        retrieval_steps_per_seed.append(steps)
        retrieval_presentations_per_seed.append(presentations)
        retrieval_rows[str(seed)] = {"optimizer_steps": steps, "case_presentations": presentations}
    if len(set(retrieval_steps_per_seed)) != 1 or len(set(retrieval_presentations_per_seed)) != 1:
        raise ValueError("retrieval training accounting differs across seeds")
    dmc04_steps_per_seed = retrieval_steps_per_seed[0]
    dmc04_presentations_per_seed = retrieval_presentations_per_seed[0]

    suite_queries = evaluated_queries_per_seed * len(EVIDENCE_SEEDS)
    unique_suite_steps = dmc01_steps + len(EVIDENCE_SEEDS) * (dmc03_steps_per_seed + dmc04_steps_per_seed)
    dmc04b = {
        "historical_wall_time": "TRAINING_COST_UNKNOWN",
        "historical_energy": "TRAINING_COST_UNKNOWN",
        "historical_dollar_cost": "TRAINING_COST_UNKNOWN",
        "unique_suite_optimizer_steps": unique_suite_steps,
        "optimizer_steps_per_paired_seed_excluding_shared_decoder": dmc03_steps_per_seed + dmc04_steps_per_seed,
        "shared_decoder_optimizer_steps": dmc01_steps,
        "amortized_heterogeneous_optimizer_steps_per_evaluated_query": unique_suite_steps / suite_queries,
        "warning": "Optimizer steps span different model sizes and batch semantics and are not equivalent compute units.",
    }
    all_history = {
        "historical_wall_time": "TRAINING_COST_UNKNOWN",
        "historical_energy": "TRAINING_COST_UNKNOWN",
        "historical_dollar_cost": "TRAINING_COST_UNKNOWN",
        "unique_suite_optimizer_steps": dmc01_steps + len(EVIDENCE_SEEDS) * dmc04_steps_per_seed,
        "optimizer_steps_per_paired_seed_excluding_shared_decoder": dmc04_steps_per_seed,
        "shared_decoder_optimizer_steps": dmc01_steps,
        "amortized_heterogeneous_optimizer_steps_per_evaluated_query": (dmc01_steps + len(EVIDENCE_SEEDS) * dmc04_steps_per_seed) / suite_queries,
        "warning": "Optimizer steps span different model sizes and batch semantics and are not equivalent compute units.",
    }
    return {
        "status": "TRAINING_COST_UNKNOWN",
        "reason": "Historical wall time, energy, and dollar cost were not recorded by DMC-01, DMC-03, or DMC-04R2.",
        "manifests": {
            "dmc01": verify_manifest(ROOT / "artifacts/dmc01"),
            "dmc03": verify_manifest(ROOT / "artifacts/dmc03"),
            "dmc04r2": verify_manifest(ROOT / "artifacts/dmc04r2"),
        },
        "components": {
            "decoder_dmc01_seed1337": {
                "parameters": 30912,
                "epochs": dmc01_epochs,
                "training_cases": dmc01_cases,
                "batch_size": dmc01_batch,
                "case_presentations": dmc01_cases * dmc01_epochs,
                "optimizer_steps": dmc01_steps,
                "backward_passes": dmc01_steps,
            },
            "retention_dmc03_per_seed": {
                "parameters": 3,
                "epochs": dmc03_epochs,
                "training_examples": dmc03_count,
                "batch_size": dmc03_batch,
                "example_presentations": dmc03_count * dmc03_epochs,
                "optimizer_steps": dmc03_steps_per_seed,
                "backward_passes": dmc03_steps_per_seed,
                "evidence_seed_count": len(EVIDENCE_SEEDS),
            },
            "retrieval_dmc04r2_per_seed": {
                "parameters": int(dmc04_config["retriever"]["trainable_parameters"]),
                "epochs": int(dmc04_config["training"]["epochs"]),
                "training_cases_per_epoch": dmc04_presentations_per_seed // int(dmc04_config["training"]["epochs"]),
                "batch_size": int(dmc04_config["training"]["batch_size"]),
                "case_presentations": dmc04_presentations_per_seed,
                "optimizer_steps": dmc04_steps_per_seed,
                "backward_passes": dmc04_steps_per_seed,
                "evidence_seed_count": len(EVIDENCE_SEEDS),
                "by_seed": retrieval_rows,
            },
        },
        "training_inclusive_amortization": {
            "dmc04b": dmc04b,
            "dmc_retrieval_all_history": all_history,
            "conventional_systems": {
                "historical_training_required": False,
                "optimizer_steps": 0,
                "backward_passes": 0,
            },
        },
    }


def aggregate_runs(system: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "system": system,
        "run_count": len(runs),
        "seeds": [run["seed"] for run in runs],
        "raw_receipts": [run["raw_receipt"] for run in runs],
        "raw_sha256": [run["raw_sha256"] for run in runs],
        "worker_wall_ns": {
            "mean": statistics.mean(run["worker_wall_ns"] for run in runs),
            "by_seed": {str(run["seed"]): run["worker_wall_ns"] for run in runs},
        },
        "worker_peak_rss_kib": {
            "mean": statistics.mean(run["worker_peak_rss_kib"] for run in runs),
            "max": max(run["worker_peak_rss_kib"] for run in runs),
            "by_seed": {str(run["seed"]): run["worker_peak_rss_kib"] for run in runs},
        },
        "by_history_size": {},
        "overall": {},
    }
    metric_names = CAPABILITY_METRICS + COUNT_METRICS + TIME_METRICS + ("model_visible_records",)
    for size in map(str, HISTORY_SIZES):
        combined: dict[str, Any] = {"case_count_per_run": runs[0]["by_history_size"][size]["case_count"]}
        for metric in metric_names:
            values = []
            for run in runs:
                value = run["by_history_size"][size][metric]
                values.append(float(value if metric in CAPABILITY_METRICS else value["mean"]))
            combined[metric] = {
                "mean": statistics.mean(values),
                "std": statistics.pstdev(values),
                "by_seed": {str(run["seed"]): value for run, value in zip(runs, values)},
            }
        combined["model_visible_tokens"] = "NOT_APPLICABLE_SYNTHETIC_RECORDS"
        result["by_history_size"][size] = combined
    for metric in metric_names:
        values = []
        for run in runs:
            value = run["overall"][metric]
            values.append(float(value if metric in CAPABILITY_METRICS else value["mean"]))
        result["overall"][metric] = {
            "mean": statistics.mean(values),
            "std": statistics.pstdev(values),
            "by_seed": {str(run["seed"]): value for run, value in zip(runs, values)},
        }
    result["overall"]["model_visible_tokens"] = "NOT_APPLICABLE_SYNTHETIC_RECORDS"
    return result


def metric(aggregate: dict[str, Any], system: str, size: int | None, name: str) -> float:
    row = aggregate["systems"][system]["overall"] if size is None else aggregate["systems"][system]["by_history_size"][str(size)]
    return float(row[name]["mean"])


def online_wall_ns(aggregate: dict[str, Any], system: str, size: int) -> float:
    return metric(aggregate, system, size, "ingestion_wall_ns") + metric(aggregate, system, size, "query_wall_ns")


def conventional_dominance_check(aggregate: dict[str, Any], system: str) -> dict[str, Any]:
    comparisons = {
        "capability": all(
            metric(aggregate, system, size, "answer_accuracy")
            >= metric(aggregate, "dmc04b", size, "answer_accuracy") - 0.01
            for size in HISTORY_SIZES
        ),
        "persistent_records": all(
            metric(aggregate, system, size, "persistent_records")
            <= metric(aggregate, "dmc04b", size, "persistent_records")
            for size in HISTORY_SIZES
        ),
        "persistent_bytes": all(
            metric(aggregate, system, size, "persistent_serialized_bytes")
            <= metric(aggregate, "dmc04b", size, "persistent_serialized_bytes")
            for size in HISTORY_SIZES
        ),
        "bounded_working_records": all(
            metric(aggregate, system, size, "maximum_working_set_records")
            <= metric(aggregate, "dmc04b", size, "maximum_working_set_records")
            <= CAPACITY
            for size in HISTORY_SIZES
        ),
        "working_bytes": all(
            metric(aggregate, system, size, "working_set_serialized_bytes")
            <= metric(aggregate, "dmc04b", size, "working_set_serialized_bytes")
            for size in HISTORY_SIZES
        ),
        "query_records_inspected": all(
            metric(aggregate, system, size, "records_inspected_query")
            <= metric(aggregate, "dmc04b", size, "records_inspected_query")
            for size in HISTORY_SIZES
        ),
        "retrieval_operations": all(
            metric(aggregate, system, size, "retrieval_index_operations")
            <= metric(aggregate, "dmc04b", size, "retrieval_index_operations")
            for size in HISTORY_SIZES
        ),
        "total_online_wall_time": all(
            online_wall_ns(aggregate, system, size)
            <= online_wall_ns(aggregate, "dmc04b", size)
            for size in HISTORY_SIZES
        ),
        "learned_forward_calls": all(
            sum(
                metric(aggregate, system, size, name)
                for name in (
                    "retention_model_forward_calls",
                    "retrieval_model_forward_calls",
                    "decoder_model_forward_calls",
                )
            )
            == 0
            for size in HISTORY_SIZES
        ),
        "no_historical_training": True,
    }
    return {
        "pass": all(comparisons.values()),
        "comparisons": comparisons,
        "load_1024": {
            "answer_accuracy": metric(aggregate, system, 1024, "answer_accuracy"),
            "persistent_records": metric(aggregate, system, 1024, "persistent_records"),
            "persistent_bytes": metric(aggregate, system, 1024, "persistent_serialized_bytes"),
            "working_records": metric(aggregate, system, 1024, "maximum_working_set_records"),
            "working_bytes": metric(aggregate, system, 1024, "working_set_serialized_bytes"),
            "query_records_inspected": metric(aggregate, system, 1024, "records_inspected_query"),
            "retrieval_operations": metric(aggregate, system, 1024, "retrieval_index_operations"),
            "online_wall_ns": online_wall_ns(aggregate, system, 1024),
        },
    }


def calculate_gates(aggregate: dict[str, Any], integrity: dict[str, bool]) -> dict[str, Any]:
    dmc_accuracy = metric(aggregate, "dmc04b", None, "answer_accuracy")
    structured_accuracy = metric(aggregate, "exact_structured", None, "answer_accuracy")
    conventional_accuracy = metric(aggregate, "conventional_retrieval", None, "answer_accuracy")
    all_history_accuracy = metric(aggregate, "dmc_retrieval_all_history", None, "answer_accuracy")
    dmc_bytes_1024 = metric(aggregate, "dmc04b", 1024, "persistent_serialized_bytes")
    structured_bytes_1024 = metric(aggregate, "exact_structured", 1024, "persistent_serialized_bytes")
    storage_ratio = dmc_bytes_1024 / structured_bytes_1024
    dmc_all_gap = abs(dmc_accuracy - all_history_accuracy)
    conventional_bounded = all(
        metric(aggregate, name, size, "maximum_working_set_records") <= CAPACITY
        for name in ("exact_structured", "conventional_retrieval")
        for size in HISTORY_SIZES
    )
    matching_bounded = [
        name
        for name in BOUNDED_CONVENTIONAL_SYSTEMS
        if metric(aggregate, name, None, "answer_accuracy") >= 0.99
        and max(metric(aggregate, name, size, "maximum_working_set_records") for size in HISTORY_SIZES) <= CAPACITY
    ]
    dominance = {
        name: conventional_dominance_check(aggregate, name)
        for name in BOUNDED_CONVENTIONAL_SYSTEMS
    }
    dominators = [name for name, row in dominance.items() if row["pass"]]
    gates = {
        "dmc_capability": {"observed": dmc_accuracy, "threshold": 0.99, "pass": dmc_accuracy >= 0.99},
        "exact_structured_capability": {"observed": structured_accuracy, "threshold": 0.99, "pass": structured_accuracy >= 0.99},
        "conventional_retrieval_capability": {"observed": conventional_accuracy, "threshold": 0.99, "pass": conventional_accuracy >= 0.99},
        "capability_match": {
            "observed_max_gap": max(abs(dmc_accuracy - structured_accuracy), abs(dmc_accuracy - conventional_accuracy)),
            "threshold_max": 0.01,
            "pass": max(abs(dmc_accuracy - structured_accuracy), abs(dmc_accuracy - conventional_accuracy)) <= 0.01,
        },
        "dmc_storage_ratio_1024": {"observed": storage_ratio, "threshold_max": 0.10, "pass": storage_ratio <= 0.10},
        "conventional_bounded_working_set": {"observed_max": max(
            max(metric(aggregate, name, size, "maximum_working_set_records") for size in HISTORY_SIZES)
            for name in ("exact_structured", "conventional_retrieval")
        ), "threshold_max": CAPACITY, "pass": conventional_bounded},
        "matching_bounded_conventional_system": {
            "observed": matching_bounded,
            "threshold_min_count": 1,
            "pass": bool(matching_bounded),
        },
        "all_history_retention_ablation": {"observed_gap": dmc_all_gap, "threshold_max": 0.01, "pass": dmc_all_gap <= 0.01},
    }
    conventional_pareto = bool(dominators)
    accounting_valid = all(integrity.values())
    bounded_advantage = gates["dmc_capability"]["pass"] and not matching_bounded
    storage_only = (
        gates["dmc_capability"]["pass"]
        and gates["exact_structured_capability"]["pass"]
        and gates["conventional_retrieval_capability"]["pass"]
        and gates["capability_match"]["pass"]
        and gates["dmc_storage_ratio_1024"]["pass"]
        and gates["conventional_bounded_working_set"]["pass"]
        and gates["all_history_retention_ablation"]["pass"]
    )
    if not accounting_valid:
        terminal = "DMC_05A_ACCOUNTING_INVALID"
    elif bounded_advantage:
        terminal = "DMC_05A_BOUNDED_MEMORY_ADVANTAGE"
    elif conventional_pareto:
        terminal = "DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES"
    elif storage_only:
        terminal = "DMC_05A_STORAGE_ONLY_ADVANTAGE"
    else:
        terminal = "DMC_05A_TRADEOFF"
    return {
        "terminal_state": terminal,
        "gates": gates,
        "accounting_valid": accounting_valid,
        "bounded_advantage": bounded_advantage,
        "conventional_pareto_dominance": conventional_pareto,
        "conventional_dominators": dominators,
        "dominance_checks": dominance,
        "storage_only_conditions": storage_only,
    }


def write_curves(aggregate: dict[str, Any]) -> dict[str, Any]:
    systems = list(ALL_SYSTEMS)
    curve_metrics = {
        "accuracy": "answer_accuracy",
        "persistent_bytes": "persistent_serialized_bytes",
        "query_records_inspected": "records_inspected_query",
        "active_working_set_records": "maximum_working_set_records",
        "online_wall_ns": "online_wall_ns",
    }
    def curve_value(system: str, size: int, name: str) -> float:
        return online_wall_ns(aggregate, system, size) if name == "online_wall_ns" else metric(aggregate, system, size, name)

    curves = {
        label: {
            system: {str(size): curve_value(system, size, name) for size in HISTORY_SIZES}
            for system in systems
        }
        for label, name in curve_metrics.items()
    }
    write_json(OUT / "scaling_curves.json", curves)
    csv_lines = ["history_size,system,answer_accuracy,persistent_bytes,query_records_inspected,active_working_set_records,ingestion_wall_ns,query_wall_ns,online_wall_ns"]
    for size in HISTORY_SIZES:
        for system in systems:
            csv_lines.append(
                ",".join(
                    [
                        str(size),
                        system,
                        str(metric(aggregate, system, size, "answer_accuracy")),
                        str(metric(aggregate, system, size, "persistent_serialized_bytes")),
                        str(metric(aggregate, system, size, "records_inspected_query")),
                        str(metric(aggregate, system, size, "maximum_working_set_records")),
                        str(metric(aggregate, system, size, "ingestion_wall_ns")),
                        str(metric(aggregate, system, size, "query_wall_ns")),
                        str(online_wall_ns(aggregate, system, size)),
                    ]
                )
            )
    (OUT / "scaling_curves.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 2, figsize=(15, 14))
    axes = axes.flatten()
    labels = [
        ("answer_accuracy", "Answer accuracy", False),
        ("persistent_serialized_bytes", "Persistent bytes", True),
        ("records_inspected_query", "Records inspected at query", True),
        ("maximum_working_set_records", "Active working-set records", True),
        ("online_wall_ns", "Total online wall time (ns)", True),
    ]
    for axis, (name, title, log_scale) in zip(axes, labels):
        for system in systems:
            axis.plot(HISTORY_SIZES, [curve_value(system, size, name) for size in HISTORY_SIZES], marker="o", label=system)
        axis.set_xscale("log", base=2)
        if log_scale:
            axis.set_yscale("log")
        axis.set_title(title)
        axis.set_xlabel("History size")
        axis.grid(True, alpha=0.25)
    axes[-1].axis("off")
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=2, fontsize=9)
    fig.suptitle("DMC-05A Conventional Memory Null + Cost Scaling")
    fig.tight_layout(rect=(0, 0.08, 1, 0.97))
    fig.savefig(OUT / "scaling_curves.svg")
    plt.close(fig)
    return {"json": "artifacts/dmc05a/scaling_curves.json", "csv": "artifacts/dmc05a/scaling_curves.csv", "svg": "artifacts/dmc05a/scaling_curves.svg"}


def report_markdown(terminal: str, aggregate: dict[str, Any], gates: dict[str, Any], training: dict[str, Any]) -> str:
    lines = [
        "# DMC-05A — Conventional Memory Null + Cost Scaling",
        "",
        f"Terminal state: `{terminal}`",
        "",
        f"Conventional Pareto dominators: `{', '.join(gates['conventional_dominators']) if gates['conventional_dominators'] else 'none'}`",
        "",
        "## Capability",
        "",
        "| System | Critical recall | Retrieval accuracy | Answer accuracy |",
        "|---|---:|---:|---:|",
    ]
    for system in ALL_SYSTEMS:
        lines.append(
            f"| {system} | {metric(aggregate, system, None, 'critical_recall'):.6f} | "
            f"{metric(aggregate, system, None, 'retrieval_accuracy'):.6f} | "
            f"{metric(aggregate, system, None, 'answer_accuracy'):.6f} |"
        )
    lines.extend([
        "",
        "## Load 1024 resources",
        "",
        "| System | Persistent records | Persistent bytes | Query inspected | Working records | Working bytes | Ingestion ns | Query ns | Online ns | Learned forwards |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for system in ALL_SYSTEMS:
        forwards = sum(metric(aggregate, system, 1024, name) for name in ("retention_model_forward_calls", "retrieval_model_forward_calls", "decoder_model_forward_calls"))
        lines.append(
            f"| {system} | {metric(aggregate, system, 1024, 'persistent_records'):.3f} | "
            f"{metric(aggregate, system, 1024, 'persistent_serialized_bytes'):.3f} | "
            f"{metric(aggregate, system, 1024, 'records_inspected_query'):.3f} | "
            f"{metric(aggregate, system, 1024, 'maximum_working_set_records'):.3f} | "
            f"{metric(aggregate, system, 1024, 'working_set_serialized_bytes'):.3f} | "
            f"{metric(aggregate, system, 1024, 'ingestion_wall_ns'):.3f} | "
            f"{metric(aggregate, system, 1024, 'query_wall_ns'):.3f} | "
            f"{online_wall_ns(aggregate, system, 1024):.3f} | {forwards:.3f} |"
        )
    lines.extend([
        "",
        "## Gates",
        "",
    ])
    for name, row in gates["gates"].items():
        lines.append(f"- `{name}`: {'PASS' if row['pass'] else 'FAIL'} — {canonical(row)}")
    lines.extend([
        "",
        "## Dominance checks",
        "",
    ])
    for name, row in gates["dominance_checks"].items():
        lines.append(f"- `{name}`: {'DOMINATES' if row['pass'] else 'does not dominate'} — {canonical(row['comparisons'])}")
    lines.extend([
        "",
        "## Training accounting",
        "",
        f"Historical wall-time, energy, and dollar accounting: `{training['status']}`.",
        "Reconstructable optimizer steps and example/case presentations are preserved in `training_accounting.json`; heterogeneous optimizer steps are not converted into a magic compute or dollar score.",
        "",
        "## Boundary",
        "",
        "This experiment uses a synthetic structured benchmark and no language tokenizer or expensive language model. The generator places all utility-eligible records at the end of each measured stream, so recent-window success is a benchmark-ordering result, not evidence that recency solves general memory. No real-language inference-cost advantage is established.",
    ])
    return "\n".join(lines) + "\n"


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.exists():
        return {"pass": False, "errors": ["missing freeze"]}
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    expected = {
        "source_sha256": file_sha256(Path(__file__)),
        "test_sha256": file_sha256(ROOT / "tests/test_dmc05a.py"),
        "config_sha256": file_sha256(CONFIG_PATH),
        "contract_sha256": file_sha256(CONTRACT_PATH),
        "run2_amendment_sha256": file_sha256(RUN2_AMENDMENT_PATH),
        "run3_amendment_sha256": file_sha256(RUN3_AMENDMENT_PATH),
    }
    errors = [key for key, value in expected.items() if freeze.get(key) != value]
    if freeze.get("status") != "FROZEN_BEFORE_PROTOCOL_CORRECTION_RUN":
        errors.append("status")
    return {"pass": not errors, "expected": expected, "observed": freeze, "errors": errors}


def verify_anchors() -> dict[str, Any]:
    rows = {}
    for relative, expected in DMC04B_ANCHORS.items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        rows[relative] = {"expected": expected, "observed": observed, "pass": observed == expected}
    verdict = json.loads((ROOT / "artifacts/dmc04b/DMC04B_VERDICT.json").read_text(encoding="utf-8"))
    semantic = {
        "terminal": verdict.get("terminal_state") == "DMC_04B_COMBINED_LEARNED_MEMORY_ADVANCES",
        "integrity": bool(verdict.get("integrity")) and all(verdict["integrity"].values()),
        "no_training": verdict.get("evidence_training_executed") is False,
    }
    return {"pass": all(row["pass"] for row in rows.values()) and all(semantic.values()), "rows": rows, "semantic": semantic}


def run_preflight_tests() -> dict[str, Any]:
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_dmc05a.py"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {"command": "python3 -m pytest -q tests/test_dmc05a.py", "pass": run.returncode == 0, "returncode": run.returncode, "output": run.stdout[-4000:]}


def receipt_path_for(output: Path) -> str:
    resolved_output = output.resolve()
    try:
        return str(resolved_output.relative_to(ROOT))
    except ValueError:
        return str(resolved_output)


def run_one_worker(system: str, seed: int | None, output: Path) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", system, "--output", str(output)]
    if seed is not None:
        command.extend(["--seed", str(seed)])
    run = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if run.returncode != 0 or not output.exists():
        raise RuntimeError(f"worker failed: {system}/{seed}\n{run.stdout[-4000:]}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["raw_receipt"] = receipt_path_for(output)
    payload["raw_sha256"] = file_sha256(output)
    return payload


def manifest_for(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "SHA256SUMS.json"
    }


def run_parent() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW_OUT.mkdir(parents=True, exist_ok=True)
    freeze = verify_freeze()
    anchors = verify_anchors()
    dataset = dataset_identity()
    tests = run_preflight_tests()
    if not all((freeze["pass"], anchors["pass"], dataset["pass"], tests["pass"])):
        receipt = {"unit": "DMC-05A", "terminal_state": "DMC_05A_ACCOUNTING_INVALID", "preflight": {"freeze": freeze, "anchors": anchors, "dataset": dataset, "tests": tests}}
        write_json(OUT / "DMC05A_VERDICT.json", receipt)
        print(receipt["terminal_state"])
        return 1

    component_paths = [
        ROOT / f"artifacts/dmc03/checkpoints/retention_seed{seed}_final.pt" for seed in EVIDENCE_SEEDS
    ] + [
        ROOT / f"artifacts/dmc04r2/checkpoints/retrieval_seed{seed}_final.pt" for seed in EVIDENCE_SEEDS
    ] + [ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"]
    component_before = {str(path.relative_to(ROOT)): file_sha256(path) for path in component_paths}

    worker_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for system in DETERMINISTIC_SYSTEMS:
        output = RAW_OUT / f"{system}.json"
        worker_runs[system].append(run_one_worker(system, None, output))
    for system in DMC_SYSTEMS:
        for seed in EVIDENCE_SEEDS:
            output = RAW_OUT / f"{system}_seed{seed}.json"
            worker_runs[system].append(run_one_worker(system, seed, output))

    aggregate = {
        "unit": "DMC-05A",
        "history_sizes": list(HISTORY_SIZES),
        "systems": {system: aggregate_runs(system, worker_runs[system]) for system in ALL_SYSTEMS},
    }
    recent_states = {
        row["case_id"]: row["persistent_record_ids_sha256"]
        for row in worker_runs["recent_window_16"][0]["cases"]
    }
    ordering_by_seed = {}
    for run in worker_runs["dmc04b"]:
        matches = sum(
            recent_states[row["case_id"]] == row["persistent_record_ids_sha256"]
            for row in run["cases"]
        )
        ordering_by_seed[str(run["seed"])] = {
            "matching_persistent_sets": matches,
            "case_count": len(run["cases"]),
            "pass": matches == len(run["cases"]),
        }
    benchmark_ordering = {
        "recent_window_16_equals_dmc04b_persistent_set": all(
            row["pass"] for row in ordering_by_seed.values()
        ),
        "by_seed": ordering_by_seed,
        "interpretation": "The frozen generator appends its utility-eligible records after distractors; this is a benchmark ordering property, not a general recency claim.",
    }
    training = training_accounting(sum(EXPECTED_COUNTS.values()))

    with tempfile.TemporaryDirectory(prefix="dmc05a-replay-") as temporary:
        temporary_root = Path(temporary)
        replay_exact = run_one_worker("exact_structured", None, temporary_root / "exact.json")
        replay_dmc = run_one_worker("dmc04b", 1337, temporary_root / "dmc.json")
    first_exact = worker_runs["exact_structured"][0]
    first_dmc = next(run for run in worker_runs["dmc04b"] if run["seed"] == 1337)
    replay = {
        "exact_structured": {
            "pass": replay_projection(first_exact) == replay_projection(replay_exact),
            "first": digest(replay_projection(first_exact)),
            "second": digest(replay_projection(replay_exact)),
        },
        "dmc04b_seed1337": {
            "pass": replay_projection(first_dmc) == replay_projection(replay_dmc),
            "first": digest(replay_projection(first_dmc)),
            "second": digest(replay_projection(replay_dmc)),
        },
    }
    replay["pass"] = replay["exact_structured"]["pass"] and replay["dmc04b_seed1337"]["pass"]

    component_after = {str(path.relative_to(ROOT)): file_sha256(path) for path in component_paths}
    component_immutability = {"pass": component_before == component_after, "before": component_before, "after": component_after}

    required_metrics = all(
        all(
            all(name in aggregate["systems"][system]["by_history_size"][str(size)] for name in CAPABILITY_METRICS + COUNT_METRICS + TIME_METRICS + ("model_visible_records",))
            for size in HISTORY_SIZES
        )
        for system in ALL_SYSTEMS
    )
    capacities = (
        max(metric(aggregate, "dmc04b", size, "persistent_records") for size in HISTORY_SIZES) <= CAPACITY
        and max(metric(aggregate, "recent_window_16", size, "persistent_records") for size in HISTORY_SIZES) <= CAPACITY
        and max(metric(aggregate, "frozen_fifo_16", size, "persistent_records") for size in HISTORY_SIZES) <= CAPACITY
        and max(metric(aggregate, "random_16", size, "persistent_records") for size in HISTORY_SIZES) <= CAPACITY
    )
    all_history_counts = all(
        math.isclose(metric(aggregate, system, size, "persistent_records"), size)
        for system in ("full_history_scan", "exact_structured", "conventional_retrieval", "dmc_retrieval_all_history")
        for size in HISTORY_SIZES
    )
    token_status = all(
        aggregate["systems"][system]["by_history_size"][str(size)]["model_visible_tokens"] == "NOT_APPLICABLE_SYNTHETIC_RECORDS"
        for system in ALL_SYSTEMS
        for size in HISTORY_SIZES
    )
    integrity = {
        "freeze": freeze["pass"],
        "dmc04b_anchors": anchors["pass"],
        "dataset": dataset["pass"],
        "targeted_tests": tests["pass"],
        "worker_case_counts": all(run["case_count"] == 592 for runs in worker_runs.values() for run in runs),
        "required_metrics": required_metrics,
        "bounded_persistent_capacity": capacities,
        "all_history_record_counts": all_history_counts,
        "token_status_explicit": token_status,
        "training_manifests": all(row["pass"] for row in training["manifests"].values()),
        "training_cost_not_silently_zero": training["status"] == "TRAINING_COST_UNKNOWN",
        "component_immutability": component_immutability["pass"],
        "replay": replay["pass"],
    }
    gate_result = calculate_gates(aggregate, integrity)
    terminal = gate_result["terminal_state"]

    write_json(OUT / "preflight.json", {"freeze": freeze, "anchors": anchors, "dataset": dataset, "tests": tests})
    write_json(OUT / "aggregate.json", aggregate)
    write_json(OUT / "training_accounting.json", training)
    write_json(OUT / "replay.json", replay)
    write_json(OUT / "component_immutability.json", component_immutability)
    write_json(OUT / "benchmark_ordering.json", benchmark_ordering)
    plot_paths = write_curves(aggregate)
    verdict = {
        "unit": "DMC-05A",
        "terminal_state": terminal,
        "claim": "frozen DMC-04B retains a meaningful resource advantage over conventional all-history external memory with bounded retrieval",
        "integrity": integrity,
        "gates": gate_result,
        "training_cost_status": training["status"],
        "history_sizes": list(HISTORY_SIZES),
        "case_count_per_run": 592,
        "systems": list(ALL_SYSTEMS),
        "plots": plot_paths,
        "model_visible_tokens": "NOT_APPLICABLE_SYNTHETIC_RECORDS",
        "benchmark_ordering": benchmark_ordering,
        "protocol_history": {
            "run1": "ENGINEERING_FAILURE_NO_SCIENTIFIC_VERDICT",
            "run2": "DMC_05A_ACCOUNTING_INVALID",
            "run2_machine_label_overridden": "DMC_05A_BOUNDED_MEMORY_ADVANTAGE",
            "run3": "current corrected evidence run"
        },
        "interpretation_boundary": [
            "synthetic structured benchmark only",
            "no actual language tokenizer or expensive language-model calls",
            "historical training wall time, energy, and dollar cost unknown",
            "absolute resources preserved without a composite winner score",
        ],
    }
    write_json(OUT / "DMC05A_VERDICT.json", verdict)
    (OUT / "DMC05A_REPORT.md").write_text(report_markdown(terminal, aggregate, gate_result, training), encoding="utf-8")
    write_json(OUT / "environment.json", {"python": sys.version, "platform": platform.platform(), "pid": os.getpid(), "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 1 if terminal == "DMC_05A_ACCOUNTING_INVALID" else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=ALL_SYSTEMS)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.worker:
        if args.output is None:
            raise SystemExit("--output is required for workers")
        payload = run_worker(args.worker, args.seed)
        write_json(args.output, payload)
        print(f"DMC_05A_WORKER_COMPLETE:{args.worker}:{args.seed}")
        return 0
    if args.seed is not None or args.output is not None:
        raise SystemExit("--seed/--output require --worker")
    return run_parent()


if __name__ == "__main__":
    raise SystemExit(main())
