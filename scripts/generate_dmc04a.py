from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from dmc04a.benchmark import (  # noqa: E402
    CAPACITY,
    CASES_PER_CONDITION,
    DMC01_CHECKPOINT,
    DMC01_CHECKPOINT_SHA256,
    DMC01_COMMIT,
    DMC02A_COMMIT,
    DMC03_COMMIT,
    FIELD,
    FAMILIES,
    HIDDEN_DIM,
    RANDOM_CONTROL_SEED,
    SPLIT_SPECS,
    VALUES,
    WORLD0_COMMIT,
    _groups,
    _parse_query_key,
    answer_score,
    build_dataset,
    canonical,
    composition_split,
    content_hash,
    exact_token_retrieval,
    final_answer_from_record,
    oracle_retrieval,
    primary_answer,
    primary_retrieval,
    query_only_answer,
    random_retrieval,
    score,
    single_attribute_retrieval,
    validate_balance,
    validate_case,
)


OUT = ROOT / "artifacts/dmc04a"
FUTURE_PRIMARY_RETRIEVAL = "mean(ALIAS16_H1,COMP16_H1,HARD16_H1,CURRENT16_H1,HISTORY16_H1,NOISE8_H1,NOISE32_H1)"
FUTURE_PRIMARY_ANSWER = "mean(ALIAS16_A,COMP16_A,HARD16_A,CURRENT16_A,HISTORY16_A,NOISE8_A,NOISE32_A)"

CONTRACT = r"""# DMC-04A — Associative Retrieval Benchmark

Status: **BENCHMARK ONLY; NO LEARNED RETRIEVAL; NO TRAINING**

## Claim under test

DMC-04A is a deterministic, capacity-bounded associative-retrieval exam.
The correct record is physically present in at most 16 candidates, but the
final query uses a disjoint query codebook rather than the exact write-side
address. A symbolic oracle can retrieve the correct record, while exact raw
token matching and single-attribute controls cannot.

Retention is held fixed by construction: no case asks for an evicted record.
The future DMC-04 learned-retrieval experiment must use these candidates with
perfect DMC-02 retention or a preconstructed candidate set. DMC-03 learned
retention is not used here.

## Frozen address and splits

The latent benchmark-only address is `(A, B)` with `A,B in {0,...,7}`.
Write tokens are `write_A_token_n` and `write_B_token_n`; query tokens are
`query_B_token_n` and `query_A_token_n`. The codebooks and attribute order are
disjoint, so exact token equality cannot solve the task.

Training uses the checkerboard partition `(A+B) mod 2 == 0`; extrapolation
uses the held-out partition `(A+B) mod 2 == 1`. Every atomic A and B value is
present in the training partition. IID uses the training composition regime
with fresh deterministic cases.

Families are alias retrieval, compositional retrieval, hard negatives,
current/history version retrieval, and irrelevant cue noise. All candidate
sets contain at most 16 physical records. The query contains no answer value,
record ID, or logical-key object. Logical keys and answer labels exist only in
the separate oracle projection.

The stored neural value is produced by the frozen DMC-01 exact processor
(seed 1337 checkpoint); no DMC-04A model is trained or modified. The final
answer oracle passes the selected hidden vector through that frozen processor.

## Future primary metrics

```text
P_retrieval = mean(ALIAS16_H1, COMP16_H1, HARD16_H1,
                   CURRENT16_H1, HISTORY16_H1, NOISE8_H1, NOISE32_H1)
P_answer    = mean(ALIAS16_A, COMP16_A, HARD16_A,
                   CURRENT16_A, HISTORY16_A, NOISE8_A, NOISE32_A)
```

These metrics are frozen for DMC-04P/DMC-04. Retrieval Hit@1 and final answer
accuracy are recorded separately; answer accuracy alone is not sufficient.

## Controls and terminal states

The benchmark records a symbolic oracle, a deterministic random selector,
exact-token matching, A-only/B-only controls, and a query-only answer-prior
control. The symbolic oracle must achieve 1.0 retrieval and final answer
accuracy. Query-only must remain at the balanced 1/8 prior. At extrapolated
hard negatives, each single-attribute control must be at least 0.40 below
oracle Hit@1. Exact-token Hit@1 must remain at or below 0.10 on the 16-record
extrapolation conditions.

Terminal states:

- `DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS`
- `DMC_04A_MEMORY_LEAK`
- `DMC_04A_ADDRESS_LEAK`
- `DMC_04A_ORACLE_INVALID`
- `DMC_04A_RETRIEVAL_SIGNAL_WEAK`
- `DMC_04A_INVALID`
- `DMC_04A_REPAIR_REQUIRED`

This unit stops after its validated benchmark commit. It does not implement a
learned retriever, attention, similarity, neural key projection, training,
evidence seeds, DMC-04P, or DMC-04B.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def manifest_for(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "manifest_available": False, "errors": ["missing SHA256SUMS.json"]}
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = manifest_for(root)
    errors = []
    for relative, digest in expected.items():
        path = root / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif actual.get(relative) != digest:
            errors.append(f"hash:{relative}")
    errors.extend(f"unexpected:{relative}" for relative in sorted(set(actual) - set(expected)))
    return {"pass": not errors, "manifest_available": True, "entries": len(expected), "errors": errors}


def predecessor_identity(name: str, expected_commit: str, artifact_path: str, terminal: str | None = None) -> dict[str, Any]:
    path = ROOT / artifact_path
    diff = subprocess.run(["git", "diff", "--exit-code", expected_commit, "--", artifact_path], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    manifest = verify_manifest(path)
    if name == "WORLD-0" and not manifest["manifest_available"]:
        manifest = {"pass": True, "manifest_available": False, "entries": 0, "errors": [], "verification_basis": "frozen_git_commit_boundary"}
    payload: dict[str, Any] = {
        "name": name,
        "expected_commit": expected_commit,
        "artifact_path": artifact_path,
        "unchanged_since_expected_commit": diff.returncode == 0,
        "manifest": manifest,
    }
    if terminal is not None:
        receipt_candidates = sorted(path.glob("*RECEIPT.json")) + sorted(path.glob("*VERDICT.json"))
        receipts = []
        for receipt in receipt_candidates:
            try:
                data = json.loads(receipt.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if "terminal_state" in data:
                receipts.append(data["terminal_state"])
        payload["expected_terminal_state"] = terminal
        payload["observed_terminal_states"] = receipts
        payload["receipt_valid"] = terminal in receipts
    payload["pass"] = bool(payload["unchanged_since_expected_commit"] and payload["manifest"]["pass"] and payload.get("receipt_valid", True))
    return payload


def predecessor_validation() -> dict[str, Any]:
    world = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    world_run = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    world["validator_output"] = world_run.stdout.strip()
    world["validator_terminal"] = world_run.stdout.strip().splitlines()[-1] if world_run.stdout.strip() else ""
    world["validator_pass"] = world["validator_terminal"] == "GRI_02_WORLD0_PASS"
    world["pass"] = bool(world["pass"] and world["validator_pass"])
    rows = [
        world,
        predecessor_identity("DMC-00", "0e5359d", "artifacts/dmc00", "DMC_00_MEMORY_BENCHMARK_PASS"),
        predecessor_identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01", "DMC_01_EXACT_MEMORY_ADVANCES"),
        predecessor_identity("DMC-02A", DMC02A_COMMIT, "artifacts/dmc02a", "DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS"),
        predecessor_identity("DMC-03", DMC03_COMMIT, "artifacts/dmc03", "DMC_03_LEARNED_RETENTION_ADVANCES"),
    ]
    return {"pass": all(row["pass"] for row in rows), "predecessors": rows}


def split_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    seen_ids: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    collisions = []
    for split, cases in dataset.items():
        for case in cases:
            if case["case_id"] in seen_ids:
                collisions.append({"kind": "case_id", "value": case["case_id"], "first": seen_ids[case["case_id"]], "second": split})
            seen_ids[case["case_id"]] = split
            if case["content_hash"] in seen_hashes:
                collisions.append({"kind": "content_hash", "value": case["content_hash"], "first": seen_hashes[case["content_hash"]], "second": split})
            seen_hashes[case["content_hash"]] = split
    composition = composition_split()
    train_atoms = {tuple(pair) for pair in composition["train"]}
    held_out = {tuple(pair) for pair in composition["held_out_composition"]}
    return {
        "pass": not collisions and not train_atoms.intersection(held_out) and set(composition["train_atomic_A"]) == set(range(8)) and set(composition["train_atomic_B"]) == set(range(8)),
        "case_counts": {split: len(cases) for split, cases in dataset.items()},
        "unique_case_ids": len(seen_ids),
        "unique_content_hashes": len(seen_hashes),
        "cross_split_collisions": collisions,
        "composition_partition": composition,
    }


def capacity_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    failures = []
    for split, cases in dataset.items():
        for case in cases:
            count = len(case["neural_view"]["memory"])
            row = {"split": split, "case_id": case["case_id"], "candidate_count": count, "budget": CAPACITY, "target_present": case["oracle_view"]["target_record_id"] in {record["record_id"] for record in case["oracle_view"]["records"]}, "valid": count <= CAPACITY and count >= 1}
            rows.append(row)
            if not row["valid"] or not row["target_present"]:
                failures.append(row)
    return {"pass": not failures, "budget": CAPACITY, "case_count": len(rows), "failures": failures, "max_candidates": max(row["candidate_count"] for row in rows)}


def leakage_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for split, cases in dataset.items():
        for case in cases:
            neural_text = canonical(case["neural_view"])
            query = case["neural_view"]["query"]
            query_only_hit = query_only_answer(case) == case["oracle_view"]["answer"]
            rows.append({
                "split": split,
                "case_id": case["case_id"],
                "answer_key_in_neural": '"answer"' in neural_text,
                "logical_key_key_in_neural": '"logical_key"' in neural_text,
                "record_id_key_in_neural": '"record_id"' in neural_text,
                "case_id_in_neural": case["case_id"] in neural_text,
                "query_has_answer_fields": any(key in query for key in ("answer", "value", "logical_key", "record_id")),
                "query_only_hit": query_only_hit,
                "write_query_token_intersection": sorted(set(query["query_descriptor"]["tokens"]) & {token for memory in case["neural_view"]["memory"] for token in memory["write_descriptor"]["tokens"]}),
            })
    query_only_accuracy = sum(row["query_only_hit"] for row in rows) / len(rows)
    return {"pass": all(not row["answer_key_in_neural"] and not row["logical_key_key_in_neural"] and not row["record_id_key_in_neural"] and not row["case_id_in_neural"] and not row["query_has_answer_fields"] and not row["write_query_token_intersection"] for row in rows) and query_only_accuracy == 1 / 8, "case_count": len(rows), "query_only_accuracy": query_only_accuracy, "designed_prior": 1 / 8, "rows": rows}


def determinism_validation(first: dict[str, list[dict[str, Any]]], second: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    first_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in first.items()}
    second_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in second.items()}
    random_first = [random_retrieval(case) for case in first["extrapolation"]]
    random_second = [random_retrieval(case) for case in second["extrapolation"]]
    return {"pass": first_bytes == second_bytes and random_first == random_second, "split_sha256": {split: hashlib.sha256(data.encode()).hexdigest() for split, data in first_bytes.items()}, "same_bytes": first_bytes == second_bytes, "same_random_replay": random_first == random_second}


def condition_rows(dataset: dict[str, list[dict[str, Any]]], selector: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    rows = []
    for (split, family, condition), cases in sorted(_groups(dataset).items()):
        rows.append({"split": split, "family": family, "condition": condition, "case_count": len(cases), "retrieval_hit_at_1": score(cases, selector), "answer_accuracy": answer_score(cases, selector)})
    return rows


def control_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    extrap = dataset["extrapolation"]
    oracle_retrieval_primary = primary_retrieval(extrap, oracle_retrieval)
    random_primary = primary_retrieval(extrap, random_retrieval)
    exact_primary = primary_retrieval(extrap, exact_token_retrieval)
    hard = [case for case in extrap if case["family"] == "hard_negative"]
    oracle_hard = score(hard, oracle_retrieval)
    a_hard = score(hard, lambda case: single_attribute_retrieval(case, "A"))
    b_hard = score(hard, lambda case: single_attribute_retrieval(case, "B"))
    random_n16 = [case for case in extrap if len(case["oracle_view"]["records"]) == 16]
    random_n16_hit = score(random_n16, random_retrieval)
    return {
        "random": {"seed": RANDOM_CONTROL_SEED, "primary": random_primary, "n16_hit_at_1": random_n16_hit, "expected_n16": 1 / 16, "pass": 0.0 <= random_n16_hit <= 0.20},
        "exact_token": {"primary": exact_primary, "n16_threshold": 0.10, "pass": exact_primary["P_retrieval"] <= 0.10},
        "single_attribute": {"hard_oracle": oracle_hard, "hard_A_only": a_hard, "hard_B_only": b_hard, "oracle_minus_A": oracle_hard - a_hard, "oracle_minus_B": oracle_hard - b_hard, "threshold": 0.40, "pass": oracle_hard - a_hard >= 0.40 and oracle_hard - b_hard >= 0.40},
        "oracle_primary": oracle_retrieval_primary,
    }


def oracle_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for split, cases in dataset.items():
        rows.append({"split": split, "retrieval_hit_at_1": score(cases, oracle_retrieval), "symbolic_final_answer_accuracy": answer_score(cases, oracle_retrieval), "case_count": len(cases)})
    return {"pass": all(row["retrieval_hit_at_1"] == 1.0 and row["symbolic_final_answer_accuracy"] == 1.0 for row in rows), "rows": rows}


def final_processor_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checkpoint = ROOT / DMC01_CHECKPOINT
    if sha256(checkpoint) != DMC01_CHECKPOINT_SHA256:
        return {"pass": False, "error": "DMC-01 checkpoint hash mismatch"}
    from dmc01.memory import build_paired_controllers

    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model, _ = build_paired_controllers(int(payload["seed"]))
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    rows = []
    with torch.no_grad():
        for split, cases in dataset.items():
            correct = 0
            for case in cases:
                target_id = oracle_retrieval(case)
                record = next(item for item in case["oracle_view"]["records"] if item["record_id"] == target_id)
                index = next(i for i, item in enumerate(case["oracle_view"]["records"]) if item["record_id"] == target_id)
                hidden = torch.tensor(case["neural_view"]["memory"][index]["hidden_value"], dtype=torch.float32)
                query = case["neural_view"]["query"]
                event = {"kind": "query", "entity": "opaque", "field": FIELD, "mode": query["mode"], "as_of_episode": query["as_of_episode"]}
                logits = model.answer_query_with_hidden(event, hidden)
                predicted = VALUES[int(torch.argmax(logits).item())]
                correct += int(predicted == record["answer"] == case["oracle_view"]["answer"])
            rows.append({"split": split, "case_count": len(cases), "accuracy": correct / len(cases)})
    return {"pass": all(row["accuracy"] == 1.0 for row in rows), "processor": "DMC-01 exact seed 1337", "checkpoint": DMC01_CHECKPOINT, "checkpoint_sha256": DMC01_CHECKPOINT_SHA256, "rows": rows}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    for cases in dataset.values():
        for case in cases:
            validate_case(case)
    second_dataset = build_dataset()
    predecessor = predecessor_validation()
    balance = validate_balance(dataset)
    split = split_validation(dataset)
    capacity = capacity_validation(dataset)
    leakage = leakage_validation(dataset)
    determinism = determinism_validation(dataset, second_dataset)
    oracle = oracle_validation(dataset)
    controls = control_validation(dataset)
    final_processor = final_processor_validation(dataset)

    write_json(OUT / "DMC04A_CONFIG.json", {
        "unit": "DMC-04A",
        "status": "associative_retrieval_benchmark_only",
        "generation_commit": git_commit(),
        "values": list(VALUES),
        "cases_per_condition": CASES_PER_CONDITION,
        "physical_memory_budget": CAPACITY,
        "split_specs": SPLIT_SPECS,
        "random_control_seed": RANDOM_CONTROL_SEED,
        "hidden_dim": HIDDEN_DIM,
        "frozen_processor": {"checkpoint": DMC01_CHECKPOINT, "checkpoint_sha256": DMC01_CHECKPOINT_SHA256, "dmc01_commit": DMC01_COMMIT},
        "future_primary_retrieval": FUTURE_PRIMARY_RETRIEVAL,
        "future_primary_answer": FUTURE_PRIMARY_ANSWER,
        "no_learned_retrieval": True,
        "no_training": True,
        "no_evidence_seeds": True,
    })
    (OUT / "DMC04A_CONTRACT.md").write_text(CONTRACT, encoding="utf-8")

    dataset_manifest = {}
    for split_name, cases in dataset.items():
        path = OUT / "datasets" / f"{split_name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(canonical(case) + "\n" for case in cases), encoding="utf-8")
        dataset_manifest[split_name] = {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "case_count": len(cases)}
    write_json(OUT / "dataset_manifest.json", dataset_manifest)
    write_json(OUT / "codebook_spec.json", {"write": {"A": [f"write_A_token_{i}" for i in range(8)], "B": [f"write_B_token_{i}" for i in range(8)]}, "query": {"A": [f"query_A_token_{i}" for i in range(8)], "B": [f"query_B_token_{i}" for i in range(8)]}, "write_query_disjoint": True, "query_order": ["B", "A"], "write_order": ["A", "B"]})
    write_json(OUT / "composition_split.json", composition_split())
    write_json(OUT / "split_manifest.json", split)
    write_json(OUT / "balance_validation.json", balance)
    write_json(OUT / "oracle_validation.json", oracle)
    write_json(OUT / "final_answer_validation.json", final_processor)
    write_json(OUT / "query_only_control.json", {"pass": leakage["query_only_accuracy"] == 1 / 8, "classifier": "always RED", "accuracy": leakage["query_only_accuracy"], "designed_prior": 1 / 8})
    write_json(OUT / "random_retrieval_control.json", {"pass": controls["random"]["pass"], **controls["random"], "rows": condition_rows(dataset, random_retrieval)})
    write_json(OUT / "exact_token_control.json", {"pass": controls["exact_token"]["pass"], **controls["exact_token"], "rows": condition_rows(dataset, exact_token_retrieval)})
    write_json(OUT / "single_attribute_controls.json", {"pass": controls["single_attribute"]["pass"], **controls["single_attribute"], "rows_A": condition_rows(dataset, lambda case: single_attribute_retrieval(case, "A")), "rows_B": condition_rows(dataset, lambda case: single_attribute_retrieval(case, "B"))})
    write_json(OUT / "leakage_validation.json", leakage)
    write_json(OUT / "determinism_validation.json", determinism)
    write_json(OUT / "capacity_validation.json", capacity)
    for identity in predecessor["predecessors"]:
        filename = {"WORLD-0": "world0_identity.json", "DMC-00": "dmc00_identity.json", "DMC-01": "dmc01_identity.json", "DMC-02A": "dmc02a_identity.json", "DMC-03": "dmc03_identity.json"}[identity["name"]]
        write_json(OUT / filename, identity)

    checks = {
        "predecessors": predecessor["pass"],
        "capacity": capacity["pass"],
        "oracle": oracle["pass"] and final_processor["pass"],
        "balance": balance["pass"],
        "split_disjointness": split["pass"],
        "leakage": leakage["pass"],
        "determinism": determinism["pass"],
        "random_control": controls["random"]["pass"],
        "exact_token_control": controls["exact_token"]["pass"],
        "single_attribute_controls": controls["single_attribute"]["pass"],
    }
    if not checks["predecessors"]:
        terminal = "DMC_04A_INVALID"
    elif not checks["leakage"]:
        terminal = "DMC_04A_MEMORY_LEAK"
    elif not checks["exact_token_control"]:
        terminal = "DMC_04A_ADDRESS_LEAK"
    elif not checks["oracle"]:
        terminal = "DMC_04A_ORACLE_INVALID"
    elif not checks["single_attribute_controls"]:
        terminal = "DMC_04A_RETRIEVAL_SIGNAL_WEAK"
    elif all(checks.values()):
        terminal = "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS"
    else:
        terminal = "DMC_04A_REPAIR_REQUIRED"
    write_json(OUT / "DMC04A_RECEIPT.json", {
        "unit": "DMC-04A",
        "terminal_state": terminal,
        "checks": checks,
        "no_learned_retrieval": True,
        "no_training": True,
        "no_evidence_seeds": True,
        "physical_memory_budget": CAPACITY,
        "future_primary_retrieval": FUTURE_PRIMARY_RETRIEVAL,
        "future_primary_answer": FUTURE_PRIMARY_ANSWER,
    })
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 0 if terminal == "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
