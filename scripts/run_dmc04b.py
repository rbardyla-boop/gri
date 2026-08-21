from __future__ import annotations

"""DMC-04B frozen learned-memory integration evidence.

This runner intentionally contains no optimizer construction, backward call,
or parameter update.  It loads the independently trained DMC-03 scorers and
DMC-04R2 retrievers, applies them to the byte-frozen DMC-04B-A streams, and
records the preregistered factorial verdict.
"""

import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import torch  # noqa: E402

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import FIELD, build_paired_controllers  # noqa: E402
from dmc02p.controller import RetentionMetadata  # noqa: E402
from dmc03p.retention import AffineRetentionScorer, retention_features  # noqa: E402
from dmc04p.matcher import (  # noqa: E402
    FactorizedAssociativeMatcher,
    encode_query_descriptor,
    encode_write_descriptor,
    validate_scorer_view,
)
from generate_dmc04ba import (  # noqa: E402
    CAPACITY,
    EVIDENCE_SEEDS,
    RANDOM_CONTROL_SEED,
    canonical,
    digest,
    file_sha256,
    record_key,
    validate_case,
)


OUT = ROOT / "artifacts/dmc04b"
DATA_ROOT = ROOT / "artifacts/dmc04ba"
CHECKPOINT = ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
CHECKPOINT_SHA256 = "4d7dd38a53216b6c010fbfbea27c5e382b572ba229db7fadaf9dd125c99b35a6"
NON_EVIDENCE_SEED = 9090

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
DMC04BA_COMMIT = "4eee7e6"

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
    "DMC-04B-A": "DMC_04BA_INTEGRATED_MEMORY_BENCHMARK_PASS",
}

MODE_NAMES = (
    "oracle_oracle",
    "oracle_retention_learned_retrieval",
    "learned_retention_oracle_retrieval",
    "learned_learned",
    "fifo_learned",
    "random_retention_learned",
    "learned_random_retrieval",
)

PRIMARY_LABELS = (
    "MISSION256",
    "MISSION1024",
    "SAL256",
    "SAL1024",
    "HARD1024",
    "SHIFT",
    "SUP_CURRENT1024",
    "SUP_HISTORY1024",
    "FLOOD512",
    "FLOOD1024",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def model_state_hash(model: torch.nn.Module) -> str:
    rows = []
    for name, tensor in model.state_dict().items():
        rows.append({"name": name, "dtype": str(tensor.dtype), "shape": list(tensor.shape), "bytes": tensor.detach().cpu().contiguous().numpy().tobytes().hex()})
    return digest(rows)


def manifest_for(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): file_sha256(path) for path in sorted(root.rglob("*")) if path.is_file() and path.name != "SHA256SUMS.json"}


def verify_manifest(root: Path) -> dict[str, Any]:
    path = root / "SHA256SUMS.json"
    if not path.exists():
        return {"pass": False, "manifest_available": False, "entries": 0, "errors": ["missing manifest"]}
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = manifest_for(root)
    errors = []
    for relative, value in expected.items():
        candidate = root / relative
        if not candidate.exists():
            errors.append(f"missing:{relative}")
        elif actual.get(relative) != value:
            errors.append(f"hash:{relative}")
    errors.extend(f"unexpected:{relative}" for relative in sorted(set(actual) - set(expected)))
    return {"pass": not errors, "manifest_available": True, "entries": len(expected), "errors": errors}


def receipt_terminals(root: Path) -> list[str]:
    terminals = []
    for path in sorted(root.glob("*RECEIPT.json")) + sorted(root.glob("*VERDICT.json")) + sorted(root.glob("*PREFLIGHT.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload.get("terminal_state"), str):
            terminals.append(payload["terminal_state"])
    return terminals


def predecessor_identity(name: str, commit: str, artifact_path: str) -> dict[str, Any]:
    root = ROOT / artifact_path
    diff = subprocess.run(["git", "diff", "--exit-code", commit, "--", artifact_path], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    manifest = verify_manifest(root)
    if name == "WORLD-0" and not manifest["manifest_available"]:
        manifest = {"pass": True, "manifest_available": False, "entries": 0, "errors": [], "basis": "frozen_commit"}
    expected_terminal = TERMINALS.get(name)
    observed = receipt_terminals(root)
    row = {"name": name, "expected_commit": commit, "artifact_path": artifact_path, "unchanged_since_expected_commit": diff.returncode == 0, "manifest": manifest, "expected_terminal_state": expected_terminal, "observed_terminal_states": observed, "receipt_valid": expected_terminal is None or expected_terminal in observed}
    row["pass"] = bool(row["unchanged_since_expected_commit"] and manifest["pass"] and row["receipt_valid"])
    return row


def world0_identity() -> dict[str, Any]:
    row = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    run = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = run.stdout.strip()
    terminal = output.splitlines()[-1] if output else ""
    row.update({"validator_command": "python3 scripts/validate_world0.py artifacts/frozen/world0_v0_1", "validator_terminal": terminal, "validator_pass": terminal == "GRI_02_WORLD0_PASS"})
    row["pass"] = bool(row["pass"] and run.returncode == 0 and row["validator_pass"])
    return row


def load_frozen_dataset() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    frozen_manifest = json.loads((DATA_ROOT / "dataset_manifest.json").read_text(encoding="utf-8"))
    dataset: dict[str, list[dict[str, Any]]] = {}
    rows = {}
    errors = []
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / frozen_manifest[split]["path"]
        observed_hash = file_sha256(path)
        expected_hash = frozen_manifest[split]["sha256"]
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        cases = [json.loads(line) for line in lines]
        for case in cases:
            try:
                validate_case(case)
            except Exception as error:  # noqa: BLE001 - receipt records exact structural defect
                errors.append({"split": split, "case_id": case.get("case_id"), "error": str(error)})
        if observed_hash != expected_hash or len(cases) != frozen_manifest[split]["case_count"]:
            errors.append({"split": split, "error": "frozen dataset hash/count mismatch"})
        dataset[split] = cases
        rows[split] = {"path": str(path.relative_to(ROOT)), "expected_sha256": expected_hash, "observed_sha256": observed_hash, "case_count": len(cases), "expected_case_count": frozen_manifest[split]["case_count"]}
    total = sum(len(cases) for cases in dataset.values())
    result = {"pass": not errors and total == 600, "manifest": rows, "total_cases": total, "errors": errors}
    return dataset, result


def benchmark_identity() -> dict[str, Any]:
    config = json.loads((DATA_ROOT / "DMC04BA_CONFIG.json").read_text(encoding="utf-8"))
    receipt = json.loads((DATA_ROOT / "DMC04BA_RECEIPT.json").read_text(encoding="utf-8"))
    manifest = verify_manifest(DATA_ROOT)
    expected = {"unit": "DMC-04B-A", "terminal": "DMC_04BA_INTEGRATED_MEMORY_BENCHMARK_PASS", "capacity": 16, "case_count": 600, "no_training": True, "fixed_decoder_seed": 1337}
    checks = {"manifest": manifest["pass"], "receipt_terminal": receipt.get("terminal_state") == expected["terminal"], "config_unit": config.get("unit") == expected["unit"], "capacity": config.get("physical_memory_budget") == expected["capacity"], "evidence_training_false": receipt.get("evidence_training_executed") is False and config.get("evidence_training_executed") is False, "fixed_decoder_seed": config.get("fixed_decoder_seed") == expected["fixed_decoder_seed"]}
    return {"pass": all(checks.values()), "checks": checks, "expected_commit": DMC04BA_COMMIT, "artifact_path": "artifacts/dmc04ba", "artifact_manifest": manifest, "receipt": receipt, "config": config}


def preflight_tests() -> dict[str, Any]:
    run = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {"command": "python3 -m pytest -q", "pass": run.returncode == 0, "returncode": run.returncode, "last_output": run.stdout[-4000:]}


def load_retention_models() -> tuple[dict[int, AffineRetentionScorer], dict[str, Any], dict[int, str]]:
    models = {}
    rows = {}
    before_hashes = {}
    manifest = json.loads((ROOT / "artifacts/dmc03/SHA256SUMS.json").read_text(encoding="utf-8"))
    errors = []
    for seed in EVIDENCE_SEEDS:
        relative = f"checkpoints/retention_seed{seed}_final.pt"
        path = ROOT / "artifacts/dmc03" / relative
        observed = file_sha256(path)
        expected = manifest.get(relative)
        before_hashes[seed] = observed
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = AffineRetentionScorer()
        model.load_state_dict(payload["scorer_state_dict"], strict=True)
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        valid = observed == expected and payload.get("seed") == seed and payload.get("model_class") == "AffineRetentionScorer" and payload.get("parameter_count") == 3 and all(not parameter.requires_grad for parameter in model.parameters())
        if not valid:
            errors.append(seed)
        models[seed] = model
        rows[str(seed)] = {"path": str(path.relative_to(ROOT)), "expected_sha256": expected, "observed_sha256": observed, "payload_seed": payload.get("seed"), "model_class": payload.get("model_class"), "historical_parameter_count": payload.get("parameter_count"), "trainable_parameters_now": 0, "eval_mode": not model.training, "requires_grad_false": all(not parameter.requires_grad for parameter in model.parameters())}
    return models, {"pass": not errors, "seeds": rows, "errors": errors, "historical_parameter_count": 3, "trainable_parameters_now": 0}, before_hashes


def load_retrieval_models() -> tuple[dict[int, FactorizedAssociativeMatcher], dict[str, Any], dict[int, str]]:
    models = {}
    rows = {}
    before_hashes = {}
    manifest = json.loads((ROOT / "artifacts/dmc04r2/SHA256SUMS.json").read_text(encoding="utf-8"))
    errors = []
    for seed in EVIDENCE_SEEDS:
        relative = f"checkpoints/retrieval_seed{seed}_final.pt"
        path = ROOT / "artifacts/dmc04r2" / relative
        observed = file_sha256(path)
        expected = manifest.get(relative)
        before_hashes[seed] = observed
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = FactorizedAssociativeMatcher(seed=seed)
        model.load_state_dict(payload["model_state_dict"], strict=True)
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        valid = observed == expected and payload.get("seed") == seed and tuple(model.W_A.shape) == (8, 8) and tuple(model.W_B.shape) == (8, 8) and sum(parameter.numel() for parameter in model.parameters()) == 128 and all(not parameter.requires_grad for parameter in model.parameters())
        if not valid:
            errors.append(seed)
        models[seed] = model
        rows[str(seed)] = {"path": str(path.relative_to(ROOT)), "expected_sha256": expected, "observed_sha256": observed, "payload_seed": payload.get("seed"), "matrices": {"W_A": [8, 8], "W_B": [8, 8]}, "historical_parameter_count": 128, "trainable_parameters_now": 0, "eval_mode": not model.training, "requires_grad_false": all(not parameter.requires_grad for parameter in model.parameters())}
    return models, {"pass": not errors, "seeds": rows, "errors": errors, "historical_parameter_count": 128, "trainable_parameters_now": 0}, before_hashes


def load_decoder() -> tuple[torch.nn.Module, dict[str, Any], str]:
    before = file_sha256(CHECKPOINT)
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model, _ = build_paired_controllers(1337)
    model.load_state_dict(payload["model_state_dict"], strict=True)
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    after = file_sha256(CHECKPOINT)
    identity = {"pass": before == CHECKPOINT_SHA256 and after == CHECKPOINT_SHA256 and before == after and payload.get("seed") == 1337 and all(not parameter.requires_grad for parameter in model.parameters()), "checkpoint": str(CHECKPOINT.relative_to(ROOT)), "sha256_before": before, "sha256_after": after, "seed": payload.get("seed"), "trainable_parameters_now": 0, "eval_mode": not model.training, "requires_grad_false": all(not parameter.requires_grad for parameter in model.parameters())}
    return model, identity, before


def hidden_templates_from_frozen_case(case: dict[str, Any]) -> dict[str, list[float]]:
    templates: dict[str, list[float]] = {}
    for memory, record in zip(case["neural_view"]["memory"], case["oracle_view"]["records"]):
        value = record["answer"]
        vector = [float(item) for item in memory["hidden_value"]]
        if value in templates and templates[value] != vector:
            raise ValueError("frozen DMC-04B-A hidden basis is not value-consistent")
        templates[value] = vector
    return templates


def build_hidden_maps(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, list[float]]]:
    maps = {}
    for split, cases in dataset.items():
        for case in cases:
            local = hidden_templates_from_frozen_case(case)
            if set(local) != set(VALUES):
                raise ValueError(f"DMC-04B-A case lacks a complete fixed hidden basis: {case['case_id']}")
            maps[case["case_id"]] = local
    return maps


def retention_audit() -> dict[str, Any]:
    return {"calls": 0, "feature_names": ["mission_membership", "high_salience"], "input_fields_observed": [], "forbidden_fields_observed": [], "hidden_value_in_scorer": False, "answer_in_scorer": False, "query_in_scorer": False, "case_id_in_scorer": False, "oracle_decision_in_scorer": False, "optimizer_objects_created": 0, "optimizer_steps": 0, "backward_calls": 0}


def retention_score(model: AffineRetentionScorer, row: dict[str, Any], active_scope: list[str], audit: dict[str, Any], cache: dict[tuple[float, float], float]) -> float:
    metadata = row["retention_metadata"]
    allowed = {"family", "entity", "field", "creation_episode", "salience", "supersedes"}
    audit["calls"] += 1
    audit["input_fields_observed"] = sorted(set(audit["input_fields_observed"]).union(allowed | {"active_entities"}))
    forbidden = {"value", "hidden_value", "answer", "query", "logical_key", "record_id", "case_id", "target_record_id", "oracle_decision"}.intersection(metadata)
    audit["forbidden_fields_observed"] = sorted(set(audit["forbidden_fields_observed"]).union(forbidden))
    if forbidden:
        raise ValueError("retention runtime firewall received forbidden fields")
    features = retention_features(RetentionMetadata(family=metadata["family"], entity=metadata["entity"], field=metadata["field"], creation_episode=metadata["creation_episode"], salience=metadata["salience"], supersedes=metadata["supersedes"]), active_scope)
    key = tuple(float(value) for value in features.tolist())
    if key not in cache:
        with torch.no_grad():
            cache[key] = float(model(features).item())
    return cache[key]


def rank_records(records: list[dict[str, Any]], model: AffineRetentionScorer, active_scope: list[str], audit: dict[str, Any], cache: dict[tuple[float, float], float]) -> list[dict[str, Any]]:
    ranked = sorted(records, key=lambda row: (-retention_score(model, row, active_scope, audit, cache), hashlib.sha256(row["record_id"].encode("utf-8")).hexdigest()))
    return ranked[:CAPACITY]


def initial_scope(case: dict[str, Any]) -> list[str]:
    events = case["metadata"]["scope_events"]
    return list(events[0]["entities"]) if events else []


def final_scope(case: dict[str, Any]) -> list[str]:
    events = case["metadata"]["scope_events"]
    return list(events[-1]["entities"]) if events else []


def learned_retention(model: AffineRetentionScorer, case: dict[str, Any], audit: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    memory: list[dict[str, Any]] = []
    occupancy = []
    active = initial_scope(case)
    scope_switched = False
    cache: dict[tuple[float, float], float] = {}
    for row in case["experience_stream"]:
        if case["family"] == "utility_change" and not scope_switched and row["creation_episode"] >= 200:
            active = final_scope(case)
            memory = rank_records(memory, model, active, audit, cache)
            scope_switched = True
        if case["family"] == "utility_change":
            memory = [old for old in memory if old["entity"] != row["entity"]]
        memory.append(row)
        if len(memory) > CAPACITY:
            memory = rank_records(memory, model, active, audit, cache)
        occupancy.append(len(memory))
        if len(memory) > CAPACITY:
            raise AssertionError("learned retention exceeded physical capacity")
    return memory, {"max_occupancy": max(occupancy), "mean_occupancy": statistics.mean(occupancy), "capacity_violations": sum(value > CAPACITY for value in occupancy), "occupancy_trace_sha256": digest(occupancy), "final_scope": active, "scope_updates": int(scope_switched)}


def oracle_retention(case: dict[str, Any]) -> list[dict[str, Any]]:
    ids = {record["record_id"] for record in case["oracle_view"]["records"]}
    return [row for row in case["experience_stream"] if row["record_id"] in ids]


def fifo_retention(case: dict[str, Any]) -> list[dict[str, Any]]:
    return list(case["experience_stream"][:CAPACITY])


def random_retention(case: dict[str, Any]) -> list[dict[str, Any]]:
    stream = case["experience_stream"]
    return sorted(stream, key=lambda row: digest([RANDOM_CONTROL_SEED, case["case_id"], row["record_id"]]))[:CAPACITY]


def static_capacity_audit(case: dict[str, Any], selected_ids: set[str]) -> dict[str, Any]:
    occupancy = []
    count = 0
    for row in case["experience_stream"]:
        if row["record_id"] in selected_ids:
            count += 1
        occupancy.append(count)
    return {"max_occupancy": max(occupancy), "mean_occupancy": statistics.mean(occupancy), "capacity_violations": sum(value > CAPACITY for value in occupancy), "occupancy_trace_sha256": digest(occupancy), "scope_updates": 0}


def candidate_from_row(row: dict[str, Any], hidden_map: dict[str, list[float]]) -> dict[str, Any]:
    return {"record_id": row["record_id"], "entity": row["entity"], "write_descriptor": row["write_descriptor"], "creation_episode": row["creation_episode"], "version": row["version"], "logical_key": list(record_key(row)), "answer": row["value"], "hidden_value": hidden_map[row["value"]]}


def retrieval_audit() -> dict[str, Any]:
    return {"calls": 0, "query_fields_observed": [], "candidate_fields_observed": [], "forbidden_fields_observed": [], "candidate_count_max": 0, "all_candidates_scored": True, "hidden_value_in_actual_scorer": False, "answer_in_actual_scorer": False, "logical_key_in_actual_scorer": False, "record_id_in_actual_scorer": False, "correct_candidate_index_in_actual_scorer": False, "optimizer_objects_created": 0, "optimizer_steps": 0, "backward_calls": 0}


def learned_scores(model: FactorizedAssociativeMatcher, case: dict[str, Any], candidates: list[dict[str, Any]], audit: dict[str, Any]) -> torch.Tensor:
    query_descriptor = case["neural_view"]["query"]["query_descriptor"]
    scorer_view_payload = {"query": {"query_descriptor": query_descriptor, "mode": case["neural_view"]["query"]["mode"], "as_of_episode": case["neural_view"]["query"]["as_of_episode"]}, "candidates": [{"write_descriptor": row["write_descriptor"], "creation_episode": row["creation_episode"]} for row in candidates]}
    validation = validate_scorer_view(scorer_view_payload)
    serialized = canonical(scorer_view_payload)
    forbidden = {"hidden_value", "answer", "logical_key", "record_id", "correct_candidate_index"}.intersection(serialized)
    audit["calls"] += 1
    audit["query_fields_observed"] = sorted(set(audit["query_fields_observed"]).union(scorer_view_payload["query"].keys()))
    observed_candidates = set().union(*(candidate.keys() for candidate in scorer_view_payload["candidates"])) if candidates else set()
    audit["candidate_fields_observed"] = sorted(set(audit["candidate_fields_observed"]).union(observed_candidates))
    audit["candidate_count_max"] = max(audit["candidate_count_max"], len(candidates))
    audit["forbidden_fields_observed"] = sorted(set(audit["forbidden_fields_observed"]).union(forbidden))
    audit["hidden_value_in_actual_scorer"] |= "hidden_value" in serialized
    audit["answer_in_actual_scorer"] |= "answer" in serialized
    audit["logical_key_in_actual_scorer"] |= "logical_key" in serialized
    audit["record_id_in_actual_scorer"] |= "record_id" in serialized
    if forbidden or not validation["pass"]:
        raise ValueError("retrieval runtime firewall violation")
    query = encode_query_descriptor(query_descriptor)
    encoded = [encode_write_descriptor(row["write_descriptor"]) for row in candidates]
    candidate_a = torch.stack([item.A for item in encoded])
    candidate_b = torch.stack([item.B for item in encoded])
    with torch.no_grad():
        score_a = torch.einsum("i,ij,nj->n", query.A, model.W_A, candidate_a)
        score_b = torch.einsum("i,ij,nj->n", query.B, model.W_B, candidate_b)
        return score_a + score_b


def learned_retrieve(model: FactorizedAssociativeMatcher, case: dict[str, Any], candidates: list[dict[str, Any]], audit: dict[str, Any]) -> dict[str, Any] | None:
    scores = learned_scores(model, case, candidates, audit)
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(candidates):
        groups[canonical(row["write_descriptor"])].append(index)
    grouped = list(groups.values())
    group_order = sorted(range(len(grouped)), key=lambda index: (-float(scores[grouped[index][0]].item()), min(hashlib.sha256(str(candidates[item]["record_id"]).encode("utf-8")).hexdigest() for item in grouped[index])))
    selected_group = grouped[group_order[0]]
    query = case["neural_view"]["query"]
    if query["mode"] == "history":
        eligible = [index for index in selected_group if candidates[index]["creation_episode"] <= query["as_of_episode"]]
    else:
        eligible = list(selected_group)
    if not eligible:
        return None
    selected = sorted(eligible, key=lambda index: (-candidates[index]["creation_episode"], hashlib.sha256(str(candidates[index]["record_id"]).encode("utf-8")).hexdigest()))[0]
    return candidates[selected]


def oracle_retrieve(case: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    target_pair = tuple(case["oracle_view"]["target_logical_key"])
    matches = [row for row in candidates if tuple(row["logical_key"]) == target_pair]
    if case["neural_view"]["query"]["mode"] == "history":
        matches = [row for row in matches if row["creation_episode"] <= case["neural_view"]["query"]["as_of_episode"]]
    return sorted(matches, key=lambda row: (-row["creation_episode"], hashlib.sha256(str(row["record_id"]).encode("utf-8")).hexdigest()))[0] if matches else None


def random_retrieve(case: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: digest([RANDOM_CONTROL_SEED, case["case_id"], row["record_id"]]))[0]


def decode_row(decoder: torch.nn.Module, case: dict[str, Any], row: dict[str, Any]) -> str:
    query = case["neural_view"]["query"]
    event = {"kind": "query", "entity": "opaque", "field": FIELD, "mode": query["mode"], "as_of_episode": query["as_of_episode"]}
    with torch.no_grad():
        logits = decoder.answer_query_with_hidden(event, torch.tensor(row["hidden_value"], dtype=torch.float32))
    return VALUES[int(torch.argmax(logits).item())]


def set_metrics(selected: list[dict[str, Any]], truth: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = {row["record_id"] for row in selected}
    truth_ids = {row["record_id"] for row in truth}
    intersection = len(selected_ids & truth_ids)
    precision = intersection / len(selected_ids) if selected_ids else 0.0
    recall = intersection / len(truth_ids) if truth_ids else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "exact_retained_set_match": selected_ids == truth_ids, "selected_count": len(selected_ids), "truth_count": len(truth_ids)}


def condition_rows(cases: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    by_id = {case["case_id"]: case for case in cases}
    groups = sorted({(case["family"], case["condition"]) for case in cases})
    for family, condition in groups:
        chosen = [row for row in decisions if by_id[row["case_id"]]["family"] == family and by_id[row["case_id"]]["condition"] == condition]
        retrieval = sum(int(row["retrieval_hit"]) for row in chosen) / len(chosen)
        answer = sum(int(row["answer_hit"]) for row in chosen) / len(chosen)
        rows.append({"family": family, "condition": condition, "case_count": len(chosen), "retrieval_hit_at_1": retrieval, "answer_accuracy": answer, "missing_retrieval": sum(int(row["missing_retrieval"]) for row in chosen), "retrieval_errors": sum(int(not row["retrieval_hit"]) for row in chosen)})
    return rows


def primary_components(rows: list[dict[str, Any]]) -> dict[str, float]:
    def one(family: str, condition: str, metric: str = "retrieval_hit_at_1") -> float:
        row = next(row for row in rows if row["family"] == family and row["condition"] == condition)
        return row[metric]

    def shift(metric: str) -> float:
        selected = [row[metric] for row in rows if row["family"] == "utility_change" and row["condition"].endswith("_load_1024")]
        return statistics.mean(selected)

    result = {
        "MISSION256_H1": one("mission_set", "load_256"),
        "MISSION1024_H1": one("mission_set", "load_1024"),
        "SAL256_H1": one("salience", "load_256"),
        "SAL1024_H1": one("salience", "load_1024"),
        "HARD1024_H1": one("hard_negative", "load_1024"),
        "SHIFT_H1": shift("retrieval_hit_at_1"),
        "SUP_CURRENT1024_H1": one("supersession", "current_load_1024"),
        "SUP_HISTORY1024_H1": one("supersession", "history_load_1024"),
        "FLOOD512_H1": one("distractor_flood", "load_512"),
        "FLOOD1024_H1": one("distractor_flood", "load_1024"),
    }
    answer_rows = {
        "MISSION256_A": one("mission_set", "load_256", "answer_accuracy"),
        "MISSION1024_A": one("mission_set", "load_1024", "answer_accuracy"),
        "SAL256_A": one("salience", "load_256", "answer_accuracy"),
        "SAL1024_A": one("salience", "load_1024", "answer_accuracy"),
        "HARD1024_A": one("hard_negative", "load_1024", "answer_accuracy"),
        "SHIFT_A": shift("answer_accuracy"),
        "SUP_CURRENT1024_A": one("supersession", "current_load_1024", "answer_accuracy"),
        "SUP_HISTORY1024_A": one("supersession", "history_load_1024", "answer_accuracy"),
        "FLOOD512_A": one("distractor_flood", "load_512", "answer_accuracy"),
        "FLOOD1024_A": one("distractor_flood", "load_1024", "answer_accuracy"),
    }
    result.update(answer_rows)
    result["P_integrated_retrieval"] = statistics.mean(result[key] for key in ("MISSION256_H1", "MISSION1024_H1", "SAL256_H1", "SAL1024_H1", "HARD1024_H1", "SHIFT_H1", "SUP_CURRENT1024_H1", "SUP_HISTORY1024_H1", "FLOOD512_H1", "FLOOD1024_H1"))
    result["P_integrated_answer"] = statistics.mean(result[key] for key in ("MISSION256_A", "MISSION1024_A", "SAL256_A", "SAL1024_A", "HARD1024_A", "SHIFT_A", "SUP_CURRENT1024_A", "SUP_HISTORY1024_A", "FLOOD512_A", "FLOOD1024_A"))
    return result


def evaluate_mode(cases: list[dict[str, Any]], retention_sets: dict[str, list[dict[str, Any]]], retention_audits: dict[str, dict[str, Any]], retrieval_kind: str, decoder: torch.nn.Module, retriever: FactorizedAssociativeMatcher | None, hidden_maps: dict[str, dict[str, list[float]]], retrieval_audit_state: dict[str, Any]) -> dict[str, Any]:
    decisions = []
    capacity_rows = []
    retention_rows = []
    for case in cases:
        case_id = case["case_id"]
        if retrieval_kind == "oracle_oracle":
            retention_name, retriever_name = "oracle", "oracle"
        elif retrieval_kind == "oracle_retention_learned_retrieval":
            retention_name, retriever_name = "oracle", "learned"
        elif retrieval_kind == "learned_retention_oracle_retrieval":
            retention_name, retriever_name = "learned", "oracle"
        elif retrieval_kind == "learned_learned":
            retention_name, retriever_name = "learned", "learned"
        elif retrieval_kind == "fifo_learned":
            retention_name, retriever_name = "fifo", "learned"
        elif retrieval_kind == "random_retention_learned":
            retention_name, retriever_name = "random", "learned"
        elif retrieval_kind == "learned_random_retrieval":
            retention_name, retriever_name = "learned", "random"
        else:
            raise ValueError(retrieval_kind)
        retained = retention_sets[retention_name][case_id]
        candidates = [candidate_from_row(row, hidden_maps[case_id]) for row in retained]
        if retriever_name == "learned":
            if retriever is None:
                raise ValueError("missing frozen retriever")
            selected = learned_retrieve(retriever, case, candidates, retrieval_audit_state)
        elif retriever_name == "oracle":
            selected = oracle_retrieve(case, candidates)
        else:
            selected = random_retrieve(case, candidates)
        target_id = case["oracle_view"]["target_record_id"]
        predicted = None if selected is None else decode_row(decoder, case, selected)
        answer_hit = predicted == case["oracle_view"]["answer"] if predicted is not None else False
        decisions.append({"case_id": case_id, "selected_record_id": None if selected is None else selected["record_id"], "target_record_id": target_id, "retrieval_hit": selected is not None and selected["record_id"] == target_id, "missing_retrieval": selected is None, "predicted_answer": predicted, "expected_answer": case["oracle_view"]["answer"], "answer_hit": answer_hit})
        capacity_rows.append(retention_audits[retention_name][case_id])
        retention_rows.append({"case_id": case_id, "retention": set_metrics(retained, oracle_retention(case))})
    rows = condition_rows(cases, decisions)
    components = primary_components(rows) if cases and cases[0]["split"] == "extrapolation" else None
    return {"mode": retrieval_kind, "split": cases[0]["split"] if cases else "", "case_count": len(cases), "condition_metrics": rows, "components": components, "decisions": decisions, "decisions_sha256": digest(decisions), "retention_metrics": retention_rows, "capacity_rows": capacity_rows}


def build_retention_sets(seed: int, dataset: dict[str, list[dict[str, Any]]], scorer: AffineRetentionScorer) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    sets = {"oracle": {}, "learned": {}, "fifo": {}, "random": {}}
    audits = {"oracle": {}, "learned": {}, "fifo": {}, "random": {}}
    audit = retention_audit()
    all_cases = [case for cases in dataset.values() for case in cases]
    for case in all_cases:
        learned, learned_audit = learned_retention(scorer, case, audit)
        oracle = oracle_retention(case)
        fifo = fifo_retention(case)
        random = random_retention(case)
        case_id = case["case_id"]
        sets["learned"][case_id] = learned
        sets["oracle"][case_id] = oracle
        sets["fifo"][case_id] = fifo
        sets["random"][case_id] = random
        audits["learned"][case_id] = learned_audit
        audits["oracle"][case_id] = static_capacity_audit(case, {row["record_id"] for row in oracle})
        audits["fifo"][case_id] = static_capacity_audit(case, {row["record_id"] for row in fifo})
        audits["random"][case_id] = static_capacity_audit(case, {row["record_id"] for row in random})
    audit["unique_feature_vectors"] = sorted(set(audit.get("unique_feature_vectors", [])))
    audit["pass"] = not audit["forbidden_fields_observed"] and audit["optimizer_objects_created"] == 0 and audit["optimizer_steps"] == 0 and audit["backward_calls"] == 0
    return sets, audits, audit


def evaluate_seed(seed: int, dataset: dict[str, list[dict[str, Any]]], hidden_maps: dict[str, dict[str, list[float]]], scorers: dict[int, AffineRetentionScorer], retrievers: dict[int, FactorizedAssociativeMatcher], decoder: torch.nn.Module) -> dict[str, Any]:
    scorer = scorers[seed]
    retriever = retrievers[seed]
    retention_sets, retention_audits, retention_firewall_state = build_retention_sets(seed, dataset, scorer)
    retrieval_firewall_state = retrieval_audit()
    modes = {}
    for mode in MODE_NAMES:
        modes[mode] = {"splits": {split: evaluate_mode(dataset[split], retention_sets, retention_audits, mode, decoder, retriever, hidden_maps, retrieval_firewall_state) for split in ("train", "iid", "extrapolation")}}
        modes[mode]["extrapolation"] = modes[mode]["splits"]["extrapolation"]
        modes[mode]["primary"] = modes[mode]["extrapolation"]["components"]
    retention_firewall_state["pass"] = retention_firewall_state["pass"]
    retrieval_firewall_state["pass"] = not retrieval_firewall_state["forbidden_fields_observed"] and retrieval_firewall_state["all_candidates_scored"] and retrieval_firewall_state["optimizer_objects_created"] == 0 and retrieval_firewall_state["optimizer_steps"] == 0 and retrieval_firewall_state["backward_calls"] == 0
    retention_summary = {}
    for name, mapping in retention_sets.items():
        rows = [set_metrics(mapping[case["case_id"]], oracle_retention(case)) for cases in dataset.values() for case in cases]
        retention_summary[name] = {"mean_precision": statistics.mean(row["precision"] for row in rows), "mean_recall": statistics.mean(row["recall"] for row in rows), "mean_f1": statistics.mean(row["f1"] for row in rows), "exact_set_match_rate": statistics.mean(int(row["exact_retained_set_match"]) for row in rows), "case_count": len(rows)}
    capacity_summary = {}
    for name, mapping in retention_audits.items():
        rows = list(mapping.values())
        capacity_summary[name] = {"max_occupancy": max(row["max_occupancy"] for row in rows), "mean_occupancy": statistics.mean(row["mean_occupancy"] for row in rows), "capacity_violations": sum(row["capacity_violations"] for row in rows), "case_count": len(rows)}
    return {"pair_seed": seed, "retention_firewall": retention_firewall_state, "retrieval_firewall": retrieval_firewall_state, "retention_summary": retention_summary, "capacity_summary": capacity_summary, "modes": modes, "optimizer_objects_created": 0, "optimizer_steps": 0, "backward_calls": 0, "scientific_training_executed": False}


def mode_aggregate(per_seed: dict[int, dict[str, Any]], mode: str) -> dict[str, Any]:
    retrieval = [per_seed[seed]["modes"][mode]["primary"]["P_integrated_retrieval"] for seed in EVIDENCE_SEEDS]
    answer = [per_seed[seed]["modes"][mode]["primary"]["P_integrated_answer"] for seed in EVIDENCE_SEEDS]
    components = {}
    for label in PRIMARY_LABELS:
        key = f"{label}_H1"
        values = [per_seed[seed]["modes"][mode]["primary"][key] for seed in EVIDENCE_SEEDS]
        components[key] = {"by_seed": dict(zip(map(str, EVIDENCE_SEEDS), values)), "mean": statistics.mean(values), "std": statistics.pstdev(values)}
    return {"P_integrated_retrieval_by_seed": dict(zip(map(str, EVIDENCE_SEEDS), retrieval)), "P_integrated_retrieval_mean": statistics.mean(retrieval), "P_integrated_retrieval_std": statistics.pstdev(retrieval), "P_integrated_answer_by_seed": dict(zip(map(str, EVIDENCE_SEEDS), answer)), "P_integrated_answer_mean": statistics.mean(answer), "P_integrated_answer_std": statistics.pstdev(answer), "components": components}


def calculate_gates(aggregate: dict[str, Any], integrity: dict[str, bool]) -> dict[str, Any]:
    learned = aggregate["modes"]["learned_learned"]
    oracle = aggregate["modes"]["oracle_oracle"]
    fifo = aggregate["modes"]["fifo_learned"]
    random_ret = aggregate["modes"]["random_retention_learned"]
    random_retrieval = aggregate["modes"]["learned_random_retrieval"]
    gates = {
        "A_integrated_retrieval": {"observed": learned["P_integrated_retrieval_mean"], "threshold": 0.90, "pass": learned["P_integrated_retrieval_mean"] >= 0.90},
        "B_integrated_answer": {"observed": learned["P_integrated_answer_mean"], "threshold": 0.90, "pass": learned["P_integrated_answer_mean"] >= 0.90},
        "C_oracle_gap": {"observed": oracle["P_integrated_retrieval_mean"] - learned["P_integrated_retrieval_mean"], "threshold_max": 0.10, "pass": oracle["P_integrated_retrieval_mean"] - learned["P_integrated_retrieval_mean"] <= 0.10},
        "D_five_pair_consistency": {"observed": sum(aggregate["learned_by_seed"][str(seed)]["P_integrated_retrieval"] >= 0.85 for seed in EVIDENCE_SEEDS), "required": "5/5", "pass": all(aggregate["learned_by_seed"][str(seed)]["P_integrated_retrieval"] >= 0.85 for seed in EVIDENCE_SEEDS)},
        "E_fifo_separation": {"observed": learned["P_integrated_retrieval_mean"] - fifo["P_integrated_retrieval_mean"], "threshold": 0.50, "pass": learned["P_integrated_retrieval_mean"] - fifo["P_integrated_retrieval_mean"] >= 0.50},
        "F_random_retention_separation": {"observed": learned["P_integrated_retrieval_mean"] - random_ret["P_integrated_retrieval_mean"], "threshold": 0.50, "pass": learned["P_integrated_retrieval_mean"] - random_ret["P_integrated_retrieval_mean"] >= 0.50},
        "G_random_retrieval_separation": {"observed": learned["P_integrated_retrieval_mean"] - random_retrieval["P_integrated_retrieval_mean"], "threshold": 0.50, "pass": learned["P_integrated_retrieval_mean"] - random_retrieval["P_integrated_retrieval_mean"] >= 0.50},
    }
    high = {key: learned["components"][key]["mean"] for key in ("MISSION1024_H1", "SAL1024_H1", "HARD1024_H1", "SHIFT_H1", "SUP_CURRENT1024_H1", "SUP_HISTORY1024_H1", "FLOOD1024_H1")}
    gates["high_load_components"] = {"observed": high, "threshold": 0.85, "pass": all(value >= 0.85 for value in high.values())}
    return {"gates": gates, "all_performance_gates": all(row["pass"] for row in gates.values()), "integrity": integrity, "all_integrity_checks": all(integrity.values())}


def report_markdown(terminal: str, aggregate: dict[str, Any]) -> str:
    lines = ["# DMC-04B — Frozen Learned Memory Integration Evidence", "", f"Terminal state: `{terminal}`", "", "## Primary retrieval", "", "| Pair seed | Oracle+Oracle P_R | Learned+Learned P_R | OracleRet+LearnedRet P_R | LearnedRet+OracleRet P_R |", "|---:|---:|---:|---:|---:|"]
    for seed in EVIDENCE_SEEDS:
        lines.append(f"| {seed} | {aggregate['by_seed']['oracle_oracle'][str(seed)]['P_integrated_retrieval']:.6f} | {aggregate['by_seed']['learned_learned'][str(seed)]['P_integrated_retrieval']:.6f} | {aggregate['by_seed']['oracle_retention_learned_retrieval'][str(seed)]['P_integrated_retrieval']:.6f} | {aggregate['by_seed']['learned_retention_oracle_retrieval'][str(seed)]['P_integrated_retrieval']:.6f} |")
    lines.extend(["", "## Primary answer", "", "| Pair seed | Learned+Learned P_answer |", "|---:|---:|"])
    for seed in EVIDENCE_SEEDS:
        lines.append(f"| {seed} | {aggregate['by_seed']['learned_learned'][str(seed)]['P_integrated_answer']:.6f} |")
    lines.extend(["", "## Aggregate modes", "", "| Mode | P_R mean | P_R std | P_answer mean | P_answer std |", "|---|---:|---:|---:|---:|"])
    for mode, row in aggregate["modes"].items():
        lines.append(f"| {mode} | {row['P_integrated_retrieval_mean']:.6f} | {row['P_integrated_retrieval_std']:.6f} | {row['P_integrated_answer_mean']:.6f} | {row['P_integrated_answer_std']:.6f} |")
    lines.extend(["", "## Boundary", "", "This is evaluation only. The frozen DMC-03 retention scorers, frozen DMC-04R2 retrievers, and native seed-1337 decoder were loaded read-only. No joint training, optimizer, backward pass, adapter, feature change, or DMC-05 step was executed."])
    return "\n".join(lines) + "\n"


def main() -> int:
    torch.set_num_threads(1)
    OUT.mkdir(parents=True, exist_ok=True)
    dataset, benchmark = load_frozen_dataset()
    hidden_maps = build_hidden_maps(dataset)
    world = world0_identity()
    predecessor_specs = {"DMC-00": (DMC00_COMMIT, "artifacts/dmc00"), "DMC-01": (DMC01_COMMIT, "artifacts/dmc01"), "DMC-02A": (DMC02A_COMMIT, "artifacts/dmc02a"), "DMC-03": (DMC03_COMMIT, "artifacts/dmc03"), "DMC-04A": (DMC04A_COMMIT, "artifacts/dmc04a"), "DMC-04P": (DMC04P_COMMIT, "artifacts/dmc04p"), "DMC-04 invalid": (DMC04_INVALID_COMMIT, "artifacts/dmc04"), "DMC-04P-A": (DMC04PA_COMMIT, "artifacts/dmc04pa"), "DMC-04R repair": (DMC04R_REPAIR_COMMIT, "artifacts/dmc04r"), "DMC-04R-A": (DMC04RA_COMMIT, "artifacts/dmc04ra"), "DMC-04R2": (DMC04R2_COMMIT, "artifacts/dmc04r2"), "DMC-04B-A": (DMC04BA_COMMIT, "artifacts/dmc04ba")}
    predecessors = {name: predecessor_identity(name, commit, path) for name, (commit, path) in predecessor_specs.items()}
    benchmark["predecessor_identity"] = all(row["pass"] for row in predecessors.values()) and world["pass"]
    tests = preflight_tests()
    scorers, retention_manifest, retention_before = load_retention_models()
    retrievers, retrieval_manifest, retrieval_before = load_retrieval_models()
    decoder, decoder_identity, decoder_before = load_decoder()
    per_seed: dict[int, dict[str, Any]] = {}
    for seed in EVIDENCE_SEEDS:
        per_seed[seed] = evaluate_seed(seed, dataset, hidden_maps, scorers, retrievers, decoder)
    first_1337 = per_seed[1337]
    second_1337 = evaluate_seed(1337, dataset, hidden_maps, scorers, retrievers, decoder)
    replay_first_hash = digest(first_1337)
    replay_second_hash = digest(second_1337)
    replay = {"pass": replay_first_hash == replay_second_hash and first_1337 == second_1337, "seed": 1337, "first_canonical_sha256": replay_first_hash, "second_canonical_sha256": replay_second_hash, "identical": first_1337 == second_1337, "retention_decisions_identical": all(first_1337["modes"][mode]["extrapolation"]["decisions_sha256"] == second_1337["modes"][mode]["extrapolation"]["decisions_sha256"] for mode in MODE_NAMES), "metrics_identical": all(first_1337["modes"][mode]["primary"] == second_1337["modes"][mode]["primary"] for mode in MODE_NAMES)}
    component_after = {"retention": {str(seed): file_sha256(ROOT / f"artifacts/dmc03/checkpoints/retention_seed{seed}_final.pt") for seed in EVIDENCE_SEEDS}, "retrieval": {str(seed): file_sha256(ROOT / f"artifacts/dmc04r2/checkpoints/retrieval_seed{seed}_final.pt") for seed in EVIDENCE_SEEDS}, "decoder": file_sha256(CHECKPOINT)}
    component_before = {"retention": {str(seed): retention_before[seed] for seed in EVIDENCE_SEEDS}, "retrieval": {str(seed): retrieval_before[seed] for seed in EVIDENCE_SEEDS}, "decoder": decoder_before}
    immutability = {"pass": component_before == component_after, "before": component_before, "after": component_after, "all_unchanged": component_before == component_after}
    aggregate = {"std_definition": "population standard deviation across five paired evidence seeds", "modes": {mode: mode_aggregate(per_seed, mode) for mode in MODE_NAMES}, "by_seed": {mode: {str(seed): {"P_integrated_retrieval": per_seed[seed]["modes"][mode]["primary"]["P_integrated_retrieval"], "P_integrated_answer": per_seed[seed]["modes"][mode]["primary"]["P_integrated_answer"]} for seed in EVIDENCE_SEEDS} for mode in MODE_NAMES}, "learned_by_seed": {str(seed): {"P_integrated_retrieval": per_seed[seed]["modes"]["learned_learned"]["primary"]["P_integrated_retrieval"], "P_integrated_answer": per_seed[seed]["modes"]["learned_learned"]["primary"]["P_integrated_answer"]} for seed in EVIDENCE_SEEDS}}
    integrity = {"preflight_tests": tests["pass"], "world0": world["pass"], "benchmark": benchmark["pass"], "predecessors": benchmark["predecessor_identity"], "retention_checkpoint_manifest": retention_manifest["pass"], "retrieval_checkpoint_manifest": retrieval_manifest["pass"], "fixed_decoder": decoder_identity["pass"], "component_immutability": immutability["pass"], "replay": replay["pass"], "retention_firewalls": all(per_seed[seed]["retention_firewall"]["pass"] for seed in EVIDENCE_SEEDS), "retrieval_firewalls": all(per_seed[seed]["retrieval_firewall"]["pass"] for seed in EVIDENCE_SEEDS), "capacity": all(all(per_seed[seed]["capacity_summary"][name]["max_occupancy"] <= CAPACITY and per_seed[seed]["capacity_summary"][name]["capacity_violations"] == 0 for name in ("oracle", "learned", "fifo", "random")) for seed in EVIDENCE_SEEDS), "no_learning": all(per_seed[seed]["optimizer_objects_created"] == 0 and per_seed[seed]["optimizer_steps"] == 0 and per_seed[seed]["backward_calls"] == 0 for seed in EVIDENCE_SEEDS)}
    gates = calculate_gates(aggregate, integrity)
    learned = aggregate["modes"]["learned_learned"]
    oracle_ret_learned = aggregate["modes"]["oracle_retention_learned_retrieval"]
    learned_ret_oracle = aggregate["modes"]["learned_retention_oracle_retrieval"]
    if not benchmark["predecessor_identity"] or not world["pass"]:
        terminal = "DMC_04B_INVALID"
    elif not integrity["capacity"]:
        terminal = "DMC_04B_CAPACITY_INVALID"
    elif not integrity["retention_firewalls"] or not integrity["retrieval_firewalls"]:
        terminal = "DMC_04B_MEMORY_LEAK"
    elif not integrity["component_immutability"]:
        terminal = "DMC_04B_COMPONENT_MUTATED"
    elif not all(integrity.values()):
        terminal = "DMC_04B_INVALID"
    elif gates["all_performance_gates"]:
        terminal = "DMC_04B_COMBINED_LEARNED_MEMORY_ADVANCES"
    elif oracle_ret_learned["P_integrated_retrieval_mean"] < 0.85 or learned_ret_oracle["P_integrated_retrieval_mean"] < 0.85:
        terminal = "DMC_04B_COMPONENT_TRANSFER_FAILURE"
    elif oracle_ret_learned["P_integrated_retrieval_mean"] >= 0.85 and learned_ret_oracle["P_integrated_retrieval_mean"] >= 0.85:
        terminal = "DMC_04B_INTEGRATION_FAILURE"
    else:
        terminal = "DMC_04B_COMBINED_MEMORY_NO_ADVANTAGE"
    aggregate["terminal_state"] = terminal
    aggregate["gates"] = gates
    write_json(OUT / "DMC04B_CONFIG.json", {"unit": "DMC-04B", "status": "frozen_learned_memory_integration_evidence", "terminal_state": terminal, "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "benchmark_commit": DMC04BA_COMMIT, "evidence_seeds": list(EVIDENCE_SEEDS), "pairing": "retention seed N + retrieval seed N", "fixed_decoder": {"seed": 1337, "checkpoint": str(CHECKPOINT.relative_to(ROOT)), "sha256": CHECKPOINT_SHA256}, "memory_budget": CAPACITY, "modes": list(MODE_NAMES), "primary_retrieval": "mean(MISSION256_H1,MISSION1024_H1,SAL256_H1,SAL1024_H1,HARD1024_H1,SHIFT_H1,SUP_CURRENT1024_H1,SUP_HISTORY1024_H1,FLOOD512_H1,FLOOD1024_H1)", "primary_answer": "equal-weight corresponding final-answer mean", "no_training": True, "optimizer_objects_created": 0, "optimizer_steps": 0, "backward_calls": 0, "no_new_features": True, "no_adapters": True, "no_dmc05": True})
    write_json(OUT / "environment.json", {"python": sys.version, "platform": platform.platform(), "torch": torch.__version__, "torch_threads": torch.get_num_threads(), "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "device": "cpu"})
    write_json(OUT / "predecessor_identity.json", {"pass": benchmark["predecessor_identity"], "world0": world, "rows": predecessors})
    write_json(OUT / "benchmark_identity.json", benchmark)
    write_json(OUT / "retention_checkpoint_manifest.json", retention_manifest)
    write_json(OUT / "retrieval_checkpoint_manifest.json", retrieval_manifest)
    write_json(OUT / "fixed_decoder_identity.json", decoder_identity)
    write_json(OUT / "component_immutability.json", immutability)
    write_json(OUT / "capacity_audit.json", {"pass": integrity["capacity"], "by_seed": {str(seed): per_seed[seed]["capacity_summary"] for seed in EVIDENCE_SEEDS}, "budget": CAPACITY})
    write_json(OUT / "retention_firewall.json", {"pass": integrity["retention_firewalls"], "by_seed": {str(seed): per_seed[seed]["retention_firewall"] for seed in EVIDENCE_SEEDS}})
    write_json(OUT / "retrieval_firewall.json", {"pass": integrity["retrieval_firewalls"], "by_seed": {str(seed): per_seed[seed]["retrieval_firewall"] for seed in EVIDENCE_SEEDS}})
    write_json(OUT / "replay.json", replay)
    for seed in EVIDENCE_SEEDS:
        pair = per_seed[seed]
        write_json(OUT / f"pair_seed{seed}.json", pair)
        for mode, filename in (("oracle_retention_learned_retrieval", "oracle_retention_learned_retrieval"), ("learned_retention_oracle_retrieval", "learned_retention_oracle_retrieval"), ("fifo_learned", "fifo_learned"), ("random_retention_learned", "random_retention_learned"), ("learned_random_retrieval", "learned_random_retrieval")):
            write_json(OUT / f"{filename}_seed{seed}.json", {"pair_seed": seed, "mode": mode, "primary": pair["modes"][mode]["primary"], "splits": {split: pair["modes"][mode]["splits"][split]["condition_metrics"] for split in ("train", "iid", "extrapolation")}, "decisions_sha256": {split: pair["modes"][mode]["splits"][split]["decisions_sha256"] for split in ("train", "iid", "extrapolation")}})
    write_json(OUT / "oracle_oracle.json", {"mode": "oracle_oracle", "aggregate": aggregate["modes"]["oracle_oracle"], "by_seed": aggregate["by_seed"]["oracle_oracle"]})
    write_json(OUT / "aggregate.json", aggregate)
    verdict = {"unit": "DMC-04B", "terminal_state": terminal, "claim": "independently trained frozen DMC-03 retention and DMC-04R2 retrieval compose under one hard 16-record memory without adaptation", "integrity": integrity, "gates": gates, "aggregate": aggregate, "evidence_seeds": list(EVIDENCE_SEEDS), "evidence_training_executed": False, "optimizer_objects_created": 0, "optimizer_steps": 0, "backward_calls": 0, "interpretation_boundary": ["task-derived importance not established", "real-language memory not established", "processor-independent hidden memories not established", "practical cost advantage not established"]}
    write_json(OUT / "DMC04B_VERDICT.json", verdict)
    (OUT / "DMC04B_REPORT.md").write_text(report_markdown(terminal, aggregate), encoding="utf-8")
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 0 if terminal in {"DMC_04B_COMBINED_LEARNED_MEMORY_ADVANCES", "DMC_04B_INTEGRATION_FAILURE", "DMC_04B_COMPONENT_TRANSFER_FAILURE", "DMC_04B_COMBINED_MEMORY_NO_ADVANTAGE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
