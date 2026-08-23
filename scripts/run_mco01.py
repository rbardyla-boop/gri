#!/usr/bin/env python3
from __future__ import annotations

"""MCO-01 deterministic store-all, bounded-attention benchmark and replay harness."""

import argparse
import hashlib
import heapq
import json
import platform
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT / "experiments/mco01"
CONFIG_PATH = EXPERIMENT_ROOT / "MCO01_CONFIG.json"
CONTRACT_PATH = EXPERIMENT_ROOT / "MCO01_CONTRACT.md"
FREEZE_PATH = EXPERIMENT_ROOT / "MCO01_FREEZE.json"
TERMINAL_RECEIPT_PATH = (
    ROOT / "experiments/dmc05r/DMC_BRANCH_TERMINAL_RECEIPT.json"
)
OUT = ROOT / "artifacts/mco01"
DATASET_ROOT = OUT / "dataset"
DATASET_MANIFEST_PATH = DATASET_ROOT / "dataset_manifest.json"
RAW_ROOT = OUT / "raw"

HISTORY_SIZES = (100, 1_000, 10_000, 100_000)
SEEDS = (2601, 2602, 2603, 2604, 2605)
QUERIES_PER_HISTORY = 8
HOPS_BY_QUERY = (2, 2, 3, 3, 4, 4, 5, 5)
EXPECTED_HISTORIES = len(HISTORY_SIZES) * len(SEEDS)
EXPECTED_QUERIES = EXPECTED_HISTORIES * QUERIES_PER_HISTORY
EXPECTED_RECORDS = sum(HISTORY_SIZES) * len(SEEDS)
CAPACITY = 16
SOURCE_PRIORITY = {"AUTHORITY": 3, "CURATED": 2, "UNVERIFIED": 1}
RELATION_PRECEDENCE = ("renamed_to", "depends_on", "failure_threshold")
SYSTEMS = (
    "full_history_oracle",
    "recent_16",
    "exact_structured_lookup",
    "conventional_one_shot_retrieval",
    "iterative_need_retrieval",
)
BOUNDED_SYSTEMS = (
    "recent_16",
    "exact_structured_lookup",
    "conventional_one_shot_retrieval",
    "iterative_need_retrieval",
)
QUALITY_METRICS = (
    "answer_accuracy",
    "critical_recall",
    "dependency_chain_accuracy",
    "temporal_update_accuracy",
    "provenance_accuracy",
)
RECORD_FIELDS = frozenset(
    {
        "record_id",
        "position",
        "event_time",
        "subject",
        "relation",
        "object",
        "source",
        "operation",
        "supersedes",
    }
)
FORBIDDEN_RECORD_FIELDS = frozenset(
    {
        "answer",
        "answer_label",
        "chain_id",
        "critical",
        "expected",
        "importance",
        "query_id",
        "relevance",
        "target",
        "utility",
        "utility_label",
    }
)
RUNTIME_FIELDS = frozenset({"wall_time_seconds"})

FAMILY_SETS = (
    ("delayed_dependency", "distractor_hard"),
    ("delayed_dependency", "correction"),
    ("delayed_dependency", "rename"),
    ("delayed_dependency", "supersession"),
    ("delayed_dependency", "contradiction"),
    ("delayed_dependency", "rename", "correction"),
    ("delayed_dependency", "rename", "supersession", "contradiction"),
    ("delayed_dependency", "distractor_hard", "correction", "contradiction"),
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_int(*parts: Any) -> int:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def opaque(prefix: str, *parts: Any) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:16]}"


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = canonical(value) + "\n"
    else:
        text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def add_record(
    records: list[dict[str, Any]],
    history_id: str,
    *,
    subject: str,
    relation: str,
    object_value: str | int,
    source: str = "CURATED",
    operation: str = "assert",
    supersedes: str | None = None,
) -> dict[str, Any]:
    serial = len(records)
    row = {
        "record_id": opaque("r", history_id, serial),
        "subject": subject,
        "relation": relation,
        "object": object_value,
        "source": source,
        "operation": operation,
        "supersedes": supersedes,
    }
    records.append(row)
    return row


def add_wrong_terminal(
    records: list[dict[str, Any]],
    history_id: str,
    wrong_entity: str,
    threshold: int,
) -> None:
    add_record(
        records,
        history_id,
        subject=wrong_entity,
        relation="failure_threshold",
        object_value=threshold,
        source="AUTHORITY",
        operation="assert",
    )


def semantic_history(
    seed: int, history_size: int
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[tuple[str, str]],
]:
    """Build semantic records before their constrained random placement."""

    history_id = f"mco01_n{history_size}_s{seed}"
    records: list[dict[str, Any]] = []
    constraints: list[tuple[str, str]] = []
    blueprints: list[dict[str, Any]] = []

    for query_index, hops in enumerate(HOPS_BY_QUERY):
        families = FAMILY_SETS[query_index]
        transitions = hops - 1
        root = opaque("e", history_id, "query", query_index, "root")
        current = root
        path_ids: list[str] = []
        updated_winners: list[str] = []
        rename_index = min(1, transitions - 1) if "rename" in families else -1
        update_index = max(0, transitions - 1)
        threshold = -35 + (stable_int(seed, history_size, query_index, "threshold") % 31)

        for transition_index in range(transitions):
            relation = (
                "renamed_to" if transition_index == rename_index else "depends_on"
            )
            next_entity = opaque(
                "e", history_id, "query", query_index, "node", transition_index + 1
            )
            is_update_key = transition_index == update_index
            correction = is_update_key and "correction" in families
            supersession = is_update_key and "supersession" in families
            contradiction = is_update_key and "contradiction" in families
            old_row: dict[str, Any] | None = None

            if correction or supersession:
                wrong_entity = opaque(
                    "e",
                    history_id,
                    "query",
                    query_index,
                    "stale",
                    transition_index,
                )
                old_row = add_record(
                    records,
                    history_id,
                    subject=current,
                    relation=relation,
                    object_value=wrong_entity,
                    source="CURATED",
                    operation="assert",
                )
                add_wrong_terminal(
                    records,
                    history_id,
                    wrong_entity,
                    threshold + (9 if query_index % 2 == 0 else -9),
                )

            winner = add_record(
                records,
                history_id,
                subject=current,
                relation=relation,
                object_value=next_entity,
                source="AUTHORITY" if contradiction else "CURATED",
                operation=(
                    "correct"
                    if correction
                    else "supersede"
                    if supersession
                    else "assert"
                ),
                supersedes=old_row["record_id"] if old_row else None,
            )
            if old_row:
                constraints.append((old_row["record_id"], winner["record_id"]))

            if contradiction:
                wrong_entity = opaque(
                    "e",
                    history_id,
                    "query",
                    query_index,
                    "contradiction",
                    transition_index,
                )
                add_record(
                    records,
                    history_id,
                    subject=current,
                    relation=relation,
                    object_value=wrong_entity,
                    source="UNVERIFIED",
                    operation="observe",
                )
                add_wrong_terminal(
                    records,
                    history_id,
                    wrong_entity,
                    threshold + (13 if query_index % 2 == 0 else -13),
                )

            path_ids.append(winner["record_id"])
            if correction or supersession or contradiction:
                updated_winners.append(winner["record_id"])
            current = next_entity

        terminal = add_record(
            records,
            history_id,
            subject=current,
            relation="failure_threshold",
            object_value=threshold,
            source="AUTHORITY",
            operation="assert",
        )
        path_ids.append(terminal["record_id"])
        deployment_temperature = threshold - 5 if query_index % 2 == 0 else threshold + 5
        blueprints.append(
            {
                "query_id": opaque("q", history_id, query_index),
                "root_entity": root,
                "deployment_temperature": deployment_temperature,
                "dependency_hops": hops,
                "families": list(families),
                "planned_terminal_entity": current,
                "planned_threshold": threshold,
                "planned_path_record_ids": path_ids,
                "planned_updated_record_ids": updated_winners,
            }
        )

    if len(records) > history_size:
        raise ValueError(
            f"semantic records ({len(records)}) exceed history size ({history_size})"
        )

    distractor_index = 0
    while len(records) < history_size:
        subject = opaque("d", history_id, "subject", distractor_index)
        relation_selector = stable_int(history_id, distractor_index, "relation") % 4
        if relation_selector == 0:
            relation = "failure_threshold"
            object_value: str | int = -60 + (
                stable_int(history_id, distractor_index, "value") % 91
            )
        else:
            relation = "renamed_to" if relation_selector == 1 else "depends_on"
            object_value = opaque("d", history_id, "object", distractor_index)
        source = ("AUTHORITY", "CURATED", "UNVERIFIED")[
            stable_int(history_id, distractor_index, "source") % 3
        ]
        add_record(
            records,
            history_id,
            subject=subject,
            relation=relation,
            object_value=object_value,
            source=source,
            operation="assert",
        )
        distractor_index += 1

    return records, blueprints, constraints


def constrained_order(
    records: Sequence[dict[str, Any]],
    constraints: Sequence[tuple[str, str]],
    *,
    seed: int,
    history_size: int,
    attempt: int,
) -> list[dict[str, Any]]:
    by_id = {str(row["record_id"]): row for row in records}
    indegree = {record_id: 0 for record_id in by_id}
    successors: dict[str, list[str]] = defaultdict(list)
    for before, after in constraints:
        successors[before].append(after)
        indegree[after] += 1

    heap: list[tuple[int, str]] = []
    for record_id, degree in indegree.items():
        if degree == 0:
            heapq.heappush(
                heap,
                (
                    stable_int(seed, history_size, attempt, record_id, "placement"),
                    record_id,
                ),
            )

    ordered_ids: list[str] = []
    while heap:
        _, record_id = heapq.heappop(heap)
        ordered_ids.append(record_id)
        for successor in successors.get(record_id, []):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heapq.heappush(
                    heap,
                    (
                        stable_int(
                            seed,
                            history_size,
                            attempt,
                            successor,
                            "placement",
                        ),
                        successor,
                    ),
                )
    if len(ordered_ids) != len(records):
        raise ValueError("placement constraints contain a cycle")

    ordered: list[dict[str, Any]] = []
    for position, record_id in enumerate(ordered_ids):
        row = dict(by_id[record_id])
        row["position"] = position
        row["event_time"] = position
        ordered.append(row)
    return ordered


def index_records(
    records: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        index[(str(row["subject"]), str(row["relation"]))].append(row)
    return dict(index)


def winning_record(candidates: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    superseded = {
        str(row["supersedes"])
        for row in candidates
        if row.get("supersedes") is not None
    }
    active = [row for row in candidates if str(row["record_id"]) not in superseded]
    if not active:
        return None
    return max(
        active,
        key=lambda row: (
            SOURCE_PRIORITY[str(row["source"])],
            int(row["event_time"]),
            str(row["record_id"]),
        ),
    )


def trace_index(
    index: dict[tuple[str, str], list[dict[str, Any]]],
    root_entity: str,
    deployment_temperature: int,
) -> dict[str, Any]:
    current = root_entity
    path: list[str] = []
    visited: set[str] = set()
    for _ in range(32):
        if current in visited:
            break
        visited.add(current)
        advanced = False
        for relation in ("renamed_to", "depends_on"):
            winner = winning_record(index.get((current, relation), []))
            if winner is not None:
                path.append(str(winner["record_id"]))
                current = str(winner["object"])
                advanced = True
                break
        if advanced:
            continue
        terminal = winning_record(index.get((current, "failure_threshold"), []))
        if terminal is not None:
            threshold = int(terminal["object"])
            path.append(str(terminal["record_id"]))
            return {
                "complete": True,
                "terminal_entity": current,
                "failure_threshold": threshold,
                "requires_inspection": int(deployment_temperature) < threshold,
                "path_record_ids": path,
            }
        break
    return {
        "complete": False,
        "terminal_entity": None,
        "failure_threshold": None,
        "requires_inspection": None,
        "path_record_ids": path,
    }


def build_history(seed: int, history_size: int) -> dict[str, Any]:
    records, blueprints, constraints = semantic_history(seed, history_size)
    history_id = f"mco01_n{history_size}_s{seed}"
    planned_ids = {
        str(blueprint["query_id"]): list(blueprint["planned_path_record_ids"])
        for blueprint in blueprints
    }

    for attempt in range(10_000):
        ordered = constrained_order(
            records,
            constraints,
            seed=seed,
            history_size=history_size,
            attempt=attempt,
        )
        positions = {str(row["record_id"]): int(row["position"]) for row in ordered}
        if all(
            max(positions[record_id] for record_id in path)
            - min(positions[record_id] for record_id in path)
            > CAPACITY
            for path in planned_ids.values()
        ):
            break
    else:
        raise RuntimeError(f"could not place {history_id} without a 16-record leak")

    index = index_records(ordered)
    queries: list[dict[str, Any]] = []
    for blueprint in blueprints:
        reconstructed = trace_index(
            index,
            str(blueprint["root_entity"]),
            int(blueprint["deployment_temperature"]),
        )
        planned_path = list(blueprint["planned_path_record_ids"])
        if not reconstructed["complete"] or reconstructed["path_record_ids"] != planned_path:
            raise RuntimeError(
                f"semantic reconstruction mismatch for {blueprint['query_id']}"
            )
        if reconstructed["terminal_entity"] != blueprint["planned_terminal_entity"]:
            raise RuntimeError(f"terminal mismatch for {blueprint['query_id']}")
        if reconstructed["failure_threshold"] != blueprint["planned_threshold"]:
            raise RuntimeError(f"threshold mismatch for {blueprint['query_id']}")
        path_positions = [positions[record_id] for record_id in planned_path]
        queries.append(
            {
                "query_id": blueprint["query_id"],
                "root_entity": blueprint["root_entity"],
                "deployment_temperature": blueprint["deployment_temperature"],
                "dependency_hops": blueprint["dependency_hops"],
                "families": blueprint["families"],
                "expected": {
                    "terminal_entity": reconstructed["terminal_entity"],
                    "failure_threshold": reconstructed["failure_threshold"],
                    "requires_inspection": reconstructed["requires_inspection"],
                    "path_record_ids": planned_path,
                    "updated_record_ids": list(
                        blueprint["planned_updated_record_ids"]
                    ),
                    "critical_record_positions": path_positions,
                },
            }
        )

    return {
        "schema_version": 1,
        "experiment_id": "MCO-01",
        "history_id": history_id,
        "seed": seed,
        "history_size": history_size,
        "source_priority": SOURCE_PRIORITY,
        "query_time": history_size,
        "placement_attempt": attempt,
        "records": ordered,
        "queries": queries,
    }


def verify_history(history: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    records = list(history.get("records", []))
    history_size = int(history.get("history_size", -1))
    if len(records) != history_size:
        errors.append("record-count")
    ids = [str(row.get("record_id")) for row in records]
    if len(set(ids)) != len(ids):
        errors.append("duplicate-record-id")
    by_id = {str(row.get("record_id")): row for row in records}
    expected_positions = list(range(len(records)))
    observed_positions = [int(row.get("position", -1)) for row in records]
    if observed_positions != expected_positions:
        errors.append("position-sequence")

    for row in records:
        keys = frozenset(row)
        if keys != RECORD_FIELDS:
            errors.append(f"record-fields:{row.get('record_id')}")
        if keys & FORBIDDEN_RECORD_FIELDS:
            errors.append(f"forbidden-field:{row.get('record_id')}")
        if int(row.get("event_time", -1)) != int(row.get("position", -2)):
            errors.append(f"event-time:{row.get('record_id')}")
        if str(row.get("relation")) not in RELATION_PRECEDENCE:
            errors.append(f"relation:{row.get('record_id')}")
        if str(row.get("source")) not in SOURCE_PRIORITY:
            errors.append(f"source:{row.get('record_id')}")
        supersedes = row.get("supersedes")
        if supersedes is not None:
            old = by_id.get(str(supersedes))
            if old is None:
                errors.append(f"missing-supersedes:{row.get('record_id')}")
            else:
                if int(old["position"]) >= int(row["position"]):
                    errors.append(f"supersedes-order:{row.get('record_id')}")
                if (old["subject"], old["relation"]) != (
                    row["subject"],
                    row["relation"],
                ):
                    errors.append(f"supersedes-key:{row.get('record_id')}")

    index = index_records(records)
    query_ids: set[str] = set()
    quartiles: Counter[int] = Counter()
    family_counts: Counter[str] = Counter()
    hop_counts: Counter[int] = Counter()
    for query in history.get("queries", []):
        query_id = str(query.get("query_id"))
        if query_id in query_ids:
            errors.append(f"duplicate-query-id:{query_id}")
        query_ids.add(query_id)
        expected = query["expected"]
        path = [str(value) for value in expected["path_record_ids"]]
        if len(path) != int(query["dependency_hops"]):
            errors.append(f"hop-count:{query_id}")
        if any(record_id not in by_id for record_id in path):
            errors.append(f"missing-path-record:{query_id}")
            continue
        positions = [int(by_id[record_id]["position"]) for record_id in path]
        if max(positions) - min(positions) <= CAPACITY:
            errors.append(f"contiguous-window-leak:{query_id}")
        if set(path).issubset(set(ids[:CAPACITY])):
            errors.append(f"prefix-window-leak:{query_id}")
        if set(path).issubset(set(ids[-CAPACITY:])):
            errors.append(f"recency-window-leak:{query_id}")
        if positions != [int(value) for value in expected["critical_record_positions"]]:
            errors.append(f"position-label:{query_id}")
        reconstructed = trace_index(
            index,
            str(query["root_entity"]),
            int(query["deployment_temperature"]),
        )
        for key in (
            "terminal_entity",
            "failure_threshold",
            "requires_inspection",
            "path_record_ids",
        ):
            if reconstructed[key] != expected[key]:
                errors.append(f"reconstruction:{query_id}:{key}")
        for record_id in expected["updated_record_ids"]:
            if record_id not in path:
                errors.append(f"updated-not-critical:{query_id}:{record_id}")
                continue
            row = by_id[record_id]
            bucket = index[(str(row["subject"]), str(row["relation"]))]
            if len(bucket) < 2 or winning_record(bucket) != row:
                errors.append(f"updated-resolution:{query_id}:{record_id}")
        for position in positions:
            quartiles[min(3, (position * 4) // max(1, history_size))] += 1
        for family in query["families"]:
            family_counts[str(family)] += 1
        hop_counts[int(query["dependency_hops"])] += 1

    if len(query_ids) != QUERIES_PER_HISTORY:
        errors.append("query-count")
    if hop_counts != Counter({2: 2, 3: 2, 4: 2, 5: 2}):
        errors.append("hop-distribution")
    return {
        "pass": not errors,
        "history_id": history.get("history_id"),
        "record_count": len(records),
        "query_count": len(query_ids),
        "quartile_counts": {str(index): quartiles[index] for index in range(4)},
        "family_counts": dict(sorted(family_counts.items())),
        "hop_counts": {str(key): hop_counts[key] for key in sorted(hop_counts)},
        "errors": errors,
    }


def dataset_file_name(history_size: int, seed: int) -> str:
    return f"history_n{history_size}_s{seed}.json"


def generate_dataset(output_root: Path = DATASET_ROOT) -> dict[str, Any]:
    histories_root = output_root / "histories"
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"dataset output is not empty: {output_root}")
    histories_root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    all_integrity: list[dict[str, Any]] = []
    quartiles_by_load: dict[int, Counter[int]] = defaultdict(Counter)
    family_counts: Counter[str] = Counter()
    hop_counts: Counter[int] = Counter()

    for history_size in HISTORY_SIZES:
        for seed in SEEDS:
            history = build_history(seed, history_size)
            integrity = verify_history(history)
            if not integrity["pass"]:
                raise RuntimeError(canonical(integrity))
            file_name = dataset_file_name(history_size, seed)
            path = histories_root / file_name
            write_json(path, history, compact=True)
            files.append(
                {
                    "path": f"histories/{file_name}",
                    "sha256": file_sha256(path),
                    "bytes": path.stat().st_size,
                    "history_id": history["history_id"],
                    "history_size": history_size,
                    "seed": seed,
                    "query_count": len(history["queries"]),
                }
            )
            all_integrity.append(integrity)
            for key, value in integrity["quartile_counts"].items():
                quartiles_by_load[history_size][int(key)] += int(value)
            family_counts.update(integrity["family_counts"])
            hop_counts.update(
                {int(key): int(value) for key, value in integrity["hop_counts"].items()}
            )

    quartile_checks: dict[str, Any] = {}
    quartile_pass = True
    for history_size in HISTORY_SIZES:
        counts = quartiles_by_load[history_size]
        total = sum(counts.values())
        shares = {str(index): counts[index] / total for index in range(4)}
        passed = all(0.10 <= share <= 0.40 for share in shares.values())
        quartile_pass = quartile_pass and passed
        quartile_checks[str(history_size)] = {
            "counts": {str(index): counts[index] for index in range(4)},
            "shares": shares,
            "pass": passed,
        }
    if not quartile_pass:
        raise RuntimeError(f"aggregate placement quartiles failed: {quartile_checks}")

    manifest = {
        "experiment_id": "MCO-01",
        "schema_version": 1,
        "status": "FROZEN_DATASET_CANDIDATE",
        "config_sha256": file_sha256(CONFIG_PATH),
        "contract_sha256": file_sha256(CONTRACT_PATH),
        "generator_sha256": file_sha256(Path(__file__)),
        "history_count": len(files),
        "query_count": sum(int(row["query_count"]) for row in files),
        "record_count": sum(int(row["history_size"]) for row in files),
        "history_sizes": list(HISTORY_SIZES),
        "seeds": list(SEEDS),
        "files": files,
        "integrity": {
            "pass": all(row["pass"] for row in all_integrity) and quartile_pass,
            "history_checks_passed": sum(row["pass"] for row in all_integrity),
            "history_checks_expected": EXPECTED_HISTORIES,
            "placement_quartiles": quartile_checks,
            "family_counts": dict(sorted(family_counts.items())),
            "hop_counts": {str(key): hop_counts[key] for key in sorted(hop_counts)},
            "forbidden_record_fields": sorted(FORBIDDEN_RECORD_FIELDS),
            "contiguous_window_width": CAPACITY,
        },
    }
    manifest["dataset_digest"] = digest(
        {
            "files": [
                {"path": row["path"], "sha256": row["sha256"]} for row in files
            ],
            "history_count": manifest["history_count"],
            "query_count": manifest["query_count"],
            "record_count": manifest["record_count"],
        }
    )
    if manifest["history_count"] != EXPECTED_HISTORIES:
        raise RuntimeError("unexpected history count")
    if manifest["query_count"] != EXPECTED_QUERIES:
        raise RuntimeError("unexpected query count")
    if manifest["record_count"] != EXPECTED_RECORDS:
        raise RuntimeError("unexpected record count")
    write_json(output_root / "dataset_manifest.json", manifest)
    return manifest


def verify_dataset(
    dataset_root: Path = DATASET_ROOT, *, deep: bool = True
) -> dict[str, Any]:
    manifest_path = dataset_root / "dataset_manifest.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["missing-manifest"]}
    manifest = read_json(manifest_path)
    errors: list[str] = []
    if int(manifest.get("history_count", -1)) != EXPECTED_HISTORIES:
        errors.append("history-count")
    if int(manifest.get("query_count", -1)) != EXPECTED_QUERIES:
        errors.append("query-count")
    if int(manifest.get("record_count", -1)) != EXPECTED_RECORDS:
        errors.append("record-count")
    if manifest.get("config_sha256") != file_sha256(CONFIG_PATH):
        errors.append("config-hash")
    if manifest.get("contract_sha256") != file_sha256(CONTRACT_PATH):
        errors.append("contract-hash")
    if manifest.get("generator_sha256") != file_sha256(Path(__file__)):
        errors.append("generator-hash")
    if not manifest.get("integrity", {}).get("pass"):
        errors.append("manifest-integrity")
    for history_size in HISTORY_SIZES:
        placement = (
            manifest.get("integrity", {})
            .get("placement_quartiles", {})
            .get(str(history_size), {})
        )
        if not placement.get("pass"):
            errors.append(f"placement-quartiles:{history_size}")
    file_checks: list[dict[str, Any]] = []
    deep_checks: list[dict[str, Any]] = []
    for row in manifest.get("files", []):
        path = dataset_root / str(row["path"])
        observed = file_sha256(path) if path.exists() else None
        passed = observed == row.get("sha256")
        if not passed:
            errors.append(f"file-hash:{row.get('path')}")
        file_checks.append(
            {
                "path": row.get("path"),
                "expected_sha256": row.get("sha256"),
                "observed_sha256": observed,
                "pass": passed,
            }
        )
        if deep and passed:
            check = verify_history(read_json(path))
            deep_checks.append(check)
            if not check["pass"]:
                errors.append(f"history-integrity:{row.get('path')}")
    dataset_digest = digest(
        {
            "files": [
                {"path": row["path"], "sha256": row["sha256"]}
                for row in manifest.get("files", [])
            ],
            "history_count": manifest.get("history_count"),
            "query_count": manifest.get("query_count"),
            "record_count": manifest.get("record_count"),
        }
    )
    if dataset_digest != manifest.get("dataset_digest"):
        errors.append("dataset-digest")
    return {
        "pass": not errors,
        "manifest_sha256": file_sha256(manifest_path),
        "dataset_digest": dataset_digest,
        "file_checks": file_checks,
        "deep_checks": deep_checks,
        "errors": errors,
    }


def load_histories(dataset_root: Path = DATASET_ROOT) -> Iterable[dict[str, Any]]:
    manifest = read_json(dataset_root / "dataset_manifest.json")
    for row in manifest["files"]:
        yield read_json(dataset_root / str(row["path"]))


def public_query(query: dict[str, Any]) -> dict[str, Any]:
    """The only query fields visible to a system under test."""

    return {
        "root_entity": str(query["root_entity"]),
        "deployment_temperature": int(query["deployment_temperature"]),
    }


def serialized_record_bytes(records: Sequence[dict[str, Any]]) -> int:
    return sum(len(canonical(row).encode("utf-8")) + 1 for row in records)


def make_context(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "records": list(records),
        "index": index_records(records),
        "serialized_bytes": serialized_record_bytes(records),
    }


def path_prediction(
    path: Sequence[dict[str, Any]],
    public: dict[str, Any],
    *,
    complete: bool,
) -> dict[str, Any]:
    if not complete or not path or path[-1]["relation"] != "failure_threshold":
        return {
            "complete": False,
            "terminal_entity": None,
            "failure_threshold": None,
            "requires_inspection": None,
            "path_record_ids": [str(row["record_id"]) for row in path],
        }
    terminal = path[-1]
    threshold = int(terminal["object"])
    return {
        "complete": True,
        "terminal_entity": str(terminal["subject"]),
        "failure_threshold": threshold,
        "requires_inspection": int(public["deployment_temperature"]) < threshold,
        "path_record_ids": [str(row["record_id"]) for row in path],
    }


def traverse_external(
    index: dict[tuple[str, str], list[dict[str, Any]]],
    public: dict[str, Any],
) -> dict[str, Any]:
    """Transparent structured planner used by the exact baseline."""

    current = str(public["root_entity"])
    path: list[dict[str, Any]] = []
    visited: set[str] = set()
    external_reads = 0
    index_probes = 0
    for _ in range(32):
        if current in visited:
            break
        visited.add(current)
        selected: dict[str, Any] | None = None
        for relation in RELATION_PRECEDENCE:
            index_probes += 1
            candidates = index.get((current, relation), [])
            external_reads += len(candidates)
            winner = winning_record(candidates)
            if winner is not None:
                selected = winner
                break
        if selected is None:
            break
        path.append(selected)
        if selected["relation"] == "failure_threshold":
            prediction = path_prediction(path, public, complete=True)
            return {
                "prediction": prediction,
                "path": path,
                "external_reads": external_reads,
                "external_index_probes": index_probes,
            }
        current = str(selected["object"])
    return {
        "prediction": path_prediction(path, public, complete=False),
        "path": path,
        "external_reads": external_reads,
        "external_index_probes": index_probes,
    }


def system_full_history(
    context: dict[str, Any], public: dict[str, Any]
) -> dict[str, Any]:
    records = context["records"]
    prediction = trace_index(
        context["index"],
        str(public["root_entity"]),
        int(public["deployment_temperature"]),
    )
    return {
        "prediction": prediction,
        "retrieved_record_ids": {str(row["record_id"]) for row in records},
        "persistent_records": len(records),
        "external_bytes": int(context["serialized_bytes"]),
        "external_reads": len(records),
        "external_index_probes": 0,
        "maximum_active_records": len(records),
        "records_retrieved_per_question": len(records),
        "retrieval_rounds": 0,
    }


def system_recent_16(
    context: dict[str, Any], public: dict[str, Any]
) -> dict[str, Any]:
    active = list(context["records"][-CAPACITY:])
    prediction = trace_index(
        index_records(active),
        str(public["root_entity"]),
        int(public["deployment_temperature"]),
    )
    return {
        "prediction": prediction,
        "retrieved_record_ids": {str(row["record_id"]) for row in active},
        "persistent_records": len(active),
        "external_bytes": serialized_record_bytes(active),
        "external_reads": len(active),
        "external_index_probes": 0,
        "maximum_active_records": len(active),
        "records_retrieved_per_question": len(active),
        "retrieval_rounds": 0,
    }


def system_exact_structured_lookup(
    context: dict[str, Any], public: dict[str, Any]
) -> dict[str, Any]:
    traversal = traverse_external(context["index"], public)
    path = traversal["path"]
    return {
        "prediction": traversal["prediction"],
        "retrieved_record_ids": {str(row["record_id"]) for row in path},
        "persistent_records": len(context["records"]),
        "external_bytes": int(context["serialized_bytes"]),
        "external_reads": int(traversal["external_reads"]),
        "external_index_probes": int(traversal["external_index_probes"]),
        "maximum_active_records": len(path),
        "records_retrieved_per_question": len(path),
        "retrieval_rounds": 1,
    }


def one_shot_score(row: dict[str, Any], public: dict[str, Any]) -> tuple[int, int]:
    root = str(public["root_entity"])
    score = 0
    if str(row["subject"]) == root:
        score += 100
    if str(row["object"]) == root:
        score += 50
    if row["relation"] == "failure_threshold":
        score += 10
    elif row["relation"] == "renamed_to":
        score += 2
    elif row["relation"] == "depends_on":
        score += 1
    tie = stable_int(root, row["record_id"], "one-shot-tie")
    return score, tie


def system_conventional_one_shot(
    context: dict[str, Any], public: dict[str, Any]
) -> dict[str, Any]:
    ranked = sorted(
        context["records"],
        key=lambda row: (
            -one_shot_score(row, public)[0],
            one_shot_score(row, public)[1],
            str(row["record_id"]),
        ),
    )
    active = ranked[:CAPACITY]
    prediction = trace_index(
        index_records(active),
        str(public["root_entity"]),
        int(public["deployment_temperature"]),
    )
    return {
        "prediction": prediction,
        "retrieved_record_ids": {str(row["record_id"]) for row in active},
        "persistent_records": len(context["records"]),
        "external_bytes": int(context["serialized_bytes"]),
        "external_reads": len(context["records"]),
        "external_index_probes": 1,
        "maximum_active_records": len(active),
        "records_retrieved_per_question": len(active),
        "retrieval_rounds": 1,
    }


def system_iterative_need(
    context: dict[str, Any], public: dict[str, Any]
) -> dict[str, Any]:
    index = context["index"]
    current = str(public["root_entity"])
    retained: list[dict[str, Any]] = []
    retrieved_ids: set[str] = set()
    visited: set[str] = set()
    external_reads = 0
    index_probes = 0
    maximum_active = 0
    rounds = 0
    complete = False

    for _ in range(32):
        if current in visited:
            break
        visited.add(current)
        rounds += 1
        bundles: dict[str, list[dict[str, Any]]] = {}
        current_bundle: list[dict[str, Any]] = []
        for relation in RELATION_PRECEDENCE:
            index_probes += 1
            candidates = list(index.get((current, relation), []))
            bundles[relation] = candidates
            current_bundle.extend(candidates)
            external_reads += len(candidates)
            retrieved_ids.update(str(row["record_id"]) for row in candidates)
        active_ids = {
            str(row["record_id"]) for row in [*retained, *current_bundle]
        }
        maximum_active = max(maximum_active, len(active_ids))
        selected: dict[str, Any] | None = None
        for relation in RELATION_PRECEDENCE:
            selected = winning_record(bundles[relation])
            if selected is not None:
                break
        if selected is None:
            break
        retained.append(selected)
        if selected["relation"] == "failure_threshold":
            complete = True
            break
        current = str(selected["object"])

    prediction = path_prediction(retained, public, complete=complete)
    return {
        "prediction": prediction,
        "retrieved_record_ids": retrieved_ids,
        "persistent_records": len(context["records"]),
        "external_bytes": int(context["serialized_bytes"]),
        "external_reads": external_reads,
        "external_index_probes": index_probes,
        "maximum_active_records": maximum_active,
        "records_retrieved_per_question": len(retrieved_ids),
        "retrieval_rounds": rounds,
    }


SYSTEM_FUNCTIONS = {
    "full_history_oracle": system_full_history,
    "recent_16": system_recent_16,
    "exact_structured_lookup": system_exact_structured_lookup,
    "conventional_one_shot_retrieval": system_conventional_one_shot,
    "iterative_need_retrieval": system_iterative_need,
}


def score_outcome(
    *,
    history: dict[str, Any],
    query: dict[str, Any],
    system: str,
    outcome: dict[str, Any],
    wall_time_seconds: float,
) -> dict[str, Any]:
    expected = query["expected"]
    prediction = outcome["prediction"]
    expected_path = [str(value) for value in expected["path_record_ids"]]
    predicted_path = [str(value) for value in prediction["path_record_ids"]]
    retrieved_ids = {str(value) for value in outcome["retrieved_record_ids"]}
    answer_correct = bool(
        prediction["complete"]
        and prediction["terminal_entity"] == expected["terminal_entity"]
        and prediction["failure_threshold"] == expected["failure_threshold"]
        and prediction["requires_inspection"] == expected["requires_inspection"]
    )
    dependency_correct = bool(
        prediction["complete"]
        and prediction["terminal_entity"] == expected["terminal_entity"]
        and len(predicted_path) == int(query["dependency_hops"])
    )
    updated_ids = [str(value) for value in expected["updated_record_ids"]]
    if updated_ids:
        temporal_accuracy = sum(value in predicted_path for value in updated_ids) / len(
            updated_ids
        )
    else:
        temporal_accuracy = float(predicted_path == expected_path)
    critical_recall = sum(value in retrieved_ids for value in expected_path) / len(
        expected_path
    )
    provenance_correct = predicted_path == expected_path
    return {
        "history_id": str(history["history_id"]),
        "history_size": int(history["history_size"]),
        "seed": int(history["seed"]),
        "query_id": str(query["query_id"]),
        "dependency_hops": int(query["dependency_hops"]),
        "families": list(query["families"]),
        "system": system,
        "answer_accuracy": float(answer_correct),
        "critical_recall": critical_recall,
        "dependency_chain_accuracy": float(dependency_correct),
        "temporal_update_accuracy": temporal_accuracy,
        "provenance_accuracy": float(provenance_correct),
        "maximum_active_records": int(outcome["maximum_active_records"]),
        "records_retrieved_per_question": int(
            outcome["records_retrieved_per_question"]
        ),
        "retrieval_rounds": int(outcome["retrieval_rounds"]),
        "persistent_records": int(outcome["persistent_records"]),
        "external_bytes": int(outcome["external_bytes"]),
        "external_reads": int(outcome["external_reads"]),
        "external_index_probes": int(outcome["external_index_probes"]),
        "wall_time_seconds": wall_time_seconds,
        "prediction_complete": bool(prediction["complete"]),
        "predicted_terminal_entity": prediction["terminal_entity"],
        "predicted_failure_threshold": prediction["failure_threshold"],
        "predicted_requires_inspection": prediction["requires_inspection"],
        "predicted_path_record_ids": predicted_path,
        "expected_path_sha256": digest(expected_path),
        "retrieved_record_ids_sha256": digest(sorted(retrieved_ids)),
        "public_query_sha256": digest(public_query(query)),
    }


def normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in RUNTIME_FIELDS}


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.exists():
        return {"pass": False, "errors": ["missing-freeze"], "files": []}
    freeze = read_json(FREEZE_PATH)
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    if freeze.get("status") != "FROZEN_BEFORE_SCIENTIFIC_EXECUTION":
        errors.append("freeze-status")
    for relative, expected in freeze.get("files", {}).items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        passed = observed == expected
        if not passed:
            errors.append(f"hash:{relative}")
        rows.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "pass": passed,
            }
        )
    return {"pass": not errors, "errors": errors, "files": rows}


def preflight(*, deep_dataset: bool = True) -> dict[str, Any]:
    cfg = config()
    receipt = read_json(TERMINAL_RECEIPT_PATH)
    freeze_check = verify_freeze()
    dataset_check = verify_dataset(deep=deep_dataset)
    checks = {
        "config_preregistered": cfg.get("status")
        == "PREREGISTERED_BEFORE_DATASET_GENERATION",
        "dmc_branch_terminal": receipt.get("status") == "TERMINAL_BRANCH_STOP",
        "successor_is_mco01": receipt.get("terminal_interpretation", {}).get(
            "authorized_successor"
        )
        == "MCO-01 — STORE ALL, THINK SMALL",
        "learned_retention_disabled": cfg.get("frozen_scope", {}).get(
            "learned_retention"
        )
        is False,
        "utility_labels_disabled": cfg.get("frozen_scope", {}).get(
            "utility_labels_at_ingestion"
        )
        is False,
        "active_cap_is_16": cfg.get("frozen_scope", {}).get("active_record_cap")
        == CAPACITY,
        "freeze_identity": freeze_check["pass"],
        "dataset_identity_and_integrity": dataset_check["pass"],
    }
    errors = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not errors,
        "checks": checks,
        "freeze": freeze_check,
        "dataset": dataset_check,
        "errors": errors,
    }


def reproduce_dataset() -> dict[str, Any]:
    frozen = read_json(DATASET_MANIFEST_PATH)
    with tempfile.TemporaryDirectory(prefix="mco01-dataset-replay-") as temporary:
        replay_root = Path(temporary) / "dataset"
        replay = generate_dataset(replay_root)
        file_pairs = list(zip(frozen["files"], replay["files"], strict=True))
        files_match = all(
            left["path"] == right["path"] and left["sha256"] == right["sha256"]
            for left, right in file_pairs
        )
        result = {
            "pass": bool(
                files_match
                and frozen["dataset_digest"] == replay["dataset_digest"]
                and frozen["history_count"] == replay["history_count"]
                and frozen["query_count"] == replay["query_count"]
                and frozen["record_count"] == replay["record_count"]
            ),
            "frozen_manifest_sha256": file_sha256(DATASET_MANIFEST_PATH),
            "frozen_dataset_digest": frozen["dataset_digest"],
            "replayed_dataset_digest": replay["dataset_digest"],
            "files_match": files_match,
            "file_count": len(file_pairs),
        }
    write_json(OUT / "dataset_replay.json", result)
    return result


def run_experiment(run_id: str) -> dict[str, Any]:
    check = preflight(deep_dataset=False)
    if not check["pass"]:
        raise RuntimeError(f"preflight failed: {canonical(check['errors'])}")
    run_root = RAW_ROOT / run_id
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(f"run output is not empty: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for history in load_histories():
        context = make_context(history["records"])
        for query in history["queries"]:
            public = public_query(query)
            for system in SYSTEMS:
                before = time.perf_counter()
                outcome = SYSTEM_FUNCTIONS[system](context, public)
                elapsed = time.perf_counter() - before
                rows.append(
                    score_outcome(
                        history=history,
                        query=query,
                        system=system,
                        outcome=outcome,
                        wall_time_seconds=elapsed,
                    )
                )
    expected_rows = EXPECTED_QUERIES * len(SYSTEMS)
    if len(rows) != expected_rows:
        raise RuntimeError(f"expected {expected_rows} rows, observed {len(rows)}")
    normalized = [normalized_row(row) for row in rows]
    write_jsonl(run_root / "results.jsonl", rows)
    write_jsonl(run_root / "normalized_results.jsonl", normalized)
    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
    }
    write_json(run_root / "environment.json", environment)
    summary = {
        "experiment_id": "MCO-01",
        "run_id": run_id,
        "status": "VALID_SCIENTIFIC_RUN",
        "row_count": len(rows),
        "history_count": EXPECTED_HISTORIES,
        "query_count": EXPECTED_QUERIES,
        "systems": list(SYSTEMS),
        "normalized_results_sha256": file_sha256(
            run_root / "normalized_results.jsonl"
        ),
        "results_sha256": file_sha256(run_root / "results.jsonl"),
        "dataset_manifest_sha256": file_sha256(DATASET_MANIFEST_PATH),
        "freeze_sha256": file_sha256(FREEZE_PATH),
        "total_wall_time_seconds": time.perf_counter() - started,
        "runtime_fields_excluded_from_replay": sorted(RUNTIME_FIELDS),
    }
    write_json(run_root / "run_summary.json", summary)
    return summary


def summarize_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize an empty population")
    return {
        "n": len(rows),
        **{
            metric: statistics.fmean(float(row[metric]) for row in rows)
            for metric in QUALITY_METRICS
        },
        "maximum_active_records": max(
            int(row["maximum_active_records"]) for row in rows
        ),
        "mean_active_records": statistics.fmean(
            float(row["maximum_active_records"]) for row in rows
        ),
        "records_retrieved_per_question": statistics.fmean(
            float(row["records_retrieved_per_question"]) for row in rows
        ),
        "retrieval_rounds": statistics.fmean(
            float(row["retrieval_rounds"]) for row in rows
        ),
        "external_bytes": statistics.fmean(
            float(row["external_bytes"]) for row in rows
        ),
        "external_reads": statistics.fmean(
            float(row["external_reads"]) for row in rows
        ),
        "external_index_probes": statistics.fmean(
            float(row["external_index_probes"]) for row in rows
        ),
    }


def aggregate_rows(
    normalized_rows: Sequence[dict[str, Any]],
    runtime_rows: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_load: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    by_hop: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in normalized_rows:
        system = str(row["system"])
        by_system[system].append(row)
        by_load[int(row["history_size"])][system].append(row)
        by_hop[int(row["dependency_hops"])][system].append(row)

    runtime_by_system: dict[str, dict[str, float]] = {}
    if runtime_rows is not None:
        grouped_runtime: dict[str, list[float]] = defaultdict(list)
        for row in runtime_rows:
            grouped_runtime[str(row["system"])].append(float(row["wall_time_seconds"]))
        for system, values in grouped_runtime.items():
            runtime_by_system[system] = {
                "mean_wall_time_seconds": statistics.fmean(values),
                "total_wall_time_seconds": sum(values),
                "maximum_wall_time_seconds": max(values),
            }

    return {
        "experiment_id": "MCO-01",
        "population": {
            "rows": len(normalized_rows),
            "histories": len(
                {str(row["history_id"]) for row in normalized_rows}
            ),
            "queries": len({str(row["query_id"]) for row in normalized_rows}),
            "systems": sorted(by_system),
        },
        "overall": {
            system: summarize_rows(by_system[system]) for system in SYSTEMS
        },
        "by_history_size": {
            str(history_size): {
                system: summarize_rows(by_load[history_size][system])
                for system in SYSTEMS
            }
            for history_size in HISTORY_SIZES
        },
        "by_dependency_hops": {
            str(hops): {
                system: summarize_rows(by_hop[hops][system]) for system in SYSTEMS
            }
            for hops in sorted(set(HOPS_BY_QUERY))
        },
        "runtime_nonverdict": runtime_by_system,
    }


def bounded_quality_gate(
    aggregate: dict[str, Any], system: str
) -> dict[str, Any]:
    criteria = config()["acceptance_criteria"]
    by_load = aggregate["by_history_size"]
    metric_thresholds = {
        "answer_accuracy": criteria["bounded_system_min_answer_accuracy_each_load"],
        "critical_recall": criteria["bounded_system_min_critical_recall_each_load"],
        "dependency_chain_accuracy": criteria[
            "bounded_system_min_dependency_chain_accuracy_each_load"
        ],
        "temporal_update_accuracy": criteria[
            "bounded_system_min_temporal_update_accuracy_each_load"
        ],
        "provenance_accuracy": criteria[
            "bounded_system_min_provenance_accuracy_each_load"
        ],
    }
    metrics_each_load = {
        metric: all(
            float(by_load[str(history_size)][system][metric]) >= float(threshold)
            for history_size in HISTORY_SIZES
        )
        for metric, threshold in metric_thresholds.items()
    }
    max_active = max(
        int(by_load[str(history_size)][system]["maximum_active_records"])
        for history_size in HISTORY_SIZES
    )
    accuracy_drop = max(
        0.0,
        float(by_load["100"][system]["answer_accuracy"])
        - float(by_load["100000"][system]["answer_accuracy"]),
    )
    checks = {
        **metrics_each_load,
        "active_cap": max_active
        <= int(criteria["bounded_system_max_active_records"]),
        "scaling": accuracy_drop
        <= float(criteria["bounded_system_max_accuracy_drop_100_to_100000"]),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "maximum_active_records": max_active,
        "accuracy_drop_100_to_100000": accuracy_drop,
        "thresholds": metric_thresholds,
    }


def external_viability_gate(
    aggregate: dict[str, Any], system: str
) -> dict[str, Any]:
    criteria = config()["acceptance_criteria"]
    floor = float(criteria["external_store_failure_accuracy_floor"])
    by_load = aggregate["by_history_size"]
    load_scores = {
        str(size): float(by_load[str(size)][system]["answer_accuracy"])
        for size in HISTORY_SIZES
    }
    accuracy_drop = max(0.0, load_scores["100"] - load_scores["100000"])
    max_active = max(
        int(by_load[str(size)][system]["maximum_active_records"])
        for size in HISTORY_SIZES
    )
    checks = {
        "accuracy_floor_each_load": all(value >= floor for value in load_scores.values()),
        "active_cap": max_active <= CAPACITY,
        "scaling": accuracy_drop
        <= float(criteria["bounded_system_max_accuracy_drop_100_to_100000"]),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "load_answer_accuracy": load_scores,
        "maximum_active_records": max_active,
        "accuracy_drop_100_to_100000": accuracy_drop,
    }


def evaluate_verdict(
    aggregate: dict[str, Any], integrity_pass: bool
) -> tuple[str, dict[str, Any]]:
    criteria = config()["acceptance_criteria"]
    exact_gate = bounded_quality_gate(aggregate, "exact_structured_lookup")
    one_shot_gate = bounded_quality_gate(
        aggregate, "conventional_one_shot_retrieval"
    )
    iterative_gate = bounded_quality_gate(aggregate, "iterative_need_retrieval")
    exact_viable = external_viability_gate(aggregate, "exact_structured_lookup")
    iterative_viable = external_viability_gate(
        aggregate, "iterative_need_retrieval"
    )
    iterative_overall = float(
        aggregate["overall"]["iterative_need_retrieval"]["answer_accuracy"]
    )
    one_shot_overall = float(
        aggregate["overall"]["conventional_one_shot_retrieval"][
            "answer_accuracy"
        ]
    )
    overall_gap = iterative_overall - one_shot_overall
    hop_rows = aggregate["by_dependency_hops"]
    iterative_hard = statistics.fmean(
        float(hop_rows[str(hops)]["iterative_need_retrieval"]["answer_accuracy"])
        for hops in (3, 4, 5)
    )
    one_shot_hard = statistics.fmean(
        float(
            hop_rows[str(hops)]["conventional_one_shot_retrieval"][
                "answer_accuracy"
            ]
        )
        for hops in (3, 4, 5)
    )
    hard_gap = iterative_hard - one_shot_hard
    one_shot_close = abs(overall_gap) <= float(
        criteria["one_shot_sufficient_max_gap_to_iterative"]
    )
    iterative_material = bool(
        overall_gap
        >= float(criteria["iterative_advance_min_overall_answer_gap_vs_one_shot"])
        and hard_gap
        >= float(
            criteria["iterative_advance_min_hop_3_to_5_answer_gap_vs_one_shot"]
        )
    )
    oracle_each_load = all(
        float(
            aggregate["by_history_size"][str(size)]["full_history_oracle"][
                "answer_accuracy"
            ]
        )
        >= float(criteria["oracle_min_answer_accuracy_each_load"])
        for size in HISTORY_SIZES
    )
    gates = {
        "integrity_pass": integrity_pass,
        "oracle_each_load": oracle_each_load,
        "exact_bounded_quality": exact_gate,
        "one_shot_bounded_quality": one_shot_gate,
        "iterative_bounded_quality": iterative_gate,
        "exact_external_viability": exact_viable,
        "iterative_external_viability": iterative_viable,
        "iterative_minus_one_shot_overall_answer_accuracy": overall_gap,
        "iterative_minus_one_shot_hop_3_to_5_answer_accuracy": hard_gap,
        "one_shot_close_to_iterative": one_shot_close,
        "iterative_material_advantage": iterative_material,
    }
    if not integrity_pass or not oracle_each_load:
        return "MCO_01_ACCOUNTING_INVALID", gates
    if not (exact_viable["pass"] or iterative_viable["pass"]):
        return "MCO_01_EXTERNAL_STORE_FAILS", gates
    if one_shot_gate["pass"] and one_shot_close:
        return "MCO_01_ONE_SHOT_RETRIEVAL_SUFFICIENT", gates
    if iterative_gate["pass"] and iterative_material:
        return "MCO_01_ITERATIVE_ACQUISITION_ADVANCES", gates
    if exact_gate["pass"] or iterative_gate["pass"]:
        return "MCO_01_BOUNDED_ATTENTION_ADVANCES", gates
    return "MCO_01_EXTERNAL_STORE_FAILS", gates


def replay_check(run_ids: Sequence[str] = ("run1", "run2")) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []
    normalized_hashes: list[str] = []
    for run_id in run_ids:
        root = RAW_ROOT / run_id
        summary_path = root / "run_summary.json"
        normalized_path = root / "normalized_results.jsonl"
        if not summary_path.exists() or not normalized_path.exists():
            errors.append(f"missing-run:{run_id}")
            continue
        summary = read_json(summary_path)
        observed = file_sha256(normalized_path)
        if observed != summary.get("normalized_results_sha256"):
            errors.append(f"summary-hash:{run_id}")
        if int(summary.get("row_count", -1)) != EXPECTED_QUERIES * len(SYSTEMS):
            errors.append(f"row-count:{run_id}")
        summaries.append(summary)
        normalized_hashes.append(observed)
    if len(set(normalized_hashes)) > 1:
        errors.append("normalized-replay-mismatch")
    return {
        "pass": not errors and len(summaries) == len(run_ids),
        "run_ids": list(run_ids),
        "normalized_sha256": normalized_hashes,
        "byte_identical_after_runtime_exclusion": len(set(normalized_hashes)) == 1
        and len(normalized_hashes) == len(run_ids),
        "runtime_fields_excluded": sorted(RUNTIME_FIELDS),
        "errors": errors,
    }


def population_check(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    expected_rows = EXPECTED_QUERIES * len(SYSTEMS)
    if len(rows) != expected_rows:
        errors.append("row-count")
    system_counts = Counter(str(row["system"]) for row in rows)
    if system_counts != Counter({system: EXPECTED_QUERIES for system in SYSTEMS}):
        errors.append("system-denominators")
    load_counts = Counter(
        (int(row["history_size"]), str(row["system"])) for row in rows
    )
    expected_per_load = len(SEEDS) * QUERIES_PER_HISTORY
    if any(
        load_counts[(size, system)] != expected_per_load
        for size in HISTORY_SIZES
        for system in SYSTEMS
    ):
        errors.append("load-denominators")
    hop_counts = Counter(
        (int(row["dependency_hops"]), str(row["system"])) for row in rows
    )
    expected_per_hop = EXPECTED_HISTORIES * 2
    if any(
        hop_counts[(hops, system)] != expected_per_hop
        for hops in (2, 3, 4, 5)
        for system in SYSTEMS
    ):
        errors.append("hop-denominators")
    cap_violations = [
        f"{row['query_id']}:{row['system']}"
        for row in rows
        if row["system"] in BOUNDED_SYSTEMS
        and int(row["maximum_active_records"]) > CAPACITY
    ]
    if cap_violations:
        errors.append("active-cap")
    return {
        "pass": not errors,
        "row_count": len(rows),
        "expected_row_count": expected_rows,
        "system_counts": dict(sorted(system_counts.items())),
        "expected_per_load_per_system": expected_per_load,
        "expected_per_hop_per_system": expected_per_hop,
        "active_cap_violations": cap_violations,
        "errors": errors,
    }


def format_percent(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def render_report(
    verdict: dict[str, Any], aggregate: dict[str, Any], verification: dict[str, Any]
) -> str:
    outcome = verdict["verdict"]
    overall = aggregate["overall"]
    rows = []
    for system in SYSTEMS:
        metrics = overall[system]
        runtime = aggregate["runtime_nonverdict"].get(system, {})
        rows.append(
            "| {system} | {answer} | {critical} | {provenance} | {active} | {retrieved:.2f} | {rounds:.2f} | {reads:.2f} | {wall:.6f} |".format(
                system=system,
                answer=format_percent(float(metrics["answer_accuracy"])),
                critical=format_percent(float(metrics["critical_recall"])),
                provenance=format_percent(float(metrics["provenance_accuracy"])),
                active=int(metrics["maximum_active_records"]),
                retrieved=float(metrics["records_retrieved_per_question"]),
                rounds=float(metrics["retrieval_rounds"]),
                reads=float(metrics["external_reads"]),
                wall=float(runtime.get("mean_wall_time_seconds", 0.0)),
            )
        )
    gate = verdict["gates"]
    stop = (
        "STOP MCO-01 at this terminal deterministic verdict. The bounded-history gate passed; a separately frozen language/tokenizer/model-cost experiment is now eligible, but was not run here."
        if verdict["gate_pass"]
        else "STOP the external-store branch unless a new preregistered repair targets the observed failure."
    )
    return f"""# MCO-01 — STORE ALL, THINK SMALL

## Claim under test

A complete cheap external event history can answer delayed 2–5-hop dependency questions while exposing no more than 16 records to the active reasoner. The discriminating comparison is whether one-shot retrieval is sufficient or iterative `NEED(...)` acquisition adds material capability.

## Check

Self-verified deterministic synthetic benchmark: {EXPECTED_HISTORIES} histories, {EXPECTED_QUERIES} queries, {EXPECTED_RECORDS:,} event records, four history sizes, five evidence seeds, and two byte-identical valid scientific runs after excluding declared wall-clock fields. Required records were position-randomized, and no critical path fit within any contiguous 16-record window.

| System | Answer | Critical recall | Provenance | Max active | Records retrieved | Rounds | External reads | Mean wall seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Verdict — {'PASS' if verdict['gate_pass'] else 'FAIL'}

`{outcome}`

Iterative minus one-shot answer accuracy was {format_percent(float(gate['iterative_minus_one_shot_overall_answer_accuracy']))} overall and {format_percent(float(gate['iterative_minus_one_shot_hop_3_to_5_answer_accuracy']))} on 3–5-hop cases. Exact structured lookup and iterative acquisition both remained within the 16-record active cap if their recorded gates show `pass: true`.

## Criteria

- Frozen identity and dataset integrity: **{'PASS' if verification['preflight']['pass'] else 'FAIL'}**
- Exact population and nonzero denominators: **{'PASS' if verification['population']['pass'] else 'FAIL'}**
- Byte-identical replay after runtime exclusion: **{'PASS' if verification['replay']['pass'] else 'FAIL'}**
- Full-history oracle at every load: **{'PASS' if gate['oracle_each_load'] else 'FAIL'}**
- Exact structured bounded-quality gate: **{'PASS' if gate['exact_bounded_quality']['pass'] else 'FAIL'}**
- One-shot bounded-quality gate: **{'PASS' if gate['one_shot_bounded_quality']['pass'] else 'FAIL'}**
- Iterative bounded-quality gate: **{'PASS' if gate['iterative_bounded_quality']['pass'] else 'FAIL'}**

## Assumption register

- Events are already structured into subject, relation, object, source, update, and provenance fields.
- Source priority is correct and shared equally by all store-all systems.
- External indexes are exact, lossless, and cheap enough to retain the full synthetic history.
- The active-record count measures reasoner-visible records; persistent index state and external planner operations are reported separately.
- Wall-clock values are descriptive local measurements and are excluded from verdict and replay identity.

## Credit assignment

Credit is limited to complete structured storage plus transparent indexing and bounded acquisition. Iterative retrieval receives credit only for the measured gap over the equally informed one-shot system. DMC, learned retention, model inference, tokenizer savings, and production economics receive no credit from MCO-01.

## Verification gap

No independent verifier was available, so this is explicitly self-verified. The test does not establish robustness to natural language, extraction errors, approximate indexes, adversarial source metadata, concurrent writes, or real model reasoning. Exact structured lookup is a strong transparent planner baseline, not a claim that arbitrary real queries can be compiled perfectly.

## Stop/continue decision

{stop}

## Maturity status

`DETERMINISTIC_SYNTHETIC_MECHANISM_EVIDENCE`
"""


def build_artifact_manifest() -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    manifest_path = OUT / "SHA256SUMS.json"
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        relative = str(path.relative_to(ROOT))
        entries[relative] = {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
    manifest = {
        "experiment_id": "MCO-01",
        "entry_count": len(entries),
        "entries": entries,
    }
    write_json(manifest_path, manifest)
    return manifest


def finalize() -> dict[str, Any]:
    preflight_result = preflight(deep_dataset=True)
    replay = replay_check()
    run1_root = RAW_ROOT / "run1"
    run2_root = RAW_ROOT / "run2"
    run1_normalized = read_jsonl(run1_root / "normalized_results.jsonl")
    run2_normalized = read_jsonl(run2_root / "normalized_results.jsonl")
    run1_runtime = read_jsonl(run1_root / "results.jsonl")
    population = population_check(run1_normalized)
    second_population = population_check(run2_normalized)
    aggregate = aggregate_rows(run1_normalized, run1_runtime)
    aggregate_replay = aggregate_rows(run2_normalized)
    deterministic_aggregate = dict(aggregate)
    deterministic_aggregate.pop("runtime_nonverdict", None)
    aggregate_replay.pop("runtime_nonverdict", None)
    aggregate_match = deterministic_aggregate == aggregate_replay
    dataset_replay_path = OUT / "dataset_replay.json"
    dataset_replay = (
        read_json(dataset_replay_path)
        if dataset_replay_path.exists()
        else {"pass": False, "error": "missing-dataset-replay"}
    )
    integrity_pass = bool(
        preflight_result["pass"]
        and replay["pass"]
        and population["pass"]
        and second_population["pass"]
        and aggregate_match
        and dataset_replay.get("pass")
    )
    outcome, gates = evaluate_verdict(aggregate, integrity_pass)
    gate_pass = outcome in {
        "MCO_01_ONE_SHOT_RETRIEVAL_SUFFICIENT",
        "MCO_01_ITERATIVE_ACQUISITION_ADVANCES",
        "MCO_01_BOUNDED_ATTENTION_ADVANCES",
    }
    verification = {
        "experiment_id": "MCO-01",
        "status": "PASS" if integrity_pass else "FAIL",
        "verification_mode": "SELF_VERIFIED",
        "preflight": preflight_result,
        "dataset_replay": dataset_replay,
        "population": population,
        "second_population": second_population,
        "replay": replay,
        "aggregate_replay_match": aggregate_match,
        "all_integrity_checks_pass": integrity_pass,
    }
    verdict = {
        "experiment_id": "MCO-01",
        "status": "TERMINAL_VALID" if integrity_pass else "TERMINAL_INVALID",
        "verdict": outcome,
        "gate_pass": gate_pass,
        "scientific_claim": (
            "complete structured history supports bounded attention"
            if gate_pass
            else "complete structured history did not clear the bounded-attention gate"
        ),
        "gates": gates,
        "population": aggregate["population"],
        "training_accounting": {
            "learned_components": 0,
            "optimizer_steps": 0,
            "backward_calls": 0,
            "dmc_historical_optimizer_steps_preserved": 10880,
            "dmc_historical_training_label": "TRAINING_COST_UNKNOWN",
        },
        "stop_rule_applied": True,
    }
    write_json(OUT / "aggregate.json", aggregate)
    write_json(OUT / "verification.json", verification)
    write_json(OUT / "MCO01_VERDICT.json", verdict)
    report = render_report(verdict, aggregate, verification)
    (OUT / "MCO01_REPORT.md").write_text(report, encoding="utf-8")
    build_artifact_manifest()
    return verdict


def verify_final_artifacts() -> dict[str, Any]:
    manifest_path = OUT / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["missing-artifact-manifest"]}
    manifest = read_json(manifest_path)
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    for relative, expected in manifest.get("entries", {}).items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        passed = observed == expected.get("sha256")
        if not passed:
            errors.append(f"hash:{relative}")
        checks.append(
            {
                "path": relative,
                "expected_sha256": expected.get("sha256"),
                "observed_sha256": observed,
                "pass": passed,
            }
        )
    verification = read_json(OUT / "verification.json")
    verdict = read_json(OUT / "MCO01_VERDICT.json")
    if not verification.get("all_integrity_checks_pass"):
        errors.append("verification")
    if verdict.get("status") != "TERMINAL_VALID":
        errors.append("verdict-status")
    return {
        "pass": not errors,
        "entry_count": len(checks),
        "checks": checks,
        "verdict": verdict.get("verdict"),
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--output", type=Path, default=DATASET_ROOT)
    verify_dataset_parser = subparsers.add_parser("verify-dataset")
    verify_dataset_parser.add_argument("--shallow", action="store_true")
    subparsers.add_parser("reproduce-dataset")
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--shallow", action="store_true")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--run-id", required=True)
    subparsers.add_parser("finalize")
    subparsers.add_parser("verify")
    args = parser.parse_args(argv)

    if args.command == "generate":
        result = generate_dataset(args.output)
    elif args.command == "verify-dataset":
        result = verify_dataset(deep=not args.shallow)
    elif args.command == "reproduce-dataset":
        result = reproduce_dataset()
    elif args.command == "preflight":
        result = preflight(deep_dataset=not args.shallow)
    elif args.command == "run":
        result = run_experiment(args.run_id)
    elif args.command == "finalize":
        result = finalize()
    elif args.command == "verify":
        result = verify_final_artifacts()
    else:
        parser.error(f"unsupported command: {args.command}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
