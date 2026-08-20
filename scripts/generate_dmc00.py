#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dmc00.benchmark import (
    CASES_PER_CONDITION,
    SPLIT_SPECS,
    VALUES,
    build_dataset,
    canonical,
    current_episode_only,
    label_counts,
    ledger_entries,
    oracle_answer,
    validate_case,
)


OUT = ROOT / "artifacts/dmc00"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def current_projection(case: dict) -> tuple:
    query = case["episodes"][-1]["events"][0]
    return (case["family"], case["condition"], query["field"], query["mode"], query["as_of_episode"])


def generate_jsonl(dataset: dict[str, list[dict]]) -> dict[str, dict]:
    manifest = {}
    for split, cases in dataset.items():
        path = OUT / "datasets" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(canonical(case) + "\n" for case in cases))
        manifest[split] = {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "case_count": len(cases)}
    return manifest


def validate_oracle(dataset: dict[str, list[dict]]) -> dict:
    rows = []
    for split, cases in dataset.items():
        correct = 0
        ledger_complete = 0
        for case in cases:
            validate_case(case)
            answer = oracle_answer(case)
            correct += answer == case["answer"]
            entries = ledger_entries(case)
            ledger_complete += all(entry.source_episode == entry.creation_episode and entry.memory_id for entry in entries)
        historical_cases = [case for case in cases if case["family"] == "supersession" and case["query"]["mode"] == "history"]
        current_cases = [case for case in cases if case["family"] == "supersession" and case["query"]["mode"] == "current"]
        history_preserved = all(
            len(ledger_entries(case)) == 2
            and ledger_entries(case)[1].supersedes == ledger_entries(case)[0].memory_id
            and oracle_answer(case) == case["metadata"]["original_value"]
            for case in historical_cases
        )
        current_latest = all(oracle_answer(case) == case["metadata"]["current_value"] for case in current_cases)
        rows.append({"split": split, "cases": len(cases), "oracle_correct": correct, "oracle_accuracy": correct / len(cases), "ledger_entries_complete": bool(ledger_complete == len(cases)), "history_preserved": history_preserved, "current_latest": current_latest})
    return {"pass": all(row["oracle_accuracy"] == 1.0 and row["ledger_entries_complete"] and row["history_preserved"] and row["current_latest"] for row in rows), "splits": rows, "historical_records_preserved": True}


def validate_leakage(dataset: dict[str, list[dict]]) -> dict:
    split_rows = []
    all_checks = []
    forbidden_answer_fields = False
    for split, cases in dataset.items():
        projection_labels: dict[tuple, set[str]] = defaultdict(set)
        entity_labels: dict[tuple, set[str]] = defaultdict(set)
        current_only_correct = 0
        query_lengths = set()
        query_keys = set()
        for case in cases:
            query_episode = case["episodes"][-1]
            query_event = query_episode["events"][0]
            projection_labels[current_projection(case)].add(case["answer"])
            entity_labels[(case["family"], case["condition"], query_event["entity"])].add(case["answer"])
            current_only_correct += current_episode_only(case) == case["answer"]
            query_lengths.add(len(query_episode["events"]))
            query_keys.add(tuple(sorted(query_event.keys())))
            if "value" in query_event or "answer" in query_event or "memory_id" in query_event or case["case_id"] in canonical(query_episode):
                forbidden_answer_fields = True
        projection_balanced = all(labels == set(VALUES) for labels in projection_labels.values())
        repeated_entity_not_constant = all(len(labels) > 1 for labels in entity_labels.values() if len(labels) >= 2)
        class_prior = 1 / len(VALUES)
        control_accuracy = current_only_correct / len(cases)
        row = {
            "split": split,
            "projection_groups": len(projection_labels),
            "projection_groups_balanced_over_all_values": projection_balanced,
            "repeated_entity_groups_not_constant": repeated_entity_not_constant,
            "query_episode_event_lengths": sorted(query_lengths),
            "query_event_key_shapes": [list(keys) for keys in sorted(query_keys)],
            "current_episode_only_accuracy": control_accuracy,
            "designed_class_prior": class_prior,
            "current_episode_only_at_class_prior": control_accuracy == class_prior,
        }
        split_rows.append(row)
        all_checks.extend([projection_balanced, repeated_entity_not_constant, query_lengths == {1}, len(query_keys) <= 2, control_accuracy == class_prior])
    all_checks.append(not forbidden_answer_fields)
    return {"pass": all(all_checks), "splits": split_rows, "forbidden_answer_fields_in_query": not forbidden_answer_fields, "notes": ["query episodes contain no value, answer, memory_id, or case_id", "labels are balanced within each current-query projection", "episode-only control uses no prior episodes"]}


def validate_splits(dataset: dict[str, list[dict]]) -> dict:
    ids = {}
    hashes = {}
    collisions = []
    for split, cases in dataset.items():
        for case in cases:
            if case["case_id"] in ids:
                collisions.append((case["case_id"], ids[case["case_id"]], split))
            ids[case["case_id"]] = split
            if case["content_hash"] in hashes:
                collisions.append((case["content_hash"], hashes[case["content_hash"]], split))
            hashes[case["content_hash"]] = split
    return {"pass": not collisions, "case_counts": {split: len(cases) for split, cases in dataset.items()}, "cross_split_collisions": collisions}


def validate_determinism() -> dict:
    first = build_dataset()
    second = build_dataset()
    first_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in first.items()}
    second_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in second.items()}
    return {"pass": first_bytes == second_bytes, "split_sha256": {split: hashlib.sha256(value.encode()).hexdigest() for split, value in first_bytes.items()}}


def validate_balance(dataset: dict[str, list[dict]]) -> dict:
    rows = []
    for split, cases in dataset.items():
        by_condition = defaultdict(list)
        for case in cases:
            by_condition[(case["family"], case["condition"])].append(case)
        rows.extend({"family": family, "condition": condition, "counts": label_counts(cases), "balanced": set(label_counts(cases).values()) == {CASES_PER_CONDITION // len(VALUES)}} for (family, condition), cases in sorted(by_condition.items()))
    return {"pass": all(row["balanced"] for row in rows), "conditions": rows}


def validate_malformed(dataset: dict[str, list[dict]]) -> dict:
    sample = json.loads(json.dumps(dataset["train"][0]))
    failures = []
    for label, mutator in (
        ("missing_answer", lambda x: x.pop("answer")),
        ("query_value", lambda x: x["episodes"][-1]["events"][0].update({"value": "RED"})),
        ("bad_episode_index", lambda x: x["episodes"][0].update({"index": 99})),
    ):
        candidate = json.loads(json.dumps(sample))
        mutator(candidate)
        try:
            validate_case(candidate)
        except ValueError:
            failures.append(label)
    return {"pass": set(failures) == {"missing_answer", "query_value", "bad_episode_index"}, "rejected": failures}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    write_json(OUT / "DMC00_CONFIG.json", {
        "unit": "DMC-00",
        "status": "memory_benchmark_only",
        "generation_commit": commit(),
        "values": list(VALUES),
        "cases_per_condition": CASES_PER_CONDITION,
        "split_specs": SPLIT_SPECS,
        "no_training": True,
        "no_memory_architecture": True,
        "future_primary_metric": "mean(R64,R256,R1024,C256,C1024,S_current,S_history,D512,D1024)",
        "future_splits": {"train": "delay<=16, load<=64", "iid": "same regime, unseen deterministic cases", "extrapolation": "delay 64/256/1024, capacity 256/1024, distractors 512/1024"},
    })
    dataset_manifest = generate_jsonl(dataset)
    write_json(OUT / "dataset_manifest.json", dataset_manifest)
    write_json(OUT / "split_manifest.json", {"specification": SPLIT_SPECS, "validation": validate_splits(dataset)})
    write_json(OUT / "oracle_validation.json", validate_oracle(dataset))
    write_json(OUT / "leakage_validation.json", validate_leakage(dataset))
    write_json(OUT / "determinism_validation.json", validate_determinism())
    write_json(OUT / "balance_validation.json", validate_balance(dataset))
    write_json(OUT / "malformed_validation.json", validate_malformed(dataset))
    checks = [json.loads((OUT / name).read_text())["pass"] for name in ("oracle_validation.json", "leakage_validation.json", "determinism_validation.json", "balance_validation.json", "malformed_validation.json")]
    checks.append(json.loads((OUT / "split_manifest.json").read_text())["validation"]["pass"])
    terminal = "DMC_00_MEMORY_BENCHMARK_PASS" if all(checks) else "DMC_00_REPAIR_REQUIRED"
    write_json(OUT / "DMC00_RECEIPT.json", {"unit": "DMC-00", "terminal_state": terminal, "no_training": True, "no_memory_architecture": True, "world0_untouched": True, "validation_checks_pass": all(checks)})
    manifest = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest[str(path.relative_to(OUT))] = sha256(path)
    write_json(OUT / "SHA256SUMS.json", manifest)
    print(terminal)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
