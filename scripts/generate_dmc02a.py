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

from dmc02a.benchmark import (  # noqa: E402
    CAPACITY,
    CASES_PER_CONDITION,
    FAMILIES,
    RANDOM_CONTROL_SEED,
    SPLIT_SPECS,
    VALUES,
    bounded_oracle,
    bounded_peak_records,
    build_dataset,
    canonical,
    content_hash,
    current_episode_only,
    fifo_control,
    label_counts,
    random_retention_control,
    unbounded_oracle,
    validate_case,
)


OUT = ROOT / "artifacts/dmc02a"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC00_COMMIT = "0e5359d"
DMC01_COMMIT = "48ae98f"
FUTURE_PRIMARY = "mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)"

CONTRACT = r"""# DMC-02A — Selective Retention Benchmark

Status: **BENCHMARK ONLY; NO BOUNDED MEMORY ARCHITECTURE; NO TRAINING**

## Claim under test

The DMC-02A exam is a fair, deterministic selective-retention benchmark:
each intended condition is solvable with a hard 16-record budget using only
legitimate future-utility signals, while FIFO and deterministic random
retention materially degrade at extrapolated loads.

DMC-00 remains unchanged. DMC-01 remains an unbounded exact-memory control;
its learned models are not retrained here.

## Frozen budget and value space

- Physical record budget: **16** per case.
- Values: RED, BLUE, GREEN, YELLOW, ORANGE, PURPLE, BLACK, WHITE.
- Each condition has 16 cases, with exactly two cases per answer class.
- The final query episode contains exactly one query event and no answer value,
  memory ID, or case ID.

## Families

- **B2-A mission_set:** a 16-entity mission set is announced before writes;
  loads are 32/64 for train and IID, and 128/256/1024 for extrapolation.
- **B2-B salience:** exactly 16 HIGH writes are mixed with LOW writes;
  the query targets a HIGH record. Loads use the same split allocation.
- **B2-C supersession:** eight mission entities receive original and current
  writes, retaining 16 queryable historical/current records. Loads use the
  same split allocation; current and history are separate conditions.
- **B2-D utility_change:** phase A announces 16 keys, then a mission update
  announces phase B before phase-B writes. Overlaps are 0/25/50/75/100%.
  Training and IID use 0/50/100%; extrapolation includes all five, thereby
  holding 25% and 75% out from training. Loads use the same allocation.
- **B2-E distractor_flood:** 16 HIGH relevant writes precede LOW irrelevant
  writes. Distractor counts are 0/32 for train and IID, and 128/512/1024 for
  extrapolation.

For utility change, the benchmark includes 16 phase-B records and discards
obsolete phase-A records only after the explicit mission update. Thus the
minimum simultaneous useful record count is 16, including at 0% overlap.

## Oracles and controls

The unbounded oracle retains every write and must score 100%.

The bounded oracle has capacity 16 and may inspect only mission-set
membership, salience, mission updates, and supersession metadata. It never
uses the hidden answer or the future query choice. It must score at least
0.99, with 1.0 expected.

FIFO is a deterministic 16-record first-in-first-out ledger. Random retention
is a deterministic reservoir-style 16-record controller with independent
control seed `20260202`. At extrapolated load conditions, the bounded-oracle
primary metric must exceed each control by at least 0.40.

## Frozen primary metric

Each named component is a case-weighted mean within its exact condition.
`SHIFT` is the equal-weight mean over utility-change overlaps at load 1024.
The future bounded-memory metric is:

```text
P_bounded = mean(
    M256, M1024,
    SAL256, SAL1024,
    SUP_current_1024, SUP_history_1024,
    SHIFT,
    FLOOD512, FLOOD1024
)
```

The same metric is reported for FIFO and random retention. No model result
is produced by this unit.

## Information-theoretic accounting

Every case records total writes, query-eligible records, physical budget, and
minimum records required by the intended optimal strategy. Any case requiring
more than 16 records invalidates generation.

## Terminal states

- `DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS`
- `DMC_02A_CAPACITY_INVALID`
- `DMC_02A_MEMORY_LEAK`
- `DMC_02A_ORACLE_INVALID`
- `DMC_02A_RETENTION_SIGNAL_WEAK`
- `DMC_02A_INVALID`
- `DMC_02A_REPAIR_REQUIRED`

This unit stops after the benchmark receipt. It does not implement learned
retention, eviction, compression, learned retrieval, dimensional metadata,
consolidation, forgetting, or any training/evidence seeds.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def grouped(dataset: dict[str, list[dict]]) -> dict[tuple[str, str, str], list[dict]]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for split, cases in dataset.items():
        for case in cases:
            groups[(split, case["family"], case["condition"])].append(case)
    return groups


def score(answerer, cases: list[dict]) -> float:
    return sum(answerer(case) == case["answer"] for case in cases) / len(cases)


def condition_summary(dataset: dict[str, list[dict]], answerer, *, include_peak: bool = False) -> list[dict]:
    rows = []
    for (split, family, condition), cases in sorted(grouped(dataset).items()):
        row = {
            "split": split,
            "family": family,
            "condition": condition,
            "case_count": len(cases),
            "correct": sum(answerer(case) == case["answer"] for case in cases),
            "accuracy": score(answerer, cases),
            "answer_counts": label_counts(cases),
            "total_writes": sorted({case["metadata"]["total_writes"] for case in cases}),
            "query_eligible_records": sorted({case["metadata"]["query_eligible_records"] for case in cases}),
            "physical_memory_budget": sorted({case["metadata"]["physical_memory_budget"] for case in cases}),
            "minimum_required_records": sorted({case["metadata"]["minimum_required_records"] for case in cases}),
        }
        if include_peak:
            row["observed_peak_records"] = max(bounded_peak_records(case) for case in cases)
        rows.append(row)
    return rows


def primary_components(dataset: dict[str, list[dict]], answerer) -> dict[str, float]:
    groups = grouped(dataset)
    def condition(family: str, name: str) -> float:
        return score(answerer, groups[("extrapolation", family, name)])
    shift = sum(condition("utility_change", f"load_1024_overlap_{overlap}") for overlap in (0, 25, 50, 75, 100)) / 5
    components = {
        "M256": condition("mission_set", "load_256"),
        "M1024": condition("mission_set", "load_1024"),
        "SAL256": condition("salience", "load_256"),
        "SAL1024": condition("salience", "load_1024"),
        "SUP_current_1024": condition("supersession", "load_1024_current"),
        "SUP_history_1024": condition("supersession", "load_1024_history"),
        "SHIFT": shift,
        "FLOOD512": condition("distractor_flood", "distractors_512"),
        "FLOOD1024": condition("distractor_flood", "distractors_1024"),
    }
    components["P"] = sum(components.values()) / len(components)
    return components


def generate_jsonl(dataset: dict[str, list[dict]]) -> dict[str, dict]:
    manifest = {}
    for split, cases in dataset.items():
        path = OUT / "datasets" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(canonical(case) + "\n" for case in cases))
        manifest[split] = {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "case_count": len(cases)}
    return manifest


def validate_balance(dataset: dict[str, list[dict]]) -> dict:
    rows = []
    for (split, family, condition), cases in sorted(grouped(dataset).items()):
        counts = label_counts(cases)
        rows.append({"split": split, "family": family, "condition": condition, "counts": counts, "balanced": counts == {value: 2 for value in VALUES}})
    return {"pass": all(row["balanced"] for row in rows), "conditions": rows}


def validate_splits(dataset: dict[str, list[dict]]) -> dict:
    ids: dict[str, str] = {}
    hashes: dict[str, str] = {}
    collisions = []
    for split, cases in dataset.items():
        for case in cases:
            if case["case_id"] in ids:
                collisions.append({"kind": "case_id", "value": case["case_id"], "first": ids[case["case_id"]], "second": split})
            ids[case["case_id"]] = split
            if case["content_hash"] in hashes:
                collisions.append({"kind": "content_hash", "value": case["content_hash"], "first": hashes[case["content_hash"]], "second": split})
            hashes[case["content_hash"]] = split
    return {"pass": not collisions, "case_counts": {split: len(cases) for split, cases in dataset.items()}, "unique_case_ids": len(ids), "unique_content_hashes": len(hashes), "cross_split_collisions": collisions}


def validate_leakage(dataset: dict[str, list[dict]]) -> dict:
    rows = []
    checks = []
    forbidden_fields = {"value", "answer", "memory_id", "case_id"}
    for split, cases in dataset.items():
        projection_labels: dict[tuple, set[str]] = defaultdict(set)
        current_only_hits = 0
        query_lengths = set()
        query_shapes = set()
        query_identity_leaks = 0
        for case in cases:
            query = case["episodes"][-1]["events"][0]
            projection_labels[(case["family"], case["condition"], query["mode"])].add(case["answer"])
            current_only_hits += current_episode_only(case) == case["answer"]
            query_lengths.add(len(case["episodes"][-1]["events"]))
            query_shapes.add(tuple(sorted(query)))
            query_identity_leaks += int(any(field in query for field in forbidden_fields) or case["case_id"] in canonical(query))
        control_accuracy = current_only_hits / len(cases)
        projections_balanced = all(labels == set(VALUES) for labels in projection_labels.values())
        row = {
            "split": split,
            "projection_groups": len(projection_labels),
            "projection_groups_balanced": projections_balanced,
            "query_episode_event_lengths": sorted(query_lengths),
            "query_event_key_shapes": [list(shape) for shape in sorted(query_shapes)],
            "current_episode_only_accuracy": control_accuracy,
            "designed_class_prior": 1 / len(VALUES),
            "current_episode_only_at_class_prior": control_accuracy == 1 / len(VALUES),
            "query_identity_leaks": query_identity_leaks,
        }
        rows.append(row)
        checks.extend([projections_balanced, query_lengths == {1}, query_shapes == {("as_of_episode", "entity", "field", "kind", "mode")}, query_identity_leaks == 0, control_accuracy == 1 / len(VALUES)])
    return {"pass": all(checks), "splits": rows, "forbidden_answer_fields": sorted(forbidden_fields), "notes": ["final query episodes contain no answer value, memory ID, or case ID", "answer labels are balanced within family/condition/mode projections", "current-query-only control reads no prior episode"]}


def validate_determinism(dataset: dict[str, list[dict]]) -> dict:
    second = build_dataset()
    first_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in dataset.items()}
    second_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in second.items()}
    random_replay = (
        [random_retention_control(case) for case in dataset["extrapolation"]]
        == [random_retention_control(case) for case in second["extrapolation"]]
    )
    return {"pass": first_bytes == second_bytes and random_replay, "split_sha256": {split: hashlib.sha256(value.encode()).hexdigest() for split, value in first_bytes.items()}, "random_control_replay_identical": random_replay}


def validate_capacity(dataset: dict[str, list[dict]]) -> dict:
    rows = []
    failures = []
    for case in (case for cases in dataset.values() for case in cases):
        try:
            peak = bounded_peak_records(case)
            row = {
                "split": case["split"],
                "family": case["family"],
                "condition": case["condition"],
                "case_id": case["case_id"],
                "total_writes": case["metadata"]["total_writes"],
                "query_eligible_records": case["metadata"]["query_eligible_records"],
                "physical_memory_budget": case["metadata"]["physical_memory_budget"],
                "minimum_required_records": case["metadata"]["minimum_required_records"],
                "observed_peak_records": peak,
                "valid": case["metadata"]["minimum_required_records"] <= CAPACITY and peak <= CAPACITY,
            }
            rows.append(row)
            if not row["valid"]:
                failures.append(row)
        except Exception as exc:  # pragma: no cover - receipt should expose the failure
            failures.append({"case_id": case["case_id"], "error": repr(exc)})
    return {"pass": not failures and len(rows) == sum(len(cases) for cases in dataset.values()), "capacity": CAPACITY, "case_count": len(rows), "failures": failures, "conditions": rows}


def predecessor_identity(name: str, expected_commit: str, artifact_dir: str) -> dict:
    diff = subprocess.run(["git", "diff", "--exit-code", expected_commit, "--", artifact_dir], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {"expected_commit": expected_commit, "current_commit": git_commit(), "artifact_path": artifact_dir, "unchanged": diff.returncode == 0}


def validate_predecessors() -> dict:
    world = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    dmc00 = predecessor_identity("DMC-00", DMC00_COMMIT, "artifacts/dmc00")
    dmc01 = predecessor_identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01")
    world_validation = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    world["validator_terminal"] = world_validation.stdout.strip().splitlines()[-1] if world_validation.stdout.strip() else ""
    world["validator_pass"] = world["validator_terminal"] == "GRI_02_WORLD0_PASS"
    return {"pass": all(row["unchanged"] for row in (world, dmc00, dmc01)) and world["validator_pass"], "world0": world, "dmc00": dmc00, "dmc01": dmc01}


def validate_oracles(dataset: dict[str, list[dict]]) -> tuple[dict, dict]:
    unbounded_rows = condition_summary(dataset, unbounded_oracle)
    bounded_rows = condition_summary(dataset, bounded_oracle, include_peak=True)
    return (
        {"pass": all(row["accuracy"] == 1.0 for row in unbounded_rows), "oracle": "unbounded", "rows": unbounded_rows},
        {"pass": all(row["accuracy"] >= 0.99 and max(row["physical_memory_budget"]) == CAPACITY and row["observed_peak_records"] <= CAPACITY for row in bounded_rows), "oracle": "bounded", "capacity": CAPACITY, "minimum_accuracy": 0.99, "rows": bounded_rows},
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    for cases in dataset.values():
        for case in cases:
            validate_case(case)
    source_commit = git_commit()
    write_json(OUT / "DMC02A_CONFIG.json", {
        "unit": "DMC-02A",
        "status": "selective_retention_benchmark_only",
        "generation_commit": source_commit,
        "values": list(VALUES),
        "cases_per_condition": CASES_PER_CONDITION,
        "physical_memory_budget": CAPACITY,
        "random_control_seed": RANDOM_CONTROL_SEED,
        "split_specs": SPLIT_SPECS,
        "future_primary_metric": FUTURE_PRIMARY,
        "no_training": True,
        "no_memory_architecture": True,
        "no_evidence_seeds": True,
        "control_gap_threshold": 0.40,
    })
    (OUT / "DMC02A_CONTRACT.md").write_text(CONTRACT)
    write_json(OUT / "dataset_manifest.json", generate_jsonl(dataset))
    write_json(OUT / "split_manifest.json", {"specification": SPLIT_SPECS, "validation": validate_splits(dataset)})
    write_json(OUT / "capacity_accounting.json", validate_capacity(dataset))
    unbounded, bounded = validate_oracles(dataset)
    write_json(OUT / "unbounded_oracle.json", unbounded)
    write_json(OUT / "bounded_oracle.json", bounded)
    balance = validate_balance(dataset)
    write_json(OUT / "balance_validation.json", balance)
    leakage = validate_leakage(dataset)
    write_json(OUT / "leakage_validation.json", leakage)
    determinism = validate_determinism(dataset)
    write_json(OUT / "determinism_validation.json", determinism)

    fifo_rows = condition_summary(dataset, fifo_control)
    random_rows = condition_summary(dataset, random_retention_control)
    bounded_primary = primary_components(dataset, bounded_oracle)
    fifo_primary = primary_components(dataset, fifo_control)
    random_primary = primary_components(dataset, random_retention_control)
    control_gap = {
        "threshold": 0.40,
        "bounded": bounded_primary,
        "fifo": fifo_primary,
        "random": random_primary,
        "bounded_minus_fifo": bounded_primary["P"] - fifo_primary["P"],
        "bounded_minus_random": bounded_primary["P"] - random_primary["P"],
        "pass": bounded_primary["P"] - fifo_primary["P"] >= 0.40 and bounded_primary["P"] - random_primary["P"] >= 0.40,
    }
    write_json(OUT / "fifo_control.json", {"capacity": CAPACITY, "rows": fifo_rows, "extrapolated_primary": fifo_primary})
    write_json(OUT / "random_control.json", {"capacity": CAPACITY, "seed": RANDOM_CONTROL_SEED, "rows": random_rows, "extrapolated_primary": random_primary})
    write_json(OUT / "control_validation.json", control_gap)

    dmc00_identity = predecessor_identity("DMC-00", DMC00_COMMIT, "artifacts/dmc00")
    dmc01_identity = predecessor_identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01")
    world0_identity = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    write_json(OUT / "dmc00_identity.json", dmc00_identity)
    write_json(OUT / "dmc01_identity.json", dmc01_identity)
    write_json(OUT / "world0_identity.json", world0_identity)

    checks = {
        "capacity": json.loads((OUT / "capacity_accounting.json").read_text())["pass"],
        "unbounded_oracle": unbounded["pass"],
        "bounded_oracle": bounded["pass"],
        "balance": balance["pass"],
        "leakage": leakage["pass"],
        "determinism": determinism["pass"],
        "split_disjointness": json.loads((OUT / "split_manifest.json").read_text())["validation"]["pass"],
        "control_separation": control_gap["pass"],
        "predecessors": validate_predecessors()["pass"],
    }
    if not checks["predecessors"]:
        terminal = "DMC_02A_INVALID"
    elif not checks["capacity"]:
        terminal = "DMC_02A_CAPACITY_INVALID"
    elif not checks["leakage"]:
        terminal = "DMC_02A_MEMORY_LEAK"
    elif not checks["bounded_oracle"] or not checks["unbounded_oracle"]:
        terminal = "DMC_02A_ORACLE_INVALID"
    elif not checks["control_separation"]:
        terminal = "DMC_02A_RETENTION_SIGNAL_WEAK"
    elif all(checks.values()):
        terminal = "DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS"
    else:
        terminal = "DMC_02A_REPAIR_REQUIRED"
    write_json(OUT / "DMC02A_RECEIPT.json", {
        "unit": "DMC-02A",
        "terminal_state": terminal,
        "checks": checks,
        "no_training": True,
        "no_memory_architecture": True,
        "evidence_seeds_executed": [],
        "physical_memory_budget": CAPACITY,
        "future_primary_metric": FUTURE_PRIMARY,
    })

    manifest = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest[str(path.relative_to(OUT))] = sha256(path)
    write_json(OUT / "SHA256SUMS.json", manifest)
    print(terminal)
    return 0 if terminal == "DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
