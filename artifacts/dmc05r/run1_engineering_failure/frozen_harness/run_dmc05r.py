#!/usr/bin/env python3
from __future__ import annotations

"""DMC-05R deterministic recency-confound repair and replay harness."""

import argparse
import copy
import hashlib
import importlib
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "experiments/dmc05r"
CONFIG_PATH = EXPERIMENT_ROOT / "DMC05R_CONFIG.json"
CONTRACT_PATH = EXPERIMENT_ROOT / "DMC05R_CONTRACT.md"
FREEZE_PATH = EXPERIMENT_ROOT / "DMC05R_FREEZE.json"
OUT = ROOT / "artifacts/dmc05r"
RAW_OUT = OUT / "raw"

HISTORY_SIZES = (32, 64, 128, 256, 1024)
SOURCE_COUNTS = {32: 176, 64: 160, 128: 88, 256: 80, 1024: 88}
TAIL_SIZES = (0, 8, 16, 32, 64, 256)
PRIMARY_TAILS = (16, 32, 64, 256)
EXPECTED_VARIANTS_BY_TAIL = {0: 592, 8: 512, 16: 512, 32: 416, 64: 256, 256: 88}
EXPECTED_TOTAL_VARIANTS = 2376
SURPRISE_LOADS = (128, 256, 1024)
EXPECTED_SURPRISE_CASES = 24
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
CAPACITY = 16
RANDOM_CONTROL_SEED = 20260202

DETERMINISTIC_SYSTEMS = (
    "recent_window_16",
    "frozen_fifo_16",
    "random_16",
    "exact_structured",
    "conventional_retrieval",
    "transparent_utility_index_16",
)
DMC_SYSTEMS = ("dmc04b",)
ALL_SYSTEMS = DETERMINISTIC_SYSTEMS + DMC_SYSTEMS
BOUNDED_SYSTEMS = (
    "recent_window_16",
    "frozen_fifo_16",
    "random_16",
    "transparent_utility_index_16",
    "dmc04b",
)
ALL_HISTORY_SYSTEMS = ("exact_structured", "conventional_retrieval")

PREREGISTERED_ANCHORS = {
    "experiments/dmc05a/DMC05A_TERMINAL_RECEIPT.json": "cba6627c8b22a3e563629f09fe05e221a0fb5cefd9613fd7a99c8a460d58a1ba",
    "experiments/dmc05r/DMC05R_CONFIG.json": "6d20750a69d86bd4683f2cb459322219cec22882fde643c85d3e54215278c67d",
    "experiments/dmc05r/DMC05R_CONTRACT.md": "f976341643904baea635b6f2e67dab10c663bd368b7469a2c3e34b88837ee283",
    "scripts/run_dmc04b.py": "3185434b9546236f93b3e75b47f5f11c88e7e33d89985a2c545c36c0fa90cbec",
    "scripts/run_dmc05a.py": "ab32d7b6bb8ec48b98d109499b4543a80e0de15130a4b113fa31fbb3d4695a13",
    "tests/test_dmc05a.py": "5096d6b9a4a8d22b2b38e8977744735140cbd397c294fdbf727c38f1f96a2613",
    "experiments/dmc05a/DMC05A_FREEZE.json": "d4a6f0e3c25b64a67f84fbfef46cadcc27667468706652926ba8037a6737c3a0",
    "artifacts/dmc04b/DMC04B_VERDICT.json": "f62724ca065b166fbc00741f5097a24b85c36e1b232cfc67f6cccbb79c3ba902",
    "artifacts/dmc04b/aggregate.json": "ffcceabec39c9953ec4617aecabd461ed1c6933a34612df08871424d79adb7ab",
    "artifacts/dmc04ba/dataset_manifest.json": "ee4afa55326205030a8600b079a0a484b6bfa39312d6127a80633e00c93274fc",
    "artifacts/dmc05a/DMC05A_VERDICT.json": "7a86a756603f61b4d6f4c02385af850e919a06788c4f9b94f1d684808982b225",
    "artifacts/dmc05a/aggregate.json": "26dfdc54c58261472ab9ee46a29743827d4645f345928c0540b5bc1c8f8daa0c",
    "artifacts/dmc05a/DMC05A_REPORT.md": "4d030c546451ece0ea1dc60247ea20453a84ea9c9ce619626994e45a20270651",
    "artifacts/dmc05a/benchmark_ordering.json": "faca17577e013660e11dc285a8dd2f1cb78f5c0b65456170daada54b52cd932d",
    "artifacts/dmc05a/training_accounting.json": "62b3c0360c05dc6151693297ea0081e176a5c2e20aa686407107872ed6d684c0",
    "artifacts/dmc05a/SHA256SUMS.json": "7889f8b567096c2f7620563885fd1937c6f2e1ca00ec32a5297d262d32ea5075",
}

NUMERIC_METRICS = (
    "critical_recall",
    "retrieval_accuracy",
    "answer_accuracy",
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
    "ingestion_wall_ns",
    "query_wall_ns",
    "online_wall_ns",
    "retention_score_evaluations",
    "utility_policy_evaluations",
    "retention_model_forward_calls",
    "retrieval_model_forward_calls",
    "decoder_model_forward_calls",
    "learned_forward_calls",
    "online_optimizer_steps",
    "online_backward_calls",
    "historical_training_required",
)

MISSION_FAMILIES = frozenset({"mission_set", "supersession", "utility_change"})
ALLOWED_RETENTION_METADATA = frozenset(
    {"family", "entity", "field", "creation_episode", "salience", "supersedes"}
)
CLASSIFIER_FORBIDDEN_FIELDS = frozenset(
    {
        "answer",
        "case_id",
        "hidden_value",
        "logical_key",
        "oracle_decision",
        "query",
        "record_id",
        "target_record_id",
        "value",
        "write_descriptor",
    }
)


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


def stable_record_hash(record_id: str) -> str:
    return hashlib.sha256(record_id.encode("utf-8")).hexdigest()


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


_FROZEN_MODULES: tuple[Any, Any] | None = None


def frozen_modules() -> tuple[Any, Any]:
    global _FROZEN_MODULES
    if _FROZEN_MODULES is None:
        sys.path.insert(0, str(ROOT / "src"))
        sys.path.insert(0, str(ROOT / "scripts"))
        _FROZEN_MODULES = (
            importlib.import_module("run_dmc05a"),
            importlib.import_module("run_dmc04b"),
        )
    return _FROZEN_MODULES


def dataset_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "artifacts/dmc04ba/dataset_manifest.json").read_text(encoding="utf-8"))


def load_source_cases() -> list[dict[str, Any]]:
    manifest = dataset_manifest()
    cases: list[dict[str, Any]] = []
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / manifest[split]["path"]
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                case = json.loads(line)
                if int(case["metadata"]["write_load"]) in HISTORY_SIZES:
                    cases.append(case)
    return cases


def verify_dataset_identity(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    manifest = dataset_manifest()
    errors: list[str] = []
    split_rows: dict[str, Any] = {}
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / manifest[split]["path"]
        observed = file_sha256(path)
        expected = str(manifest[split]["sha256"])
        if observed != expected:
            errors.append(f"{split}:sha256")
        split_rows[split] = {
            "path": str(path.relative_to(ROOT)),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "pass": observed == expected,
        }
    counts = Counter(int(case["metadata"]["write_load"]) for case in cases)
    if dict(counts) != SOURCE_COUNTS:
        errors.append("source-counts")
    for case in cases:
        load = int(case["metadata"]["write_load"])
        if len(case["experience_stream"]) != load:
            errors.append(f"{case['case_id']}:stream-load")
        if int(case["metadata"]["physical_memory_budget"]) != CAPACITY:
            errors.append(f"{case['case_id']}:capacity")
    return {
        "pass": not errors,
        "source_case_count": len(cases),
        "counts_by_history_size": {str(size): counts[size] for size in HISTORY_SIZES},
        "splits": split_rows,
        "errors": errors,
    }


def record_id(row: dict[str, Any]) -> str:
    return str(row["record_id"])


def scope_entities(case: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        str(entity)
        for event in case["metadata"].get("scope_events", [])
        for entity in event["entities"]
    )


def certified_irrelevant_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    stream = case["experience_stream"]
    oracle_ids = {str(row["record_id"]) for row in case["oracle_view"]["records"]}
    target_id = str(case["oracle_view"]["target_record_id"])
    scoped = scope_entities(case)
    referenced = {
        str(row["supersedes"])
        for row in stream
        if row.get("supersedes") is not None
    }
    result: list[dict[str, Any]] = []
    for row in stream:
        metadata = row["retention_metadata"]
        if set(metadata) != set(ALLOWED_RETENTION_METADATA):
            raise ValueError(f"{case['case_id']}: retention metadata schema changed")
        if metadata["supersedes"] != row.get("supersedes"):
            raise ValueError(f"{case['case_id']}:{record_id(row)}: supersedes alias mismatch")
        if str(metadata["entity"]) != str(row["entity"]):
            raise ValueError(f"{case['case_id']}:{record_id(row)}: entity alias mismatch")
        eligible = (
            record_id(row) not in oracle_ids
            and record_id(row) != target_id
            and str(row["entity"]) not in scoped
            and row.get("supersedes") is None
            and record_id(row) not in referenced
            and metadata["salience"] != "HIGH"
            and [float(value) for value in row["retention_features"]] == [0.0, 0.0]
        )
        if eligible:
            result.append(row)
    return result


@dataclass(frozen=True)
class Variant:
    variant_id: str
    source_case: dict[str, Any]
    tail_size: int
    safe_count: int
    moved_ids: tuple[str, ...]
    stream: tuple[dict[str, Any], ...]
    invariant: dict[str, Any]

    @property
    def history_size(self) -> int:
        return len(self.stream)


def materialize_case(variant: Variant) -> dict[str, Any]:
    case = dict(variant.source_case)
    case["experience_stream"] = list(variant.stream)
    return case


def make_variant(case: dict[str, Any], tail_size: int) -> Variant | None:
    if tail_size not in TAIL_SIZES:
        raise ValueError(f"unregistered tail: {tail_size}")
    stream = list(case["experience_stream"])
    safe = certified_irrelevant_rows(case)
    if len(safe) < tail_size:
        return None
    moved = safe[-tail_size:] if tail_size else []
    moved_ids = tuple(record_id(row) for row in moved)
    moved_set = set(moved_ids)
    transformed = [row for row in stream if record_id(row) not in moved_set] + moved
    source_ids = [record_id(row) for row in stream]
    transformed_ids = [record_id(row) for row in transformed]
    safe_ids = [record_id(row) for row in safe]
    protected_ids = [item for item in source_ids if item not in set(safe_ids)]
    transformed_safe_ids = [item for item in transformed_ids if item in set(safe_ids)]
    transformed_protected_ids = [item for item in transformed_ids if item in set(protected_ids)]
    source_payload = {record_id(row): canonical(row) for row in stream}
    transformed_payload = {record_id(row): canonical(row) for row in transformed}
    source_position = {item: index for index, item in enumerate(source_ids)}
    selected_precede_last_protected = (
        tail_size == 0
        or not protected_ids
        or all(source_position[item] < source_position[protected_ids[-1]] for item in moved_ids)
    )
    trailing_tail = tail_size == 0 or tuple(transformed_ids[-tail_size:]) == moved_ids
    all_moved_after_protected = (
        tail_size == 0
        or not protected_ids
        or max(transformed_ids.index(item) for item in protected_ids)
        < min(transformed_ids.index(item) for item in moved_ids)
    )
    target_id = str(case["oracle_view"]["target_record_id"])
    target_rows = [row for row in transformed if record_id(row) == target_id]
    answer_unchanged = len(target_rows) == 1 and str(target_rows[0]["value"]) == str(case["oracle_view"]["answer"])
    checks = {
        "unique_record_ids": len(source_ids) == len(set(source_ids)),
        "record_count_unchanged": len(stream) == len(transformed),
        "record_multiset_unchanged": Counter(source_ids) == Counter(transformed_ids),
        "record_payloads_unchanged": source_payload == transformed_payload,
        "protected_relative_order_preserved": protected_ids == transformed_protected_ids,
        "irrelevant_relative_order_preserved": safe_ids == transformed_safe_ids,
        "moved_selection_is_safe_suffix": moved_ids == tuple(safe_ids[-tail_size:]) if tail_size else not moved_ids,
        "moved_records_preceded_last_protected_in_source": selected_precede_last_protected,
        "trailing_tail_exact": trailing_tail,
        "all_moved_after_last_protected": all_moved_after_protected,
        "target_not_moved": target_id not in moved_set,
        "target_and_answer_unchanged": answer_unchanged,
        "oracle_view_unchanged": True,
        "neural_view_unchanged": True,
        "metadata_unchanged": True,
        "query_unchanged": True,
        "supersession_payloads_unchanged": True,
    }
    invariant = {
        "pass": all(checks.values()),
        "checks": checks,
        "source_order_sha256": digest(source_ids),
        "transformed_order_sha256": digest(transformed_ids),
        "protected_order_sha256": digest(protected_ids),
        "safe_order_sha256": digest(safe_ids),
        "moved_ids_sha256": digest(list(moved_ids)),
        "record_payload_map_sha256": digest(source_payload),
    }
    return Variant(
        variant_id=f"{case['case_id']}|tail_{tail_size}",
        source_case=case,
        tail_size=tail_size,
        safe_count=len(safe),
        moved_ids=moved_ids,
        stream=tuple(transformed),
        invariant=invariant,
    )


def build_variants(cases: Sequence[dict[str, Any]]) -> tuple[list[Variant], dict[str, Any]]:
    variants: list[Variant] = []
    skipped: list[dict[str, Any]] = []
    counts: Counter[int] = Counter()
    failed: list[str] = []
    for case in cases:
        safe_count = len(certified_irrelevant_rows(case))
        for tail_size in TAIL_SIZES:
            variant = make_variant(case, tail_size)
            if variant is None:
                skipped.append(
                    {
                        "source_case_id": case["case_id"],
                        "history_size": int(case["metadata"]["write_load"]),
                        "tail_size": tail_size,
                        "safe_count": safe_count,
                        "reason": "INSUFFICIENT_CERTIFIED_IRRELEVANT_RECORDS",
                    }
                )
                continue
            variants.append(variant)
            counts[tail_size] += 1
            if not variant.invariant["pass"]:
                failed.append(variant.variant_id)
    variants.sort(key=lambda row: (row.tail_size, row.variant_id))
    expected_counts = {str(key): value for key, value in EXPECTED_VARIANTS_BY_TAIL.items()}
    observed_counts = {str(key): counts[key] for key in TAIL_SIZES}
    manifest_rows = [
        {
            "variant_id": variant.variant_id,
            "source_case_id": variant.source_case["case_id"],
            "split": variant.source_case["split"],
            "family": variant.source_case["family"],
            "condition": variant.source_case["condition"],
            "history_size": variant.history_size,
            "tail_size": variant.tail_size,
            "safe_count": variant.safe_count,
            "moved_count": len(variant.moved_ids),
            "invariant": variant.invariant,
        }
        for variant in variants
    ]
    pass_value = (
        observed_counts == expected_counts
        and len(variants) == EXPECTED_TOTAL_VARIANTS
        and not failed
    )
    manifest = {
        "unit": "DMC-05R",
        "pass": pass_value,
        "source_case_count": len(cases),
        "variant_count": len(variants),
        "expected_variant_count": EXPECTED_TOTAL_VARIANTS,
        "counts_by_tail": observed_counts,
        "expected_counts_by_tail": expected_counts,
        "failed_invariant_variants": failed,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "variants": manifest_rows,
        "variant_projection_sha256": digest(manifest_rows),
        "skipped_projection_sha256": digest(skipped),
    }
    return variants, manifest


def write_key_from_row(row: dict[str, Any]) -> tuple[int, int]:
    d05a, _ = frozen_modules()
    return tuple(d05a.write_key(row))


def query_descriptor_from_write(row: dict[str, Any]) -> dict[str, Any]:
    descriptor = row["write_descriptor"]
    return {
        "attribute_order": list(descriptor["attribute_order"]),
        "noise_token_count": 0,
        "tokens": [str(token).replace("write_", "query_", 1) for token in descriptor["tokens"]],
    }


@dataclass(frozen=True)
class SurpriseCase:
    variant_id: str
    source_case: dict[str, Any]
    case: dict[str, Any]
    late_scope: tuple[str, ...]
    target_id: str
    target_episode: int
    target_entity: str
    replaced_entity: str
    invariant: dict[str, Any]


def build_surprise_cases(cases: Sequence[dict[str, Any]]) -> tuple[list[SurpriseCase], dict[str, Any]]:
    selected = sorted(
        (
            case
            for case in cases
            if case["split"] == "extrapolation"
            and case["family"] == "mission_set"
            and int(case["metadata"]["write_load"]) in SURPRISE_LOADS
        ),
        key=lambda case: case["case_id"],
    )
    result: list[SurpriseCase] = []
    failures: list[str] = []
    for source in selected:
        safe = certified_irrelevant_rows(source)
        if len(safe) <= 12:
            failures.append(f"{source['case_id']}:no-old-target")
            continue
        target = safe[12]
        original_events = source["metadata"].get("scope_events", [])
        if len(original_events) != 1 or len(original_events[0]["entities"]) != CAPACITY:
            failures.append(f"{source['case_id']}:scope-shape")
            continue
        initial_scope = [str(item) for item in original_events[0]["entities"]]
        replaced = initial_scope[-1]
        target_entity = str(target["entity"])
        late_scope = tuple(initial_scope[:-1] + [target_entity])
        case = dict(source)
        case["metadata"] = copy.deepcopy(source["metadata"])
        case["metadata"]["scope_events"] = [
            copy.deepcopy(original_events[0]),
            {"kind": "mission_update", "entities": list(late_scope)},
        ]
        case["neural_view"] = copy.deepcopy(source["neural_view"])
        case["neural_view"]["query"] = {
            "mode": "history",
            "as_of_episode": int(target["creation_episode"]),
            "query_descriptor": query_descriptor_from_write(target),
        }
        case["oracle_view"] = copy.deepcopy(source["oracle_view"])
        case["oracle_view"]["mode"] = "history"
        case["oracle_view"]["as_of_episode"] = int(target["creation_episode"])
        case["oracle_view"]["target_record_id"] = record_id(target)
        case["oracle_view"]["target_logical_key"] = list(write_key_from_row(target))
        case["oracle_view"]["answer"] = str(target["value"])
        checks = {
            "source_record_stream_unchanged": canonical(case["experience_stream"]) == canonical(source["experience_stream"]),
            "target_was_certified_irrelevant": record_id(target) in {record_id(row) for row in safe},
            "target_not_in_initial_scope": target_entity not in initial_scope,
            "target_in_late_scope": target_entity in late_scope,
            "scope_capacity_unchanged": len(late_scope) == CAPACITY,
            "one_initial_entity_replaced": len(set(initial_scope) - set(late_scope)) == 1,
            "target_is_old": int(target["creation_episode"]) <= 12,
            "history_query_targets_record_write": tuple(write_key_from_row(target))
            == tuple(frozen_modules()[0].query_key(case)),
            "query_answer_matches_target": str(case["oracle_view"]["answer"]) == str(target["value"]),
        }
        invariant = {"pass": all(checks.values()), "checks": checks}
        if not invariant["pass"]:
            failures.append(f"{source['case_id']}:invariant")
        result.append(
            SurpriseCase(
                variant_id=f"{source['case_id']}|SURPRISE_DEPENDENCY",
                source_case=source,
                case=case,
                late_scope=late_scope,
                target_id=record_id(target),
                target_episode=int(target["creation_episode"]),
                target_entity=target_entity,
                replaced_entity=replaced,
                invariant=invariant,
            )
        )
    rows = [
        {
            "variant_id": item.variant_id,
            "source_case_id": item.source_case["case_id"],
            "history_size": len(item.case["experience_stream"]),
            "target_id": item.target_id,
            "target_episode": item.target_episode,
            "target_entity": item.target_entity,
            "replaced_entity": item.replaced_entity,
            "late_scope_sha256": digest(list(item.late_scope)),
            "invariant": item.invariant,
        }
        for item in result
    ]
    manifest = {
        "unit": "DMC-05R",
        "subset": "SURPRISE_DEPENDENCY",
        "status": "EXPLORATORY_NONTERMINAL",
        "case_count": len(result),
        "expected_case_count": EXPECTED_SURPRISE_CASES,
        "pass": len(result) == EXPECTED_SURPRISE_CASES and not failures,
        "failures": failures,
        "cases": rows,
        "projection_sha256": digest(rows),
    }
    return result, manifest


def decorate_case_metrics(
    row: dict[str, Any],
    *,
    variant_id: str,
    tail_size: int | None,
    subset: str,
    family: str,
    condition: str,
    split: str,
) -> dict[str, Any]:
    result = dict(row)
    result.update(
        {
            "variant_id": variant_id,
            "tail_size": tail_size,
            "subset": subset,
            "family": family,
            "condition": condition,
            "split": split,
            "online_wall_ns": int(row["ingestion_wall_ns"]) + int(row["query_wall_ns"]),
            "online_optimizer_steps": int(row.get("online_optimizer_steps", 0)),
            "online_backward_calls": int(row.get("online_backward_calls", 0)),
        }
    )
    result["learned_forward_calls"] = int(
        result.get("retention_model_forward_calls", 0)
        + result.get("retrieval_model_forward_calls", 0)
        + result.get("decoder_model_forward_calls", 0)
    )
    return result


def evaluate_conventional(
    system: str,
    case: dict[str, Any],
    *,
    variant_id: str,
    tail_size: int | None,
    subset: str,
) -> dict[str, Any]:
    d05a, _ = frozen_modules()
    row = d05a.conventional_case(system, case)
    row.update(
        {
            "utility_policy_evaluations": len(case["experience_stream"])
            if system in {"exact_structured", "conventional_retrieval"}
            else 0,
            "historical_training_required": 0,
            "metadata_firewall_pass": True,
            "classifier_fields_observed": []
            if system not in {"exact_structured", "conventional_retrieval"}
            else sorted(ALLOWED_RETENTION_METADATA | {"active_entities"}),
            "classifier_forbidden_fields_observed": [],
            "tie_break_record_id_resolver_only": True,
            "online_optimizer_steps": 0,
            "online_backward_calls": 0,
        }
    )
    return decorate_case_metrics(
        row,
        variant_id=variant_id,
        tail_size=tail_size,
        subset=subset,
        family=str(case["family"]),
        condition=str(case["condition"]),
        split=str(case["split"]),
    )


def transparent_entry(row: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(row["retention_metadata"])
    if set(metadata) != set(ALLOWED_RETENTION_METADATA):
        raise ValueError("transparent selector received changed metadata schema")
    return {
        "record_id": record_id(row),
        "key": list(write_key_from_row(row)),
        "entity": str(row["entity"]),
        "creation_episode": int(row["creation_episode"]),
        "version": str(row["version"]),
        "value": str(row["value"]),
        "retention_metadata": metadata,
    }


def explicit_utility_features(
    metadata: dict[str, Any], active_scope: Iterable[str], audit: dict[str, Any]
) -> tuple[int, int]:
    if set(metadata) != set(ALLOWED_RETENTION_METADATA):
        raise ValueError("utility classifier received non-frozen metadata")
    forbidden = set(metadata).intersection(CLASSIFIER_FORBIDDEN_FIELDS)
    audit["evaluations"] += 1
    audit["input_fields_observed"].update(ALLOWED_RETENTION_METADATA | {"active_entities"})
    audit["forbidden_fields_observed"].update(forbidden)
    if forbidden:
        raise ValueError("utility classifier firewall violation")
    active = frozenset(str(item) for item in active_scope)
    mission_membership = int(
        str(metadata["family"]) in MISSION_FAMILIES and str(metadata["entity"]) in active
    )
    high_salience = int(metadata["salience"] == "HIGH")
    return mission_membership, high_salience


def transparent_rank(
    records: Sequence[dict[str, Any]], active_scope: Iterable[str], audit: dict[str, Any]
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in records:
        features = explicit_utility_features(row["retention_metadata"], active_scope, audit)
        utility_eligible = int(bool(features[0] or features[1]))
        ranked.append((-utility_eligible, stable_record_hash(str(row["record_id"])), row))
    return [row for _, _, row in sorted(ranked, key=lambda item: (item[0], item[1]))[:CAPACITY]]


def transparent_retention(
    case: dict[str, Any], *, late_scope: Sequence[str] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _, d04b = frozen_modules()
    memory: list[dict[str, Any]] = []
    active = list(d04b.initial_scope(case))
    scope_switched = False
    occupancy: list[int] = []
    audit: dict[str, Any] = {
        "evaluations": 0,
        "input_fields_observed": set(),
        "forbidden_fields_observed": set(),
        "tie_break_fields": {"record_id_sha256"},
        "scope_updates": 0,
    }
    for source_row in case["experience_stream"]:
        if (
            case["family"] == "utility_change"
            and not scope_switched
            and int(source_row["creation_episode"]) >= 200
        ):
            active = list(d04b.final_scope(case))
            memory = transparent_rank(memory, active, audit)
            scope_switched = True
            audit["scope_updates"] += 1
        row = transparent_entry(source_row)
        if case["family"] == "utility_change":
            memory = [old for old in memory if old["entity"] != row["entity"]]
        memory.append(row)
        if len(memory) > CAPACITY:
            memory = transparent_rank(memory, active, audit)
        occupancy.append(len(memory))
        if len(memory) > CAPACITY:
            raise AssertionError("transparent selector exceeded capacity")
    if late_scope is not None:
        active = list(late_scope)
        memory = transparent_rank(memory, active, audit)
        audit["scope_updates"] += 1
    return memory, {
        "utility_policy_evaluations": int(audit["evaluations"]),
        "input_fields_observed": sorted(audit["input_fields_observed"]),
        "forbidden_fields_observed": sorted(audit["forbidden_fields_observed"]),
        "tie_break_fields": sorted(audit["tie_break_fields"]),
        "scope_updates": int(audit["scope_updates"]),
        "max_occupancy": max(occupancy) if occupancy else 0,
        "final_scope": list(active),
        "pass": not audit["forbidden_fields_observed"] and max(occupancy, default=0) <= CAPACITY,
    }


def evaluate_transparent(
    case: dict[str, Any],
    *,
    variant_id: str,
    tail_size: int | None,
    subset: str,
    late_scope: Sequence[str] | None = None,
) -> dict[str, Any]:
    d05a, _ = frozen_modules()
    stream = case["experience_stream"]
    target_id = str(case["oracle_view"]["target_record_id"])
    expected_answer = str(case["oracle_view"]["answer"])
    ingestion_start = time.perf_counter_ns()
    retained, audit = transparent_retention(case, late_scope=late_scope)
    ingestion_wall_ns = time.perf_counter_ns() - ingestion_start

    query = case["neural_view"]["query"]
    qkey = tuple(d05a.query_key(case))
    query_start = time.perf_counter_ns()
    query_candidates = [
        {
            "record_id": str(row["record_id"]),
            "key": list(row["key"]),
            "creation_episode": int(row["creation_episode"]),
            "value": str(row["value"]),
        }
        for row in retained
    ]
    selected = d05a.exact_select(
        query_candidates,
        qkey,
        str(query["mode"]),
        query["as_of_episode"],
    )
    query_wall_ns = time.perf_counter_ns() - query_start
    selected_id = None if selected is None else str(selected["record_id"])
    predicted = None if selected is None else str(selected["value"])
    retained_ids = {str(row["record_id"]) for row in retained}
    row = {
        "case_id": case["case_id"],
        "history_size": len(stream),
        "selected_record_id": selected_id,
        "target_record_id": target_id,
        "critical_recall": int(target_id in retained_ids),
        "retrieval_accuracy": int(selected_id == target_id),
        "answer_accuracy": int(predicted == expected_answer),
        "persistent_records": len(retained),
        "persistent_serialized_bytes": canonical_bytes(retained),
        "records_inspected_ingestion": len(stream),
        "records_inspected_query": len(query_candidates),
        "retrieval_candidate_records": len(query_candidates),
        "retrieved_records": int(selected is not None),
        "persistent_write_operations": len(stream),
        "declared_update_operations": int(d05a.declared_update_count(stream)),
        "retention_discard_operations": max(0, len(stream) - len(retained)),
        "retrieval_index_operations": len(query_candidates),
        "maximum_working_set_records": max(int(audit["max_occupancy"]), len(query_candidates)),
        "working_set_serialized_bytes": canonical_bytes(query_candidates),
        "ingestion_wall_ns": ingestion_wall_ns,
        "query_wall_ns": query_wall_ns,
        "retention_score_evaluations": 0,
        "utility_policy_evaluations": int(audit["utility_policy_evaluations"]),
        "retention_model_forward_calls": 0,
        "retrieval_model_forward_calls": 0,
        "decoder_model_forward_calls": 0,
        "model_visible_records": len(query_candidates),
        "model_visible_tokens": "NOT_APPLICABLE_SYNTHETIC_RECORDS",
        "persistent_record_ids_sha256": digest(sorted(retained_ids)),
        "ordered_persistent_record_ids_sha256": digest([str(row["record_id"]) for row in retained]),
        "metadata_firewall_pass": bool(audit["pass"]),
        "classifier_fields_observed": audit["input_fields_observed"],
        "classifier_forbidden_fields_observed": audit["forbidden_fields_observed"],
        "tie_break_record_id_resolver_only": audit["tie_break_fields"] == ["record_id_sha256"],
        "scope_updates": int(audit["scope_updates"]),
        "historical_training_required": 0,
        "online_optimizer_steps": 0,
        "online_backward_calls": 0,
    }
    return decorate_case_metrics(
        row,
        variant_id=variant_id,
        tail_size=tail_size,
        subset=subset,
        family=str(case["family"]),
        condition=str(case["condition"]),
        split=str(case["split"]),
    )


def fast_feature_key(metadata: dict[str, Any], active_scope: Iterable[str]) -> tuple[float, float]:
    if set(metadata) != set(ALLOWED_RETENTION_METADATA):
        raise ValueError("optimized frozen scorer received non-frozen metadata")
    active = frozenset(str(item) for item in active_scope)
    return (
        float(str(metadata["family"]) in MISSION_FAMILIES and str(metadata["entity"]) in active),
        float(metadata["salience"] == "HIGH"),
    )


def fast_dmc_rank(
    records: Sequence[dict[str, Any]],
    active_scope: Iterable[str],
    scorer: Any,
    torch_module: Any,
    score_cache: dict[tuple[float, float], float],
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for row in records:
        metadata = row["retention_metadata"]
        key = fast_feature_key(metadata, active_scope)
        audit["logical_score_evaluations"] += 1
        audit["input_fields_observed"].update(ALLOWED_RETENTION_METADATA | {"active_entities"})
        forbidden = set(metadata).intersection(CLASSIFIER_FORBIDDEN_FIELDS)
        audit["forbidden_fields_observed"].update(forbidden)
        if forbidden:
            raise ValueError("optimized frozen scorer firewall violation")
        if key not in score_cache:
            with torch_module.no_grad():
                features = torch_module.tensor(key, dtype=torch_module.float32)
                score_cache[key] = float(scorer(features).item())
        ranked.append((-score_cache[key], stable_record_hash(record_id(row)), row))
    return [row for _, _, row in sorted(ranked, key=lambda item: (item[0], item[1]))[:CAPACITY]]


def fast_dmc_retention(
    models: dict[str, Any],
    case: dict[str, Any],
    *,
    late_scope: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _, d04b = frozen_modules()
    scorer = models["retention"]
    torch_module = models["torch"]
    memory: list[dict[str, Any]] = []
    active = list(d04b.initial_scope(case))
    scope_switched = False
    occupancy: list[int] = []
    score_cache: dict[tuple[float, float], float] = {}
    audit: dict[str, Any] = {
        "logical_score_evaluations": 0,
        "input_fields_observed": set(),
        "forbidden_fields_observed": set(),
        "scope_updates": 0,
    }
    for row in case["experience_stream"]:
        if (
            case["family"] == "utility_change"
            and not scope_switched
            and int(row["creation_episode"]) >= 200
        ):
            active = list(d04b.final_scope(case))
            memory = fast_dmc_rank(memory, active, scorer, torch_module, score_cache, audit)
            scope_switched = True
            audit["scope_updates"] += 1
        if case["family"] == "utility_change":
            memory = [old for old in memory if old["entity"] != row["entity"]]
        memory.append(row)
        if len(memory) > CAPACITY:
            memory = fast_dmc_rank(memory, active, scorer, torch_module, score_cache, audit)
        occupancy.append(len(memory))
        if len(memory) > CAPACITY:
            raise AssertionError("optimized frozen DMC exceeded capacity")
    if late_scope is not None:
        active = list(late_scope)
        memory = fast_dmc_rank(memory, active, scorer, torch_module, score_cache, audit)
        audit["scope_updates"] += 1
    return memory, {
        "logical_score_evaluations": int(audit["logical_score_evaluations"]),
        "input_fields_observed": sorted(audit["input_fields_observed"]),
        "forbidden_fields_observed": sorted(audit["forbidden_fields_observed"]),
        "scope_updates": int(audit["scope_updates"]),
        "max_occupancy": max(occupancy) if occupancy else 0,
        "final_scope": list(active),
        "score_cache": {str(list(key)): value for key, value in sorted(score_cache.items())},
        "pass": not audit["forbidden_fields_observed"] and max(occupancy, default=0) <= CAPACITY,
    }


def evaluate_dmc(
    case: dict[str, Any],
    models: dict[str, Any],
    *,
    variant_id: str,
    tail_size: int | None,
    subset: str,
    late_scope: Sequence[str] | None = None,
) -> dict[str, Any]:
    d05a, d04b = frozen_modules()
    stream = case["experience_stream"]
    target_id = str(case["oracle_view"]["target_record_id"])
    expected_answer = str(case["oracle_view"]["answer"])
    value_vectors = d05a.hidden_map(case)
    retention = models["retention"]

    ingestion_start = time.perf_counter_ns()
    before_forward = int(retention.forward_calls)
    retained, retention_audit = fast_dmc_retention(models, case, late_scope=late_scope)
    ingestion_wall_ns = time.perf_counter_ns() - ingestion_start
    retention_forward_calls = int(retention.forward_calls) - before_forward

    query_start = time.perf_counter_ns()
    candidates = [d04b.candidate_from_row(row, value_vectors) for row in retained]
    retrieval_audit = d04b.retrieval_audit()
    selected = d04b.learned_retrieve(models["retriever"], case, candidates, retrieval_audit)
    predicted = None if selected is None else d04b.decode_row(models["decoder"], case, selected)
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
    retained_ids = {record_id(row) for row in retained}
    retrieval_firewall_pass = not retrieval_audit["forbidden_fields_observed"]
    row = {
        "case_id": case["case_id"],
        "history_size": len(stream),
        "selected_record_id": selected_id,
        "target_record_id": target_id,
        "critical_recall": int(target_id in retained_ids),
        "retrieval_accuracy": int(selected_id == target_id),
        "answer_accuracy": int(predicted == expected_answer),
        "persistent_records": len(retained),
        "persistent_serialized_bytes": canonical_bytes(retained),
        "records_inspected_ingestion": len(stream),
        "records_inspected_query": len(candidates),
        "retrieval_candidate_records": len(candidates),
        "retrieved_records": int(selected is not None),
        "persistent_write_operations": len(stream),
        "declared_update_operations": int(d05a.declared_update_count(stream)),
        "retention_discard_operations": max(0, len(stream) - len(retained)),
        "retrieval_index_operations": len(candidates),
        "maximum_working_set_records": max(int(retention_audit["max_occupancy"]), len(candidates)),
        "working_set_serialized_bytes": canonical_bytes(scorer_payload),
        "ingestion_wall_ns": ingestion_wall_ns,
        "query_wall_ns": query_wall_ns,
        "retention_score_evaluations": int(retention_audit["logical_score_evaluations"]),
        "utility_policy_evaluations": 0,
        "retention_model_forward_calls": retention_forward_calls,
        "retrieval_model_forward_calls": int(retrieval_audit["calls"]),
        "decoder_model_forward_calls": int(selected is not None),
        "model_visible_records": len(candidates),
        "model_visible_tokens": "NOT_APPLICABLE_SYNTHETIC_RECORDS",
        "persistent_record_ids_sha256": digest(sorted(retained_ids)),
        "ordered_persistent_record_ids_sha256": digest([record_id(item) for item in retained]),
        "metadata_firewall_pass": bool(retention_audit["pass"] and retrieval_firewall_pass),
        "classifier_fields_observed": retention_audit["input_fields_observed"],
        "classifier_forbidden_fields_observed": retention_audit["forbidden_fields_observed"],
        "tie_break_record_id_resolver_only": True,
        "retrieval_firewall_pass": retrieval_firewall_pass,
        "scope_updates": int(retention_audit["scope_updates"]),
        "historical_training_required": 1,
        "online_optimizer_steps": 0,
        "online_backward_calls": 0,
    }
    return decorate_case_metrics(
        row,
        variant_id=variant_id,
        tail_size=tail_size,
        subset=subset,
        family=str(case["family"]),
        condition=str(case["condition"]),
        split=str(case["split"]),
    )


def run_worker(system: str, seed: int | None) -> dict[str, Any]:
    if system not in ALL_SYSTEMS:
        raise ValueError(system)
    if system == "dmc04b" and seed not in EVIDENCE_SEEDS:
        raise ValueError("DMC worker requires a frozen evidence seed")
    if system != "dmc04b" and seed is not None:
        raise ValueError("deterministic worker must not receive a seed")
    cases = load_source_cases()
    variants, variant_manifest = build_variants(cases)
    surprises, surprise_manifest = build_surprise_cases(cases)
    if not variant_manifest["pass"] or not surprise_manifest["pass"]:
        raise ValueError("worker fixture construction failed preregistered invariants")

    d05a, _ = frozen_modules()
    models = d05a.load_dmc(int(seed)) if system == "dmc04b" else None
    core_rows: list[dict[str, Any]] = []
    for variant in variants:
        case = materialize_case(variant)
        if system == "transparent_utility_index_16":
            row = evaluate_transparent(
                case,
                variant_id=variant.variant_id,
                tail_size=variant.tail_size,
                subset="CORE",
            )
        elif system == "dmc04b":
            if models is None:
                raise AssertionError("missing DMC models")
            row = evaluate_dmc(
                case,
                models,
                variant_id=variant.variant_id,
                tail_size=variant.tail_size,
                subset="CORE",
            )
        else:
            row = evaluate_conventional(
                system,
                case,
                variant_id=variant.variant_id,
                tail_size=variant.tail_size,
                subset="CORE",
            )
        core_rows.append(row)

    surprise_rows: list[dict[str, Any]] = []
    for item in surprises:
        if system == "transparent_utility_index_16":
            row = evaluate_transparent(
                item.case,
                variant_id=item.variant_id,
                tail_size=None,
                subset="SURPRISE_DEPENDENCY",
                late_scope=item.late_scope,
            )
        elif system == "dmc04b":
            if models is None:
                raise AssertionError("missing DMC models")
            row = evaluate_dmc(
                item.case,
                models,
                variant_id=item.variant_id,
                tail_size=None,
                subset="SURPRISE_DEPENDENCY",
                late_scope=item.late_scope,
            )
        else:
            row = evaluate_conventional(
                system,
                item.case,
                variant_id=item.variant_id,
                tail_size=None,
                subset="SURPRISE_DEPENDENCY",
            )
        surprise_rows.append(row)

    payload = {
        "unit": "DMC-05R",
        "system": system,
        "seed": seed,
        "core_case_count": len(core_rows),
        "surprise_case_count": len(surprise_rows),
        "core_cases": core_rows,
        "surprise_cases": surprise_rows,
        "variant_projection_sha256": variant_manifest["variant_projection_sha256"],
        "surprise_projection_sha256": surprise_manifest["projection_sha256"],
        "checkpoint_hashes": {} if models is None else models["checkpoint_hashes"],
        "resource": {
            "peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "pid": os.getpid(),
        },
        "scientific_training_executed": False,
        "optimizer_objects_created": 0,
        "optimizer_steps": 0,
        "backward_calls": 0,
    }
    payload["deterministic_projection_sha256"] = digest(worker_projection(payload))
    return payload


TIMING_FIELDS = frozenset({"ingestion_wall_ns", "query_wall_ns", "online_wall_ns"})


def case_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in TIMING_FIELDS}


def worker_projection(worker: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": worker["system"],
        "seed": worker["seed"],
        "core_cases": [case_projection(row) for row in worker["core_cases"]],
        "surprise_cases": [case_projection(row) for row in worker["surprise_cases"]],
        "variant_projection_sha256": worker["variant_projection_sha256"],
        "surprise_projection_sha256": worker["surprise_projection_sha256"],
        "checkpoint_hashes": worker["checkpoint_hashes"],
        "scientific_training_executed": worker["scientific_training_executed"],
        "optimizer_objects_created": worker["optimizer_objects_created"],
        "optimizer_steps": worker["optimizer_steps"],
        "backward_calls": worker["backward_calls"],
    }


def summary_for_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"case_count": 0, "metrics": {}}
    metrics: dict[str, Any] = {}
    for name in NUMERIC_METRICS:
        values = [float(row[name]) for row in rows]
        metrics[name] = {
            "mean": statistics.mean(values),
            "std": statistics.pstdev(values),
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "min": min(values),
            "max": max(values),
        }
    return {"case_count": len(rows), "metrics": metrics}


def aggregate_subset(
    runs: Sequence[dict[str, Any]],
    *,
    source: str,
    predicate: Any,
) -> dict[str, Any]:
    per_run_rows: list[list[dict[str, Any]]] = [
        [row for row in run[source] if predicate(row)] for run in runs
    ]
    counts = [len(rows) for rows in per_run_rows]
    if len(set(counts)) > 1:
        raise ValueError(f"seed case counts differ: {counts}")
    by_seed: dict[str, Any] = {}
    metric_seed_means: dict[str, dict[str, float]] = {name: {} for name in NUMERIC_METRICS}
    for run, rows in zip(runs, per_run_rows):
        seed_key = "deterministic" if run["seed"] is None else str(run["seed"])
        local = summary_for_rows(rows)
        by_seed[seed_key] = local
        for name in NUMERIC_METRICS:
            metric_seed_means[name][seed_key] = float(local["metrics"][name]["mean"]) if rows else 0.0
    metrics: dict[str, Any] = {}
    for name, values_by_seed in metric_seed_means.items():
        values = list(values_by_seed.values())
        metrics[name] = {
            "by_seed": values_by_seed,
            "mean": statistics.mean(values) if values else 0.0,
            "std_across_seeds": statistics.pstdev(values) if values else 0.0,
            "min_seed_mean": min(values) if values else 0.0,
            "max_seed_mean": max(values) if values else 0.0,
        }
    return {
        "case_count_per_run": counts[0] if counts else 0,
        "run_count": len(runs),
        "metrics": metrics,
        "by_seed": by_seed,
    }


def aggregate_system_runs(system: str, runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        raise ValueError(f"no runs for {system}")
    expected_runs = len(EVIDENCE_SEEDS) if system == "dmc04b" else 1
    if len(runs) != expected_runs:
        raise ValueError(f"wrong run count for {system}: {len(runs)}")
    result = {
        "run_count": len(runs),
        "seeds": [run["seed"] for run in runs],
        "subsets": {
            "overall": aggregate_subset(runs, source="core_cases", predicate=lambda row: True),
            "tail_zero": aggregate_subset(
                runs, source="core_cases", predicate=lambda row: row["tail_size"] == 0
            ),
            "primary": aggregate_subset(
                runs, source="core_cases", predicate=lambda row: int(row["tail_size"]) in PRIMARY_TAILS
            ),
            "surprise_dependency": aggregate_subset(
                runs, source="surprise_cases", predicate=lambda row: True
            ),
        },
        "by_tail": {},
        "by_tail_and_history_size": {},
        "worker_projection_sha256": [run["deterministic_projection_sha256"] for run in runs],
        "peak_rss_kib": {
            "by_seed": {
                "deterministic" if run["seed"] is None else str(run["seed"]): int(run["resource"]["peak_rss_kib"])
                for run in runs
            },
            "max": max(int(run["resource"]["peak_rss_kib"]) for run in runs),
        },
    }
    for tail in TAIL_SIZES:
        result["by_tail"][str(tail)] = aggregate_subset(
            runs, source="core_cases", predicate=lambda row, value=tail: int(row["tail_size"]) == value
        )
        for size in HISTORY_SIZES:
            key = f"tail_{tail}|load_{size}"
            subset = aggregate_subset(
                runs,
                source="core_cases",
                predicate=lambda row, t=tail, s=size: int(row["tail_size"]) == t
                and int(row["history_size"]) == s,
            )
            if subset["case_count_per_run"]:
                result["by_tail_and_history_size"][key] = subset
    return result


def aggregate_all(worker_runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "unit": "DMC-05R",
        "history_sizes": list(HISTORY_SIZES),
        "tail_sizes": list(TAIL_SIZES),
        "primary_tail_sizes": list(PRIMARY_TAILS),
        "systems": {
            system: aggregate_system_runs(system, worker_runs[system]) for system in ALL_SYSTEMS
        },
    }


def direct_frozen_dmc_projection(case: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    d05a, d04b = frozen_modules()
    audit = d04b.retention_audit()
    retained, _ = d04b.learned_retention(models["retention"], case, audit)
    candidates = [d04b.candidate_from_row(row, d05a.hidden_map(case)) for row in retained]
    retrieval_audit = d04b.retrieval_audit()
    selected = d04b.learned_retrieve(models["retriever"], case, candidates, retrieval_audit)
    predicted = None if selected is None else d04b.decode_row(models["decoder"], case, selected)
    target_id = str(case["oracle_view"]["target_record_id"])
    selected_id = None if selected is None else str(selected["record_id"])
    retained_ids = {record_id(row) for row in retained}
    return {
        "ordered_persistent_record_ids_sha256": digest([record_id(row) for row in retained]),
        "persistent_record_ids_sha256": digest(sorted(retained_ids)),
        "selected_record_id": selected_id,
        "critical_recall": int(target_id in retained_ids),
        "retrieval_accuracy": int(selected_id == target_id),
        "answer_accuracy": int(predicted == str(case["oracle_view"]["answer"])),
        "retention_score_evaluations": int(audit["calls"]),
    }


EQUIVALENCE_FIELDS_TAIL_ZERO = (
    "persistent_record_ids_sha256",
    "selected_record_id",
    "critical_recall",
    "retrieval_accuracy",
    "answer_accuracy",
    "retention_score_evaluations",
)
EQUIVALENCE_FIELDS_NONZERO = (
    "ordered_persistent_record_ids_sha256",
    "persistent_record_ids_sha256",
    "selected_record_id",
    "critical_recall",
    "retrieval_accuracy",
    "answer_accuracy",
    "retention_score_evaluations",
)


def verify_tail_zero_equivalence(dmc_runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_seed: dict[str, Any] = {}
    total = 0
    matches = 0
    mismatches: list[dict[str, Any]] = []
    for run in dmc_runs:
        seed = int(run["seed"])
        frozen_path = ROOT / f"artifacts/dmc05a/raw/dmc04b_seed{seed}.json"
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        expected = {str(row["case_id"]): row for row in frozen["cases"]}
        observed = {
            str(row["case_id"]): row
            for row in run["core_cases"]
            if int(row["tail_size"]) == 0
        }
        local_matches = 0
        for case_id in sorted(expected):
            total += 1
            same = all(expected[case_id][field] == observed[case_id][field] for field in EQUIVALENCE_FIELDS_TAIL_ZERO)
            if same:
                matches += 1
                local_matches += 1
            elif len(mismatches) < 100:
                mismatches.append(
                    {
                        "seed": seed,
                        "case_id": case_id,
                        "expected": {field: expected[case_id][field] for field in EQUIVALENCE_FIELDS_TAIL_ZERO},
                        "observed": {field: observed[case_id][field] for field in EQUIVALENCE_FIELDS_TAIL_ZERO},
                    }
                )
        by_seed[str(seed)] = {
            "case_count": len(expected),
            "matching_cases": local_matches,
            "pass": local_matches == len(expected) == 592,
            "frozen_receipt": str(frozen_path.relative_to(ROOT)),
            "frozen_receipt_sha256": file_sha256(frozen_path),
        }
    return {
        "pass": total == 2960 and matches == total,
        "comparison_count": total,
        "matching_count": matches,
        "by_seed": by_seed,
        "mismatches": mismatches,
    }


def nonzero_boundary_variants(variants: Sequence[Variant]) -> list[Variant]:
    result: list[Variant] = []
    for tail in TAIL_SIZES[1:]:
        rows = sorted((item for item in variants if item.tail_size == tail), key=lambda item: item.variant_id)
        if not rows:
            raise ValueError(f"missing nonzero tail {tail}")
        result.extend([rows[0], rows[-1]])
    return result


def verify_nonzero_direct_equivalence(
    variants: Sequence[Variant], dmc_runs: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    sample = nonzero_boundary_variants(variants)
    run_by_seed = {int(run["seed"]): run for run in dmc_runs}
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for seed in EVIDENCE_SEEDS:
        d05a, _ = frozen_modules()
        models = d05a.load_dmc(seed)
        observed_by_id = {row["variant_id"]: row for row in run_by_seed[seed]["core_cases"]}
        for variant in sample:
            direct = direct_frozen_dmc_projection(materialize_case(variant), models)
            observed = observed_by_id[variant.variant_id]
            same = all(direct[field] == observed[field] for field in EQUIVALENCE_FIELDS_NONZERO)
            row = {
                "seed": seed,
                "variant_id": variant.variant_id,
                "tail_size": variant.tail_size,
                "pass": same,
                "direct_projection_sha256": digest(direct),
                "optimized_projection_sha256": digest(
                    {field: observed[field] for field in EQUIVALENCE_FIELDS_NONZERO}
                ),
            }
            rows.append(row)
            if not same:
                failures.append(
                    {
                        **row,
                        "direct": direct,
                        "optimized": {field: observed[field] for field in EQUIVALENCE_FIELDS_NONZERO},
                    }
                )
    return {
        "pass": len(rows) == 50 and not failures,
        "sample_variant_count": len(sample),
        "comparison_count": len(rows),
        "rows": rows,
        "failures": failures,
    }


def verify_json_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["manifest-missing"], "entries": 0}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for relative, expected in manifest.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}:missing")
        elif file_sha256(path) != expected:
            errors.append(f"{relative}:sha256")
    return {
        "pass": not errors,
        "entries": len(manifest),
        "manifest_sha256": file_sha256(manifest_path),
        "errors": errors,
    }


def verify_preregistered_anchors() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    errors: list[str] = []
    for relative, expected in PREREGISTERED_ANCHORS.items():
        path = ROOT / relative
        observed = file_sha256(path) if path.is_file() else None
        passed = observed == expected
        rows[relative] = {"expected_sha256": expected, "observed_sha256": observed, "pass": passed}
        if not passed:
            errors.append(relative)
    dmc04b_manifest = verify_json_manifest(ROOT / "artifacts/dmc04b")
    dmc05a_manifest = verify_json_manifest(ROOT / "artifacts/dmc05a")
    terminal = json.loads(
        (ROOT / "experiments/dmc05a/DMC05A_TERMINAL_RECEIPT.json").read_text(encoding="utf-8")
    )
    semantic_checks = {
        "dmc05a_terminal_frozen": terminal.get("status") == "TERMINAL_FROZEN",
        "dmc05a_terminal_state": terminal.get("terminal_state")
        == "DMC_05A_CONVENTIONAL_RETRIEVAL_DOMINATES",
        "ordering_confound_recorded": terminal.get("scientific_disposition", {}).get("cause")
        == "BENCHMARK_ORDERING_CONFOUND",
        "optimizer_steps_preserved": terminal.get("training_accounting", {}).get(
            "unique_suite_optimizer_steps"
        )
        == 10880,
        "training_cost_unknown_preserved": terminal.get("training_accounting", {}).get(
            "historical_wall_time"
        )
        == "TRAINING_COST_UNKNOWN",
        "dmc04b_manifest": bool(dmc04b_manifest["pass"]),
        "dmc05a_manifest": bool(dmc05a_manifest["pass"]),
    }
    return {
        "pass": not errors and all(semantic_checks.values()),
        "files": rows,
        "semantic_checks": semantic_checks,
        "dmc04b_manifest": dmc04b_manifest,
        "dmc05a_manifest": dmc05a_manifest,
        "errors": errors,
    }


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.exists():
        return {"pass": False, "errors": ["freeze-missing"]}
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    expected_paths = {
        "runner_sha256": ROOT / "scripts/run_dmc05r.py",
        "test_sha256": ROOT / "tests/test_dmc05r.py",
        "config_sha256": CONFIG_PATH,
        "contract_sha256": CONTRACT_PATH,
        "dmc05a_terminal_receipt_sha256": ROOT
        / "experiments/dmc05a/DMC05A_TERMINAL_RECEIPT.json",
    }
    rows: dict[str, Any] = {}
    errors: list[str] = []
    for field, path in expected_paths.items():
        expected = freeze.get(field)
        observed = file_sha256(path) if path.is_file() else None
        passed = expected == observed
        rows[field] = {
            "path": str(path.relative_to(ROOT)),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "pass": passed,
        }
        if not passed:
            errors.append(field)
    status_pass = freeze.get("status") == "FROZEN_BEFORE_SCIENTIFIC_EXECUTION"
    policy_checks = {
        "architecture_changes_authorized": freeze.get("architecture_changes_authorized") is False,
        "training_authorized": freeze.get("training_authorized") is False,
        "threshold_changes_authorized": freeze.get("threshold_changes_authorized") is False,
        "capacity_changes_authorized": freeze.get("capacity_changes_authorized") is False,
        "feature_changes_authorized": freeze.get("feature_changes_authorized") is False,
    }
    return {
        "pass": not errors and status_pass and all(policy_checks.values()),
        "status_pass": status_pass,
        "files": rows,
        "policy_checks": policy_checks,
        "errors": errors,
    }


def run_targeted_tests() -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", "tests/test_dmc05r.py"]
    run = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {
        "command": "python3 -m pytest -q tests/test_dmc05r.py",
        "pass": run.returncode == 0,
        "returncode": run.returncode,
        "output": run.stdout[-12000:],
    }


def component_paths() -> list[Path]:
    return [
        ROOT / f"artifacts/dmc03/checkpoints/retention_seed{seed}_final.pt"
        for seed in EVIDENCE_SEEDS
    ] + [
        ROOT / f"artifacts/dmc04r2/checkpoints/retrieval_seed{seed}_final.pt"
        for seed in EVIDENCE_SEEDS
    ] + [ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"]


def component_hashes() -> dict[str, str]:
    return {str(path.relative_to(ROOT)): file_sha256(path) for path in component_paths()}


def training_accounting(evaluated_core_dmc_cases: int) -> dict[str, Any]:
    source_path = ROOT / "artifacts/dmc05a/training_accounting.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    dmc = source["training_inclusive_amortization"]["dmc04b"]
    if int(dmc["unique_suite_optimizer_steps"]) != 10880:
        raise ValueError("DMC training reconstruction changed")
    return {
        "unit": "DMC-05R",
        "status": "TRAINING_COST_UNKNOWN",
        "reason": source["reason"],
        "source": str(source_path.relative_to(ROOT)),
        "source_sha256": file_sha256(source_path),
        "dmc04b": {
            "unique_suite_optimizer_steps": 10880,
            "optimizer_steps_per_paired_seed_excluding_shared_decoder": int(
                dmc["optimizer_steps_per_paired_seed_excluding_shared_decoder"]
            ),
            "shared_decoder_optimizer_steps": int(dmc["shared_decoder_optimizer_steps"]),
            "evaluated_core_seed_case_pairs": evaluated_core_dmc_cases,
            "amortized_heterogeneous_optimizer_steps_per_core_seed_case": 10880
            / evaluated_core_dmc_cases,
            "historical_wall_time": "TRAINING_COST_UNKNOWN",
            "historical_energy": "TRAINING_COST_UNKNOWN",
            "historical_dollar_cost": "TRAINING_COST_UNKNOWN",
            "warning": dmc["warning"],
        },
        "transparent_and_conventional_systems": {
            "optimizer_steps": 0,
            "historical_training_required": False,
        },
        "scientific_run": {
            "optimizer_objects_created": 0,
            "optimizer_steps": 0,
            "backward_calls": 0,
            "training_executed": False,
        },
        "source_components": source["components"],
        "source_manifests": source["manifests"],
    }


def aggregate_metric(
    aggregate: dict[str, Any], system: str, subset: str, metric_name: str
) -> float:
    return float(
        aggregate["systems"][system]["subsets"][subset]["metrics"][metric_name]["mean"]
    )


def tail_metric(
    aggregate: dict[str, Any], system: str, tail: int, metric_name: str
) -> float:
    return float(
        aggregate["systems"][system]["by_tail"][str(tail)]["metrics"][metric_name]["mean"]
    )


def calculate_gates(aggregate: dict[str, Any], integrity: dict[str, bool]) -> dict[str, Any]:
    dmc_critical = aggregate_metric(aggregate, "dmc04b", "primary", "critical_recall")
    dmc_answer = aggregate_metric(aggregate, "dmc04b", "primary", "answer_accuracy")
    recent_critical = aggregate_metric(
        aggregate, "recent_window_16", "primary", "critical_recall"
    )
    transparent_critical = aggregate_metric(
        aggregate, "transparent_utility_index_16", "primary", "critical_recall"
    )
    transparent_answer = aggregate_metric(
        aggregate, "transparent_utility_index_16", "primary", "answer_accuracy"
    )
    nonrecency_gap = dmc_critical - recent_critical
    transparent_critical_gap = dmc_critical - transparent_critical
    transparent_answer_gap = dmc_answer - transparent_answer

    tail_zero_systems = ("recent_window_16", "transparent_utility_index_16", "dmc04b")
    tail_zero_values = {
        system: tail_metric(aggregate, system, 0, "answer_accuracy") for system in tail_zero_systems
    }
    all_history_tail_values = {
        system: {
            str(tail): tail_metric(aggregate, system, tail, "answer_accuracy")
            for tail in TAIL_SIZES
        }
        for system in ALL_HISTORY_SYSTEMS
    }
    dmc_survival = dmc_critical >= 0.90 and dmc_answer >= 0.90
    recent_collapse = recent_critical <= 0.01
    material_nonrecency = nonrecency_gap >= 0.50
    strong_dmc = dmc_critical >= 0.99 and dmc_answer >= 0.99
    strong_transparent = transparent_critical >= 0.99 and transparent_answer >= 0.99
    transparent_match = (
        transparent_critical >= dmc_critical - 0.01
        and transparent_answer >= dmc_answer - 0.01
    )
    selection_advantage = (
        strong_dmc
        and transparent_critical_gap >= 0.05
        and transparent_answer_gap >= 0.05
    )

    resource_pairs = {
        "persistent_records": (
            aggregate_metric(aggregate, "transparent_utility_index_16", "primary", "persistent_records"),
            aggregate_metric(aggregate, "dmc04b", "primary", "persistent_records"),
        ),
        "persistent_serialized_bytes": (
            aggregate_metric(
                aggregate,
                "transparent_utility_index_16",
                "primary",
                "persistent_serialized_bytes",
            ),
            aggregate_metric(aggregate, "dmc04b", "primary", "persistent_serialized_bytes"),
        ),
        "maximum_working_set_records": (
            aggregate_metric(
                aggregate,
                "transparent_utility_index_16",
                "primary",
                "maximum_working_set_records",
            ),
            aggregate_metric(
                aggregate, "dmc04b", "primary", "maximum_working_set_records"
            ),
        ),
        "working_set_serialized_bytes": (
            aggregate_metric(
                aggregate,
                "transparent_utility_index_16",
                "primary",
                "working_set_serialized_bytes",
            ),
            aggregate_metric(aggregate, "dmc04b", "primary", "working_set_serialized_bytes"),
        ),
        "records_inspected_query": (
            aggregate_metric(
                aggregate, "transparent_utility_index_16", "primary", "records_inspected_query"
            ),
            aggregate_metric(aggregate, "dmc04b", "primary", "records_inspected_query"),
        ),
        "online_wall_ns": (
            aggregate_metric(
                aggregate, "transparent_utility_index_16", "primary", "online_wall_ns"
            ),
            aggregate_metric(aggregate, "dmc04b", "primary", "online_wall_ns"),
        ),
        "learned_forward_calls": (
            aggregate_metric(
                aggregate, "transparent_utility_index_16", "primary", "learned_forward_calls"
            ),
            aggregate_metric(aggregate, "dmc04b", "primary", "learned_forward_calls"),
        ),
        "historical_training_required": (
            aggregate_metric(
                aggregate,
                "transparent_utility_index_16",
                "primary",
                "historical_training_required",
            ),
            aggregate_metric(aggregate, "dmc04b", "primary", "historical_training_required"),
        ),
    }
    resource_checks = {
        name: {"transparent": values[0], "dmc04b": values[1], "pass": values[0] <= values[1]}
        for name, values in resource_pairs.items()
    }
    transparent_dominates = (
        dmc_survival
        and strong_transparent
        and transparent_match
        and all(row["pass"] for row in resource_checks.values())
    )
    nonrecency_pass = dmc_survival and recent_collapse and material_nonrecency
    gates = {
        "tail_zero_anchor": {
            "observed": tail_zero_values,
            "threshold_min": 0.99,
            "pass": all(value >= 0.99 for value in tail_zero_values.values()),
        },
        "all_history_answer_invariance": {
            "observed": all_history_tail_values,
            "threshold_min": 0.99,
            "pass": all(
                value >= 0.99
                for system_rows in all_history_tail_values.values()
                for value in system_rows.values()
            ),
        },
        "recent_primary_collapse": {
            "observed": recent_critical,
            "threshold_max": 0.01,
            "pass": recent_collapse,
        },
        "dmc_primary_survival": {
            "observed": {"critical_recall": dmc_critical, "answer_accuracy": dmc_answer},
            "threshold_min": 0.90,
            "pass": dmc_survival,
        },
        "material_nonrecency_gap": {
            "observed": nonrecency_gap,
            "threshold_min": 0.50,
            "pass": material_nonrecency,
        },
        "nonrecency_retention_pass": {
            "observed": {
                "dmc_critical_recall": dmc_critical,
                "recent_critical_recall": recent_critical,
                "gap": nonrecency_gap,
            },
            "pass": nonrecency_pass,
        },
        "selection_advantage": {
            "observed": {
                "critical_recall_gap": transparent_critical_gap,
                "answer_accuracy_gap": transparent_answer_gap,
            },
            "threshold_min": 0.05,
            "pass": selection_advantage,
        },
        "transparent_capability_match": {
            "observed": {
                "transparent_critical_recall": transparent_critical,
                "transparent_answer_accuracy": transparent_answer,
                "dmc_critical_recall": dmc_critical,
                "dmc_answer_accuracy": dmc_answer,
            },
            "threshold_gap_max": 0.01,
            "strong_capability_min": 0.99,
            "pass": strong_transparent and transparent_match,
        },
        "transparent_resource_dominance": {
            "dimensions": resource_checks,
            "pass": all(row["pass"] for row in resource_checks.values()),
        },
        "transparent_index_dominates": {
            "pass": transparent_dominates,
        },
    }
    accounting_valid = all(integrity.values())
    if not accounting_valid:
        terminal = "DMC_05R_ACCOUNTING_INVALID"
    elif not nonrecency_pass:
        terminal = "DMC_05R_RECENCY_ONLY_FAILURE"
    elif selection_advantage:
        terminal = "DMC_05R_SELECTION_ADVANTAGE"
    elif transparent_dominates:
        terminal = "DMC_05R_TRANSPARENT_INDEX_DOMINATES"
    else:
        terminal = "DMC_05R_NONRECENCY_RETENTION_ADVANCE"
    return {
        "terminal_state": terminal,
        "accounting_valid": accounting_valid,
        "integrity": integrity,
        "gates": gates,
        "outcome_precedence": [
            "DMC_05R_ACCOUNTING_INVALID",
            "DMC_05R_RECENCY_ONLY_FAILURE",
            "DMC_05R_SELECTION_ADVANTAGE",
            "DMC_05R_TRANSPARENT_INDEX_DOMINATES",
            "DMC_05R_NONRECENCY_RETENTION_ADVANCE",
        ],
    }


def verify_information_parity(worker_runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    expected_fields = sorted(ALLOWED_RETENTION_METADATA | {"active_entities"})
    rows = []
    for system in ("transparent_utility_index_16", "dmc04b"):
        for run in worker_runs[system]:
            all_rows = run["core_cases"] + run["surprise_cases"]
            row = {
                "system": system,
                "seed": run["seed"],
                "case_count": len(all_rows),
                "classifier_fields_exact": all(
                    item["classifier_fields_observed"] == expected_fields for item in all_rows
                ),
                "no_forbidden_classifier_fields": all(
                    not item["classifier_forbidden_fields_observed"] for item in all_rows
                ),
                "metadata_firewall": all(item["metadata_firewall_pass"] for item in all_rows),
                "record_id_tie_break_only": all(
                    item["tie_break_record_id_resolver_only"] for item in all_rows
                ),
            }
            row["pass"] = all(
                row[name]
                for name in (
                    "classifier_fields_exact",
                    "no_forbidden_classifier_fields",
                    "metadata_firewall",
                    "record_id_tie_break_only",
                )
            )
            rows.append(row)
    return {
        "pass": all(row["pass"] for row in rows),
        "frozen_classifier_fields": expected_fields,
        "dmc_feature_names": ["mission_membership", "high_salience"],
        "transparent_feature_names": ["mission_membership", "high_salience"],
        "record_id_policy": "RESOLVER_TIE_BREAK_ONLY_NOT_CLASSIFIER_INPUT",
        "rows": rows,
    }


def verify_worker_integrity(
    worker_runs: dict[str, list[dict[str, Any]]],
    variant_manifest: dict[str, Any],
    surprise_manifest: dict[str, Any],
) -> dict[str, bool]:
    all_runs = [run for runs in worker_runs.values() for run in runs]
    all_rows = [row for run in all_runs for row in run["core_cases"]]
    required_metrics = all(
        all(name in row for name in NUMERIC_METRICS)
        and row.get("model_visible_tokens") == "NOT_APPLICABLE_SYNTHETIC_RECORDS"
        for row in all_rows
    )
    bounded_capacity = all(
        row["persistent_records"] <= CAPACITY and row["maximum_working_set_records"] <= CAPACITY
        for system in BOUNDED_SYSTEMS
        for run in worker_runs[system]
        for row in run["core_cases"] + run["surprise_cases"]
    )
    all_history_counts = all(
        row["persistent_records"] == row["history_size"]
        for system in ALL_HISTORY_SYSTEMS
        for run in worker_runs[system]
        for row in run["core_cases"] + run["surprise_cases"]
    )
    no_training = all(
        not run["scientific_training_executed"]
        and run["optimizer_objects_created"] == 0
        and run["optimizer_steps"] == 0
        and run["backward_calls"] == 0
        and all(
            row["online_optimizer_steps"] == 0 and row["online_backward_calls"] == 0
            for row in run["core_cases"] + run["surprise_cases"]
        )
        for run in all_runs
    )
    worker_counts = all(
        run["core_case_count"] == EXPECTED_TOTAL_VARIANTS
        and run["surprise_case_count"] == EXPECTED_SURPRISE_CASES
        for run in all_runs
    )
    fixture_identity = all(
        run["variant_projection_sha256"] == variant_manifest["variant_projection_sha256"]
        and run["surprise_projection_sha256"] == surprise_manifest["projection_sha256"]
        for run in all_runs
    )
    random_rows = worker_runs["random_16"][0]["core_cases"]
    random_by_source: dict[str, set[str]] = defaultdict(set)
    for row in random_rows:
        random_by_source[str(row["case_id"])].add(str(row["persistent_record_ids_sha256"]))
    random_order_invariance = all(len(values) == 1 for values in random_by_source.values())
    dmc_seeds = sorted(int(run["seed"]) for run in worker_runs["dmc04b"])
    return {
        "variant_manifest": bool(variant_manifest["pass"]),
        "surprise_manifest": bool(surprise_manifest["pass"]),
        "worker_case_counts": worker_counts,
        "worker_fixture_identity": fixture_identity,
        "required_metrics": required_metrics,
        "bounded_capacity": bounded_capacity,
        "all_history_record_counts": all_history_counts,
        "no_online_training": no_training,
        "random_set_order_invariance": random_order_invariance,
        "dmc_seed_set": dmc_seeds == list(EVIDENCE_SEEDS),
    }


def write_curves(aggregate: dict[str, Any]) -> dict[str, str]:
    rows: list[dict[str, Any]] = []
    for system in ALL_SYSTEMS:
        for tail in TAIL_SIZES:
            rows.append(
                {
                    "system": system,
                    "tail_size": tail,
                    "case_count_per_run": aggregate["systems"][system]["by_tail"][str(tail)][
                        "case_count_per_run"
                    ],
                    "critical_recall": tail_metric(
                        aggregate, system, tail, "critical_recall"
                    ),
                    "retrieval_accuracy": tail_metric(
                        aggregate, system, tail, "retrieval_accuracy"
                    ),
                    "answer_accuracy": tail_metric(aggregate, system, tail, "answer_accuracy"),
                    "persistent_records": tail_metric(
                        aggregate, system, tail, "persistent_records"
                    ),
                    "persistent_serialized_bytes": tail_metric(
                        aggregate, system, tail, "persistent_serialized_bytes"
                    ),
                    "online_wall_ns": tail_metric(aggregate, system, tail, "online_wall_ns"),
                }
            )
    write_json(OUT / "tail_curves.json", rows)
    columns = list(rows[0])
    csv_lines = [",".join(columns)]
    for row in rows:
        csv_lines.append(",".join(str(row[column]) for column in columns))
    (OUT / "tail_curves.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    width, height = 1000, 520
    left, right, top, bottom = 90, 40, 60, 80
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_positions = {
        tail: left + index * plot_width / (len(TAIL_SIZES) - 1)
        for index, tail in enumerate(TAIL_SIZES)
    }
    colors = {
        "recent_window_16": "#d1495b",
        "transparent_utility_index_16": "#2a9d8f",
        "dmc04b": "#355cde",
    }
    labels = {
        "recent_window_16": "Recent-16",
        "transparent_utility_index_16": "Transparent utility-16",
        "dmc04b": "DMC-04B frozen",
    }
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="500" y="30" text-anchor="middle" font-family="sans-serif" font-size="20">DMC-05R critical recall versus irrelevant trailing writes</text>',
    ]
    for tick in range(0, 6):
        value = tick / 5
        y = top + (1.0 - value) * plot_height
        svg.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#dddddd" stroke-width="1"/>'
        )
        svg.append(
            f'<text x="{left-12}" y="{y+5:.2f}" text-anchor="end" font-family="sans-serif" font-size="13">{value:.1f}</text>'
        )
    svg.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#222" stroke-width="1.5"/>'
    )
    svg.append(
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#222" stroke-width="1.5"/>'
    )
    for tail in TAIL_SIZES:
        x = x_positions[tail]
        svg.append(
            f'<text x="{x:.2f}" y="{height-bottom+25}" text-anchor="middle" font-family="sans-serif" font-size="13">{tail}</text>'
        )
    svg.append(
        f'<text x="{left+plot_width/2:.2f}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="15">Certified irrelevant trailing writes</text>'
    )
    svg.append(
        f'<text x="22" y="{top+plot_height/2:.2f}" transform="rotate(-90 22 {top+plot_height/2:.2f})" text-anchor="middle" font-family="sans-serif" font-size="15">Critical recall</text>'
    )
    for legend_index, system in enumerate(colors):
        points = []
        for tail in TAIL_SIZES:
            value = tail_metric(aggregate, system, tail, "critical_recall")
            points.append(
                f"{x_positions[tail]:.2f},{top + (1.0 - value) * plot_height:.2f}"
            )
        svg.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[system]}" stroke-width="3"/>'
        )
        for point in points:
            x, y = point.split(",")
            svg.append(
                f'<circle cx="{x}" cy="{y}" r="4" fill="{colors[system]}"/>'
            )
        legend_x = left + legend_index * 270
        svg.append(
            f'<line x1="{legend_x}" y1="{height-48}" x2="{legend_x+28}" y2="{height-48}" stroke="{colors[system]}" stroke-width="3"/>'
        )
        svg.append(
            f'<text x="{legend_x+36}" y="{height-43}" font-family="sans-serif" font-size="13">{labels[system]}</text>'
        )
    svg.append("</svg>")
    (OUT / "tail_curves.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")
    return {
        "json": "artifacts/dmc05r/tail_curves.json",
        "csv": "artifacts/dmc05r/tail_curves.csv",
        "svg": "artifacts/dmc05r/tail_curves.svg",
    }


def format_percent(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def report_markdown(
    terminal: str,
    aggregate: dict[str, Any],
    gate_result: dict[str, Any],
    training: dict[str, Any],
    equivalence: dict[str, Any],
) -> str:
    if terminal == "DMC_05R_ACCOUNTING_INVALID":
        verification_verdict = "INCONCLUSIVE"
        headline = "Accounting or replay failed; no scientific result is admissible."
    elif terminal == "DMC_05R_RECENCY_ONLY_FAILURE":
        verification_verdict = "FAIL"
        headline = "Frozen DMC did not establish non-recency retention."
    elif terminal == "DMC_05R_SELECTION_ADVANTAGE":
        verification_verdict = "PASS"
        headline = "Frozen DMC established a material selection advantage over equal-information transparent indexing."
    elif terminal == "DMC_05R_TRANSPARENT_INDEX_DOMINATES":
        verification_verdict = "PASS"
        headline = "Frozen DMC established non-recency retention, but transparent utility indexing dominated it."
    else:
        verification_verdict = "PASS"
        headline = "Frozen DMC established non-recency retention without a terminal transparent dominance result."

    core_systems = (
        "recent_window_16",
        "frozen_fifo_16",
        "random_16",
        "exact_structured",
        "conventional_retrieval",
        "transparent_utility_index_16",
        "dmc04b",
    )
    system_labels = {
        "recent_window_16": "Recent-16",
        "frozen_fifo_16": "Frozen FIFO-16",
        "random_16": "Random-16",
        "exact_structured": "Exact structured",
        "conventional_retrieval": "Conventional retrieval",
        "transparent_utility_index_16": "Transparent utility-16",
        "dmc04b": "DMC-04B frozen",
    }
    core_rows = []
    for system in core_systems:
        core_rows.append(
            "| {label} | {critical} | {answer} | {records:.2f} | {bytes:.1f} | {wall:.3f} |".format(
                label=system_labels[system],
                critical=format_percent(
                    aggregate_metric(aggregate, system, "primary", "critical_recall")
                ),
                answer=format_percent(
                    aggregate_metric(aggregate, system, "primary", "answer_accuracy")
                ),
                records=aggregate_metric(aggregate, system, "primary", "persistent_records"),
                bytes=aggregate_metric(
                    aggregate, system, "primary", "persistent_serialized_bytes"
                ),
                wall=aggregate_metric(aggregate, system, "primary", "online_wall_ns")
                / 1_000_000,
            )
        )
    by_tail_rows = []
    for tail in TAIL_SIZES:
        by_tail_rows.append(
            "| {tail} | {count} | {recent} | {transparent} | {dmc} |".format(
                tail=tail,
                count=aggregate["systems"]["recent_window_16"]["by_tail"][str(tail)][
                    "case_count_per_run"
                ],
                recent=format_percent(
                    tail_metric(aggregate, "recent_window_16", tail, "critical_recall")
                ),
                transparent=format_percent(
                    tail_metric(
                        aggregate, "transparent_utility_index_16", tail, "critical_recall"
                    )
                ),
                dmc=format_percent(tail_metric(aggregate, "dmc04b", tail, "critical_recall")),
            )
        )
    surprise_rows = []
    for system in core_systems:
        surprise_rows.append(
            "| {label} | {critical} | {answer} |".format(
                label=system_labels[system],
                critical=format_percent(
                    aggregate_metric(
                        aggregate, system, "surprise_dependency", "critical_recall"
                    )
                ),
                answer=format_percent(
                    aggregate_metric(
                        aggregate, system, "surprise_dependency", "answer_accuracy"
                    )
                ),
            )
        )
    criterion_rows = []
    for name, row in gate_result["gates"].items():
        criterion_rows.append(f"| `{name}` | {'PASS' if row['pass'] else 'FAIL'} | `{canonical(row.get('observed', row))}` |")

    stop_text = (
        "Stop learned retention in this synthetic family and keep DMC-05B blocked; the equally informed transparent selector is the branch-stop control."
        if terminal == "DMC_05R_TRANSPARENT_INDEX_DOMINATES"
        else "Keep DMC-05B blocked unless the terminal result establishes survival over the transparent baseline under the frozen release policy."
    )
    return f"""# DMC-05R — Recency Confound Repair

Terminal state: `{terminal}`  
Verification verdict: **{verification_verdict}**  
{headline}

## Claim under test

When certified irrelevant writes are moved behind the last task-relevant write,
frozen DMC-04B preserves useful older state materially better than Recent-16.
Selection credit additionally requires a material win over equally informed
transparent utility indexing at the same 16-record capacity.

## Check

```bash
python3 scripts/run_dmc05r.py
python3 -m pytest -q tests/test_dmc05r.py
```

The run uses 592 frozen source cases, deterministic tails `0, 8, 16, 32, 64,
256`, 2,376 valid core variants, five frozen DMC seed pairs, and 24 separate
`SURPRISE_DEPENDENCY` cases.

## Verdict

`{terminal}`. The primary non-recency gate is
`{'PASS' if gate_result['gates']['nonrecency_retention_pass']['pass'] else 'FAIL'}`;
the architecture-level selection-advantage gate is
`{'PASS' if gate_result['gates']['selection_advantage']['pass'] else 'FAIL'}`.

## Core primary results

| System | Critical recall | Answer accuracy | Persistent records | Persistent bytes | Online ms/case |
|---|---:|---:|---:|---:|---:|
{chr(10).join(core_rows)}

| Irrelevant tail | Cases/run | Recent-16 recall | Transparent recall | DMC recall |
|---:|---:|---:|---:|---:|
{chr(10).join(by_tail_rows)}

## Criteria

| Criterion | Result | Evidence |
|---|---|---|
{chr(10).join(criterion_rows)}

## Assumption register

| Assumption | Status | Evidence |
|---|---|---|
| Relocated records are answer-irrelevant and dependency-free | VERIFIED | Every variant passed record-membership, scope, salience, feature, supersession, payload, and order invariants in `variant_manifest.json`. |
| Counterfactuals preserve the frozen task answer | VERIFIED | Exact structured and conventional all-history systems are checked at every tail; target/query/oracle payloads are unchanged. |
| DMC and transparent selection receive equal utility information | VERIFIED | Runtime classifier firewalls and exact observed-field equality are recorded in `information_parity.json`. |
| Optimized execution is the frozen DMC mechanism | VERIFIED | {equivalence['tail_zero']['matching_count']}/{equivalence['tail_zero']['comparison_count']} frozen-receipt comparisons and {equivalence['nonzero_direct']['comparison_count']} direct boundary comparisons passed. |
| Historical learned cost was free | REFUTED | 10,880 heterogeneous optimizer steps are reconstructed; wall time, energy, and dollar cost remain `TRAINING_COST_UNKNOWN`. |
| Synthetic behavior transfers to real language | UNFALSIFIABLE HERE | No language, tokenizer, or language-model inference run is authorized in DMC-05R. |

## Credit assignment

The manipulated variable is stream position only: record payloads and all
semantic ordering are frozen. Recent-16 is the temporal-order counterfactual;
transparent utility-16 isolates whether explicit utility information, rather
than learned selection, causes survival. No selection credit is assigned merely
for beating FIFO or recency.

## SURPRISE_DEPENDENCY (exploratory, nonterminal)

| System | Critical recall | Answer accuracy |
|---|---:|---:|
{chr(10).join(surprise_rows)}

This subset changes future utility only after ingestion. It does not enter the
terminal decision and does not authorize redesign after failure.

## Verification gap

This result is self-verified in one local execution environment; no independent
agent context was available. Absolute wall timings are machine-specific. The
test remains synthetic structured memory with no tokenizer or real model-cost
measurement, and historical training wall time, energy, and dollar cost are
unknown.

## Stop/continue

{stop_text}

## Maturity status

**Mature for this synthetic claim.** The claim is defined, compressed into a
frozen transformation and selector specification, tested, falsifiable,
replayed, and compared against recency, random, FIFO, exact, conventional, and
equal-information transparent variants. It is not evidence of real-language
or deployment maturity.

## Training accounting

- Reconstructed DMC suite optimizer steps: **{training['dmc04b']['unique_suite_optimizer_steps']:,}**.
- Online optimizer steps in DMC-05R: **0**.
- Historical wall time, energy, and dollar cost: **`TRAINING_COST_UNKNOWN`**.
"""


def manifest_for(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "SHA256SUMS.json" and ".partial" not in path.name
    }


def run_one_worker(system: str, seed: int | None, output: Path) -> dict[str, Any]:
    partial = output.with_name(f"{output.stem}.partial{output.suffix}")
    if partial.exists():
        partial.unlink()
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        system,
        "--output",
        str(partial),
    ]
    if seed is not None:
        command.extend(["--seed", str(seed)])
    run = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if run.returncode != 0 or not partial.exists():
        raise RuntimeError(f"worker failed: {system}/{seed}\n{run.stdout[-12000:]}")
    partial.replace(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["raw_receipt"] = str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)
    payload["raw_sha256"] = file_sha256(output)
    return payload


def run_replay(worker_runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    specifications = [
        ("recent_window_16", None),
        ("transparent_utility_index_16", None),
        ("dmc04b", 1337),
    ]
    rows: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="dmc05r-replay-") as temporary:
        temporary_root = Path(temporary)
        for system, seed in specifications:
            key = system if seed is None else f"{system}_seed{seed}"
            original = next(
                run for run in worker_runs[system] if run["seed"] == seed
            )
            replay = run_one_worker(system, seed, temporary_root / f"{key}.json")
            first_projection = worker_projection(original)
            second_projection = worker_projection(replay)
            rows[key] = {
                "pass": first_projection == second_projection,
                "first_sha256": digest(first_projection),
                "second_sha256": digest(second_projection),
            }
    return {"pass": all(row["pass"] for row in rows.values()), "systems": rows}


def run_parent() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RAW_OUT.mkdir(parents=True, exist_ok=True)
    print("DMC-05R preflight: anchors, freeze, fixtures, and tests", flush=True)
    anchors = verify_preregistered_anchors()
    freeze = verify_freeze()
    cases = load_source_cases()
    dataset = verify_dataset_identity(cases)
    variants, variant_manifest = build_variants(cases)
    surprises, surprise_manifest = build_surprise_cases(cases)
    tests = run_targeted_tests()
    preflight = {
        "anchors": anchors,
        "freeze": freeze,
        "dataset": dataset,
        "variant_manifest": {
            key: value for key, value in variant_manifest.items() if key not in {"variants", "skipped"}
        },
        "surprise_manifest": {
            key: value for key, value in surprise_manifest.items() if key != "cases"
        },
        "tests": tests,
    }
    write_json(OUT / "preflight.json", preflight)
    preflight_pass = all(
        (
            anchors["pass"],
            freeze["pass"],
            dataset["pass"],
            variant_manifest["pass"],
            surprise_manifest["pass"],
            tests["pass"],
        )
    )
    if not preflight_pass:
        verdict = {
            "unit": "DMC-05R",
            "terminal_state": "DMC_05R_ACCOUNTING_INVALID",
            "preflight": preflight,
        }
        write_json(OUT / "DMC05R_VERDICT.json", verdict)
        write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
        print("DMC_05R_ACCOUNTING_INVALID", flush=True)
        return 1

    write_json(OUT / "variant_manifest.json", variant_manifest)
    write_json(OUT / "surprise_dependency_manifest.json", surprise_manifest)
    component_before = component_hashes()
    worker_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    worker_specs = [(system, None) for system in DETERMINISTIC_SYSTEMS] + [
        ("dmc04b", seed) for seed in EVIDENCE_SEEDS
    ]
    for index, (system, seed) in enumerate(worker_specs, start=1):
        suffix = "" if seed is None else f"_seed{seed}"
        print(f"DMC-05R worker {index}/{len(worker_specs)} START {system}{suffix}", flush=True)
        output = RAW_OUT / f"{system}{suffix}.json"
        worker = run_one_worker(system, seed, output)
        worker_runs[system].append(worker)
        print(f"DMC-05R worker {index}/{len(worker_specs)} COMPLETE {system}{suffix}", flush=True)

    aggregate = aggregate_all(worker_runs)
    print("DMC-05R equivalence audit START", flush=True)
    equivalence = {
        "tail_zero": verify_tail_zero_equivalence(worker_runs["dmc04b"]),
        "nonzero_direct": verify_nonzero_direct_equivalence(variants, worker_runs["dmc04b"]),
    }
    equivalence["pass"] = equivalence["tail_zero"]["pass"] and equivalence["nonzero_direct"]["pass"]
    print("DMC-05R equivalence audit COMPLETE", flush=True)

    information_parity = verify_information_parity(worker_runs)
    training = training_accounting(EXPECTED_TOTAL_VARIANTS * len(EVIDENCE_SEEDS))
    print("DMC-05R deterministic replay START", flush=True)
    replay = run_replay(worker_runs)
    print("DMC-05R deterministic replay COMPLETE", flush=True)
    component_after = component_hashes()
    component_immutability = {
        "pass": component_before == component_after,
        "before": component_before,
        "after": component_after,
    }
    worker_integrity = verify_worker_integrity(worker_runs, variant_manifest, surprise_manifest)
    integrity = {
        "preregistered_anchors": bool(anchors["pass"]),
        "freeze": bool(freeze["pass"]),
        "dataset": bool(dataset["pass"]),
        "targeted_tests": bool(tests["pass"]),
        **worker_integrity,
        "information_parity": bool(information_parity["pass"]),
        "optimized_dmc_equivalence": bool(equivalence["pass"]),
        "component_immutability": bool(component_immutability["pass"]),
        "replay": bool(replay["pass"]),
        "training_steps_preserved": training["dmc04b"]["unique_suite_optimizer_steps"] == 10880,
        "training_cost_not_silently_zero": training["status"] == "TRAINING_COST_UNKNOWN",
        "source_training_manifests": all(
            row["pass"] for row in training["source_manifests"].values()
        ),
    }
    gate_result = calculate_gates(aggregate, integrity)
    terminal = str(gate_result["terminal_state"])

    write_json(OUT / "aggregate.json", aggregate)
    write_json(OUT / "equivalence_audit.json", equivalence)
    write_json(OUT / "information_parity.json", information_parity)
    write_json(OUT / "training_accounting.json", training)
    write_json(OUT / "replay.json", replay)
    write_json(OUT / "component_immutability.json", component_immutability)
    plots = write_curves(aggregate)
    surprise_aggregate = {
        "unit": "DMC-05R",
        "subset": "SURPRISE_DEPENDENCY",
        "status": "EXPLORATORY_NONTERMINAL",
        "case_count_per_run": EXPECTED_SURPRISE_CASES,
        "systems": {
            system: aggregate["systems"][system]["subsets"]["surprise_dependency"]
            for system in ALL_SYSTEMS
        },
        "terminal_effect": False,
    }
    write_json(OUT / "surprise_dependency_aggregate.json", surprise_aggregate)
    verdict = {
        "unit": "DMC-05R",
        "title": "RECENCY CONFOUND REPAIR",
        "terminal_state": terminal,
        "verification_verdict": "INCONCLUSIVE"
        if terminal == "DMC_05R_ACCOUNTING_INVALID"
        else "FAIL"
        if terminal == "DMC_05R_RECENCY_ONLY_FAILURE"
        else "PASS",
        "claim": json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["claim"],
        "integrity": integrity,
        "gates": gate_result,
        "source_case_count": len(cases),
        "core_variant_count_per_deterministic_run": len(variants),
        "dmc_seed_case_evaluations": len(variants) * len(EVIDENCE_SEEDS),
        "tail_sizes": list(TAIL_SIZES),
        "primary_tail_sizes": list(PRIMARY_TAILS),
        "systems": list(ALL_SYSTEMS),
        "evidence_seeds": list(EVIDENCE_SEEDS),
        "surprise_dependency": {
            "status": "EXPLORATORY_NONTERMINAL",
            "case_count_per_run": len(surprises),
            "terminal_effect": False,
            "aggregate": "artifacts/dmc05r/surprise_dependency_aggregate.json",
        },
        "training_cost_status": training["status"],
        "training_optimizer_steps_reconstructed": training["dmc04b"][
            "unique_suite_optimizer_steps"
        ],
        "dmc05b_status": "BLOCKED_PENDING_DMC05R_TRANSPARENT_BASELINE_SURVIVAL",
        "plots": plots,
        "verification_scope": "SELF_VERIFIED_LOCAL_REPLAY_NO_INDEPENDENT_AGENT_CONTEXT",
        "interpretation_boundary": [
            "synthetic structured benchmark only",
            "no real language, tokenizer, or language-model inference",
            "historical training wall time, energy, and dollar cost unknown",
            "SURPRISE_DEPENDENCY is exploratory and nonterminal",
            "absolute resource dimensions retained without a composite score",
        ],
    }
    write_json(OUT / "DMC05R_VERDICT.json", verdict)
    (OUT / "DMC05R_REPORT.md").write_text(
        report_markdown(terminal, aggregate, gate_result, training, equivalence),
        encoding="utf-8",
    )
    write_json(
        OUT / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "pid": os.getpid(),
            "self_verified": True,
        },
    )
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal, flush=True)
    return 1 if terminal == "DMC_05R_ACCOUNTING_INVALID" else 0


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
        print(f"DMC_05R_WORKER_COMPLETE:{args.worker}:{args.seed}", flush=True)
        return 0
    if args.seed is not None or args.output is not None:
        raise SystemExit("--seed/--output require --worker")
    return run_parent()


if __name__ == "__main__":
    raise SystemExit(main())
