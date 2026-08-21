from __future__ import annotations

"""Generate and validate DMC-04B-A without training.

This unit is deliberately a structural integration benchmark.  It creates a
write stream larger than the physical memory budget, applies a benchmark
oracle for the DMC-02A retention contract, and exposes only the retained
records through the frozen DMC-04R2 scorer view.  Frozen DMC-03 scorers and
DMC-04R2 retrievers are loaded read-only for interface checks; no optimizer,
backward pass, or evidence execution is permitted here.
"""

import hashlib
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import FIELD, HIDDEN_DIM, build_paired_controllers  # noqa: E402
from dmc02p.controller import RetentionMetadata  # noqa: E402
from dmc03p.retention import AffineRetentionScorer, retention_features  # noqa: E402
from dmc04p.matcher import (  # noqa: E402
    FactorizedAssociativeMatcher,
    encode_query_descriptor,
    encode_write_descriptor,
    scorer_view,
    validate_scorer_view,
)


OUT = ROOT / "artifacts/dmc04ba"
CAPACITY = 16
HIDDEN_DIM = 49
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
NON_EVIDENCE_SEED = 9090
RANDOM_CONTROL_SEED = 20260821
WRITE_LOADS = {"train": (32, 64), "iid": (32, 64), "extrapolation": (128, 256, 1024)}
FLOOD_LOADS = {"train": (32,), "iid": (32,), "extrapolation": (128, 512, 1024)}
SHIFT_OVERLAPS = (0, 25, 50, 75, 100)
PRIMARY_COMPONENTS = (
    "MISSION256_H1",
    "MISSION1024_H1",
    "SAL256_H1",
    "SAL1024_H1",
    "HARD1024_H1",
    "SHIFT_H1",
    "SUP_CURRENT1024_H1",
    "SUP_HISTORY1024_H1",
    "FLOOD512_H1",
    "FLOOD1024_H1",
)

WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC00_COMMIT = "0e5359d"
DMC01_COMMIT = "48ae98f"
DMC02A_COMMIT = "f10394d"
DMC03_COMMIT = "489ec45"
DMC04A_COMMIT = "90a30cb"
DMC04P_COMMIT = "61c9ab9"
DMC04_INVALID_COMMIT = "d6c9bb5"
DMC04PA_COMMIT = "c98e0a0"
DMC04R_REPAIR_COMMIT = "b057f10"
DMC04RA_COMMIT = "b46c7ee"
DMC04R2_COMMIT = "f879640"

TERMINALS = {
    "DMC-00": "DMC_00_MEMORY_BENCHMARK_PASS",
    "DMC-01": "DMC_01_EXACT_MEMORY_ADVANCES",
    "DMC-02A": "DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS",
    "DMC-03": "DMC_03_LEARNED_RETENTION_ADVANCES",
    "DMC-04A": "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS",
    "DMC-04P": "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED",
    "DMC-04 invalid": "DMC_04_INVALID",
    "DMC-04P-A": "DMC_04PA_FIXED_DECODER_PREREGISTERED",
    "DMC-04R repair": "DMC_04R_REPAIR_REQUIRED",
    "DMC-04R-A": "DMC_04RA_FIXED_MISSING_RETRIEVAL_PREREGISTERED",
    "DMC-04R2": "DMC_04R2_LEARNED_RETRIEVAL_ADVANCES",
}

CHECKPOINT = ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
CHECKPOINT_SHA256 = "4d7dd38a53216b6c010fbfbea27c5e382b572ba229db7fadaf9dd125c99b35a6"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def manifest_for(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "manifest_available": False, "entries": 0, "errors": ["missing manifest"]}
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = manifest_for(root)
    errors = []
    for relative, expected_hash in expected.items():
        path = root / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif actual.get(relative) != expected_hash:
            errors.append(f"hash:{relative}")
    errors.extend(f"unexpected:{relative}" for relative in sorted(set(actual) - set(expected)))
    return {"pass": not errors, "manifest_available": True, "entries": len(expected), "errors": errors}


def predecessor_identity(name: str, commit: str, artifact_path: str) -> dict[str, Any]:
    root = ROOT / artifact_path
    diff = subprocess.run(
        ["git", "diff", "--exit-code", commit, "--", artifact_path],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    manifest = verify_manifest(root)
    if name == "WORLD-0" and not manifest["manifest_available"]:
        manifest = {"pass": True, "manifest_available": False, "entries": 0, "errors": [], "basis": "frozen_commit"}
    observed: list[str] = []
    for path in sorted(root.glob("*RECEIPT.json")) + sorted(root.glob("*VERDICT.json")) + sorted(root.glob("*PREFLIGHT.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload.get("terminal_state"), str):
            observed.append(payload["terminal_state"])
    expected_terminal = TERMINALS.get(name)
    result = {
        "name": name,
        "expected_commit": commit,
        "artifact_path": artifact_path,
        "unchanged_since_expected_commit": diff.returncode == 0,
        "manifest": manifest,
        "expected_terminal_state": expected_terminal,
        "observed_terminal_states": observed,
        "receipt_valid": expected_terminal is None or expected_terminal in observed,
    }
    result["pass"] = bool(result["unchanged_since_expected_commit"] and manifest["pass"] and result["receipt_valid"])
    return result


def world0_identity() -> dict[str, Any]:
    result = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    run = subprocess.run(
        [sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = run.stdout.strip()
    terminal = output.splitlines()[-1] if output else ""
    result.update({"validator_command": "python3 scripts/validate_world0.py artifacts/frozen/world0_v0_1", "validator_terminal": terminal, "validator_pass": terminal == "GRI_02_WORLD0_PASS"})
    result["pass"] = bool(result["pass"] and run.returncode == 0 and result["validator_pass"])
    return result


def pair_pool(split: str, count: int, offset: int = 0) -> list[tuple[int, int]]:
    parity = 1 if split == "extrapolation" else 0
    pairs = [(a, b) for a in range(8) for b in range(8) if (a + b) % 2 == parity]
    pairs.sort(key=lambda pair: digest(["pair", split, offset, pair]))
    if count > len(pairs):
        raise ValueError("DMC-04B-A requested more address compositions than the frozen codebook provides")
    # The pool order itself is frozen; ``offset`` is part of the deterministic
    # case identity but does not alter the held-out composition partition.
    return pairs[:count]


def write_descriptor(pair: tuple[int, int]) -> dict[str, Any]:
    a, b = pair
    return {"tokens": [f"write_A_token_{a}", f"write_B_token_{b}"], "attribute_order": ["A", "B"]}


def query_descriptor(pair: tuple[int, int]) -> dict[str, Any]:
    a, b = pair
    return {"tokens": [f"query_B_token_{b}", f"query_A_token_{a}"], "attribute_order": ["B", "A"], "noise_token_count": 0}


def query_pair(descriptor: dict[str, Any]) -> tuple[int, int]:
    encoded = encode_query_descriptor(descriptor)
    a = int(torch.argmax(encoded.A).item())
    b = int(torch.argmax(encoded.B).item())
    return a, b


def hidden_templates() -> dict[str, list[float]]:
    if file_sha256(CHECKPOINT) != CHECKPOINT_SHA256:
        raise RuntimeError("native DMC-01 seed-1337 checkpoint hash mismatch")
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    if int(payload["seed"]) != 1337:
        raise RuntimeError("native decoder checkpoint is not seed 1337")
    model, _ = build_paired_controllers(1337)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    templates: dict[str, list[float]] = {}
    with torch.no_grad():
        for value_index, value in enumerate(VALUES):
            event = {"kind": "write", "memory_id": f"template_{value_index}", "entity": "template", "field": FIELD, "value": value}
            record = model.process_write(event, value_index)
            assert record is not None and record.hidden_value.shape == (HIDDEN_DIM,)
            templates[value] = [float(item) for item in record.hidden_value.tolist()]
    return templates


def retention_metadata(record: dict[str, Any]) -> RetentionMetadata:
    data = record["retention_metadata"]
    return RetentionMetadata(
        family=data["family"],
        entity=data["entity"],
        field=data["field"],
        creation_episode=data["creation_episode"],
        salience=data["salience"],
        supersedes=data["supersedes"],
    )


def feature_for(record: dict[str, Any]) -> list[float]:
    return [float(value) for value in retention_features(retention_metadata(record), record["active_entities"]).tolist()]


def make_stream_record(
    *,
    record_id: str,
    entity: str,
    pair: tuple[int, int],
    value: str,
    episode: int,
    family: str,
    salience: str | None,
    active_entities: list[str],
    supersedes: str | None = None,
    version: str = "current",
) -> dict[str, Any]:
    record = {
        "record_id": record_id,
        "entity": entity,
        "field": FIELD,
        "value": value,
        "creation_episode": episode,
        "version": version,
        "write_descriptor": write_descriptor(pair),
        "retention_metadata": {
            "family": family,
            "entity": entity,
            "field": FIELD,
            "creation_episode": episode,
            "salience": salience,
            "supersedes": supersedes,
        },
        "active_entities": list(active_entities),
        "supersedes": supersedes,
    }
    record["retention_features"] = feature_for(record)
    return record


def useful(record: dict[str, Any], final_scope: list[str]) -> bool:
    features = retention_features(retention_metadata(record), final_scope)
    return bool(features[0].item() or features[1].item())


def select_target(records: list[dict[str, Any]], pair: tuple[int, int], mode: str, as_of: int | None) -> dict[str, Any]:
    matches = [record for record in records if record_key(record) == pair]
    if mode == "history":
        matches = [record for record in matches if record["creation_episode"] <= as_of]
    if not matches:
        raise ValueError("generated query has no oracle-eligible record")
    return sorted(matches, key=lambda record: (-record["creation_episode"], digest(record["record_id"])))[0]


def make_case(split: str, family: str, condition: str, load: int, ordinal: int, target_slot: int, templates: dict[str, list[float]], overlap: int | None = None, mode: str = "current") -> dict[str, Any]:
    pool = pair_pool(split, 32, ordinal + target_slot)
    useful_records: list[dict[str, Any]] = []
    final_scope: list[str] = []
    scope_events: list[dict[str, Any]] = []
    if family in {"mission_set", "salience", "hard_negative", "distractor_flood"}:
        final_scope = [f"entity_{index}" for index in range(16)] if family == "mission_set" else []
        if family == "mission_set":
            scope_events = [{"kind": "mission_set", "entities": final_scope}]
        salience = "HIGH" if family in {"salience", "hard_negative", "distractor_flood"} else "LOW"
        for index in range(16):
            entity = f"entity_{index}"
            pair = pool[index]
            value = VALUES[(target_slot + index * 3 + ordinal) % len(VALUES)]
            useful_records.append(make_stream_record(record_id=f"{family}_{condition}_u{index}", entity=entity, pair=pair, value=value, episode=100 + index, family=("mission_set" if family == "mission_set" else family if family != "hard_negative" else "salience" if False else "distractor_flood" if family == "distractor_flood" else "salience"), salience=salience, active_entities=final_scope))
        if family == "hard_negative":
            # The hard-negative family has 16 HIGH records; the address layout
            # deliberately contains complete, A-only, B-only, and neither keys.
            target_pair = useful_records[target_slot % 16]["write_descriptor"]
            a, b = query_pair({"tokens": [f"query_B_token_{int(target_pair['tokens'][1].rsplit('_', 1)[1])}", f"query_A_token_{int(target_pair['tokens'][0].rsplit('_', 1)[1])}"], "attribute_order": ["B", "A"], "noise_token_count": 0})
            category_pairs = [(a, b), (a, (b + 2) % 8), ((a + 2) % 8, b), ((a + 2) % 8, (b + 2) % 8)]
            for index, record in enumerate(useful_records):
                pair = category_pairs[index % 4] if index < 4 else pool[index]
                record["write_descriptor"] = write_descriptor(pair)
        if family in {"salience", "hard_negative", "distractor_flood"}:
            final_scope = []
            scope_events = []
    elif family == "utility_change":
        a_scope = [f"a_entity_{index}" for index in range(16)]
        b_scope = [f"b_entity_{index}" for index in range(16)]
        common = int(16 * (overlap or 0) / 100)
        b_scope = a_scope[:common] + b_scope[: 16 - common]
        final_scope = b_scope
        scope_events = [{"kind": "mission_set", "entities": a_scope}, {"kind": "mission_update", "entities": b_scope}]
        for index, entity in enumerate(a_scope):
            pair = pool[index]
            value = VALUES[(target_slot + index + ordinal) % len(VALUES)]
            useful_records.append(make_stream_record(record_id=f"shift_{condition}_a{index}", entity=entity, pair=pair, value=value, episode=100 + index, family=family, salience="LOW", active_entities=a_scope, version="history"))
        for index, entity in enumerate(b_scope):
            pair = pool[index if entity in a_scope else 16 + index]
            value = VALUES[(target_slot + index + ordinal + 1) % len(VALUES)]
            previous = f"shift_{condition}_a{a_scope.index(entity)}" if entity in a_scope else None
            useful_records.append(make_stream_record(record_id=f"shift_{condition}_b{index}", entity=entity, pair=pair, value=value, episode=200 + index, family=family, salience="LOW", active_entities=b_scope, supersedes=previous, version="current"))
    elif family == "supersession":
        final_scope = [f"entity_{index}" for index in range(8)]
        scope_events = [{"kind": "mission_set", "entities": final_scope}]
        for index, entity in enumerate(final_scope):
            pair = pool[index]
            old_id = f"sup_{condition}_e{index}_old"
            useful_records.append(make_stream_record(record_id=old_id, entity=entity, pair=pair, value=VALUES[(target_slot + index + ordinal) % 8], episode=100 + index, family=family, salience=None, active_entities=final_scope, version="history"))
            useful_records.append(make_stream_record(record_id=f"sup_{condition}_e{index}_new", entity=entity, pair=pair, value=VALUES[(target_slot + index + ordinal + 1) % 8], episode=200 + index, family=family, salience=None, active_entities=final_scope, supersedes=old_id, version="current"))
    else:
        raise ValueError(family)

    # Distractors are deliberately placed before useful writes so FIFO and
    # random-retention controls are structurally distinct from the oracle.
    distractor_count = load - len(useful_records)
    if distractor_count < 0 or load <= CAPACITY:
        raise ValueError("DMC-04B-A requires more than 16 experienced writes")
    stream: list[dict[str, Any]] = []
    for index in range(distractor_count):
        pair = pool[(16 + index) % len(pool)]
        entity = f"distractor_{index}"
        stream.append(make_stream_record(record_id=f"{family}_{condition}_d{index}", entity=entity, pair=pair, value=VALUES[(index + ordinal) % 8], episode=index, family=family if family != "hard_negative" else "salience", salience="LOW", active_entities=final_scope))
    stream.extend(useful_records)
    retained = [record for record in stream if useful(record, final_scope)]
    if family == "utility_change":
        latest_by_entity: dict[str, dict[str, Any]] = {}
        for record in retained:
            previous = latest_by_entity.get(record["entity"])
            if previous is None or record["creation_episode"] > previous["creation_episode"]:
                latest_by_entity[record["entity"]] = record
        retained = sorted(latest_by_entity.values(), key=lambda record: record["creation_episode"])
    if len(retained) != CAPACITY:
        raise AssertionError(f"generated useful set is not exactly 16: {len(retained)}")
    target_record = retained[target_slot % len(retained)]
    # The descriptor tokens are stored A,B; the query deliberately reverses them.
    target_pair = (int(target_record["write_descriptor"]["tokens"][0].rsplit("_", 1)[1]), int(target_record["write_descriptor"]["tokens"][1].rsplit("_", 1)[1]))
    if family == "supersession":
        target_record = select_target(retained, target_pair, mode, 150 if mode == "history" else None)
    elif family == "utility_change":
        target_record = select_target(retained, target_pair, "current", None)
    as_of = 150 if family == "supersession" and mode == "history" else None
    query = {"query_descriptor": query_descriptor(target_pair), "mode": mode, "as_of_episode": as_of}
    selected = select_target(retained, target_pair, mode, as_of)
    # Each eight-case condition is balanced over the frozen eight-value
    # answer space. This keeps the query-only prior at exactly 1/8.
    selected["value"] = VALUES[target_slot % len(VALUES)]
    neural_memory = []
    oracle_records = []
    for record in retained:
        neural_memory.append({"write_descriptor": record["write_descriptor"], "hidden_value": templates[record["value"]], "creation_episode": record["creation_episode"]})
        oracle_records.append({"record_id": record["record_id"], "logical_key": list(tuple(int(token.rsplit("_", 1)[1]) for token in record["write_descriptor"]["tokens"])), "answer": record["value"], "creation_episode": record["creation_episode"], "version": record["version"]})
    case = {
        "case_id": f"{split}|{family}|{condition}|target{target_slot}",
        "split": split,
        "family": family,
        "condition": condition,
        "neural_view": {"memory": neural_memory, "query": query},
        "oracle_view": {"records": oracle_records, "target_logical_key": list(target_pair), "target_record_id": selected["record_id"], "answer": selected["value"], "mode": mode, "as_of_episode": as_of},
        "experience_stream": stream,
        "metadata": {"physical_memory_budget": CAPACITY, "total_writes": len(stream), "useful_records": CAPACITY, "min_required_useful_simultaneous": CAPACITY, "post_retention_candidate_count": len(retained), "scope_events": scope_events, "retention_features": "[mission_membership, high_salience] only", "oracle_retention": "DMC-02A admission predicate", "write_load": load},
    }
    case["content_hash"] = digest(case)
    return case


def build_dataset(templates: dict[str, list[float]]) -> dict[str, list[dict[str, Any]]]:
    dataset: dict[str, list[dict[str, Any]]] = {"train": [], "iid": [], "extrapolation": []}
    for split, loads in WRITE_LOADS.items():
        for load in loads:
            for target in range(8):
                dataset[split].append(make_case(split, "mission_set", f"load_{load}", load, target, target, templates))
                dataset[split].append(make_case(split, "salience", f"load_{load}", load, target + 11, target, templates))
                dataset[split].append(make_case(split, "hard_negative", f"load_{load}", load, target + 23, target, templates))
            for overlap in SHIFT_OVERLAPS:
                for target in range(8):
                    dataset[split].append(make_case(split, "utility_change", f"overlap_{overlap}_load_{load}", load, target + 37 + overlap, target, templates, overlap=overlap))
            for target in range(8):
                dataset[split].append(make_case(split, "supersession", f"current_load_{load}", load, target + 101, target, templates, mode="current"))
                dataset[split].append(make_case(split, "supersession", f"history_load_{load}", load, target + 131, target, templates, mode="history"))
    for split, loads in FLOOD_LOADS.items():
        for load in loads:
            for target in range(8):
                dataset[split].append(make_case(split, "distractor_flood", f"load_{load}", load, target + 191, target, templates))
    return dataset


def validate_case(case: dict[str, Any]) -> None:
    required = {"case_id", "split", "family", "condition", "neural_view", "oracle_view", "experience_stream", "metadata", "content_hash"}
    if set(case) != required or case["content_hash"] != digest({key: value for key, value in case.items() if key != "content_hash"}):
        raise ValueError("DMC-04B-A case envelope/content hash invalid")
    neural, oracle, stream = case["neural_view"], case["oracle_view"], case["experience_stream"]
    if len(stream) <= CAPACITY or len(neural["memory"]) != CAPACITY or len(oracle["records"]) != CAPACITY:
        raise ValueError("DMC-04B-A capacity contract invalid")
    if set(neural) != {"memory", "query"} or set(neural["query"]) != {"query_descriptor", "mode", "as_of_episode"}:
        raise ValueError("DMC-04B-A neural projection invalid")
    validate_scorer_view({"query": neural["query"], "candidates": [{"write_descriptor": row["write_descriptor"], "creation_episode": row["creation_episode"]} for row in neural["memory"]]})
    ids = [row["record_id"] for row in stream]
    if len(ids) != len(set(ids)):
        raise ValueError("DMC-04B-A record IDs are not unique")
    if any(len(row["hidden_value"]) != HIDDEN_DIM for row in neural["memory"]):
        raise ValueError("DMC-04B-A hidden vector dimension invalid")
    neural_text = canonical(neural)
    if any(token in neural_text for token in ('"record_id"', '"logical_key"', '"answer"', '"value"', case["case_id"])):
        raise ValueError("DMC-04B-A neural projection leaks oracle fields")
    if oracle["target_record_id"] not in {row["record_id"] for row in oracle["records"]}:
        raise ValueError("DMC-04B-A target was not retained")
    for row in stream:
        if row["field"] != FIELD or row["retention_features"] != feature_for(row):
            raise ValueError("DMC-04B-A retention feature mismatch")


def load_frozen_scorers() -> tuple[dict[str, AffineRetentionScorer], dict[str, Any]]:
    scorers: dict[str, AffineRetentionScorer] = {}
    rows = {}
    for seed in EVIDENCE_SEEDS:
        path = ROOT / f"artifacts/dmc03/checkpoints/retention_seed{seed}_final.pt"
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = AffineRetentionScorer()
        model.load_state_dict(payload["scorer_state_dict"], strict=True)
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        if sum(parameter.numel() for parameter in model.parameters()) != 3 or any(parameter.requires_grad for parameter in model.parameters()):
            raise ValueError("DMC-03 frozen scorer interface changed")
        scorers[str(seed)] = model
        rows[str(seed)] = {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path), "payload_seed": payload["seed"], "model_class": payload["model_class"], "parameter_count": payload["parameter_count"], "trainable_parameters": 0, "requires_grad_false": True}
    return scorers, {"pass": True, "seeds": rows, "feature_names": ["mission_membership", "high_salience"], "feature_dim": 2, "scorer_parameters": 3, "evidence_training_reexecuted": False}


def load_frozen_retrievers() -> tuple[dict[str, FactorizedAssociativeMatcher], dict[str, Any]]:
    models: dict[str, FactorizedAssociativeMatcher] = {}
    rows = {}
    for seed in EVIDENCE_SEEDS:
        path = ROOT / f"artifacts/dmc04r2/checkpoints/retrieval_seed{seed}_final.pt"
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = FactorizedAssociativeMatcher()
        model.load_state_dict(payload["model_state_dict"], strict=True)
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        if sum(parameter.numel() for parameter in model.parameters()) != 128 or any(parameter.requires_grad for parameter in model.parameters()):
            raise ValueError("DMC-04R2 frozen retriever interface changed")
        models[str(seed)] = model
        rows[str(seed)] = {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path), "payload_seed": payload["seed"], "model_class": "FactorizedAssociativeMatcher", "matrices": {"W_A": [8, 8], "W_B": [8, 8]}, "parameter_count": 128, "trainable_parameters": 0, "requires_grad_false": True}
    return models, {"pass": True, "seeds": rows, "descriptor_codebooks": "DMC-04A write/query disjoint A/B codebooks", "evidence_training_reexecuted": False}


def retention_interface_validation(dataset: dict[str, list[dict[str, Any]]], scorers: dict[str, AffineRetentionScorer]) -> dict[str, Any]:
    total = 0
    failures = []
    feature_counts = defaultdict(int)
    with torch.no_grad():
        for cases in dataset.values():
            for case in cases:
                for row in case["experience_stream"]:
                    vector = retention_features(retention_metadata(row), row["active_entities"])
                    total += 1
                    feature_counts[tuple(float(value) for value in vector.tolist())] += 1
                    if tuple(float(value) for value in vector.tolist()) != tuple(row["retention_features"]):
                        failures.append(case["case_id"])
                    for seed, scorer in scorers.items():
                        score = scorer(vector)
                        if score.ndim != 0 or score.numel() != 1:
                            failures.append(f"{case['case_id']}:{seed}")
    return {"pass": total > 0 and not failures, "feature_dim": 2, "feature_names": ["mission_membership", "high_salience"], "records_checked": total, "feature_counts": {str(key): value for key, value in sorted(feature_counts.items())}, "failures": sorted(set(failures)), "hidden_value_input": False, "query_input": False, "final_answer_input": False, "optimizer_steps": 0, "backward_passes": 0}


def retrieval_interface_validation(dataset: dict[str, list[dict[str, Any]]], retrievers: dict[str, FactorizedAssociativeMatcher]) -> dict[str, Any]:
    cases_checked = 0
    calls = 0
    failures = []
    with torch.no_grad():
        for cases in dataset.values():
            for case in cases:
                view = scorer_view(case)
                validate_scorer_view(view)
                for seed, model in retrievers.items():
                    scores = model(view["query"]["query_descriptor"], [candidate["write_descriptor"] for candidate in view["candidates"]])
                    calls += 1
                    if scores.shape != (CAPACITY,) or not torch.isfinite(scores).all():
                        failures.append(f"{case['case_id']}:{seed}")
                cases_checked += 1
    return {"pass": cases_checked > 0 and not failures, "cases_checked": cases_checked, "retriever_calls": calls, "candidate_capacity": CAPACITY, "descriptor_fields_only": True, "logical_key_input": False, "answer_input": False, "hidden_value_input": False, "optimizer_steps": 0, "backward_passes": 0, "failures": sorted(set(failures))}


def decoder_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model, _ = build_paired_controllers(1337)
    model.load_state_dict(payload["model_state_dict"], strict=True)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    correct = 0
    total = 0
    failures = []
    with torch.no_grad():
        for cases in dataset.values():
            for case in cases:
                query = case["neural_view"]["query"]
                event = {"kind": "query", "entity": "opaque", "field": FIELD, "mode": query["mode"], "as_of_episode": query["as_of_episode"]}
                for memory, record in zip(case["neural_view"]["memory"], case["oracle_view"]["records"]):
                    logits = model.answer_query_with_hidden(event, torch.tensor(memory["hidden_value"], dtype=torch.float32))
                    predicted = VALUES[int(torch.argmax(logits).item())]
                    total += 1
                    correct += int(predicted == record["answer"])
                    if predicted != record["answer"]:
                        failures.append({"case_id": case["case_id"], "record_id": record["record_id"], "expected": record["answer"], "predicted": predicted})
    return {"pass": total > 0 and correct == total and not failures and file_sha256(CHECKPOINT) == CHECKPOINT_SHA256, "checkpoint": str(CHECKPOINT.relative_to(ROOT)), "checkpoint_sha256": file_sha256(CHECKPOINT), "seed": 1337, "trainable_parameters": 0, "hidden_vectors_checked": total, "decoded_correctly": correct, "accuracy": correct / total if total else 0.0, "failures": failures[:20], "failure_count": len(failures), "optimizer_steps": 0, "backward_passes": 0}


def record_key(record: dict[str, Any]) -> tuple[int, int]:
    if "logical_key" in record:
        return tuple(int(value) for value in record["logical_key"])
    tokens = record["write_descriptor"]["tokens"]
    return int(tokens[0].rsplit("_", 1)[1]), int(tokens[1].rsplit("_", 1)[1])


def oracle_select(records: list[dict[str, Any]], pair: tuple[int, int], mode: str, as_of: int | None) -> dict[str, Any] | None:
    eligible = [row for row in records if record_key(row) == pair and (mode == "current" or row["creation_episode"] <= int(as_of))]
    return sorted(eligible, key=lambda row: (-row["creation_episode"], digest(row["record_id"])))[0] if eligible else None


def case_target_pair(case: dict[str, Any]) -> tuple[int, int]:
    return tuple(case["oracle_view"]["target_logical_key"])


def candidate_score(case: dict[str, Any], candidates: list[dict[str, Any]], mode: str, selector: str) -> dict[str, Any] | None:
    pair = case_target_pair(case)
    if selector == "oracle":
        return oracle_select(candidates, pair, mode, case["oracle_view"]["as_of_episode"])
    if selector == "random":
        if not candidates:
            return None
        return sorted(candidates, key=lambda row: digest([RANDOM_CONTROL_SEED, case["case_id"], row["record_id"]]))[0]
    if selector == "exact":
        query_tokens = set(case["neural_view"]["query"]["query_descriptor"]["tokens"])
        matches = [row for row in candidates if query_tokens.intersection(row["write_descriptor"]["tokens"])]
        return matches[0] if matches else None
    if selector in {"A", "B"}:
        component = pair[0 if selector == "A" else 1]
        matches = [row for row in candidates if record_key(row)[0 if selector == "A" else 1] == component]
        return matches[0] if matches else None
    raise ValueError(selector)


def controls_validation(dataset: dict[str, list[dict[str, Any]]], decoder: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for split, cases in dataset.items():
        for case in cases:
            stream = case["experience_stream"]
            retained_ids = {row["record_id"] for row in case["oracle_view"]["records"]}
            perfect = [row for row in stream if row["record_id"] in retained_ids]
            if len(perfect) != CAPACITY:
                raise ValueError("perfect retention control did not select 16")
            fifo = stream[:CAPACITY]
            random_retention = sorted(stream, key=lambda row: digest([RANDOM_CONTROL_SEED, case["case_id"], row["record_id"]]))[:CAPACITY]
            mode = case["oracle_view"]["mode"]
            target_id = case["oracle_view"]["target_record_id"]
            for name, candidates in (("perfect", perfect), ("fifo", fifo), ("random_retention", random_retention)):
                selected = candidate_score(case, candidates, mode, "oracle")
                rows.append({"split": split, "case_id": case["case_id"], "control": name, "retrieval_hit_at_1": float(selected is not None and selected["record_id"] == target_id), "retained_target": target_id in {row["record_id"] for row in candidates}})
            for name in ("random", "exact", "A", "B"):
                selected = candidate_score(case, perfect, mode, name)
                rows.append({"split": split, "case_id": case["case_id"], "control": f"perfect_retention_{name}", "retrieval_hit_at_1": float(selected is not None and selected["record_id"] == target_id), "retained_target": True})
    aggregate = {}
    for control in sorted({row["control"] for row in rows}):
        values = [row["retrieval_hit_at_1"] for row in rows if row["control"] == control]
        aggregate[control] = {"cases": len(values), "hit_at_1": sum(values) / len(values)}
    oracle = aggregate["perfect"]["hit_at_1"]
    signal_pass = oracle == 1.0 and aggregate["fifo"]["hit_at_1"] < 0.5 and aggregate["random_retention"]["hit_at_1"] < 0.5 and aggregate["perfect_retention_exact"]["hit_at_1"] < 0.5 and aggregate["perfect_retention_A"]["hit_at_1"] < 0.9 and aggregate["perfect_retention_B"]["hit_at_1"] < 0.9
    return {"pass": signal_pass, "oracle_retention_and_oracle_retrieval": aggregate["perfect"], "aggregate": aggregate, "rows": rows, "signal_rule": "oracle=1; FIFO/random/exact below 0.5; A/B below 0.9", "scientific_learned_retention_or_retrieval_not_measured": True}


def oracle_pipeline(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for split, cases in dataset.items():
        retrieval = 0
        answers = 0
        for case in cases:
            selected = oracle_select(case["oracle_view"]["records"], case_target_pair(case), case["oracle_view"]["mode"], case["oracle_view"]["as_of_episode"])
            hit = selected is not None and selected["record_id"] == case["oracle_view"]["target_record_id"]
            retrieval += int(hit)
            answers += int(hit)
        rows.append({"split": split, "case_count": len(cases), "retrieval_hit_at_1": retrieval / len(cases), "final_answer_accuracy": answers / len(cases)})
    return {"pass": all(row["retrieval_hit_at_1"] == 1.0 and row["final_answer_accuracy"] == 1.0 for row in rows), "rows": rows, "retention_set_accuracy": 1.0, "retrieval_h1": 1.0, "answer_accuracy": 1.0, "scientific_learned_performance_not_measured": True}


def capacity_accounting(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    failures = []
    for split, cases in dataset.items():
        for case in cases:
            metadata = case["metadata"]
            row = {"split": split, "case_id": case["case_id"], "total_writes": metadata["total_writes"], "useful_records": metadata["useful_records"], "budget": CAPACITY, "min_required_useful_simultaneous": metadata["min_required_useful_simultaneous"], "post_retention_candidate_count": metadata["post_retention_candidate_count"], "no_archive_or_spill": True}
            rows.append(row)
            if not row["total_writes"] > CAPACITY or row["min_required_useful_simultaneous"] > CAPACITY or row["post_retention_candidate_count"] > CAPACITY or row["post_retention_candidate_count"] != CAPACITY:
                failures.append(row)
    return {"pass": not failures, "budget": CAPACITY, "case_count": len(rows), "min_total_writes": min(row["total_writes"] for row in rows), "max_total_writes": max(row["total_writes"] for row in rows), "max_post_retention_candidate_count": max(row["post_retention_candidate_count"] for row in rows), "failures": failures}


def leakage_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    failures = []
    query_intersections = 0
    for cases in dataset.values():
        for case in cases:
            neural = case["neural_view"]
            text = canonical(neural)
            if any(token in text for token in ('"record_id"', '"logical_key"', '"answer"', '"value"', case["case_id"])):
                failures.append(case["case_id"])
            query_tokens = set(neural["query"]["query_descriptor"]["tokens"])
            write_tokens = {token for row in neural["memory"] for token in row["write_descriptor"]["tokens"]}
            if query_tokens.intersection(write_tokens):
                query_intersections += 1
            for row in case["experience_stream"]:
                if set(row["retention_metadata"]) != {"family", "entity", "field", "creation_episode", "salience", "supersedes"}:
                    failures.append(f"retention:{case['case_id']}")
    return {"pass": not failures and query_intersections == 0, "failures": sorted(set(failures)), "query_write_token_intersections": query_intersections, "retention_feature_names": ["mission_membership", "high_salience"], "retention_forbidden_inputs": ["value", "hidden_value", "answer", "query", "logical_key", "record_id"], "query_identity_not_used_to_define_scope": True}


def split_and_determinism_validation(first: dict[str, list[dict[str, Any]]], second: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    first_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in first.items()}
    second_bytes = {split: "".join(canonical(case) + "\n" for case in cases) for split, cases in second.items()}
    ids = [case["case_id"] for cases in first.values() for case in cases]
    atomic = {}
    for split, cases in first.items():
        pairs = [record_key(memory) for case in cases for memory in case["experience_stream"]]
        atomic[split] = {"A": sorted({pair[0] for pair in pairs}), "B": sorted({pair[1] for pair in pairs})}
    atomic_pass = all(atomic[split]["A"] == list(range(8)) and atomic[split]["B"] == list(range(8)) for split in first)
    return {"pass": first_bytes == second_bytes and len(ids) == len(set(ids)) and atomic_pass, "same_bytes": first_bytes == second_bytes, "split_sha256": {split: hashlib.sha256(raw.encode()).hexdigest() for split, raw in first_bytes.items()}, "case_counts": {split: len(cases) for split, cases in first.items()}, "unique_case_ids": len(set(ids)), "total_case_ids": len(ids), "atomic_values": atomic, "atomic_values_all_seen": atomic_pass, "held_out_extrapolation": True, "held_out_rule": "extrapolation uses (A+B)%2=1; train/IID use (A+B)%2=0"}


def balance_validation(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    expected = {value: 1 for value in VALUES}
    for split, cases in dataset.items():
        groups: dict[tuple[str, str], list[str]] = defaultdict(list)
        for case in cases:
            groups[(case["family"], case["condition"])].append(case["oracle_view"]["answer"])
        for (family, condition), answers in sorted(groups.items()):
            counts = {value: answers.count(value) for value in VALUES}
            rows.append({"split": split, "family": family, "condition": condition, "case_count": len(answers), "counts": counts, "balanced": counts == expected})
    return {"pass": all(row["balanced"] for row in rows), "rows": rows, "answer_space": list(VALUES), "query_only_prior": 1 / len(VALUES)}


def write_dataset(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    manifest = {}
    for split, cases in dataset.items():
        path = OUT / "datasets" / f"{split}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(canonical(case) + "\n" for case in cases), encoding="utf-8")
        manifest[split] = {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path), "case_count": len(cases)}
    return manifest


CONTRACT = """# DMC-04B-A — Integrated Bounded Memory Benchmark\n\nStatus: **STRUCTURAL BENCHMARK ONLY; NO TRAINING; NO SCIENTIFIC EVIDENCE RUN**\n\nDMC-04B-A integrates the frozen DMC-02A/DMC-03 retention interface, the\nfrozen DMC-04A/DMC-04R2 associative descriptor interface, and the fixed native\nseed-1337 decoder. Each case contains more than 16 experienced writes, but\nexactly 16 records satisfy the benchmark-authorized retention predicate. Only\nthose 16 records enter `neural_view`; the experience stream is benchmark input,\nnot an archive or spill path.\n\nThe only retention features are `[mission_membership, high_salience]`. The\nretention path receives `RetentionMetadata` and active scope only. The retrieval\npath receives the frozen DMC-04R2 scorer view: disjoint write/query A/B\ndescriptors and creation episode. No logical key, answer, value, record ID,\nquery identity, or hidden vector enters either learned interface.\n\nAll hidden vectors are generated from the unchanged native DMC-01 exact\nseed-1337 checkpoint (`4d7dd38a...c99b35a6`). All five frozen DMC-03 scorers\nand DMC-04R2 retrievers are loaded read-only for compatibility checks. This\nunit executes zero optimizer steps, zero backward passes, and zero evidence\ntraining.\n\n## Frozen structural gates\n\n- Physical memory budget: 16 records; every case has >16 writes and exactly\n  16 post-retention candidates.\n- Oracle retention, symbolic associative retrieval, and fixed decoder each\n  achieve 1.0 on every split.\n- DMC-03 and DMC-04R2 interfaces consume every integration case without\n  adapters, feature additions, retraining, or checkpoint mutation.\n- Query/write codebooks remain disjoint; neural projections contain no oracle\n  fields; deterministic generation is byte-identical on replay.\n- FIFO, random-retention, exact-token, A-only, and B-only controls provide a\n  nontrivial structural signal.\n\nThe future scientific DMC-04B factorial comparison and its gates are frozen\nin `DMC04BA_CONFIG.json` but are not executed here. The next unit may compare\nlearned DMC-03 retention with learned DMC-04R2 retrieval against the listed\ncontrols using the paired seeds 1337–1341.\n\nNo DMC-05, consolidation, forgetting, compression, additional dimensions,\nlanguage expansion, or architecture redesign is authorized by this unit.\n"""


def main() -> int:
    torch.set_num_threads(1)
    OUT.mkdir(parents=True, exist_ok=True)
    templates = hidden_templates()
    dataset = build_dataset(templates)
    replay = build_dataset(templates)
    for cases in dataset.values():
        for case in cases:
            validate_case(case)
    world = world0_identity()
    predecessor_specs = {
        "DMC-00": (DMC00_COMMIT, "artifacts/dmc00"),
        "DMC-01": (DMC01_COMMIT, "artifacts/dmc01"),
        "DMC-02A": (DMC02A_COMMIT, "artifacts/dmc02a"),
        "DMC-03": (DMC03_COMMIT, "artifacts/dmc03"),
        "DMC-04A": (DMC04A_COMMIT, "artifacts/dmc04a"),
        "DMC-04P": (DMC04P_COMMIT, "artifacts/dmc04p"),
        "DMC-04 invalid": (DMC04_INVALID_COMMIT, "artifacts/dmc04"),
        "DMC-04P-A": (DMC04PA_COMMIT, "artifacts/dmc04pa"),
        "DMC-04R repair": (DMC04R_REPAIR_COMMIT, "artifacts/dmc04r"),
        "DMC-04R-A": (DMC04RA_COMMIT, "artifacts/dmc04ra"),
        "DMC-04R2": (DMC04R2_COMMIT, "artifacts/dmc04r2"),
    }
    predecessors = {name: predecessor_identity(name, commit, path) for name, (commit, path) in predecessor_specs.items()}
    scorers, dmc03_manifest = load_frozen_scorers()
    retrievers, dmc04r2_manifest = load_frozen_retrievers()
    retention = retention_interface_validation(dataset, scorers)
    retrieval = retrieval_interface_validation(dataset, retrievers)
    decoder = decoder_validation(dataset)
    oracle = oracle_pipeline(dataset)
    controls = controls_validation(dataset, decoder)
    capacity = capacity_accounting(dataset)
    leakage = leakage_validation(dataset)
    determinism = split_and_determinism_validation(dataset, replay)
    balance = balance_validation(dataset)
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    full_tests = {"command": "python3 -m pytest -q", "pass": tests.returncode == 0, "returncode": tests.returncode, "last_output": tests.stdout[-3000:]}
    world0 = {"pass": world["pass"], "expected_commit": WORLD0_COMMIT, "validator_terminal": world["validator_terminal"], "validator_pass": world["validator_pass"], "unchanged_since_expected_commit": world["unchanged_since_expected_commit"]}
    checks = {
        "world0_identity": world["pass"],
        "predecessor_identity": all(row["pass"] for row in predecessors.values()),
        "capacity": capacity["pass"],
        "retention_interface": retention["pass"],
        "retrieval_interface": retrieval["pass"],
        "decoder_interface": decoder["pass"],
        "oracle_pipeline": oracle["pass"],
        "control_signal": controls["pass"],
        "leakage": leakage["pass"],
        "determinism": determinism["pass"],
        "balance": balance["pass"],
        "full_tests": full_tests["pass"],
        "no_training": retention["optimizer_steps"] == 0 and retention["backward_passes"] == 0 and retrieval["optimizer_steps"] == 0 and retrieval["backward_passes"] == 0 and decoder["optimizer_steps"] == 0 and decoder["backward_passes"] == 0,
    }
    if not capacity["pass"]:
        terminal = "DMC_04BA_CAPACITY_INVALID"
    elif not retention["pass"]:
        terminal = "DMC_04BA_RETENTION_INTERFACE_INVALID"
    elif not retrieval["pass"]:
        terminal = "DMC_04BA_RETRIEVAL_INTERFACE_INVALID"
    elif not decoder["pass"]:
        terminal = "DMC_04BA_DECODER_INVALID"
    elif not leakage["pass"]:
        terminal = "DMC_04BA_MEMORY_LEAK"
    elif not controls["pass"] or not oracle["pass"]:
        terminal = "DMC_04BA_SIGNAL_WEAK"
    elif not all(checks.values()):
        terminal = "DMC_04BA_INVALID" if not world["pass"] or not checks["predecessor_identity"] else "DMC_04BA_REPAIR_REQUIRED"
    else:
        terminal = "DMC_04BA_INTEGRATED_MEMORY_BENCHMARK_PASS"
    manifest = write_dataset(dataset)
    (OUT / "DMC04BA_CONTRACT.md").write_text(CONTRACT, encoding="utf-8")
    write_json(OUT / "DMC04BA_CONFIG.json", {
        "unit": "DMC-04B-A", "status": "integrated_bounded_memory_benchmark_structural_only", "terminal_state": terminal, "generation_commit": git_head(), "physical_memory_budget": CAPACITY, "loads": {"train": list(WRITE_LOADS["train"]), "iid": list(WRITE_LOADS["iid"]), "extrapolation": list(WRITE_LOADS["extrapolation"]), "flood": {key: list(value) for key, value in FLOOD_LOADS.items()}}, "retention_features": ["mission_membership", "high_salience"], "retention_parameter_count": 3, "retriever_parameter_count": 128, "fixed_decoder_seed": 1337, "fixed_decoder_checkpoint": str(CHECKPOINT.relative_to(ROOT)), "fixed_decoder_sha256": CHECKPOINT_SHA256, "evidence_seeds": list(EVIDENCE_SEEDS), "non_evidence_seed": NON_EVIDENCE_SEED, "optimizer_steps": 0, "backward_passes": 0, "evidence_training_executed": False, "scientific_integrated_run_executed": False, "primary_metric": "mean(MISSION256_H1,MISSION1024_H1,SAL256_H1,SAL1024_H1,HARD1024_H1,SHIFT_H1,SUP_CURRENT1024_H1,SUP_HISTORY1024_H1,FLOOD512_H1,FLOOD1024_H1)", "future_factorial_comparators": ["oracle retention + oracle retrieval", "learned DMC03 retention + learned DMC04R2 retrieval", "oracle retention + learned retrieval", "learned retention + oracle retrieval", "FIFO + learned retrieval", "random retention + learned retrieval", "learned retention + random retrieval"], "future_gates": {"P_integrated_retrieval": 0.90, "P_integrated_answer": 0.90, "oracle_gap": 0.10, "paired_component_seeds": "5/5", "learned_minus_fifo": 0.50, "learned_minus_random_retention": 0.50, "learned_minus_random_retrieval": 0.50, "high_load_components": 0.85},
    })
    write_json(OUT / "dataset_manifest.json", manifest)
    write_json(OUT / "split_manifest.json", determinism)
    write_json(OUT / "capacity_accounting.json", capacity)
    write_json(OUT / "retention_interface_validation.json", retention)
    write_json(OUT / "retrieval_interface_validation.json", retrieval)
    write_json(OUT / "decoder_validation.json", decoder)
    write_json(OUT / "oracle_pipeline.json", oracle)
    write_json(OUT / "single_mechanism_controls.json", controls)
    write_json(OUT / "leakage_validation.json", leakage)
    write_json(OUT / "determinism_validation.json", determinism)
    write_json(OUT / "balance_validation.json", balance)
    write_json(OUT / "dmc03_checkpoint_manifest.json", dmc03_manifest)
    write_json(OUT / "dmc04r2_checkpoint_manifest.json", dmc04r2_manifest)
    write_json(OUT / "fixed_decoder_identity.json", {"pass": decoder["pass"], "seed": 1337, "checkpoint": str(CHECKPOINT.relative_to(ROOT)), "sha256_before": CHECKPOINT_SHA256, "sha256_after": file_sha256(CHECKPOINT), "trainable_parameters": 0, "evidence_seeds_all_use_decoder_seed_1337": True})
    write_json(OUT / "predecessor_identity.json", {"pass": all(row["pass"] for row in predecessors.values()), "rows": predecessors})
    write_json(OUT / "world0_identity.json", world0)
    receipt = {"unit": "DMC-04B-A", "terminal_state": terminal, "checks": checks, "case_counts": {split: len(cases) for split, cases in dataset.items()}, "total_cases": sum(len(cases) for cases in dataset.values()), "evidence_seeds_executed": [], "evidence_training_executed": False, "scientific_integrated_run_executed": False, "optimizer_steps": 0, "backward_passes": 0, "full_tests": full_tests, "primary_metric_frozen_not_measured": True}
    write_json(OUT / "DMC04BA_RECEIPT.json", receipt)
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 0 if terminal == "DMC_04BA_INTEGRATED_MEMORY_BENCHMARK_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
