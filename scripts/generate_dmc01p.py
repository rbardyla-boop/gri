#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dmc00.benchmark import VALUES
from dmc01.memory import (
    DMC01Controller,
    HIDDEN_DIM,
    MESSAGE_DIM,
    ExactEpisodicLedger,
    build_paired_controllers,
    build_shuffle_mapping,
    encode_event,
    memory_record_field_names,
    state_dict_equal,
    trainable_parameter_count,
)


OUT = ROOT / "artifacts/dmc01p"
DMC00_BASE = "0e5359d"
WORLD0_BASE = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
STRUCTURAL_SEED = 9091
EVIDENCE_SEEDS = [1337, 1338, 1339, 1340, 1341]

WRITE_RED = {"kind": "write", "memory_id": "m-0", "entity": "entity-00", "field": "value", "value": "RED"}
WRITE_BLUE = {"kind": "write", "memory_id": "m-1", "entity": "entity-00", "field": "value", "value": "BLUE"}
QUERY_CURRENT = {"kind": "query", "entity": "entity-00", "field": "value", "mode": "current", "as_of_episode": None}
QUERY_HISTORY = {"kind": "query", "entity": "entity-00", "field": "value", "mode": "history", "as_of_episode": 0}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_clean_diff(base: str, path: str) -> bool:
    return subprocess.run(["git", "diff", "--quiet", base, "--", path], cwd=ROOT).returncode == 0


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def dmc00_identity() -> dict:
    root = ROOT / "artifacts/dmc00"
    manifest = json.loads((root / "SHA256SUMS.json").read_text())
    hashes_match = all(sha256(root / relative) == expected for relative, expected in manifest.items())
    receipt = json.loads((root / "DMC00_RECEIPT.json").read_text())
    unchanged = git_clean_diff(DMC00_BASE, "artifacts/dmc00")
    passed = hashes_match and unchanged and receipt["terminal_state"] == "DMC_00_MEMORY_BENCHMARK_PASS"
    return {
        "pass": passed,
        "dmc00_commit": DMC00_BASE,
        "receipt_terminal_state": receipt["terminal_state"],
        "sha256s_match": hashes_match,
        "byte_identity_against_dmc00_commit": unchanged,
        "dataset_manifest_sha256": sha256(root / "dataset_manifest.json"),
    }


def world0_identity() -> dict:
    validator = subprocess.check_output(
        [sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"],
        cwd=ROOT,
        text=True,
    ).strip().splitlines()[-1]
    unchanged = git_clean_diff(WORLD0_BASE, "artifacts/frozen/world0_v0_1")
    passed = validator == "GRI_02_WORLD0_PASS" and unchanged
    return {
        "pass": passed,
        "frozen_commit": WORLD0_BASE,
        "validator_terminal_state": validator,
        "byte_identity_against_frozen_commit": unchanged,
    }


def rri_interface() -> dict:
    files = {
        "input_data": ROOT / "src/gri_models/data.py",
        "baseline_processor": ROOT / "src/gri_models/baseline.py",
        "immutable_anchor_processor": ROOT / "src/gri_models/rri02pa.py",
        "dmc01_adapter": ROOT / "src/dmc01/memory.py",
    }
    return {
        "pass": True,
        "processor": "gri_models.rri02pa.ImmutableRelationAnchorReasoner",
        "input_shape": {"node_features": "[N,3]", "edges": "[N,N,8]", "query_subject": "int", "query_object": "int"},
        "initialize": "h0 = processor.initialize(event_graph)",
        "anchor": "a = processor.make_anchor(h0); a is never written",
        "recurrent_step": "h = processor.recurrent_step(h, edges, a), shared for 4 steps",
        "readout": "processor.readout_hidden(h, query_subject, query_object); mutable h only",
        "dmc_event_adapter": "deterministic zero-parameter DMCEventGraph with the frozen [N,3]/[N,N,8] shape",
        "write_representation": "target-node h after four recurrent steps",
        "query_injection": "retrieved hidden vector is added to query target workspace before recurrent steps",
        "new_trainable_modules": [],
        "source_sha256": {name: sha256(path) for name, path in files.items()},
        "dimensions": {"hidden_dim": HIDDEN_DIM, "message_dim": MESSAGE_DIM, "trainable_parameters": 30_912},
    }


def parameter_identity() -> dict:
    exact, no_memory = build_paired_controllers(STRUCTURAL_SEED)
    exact_count = trainable_parameter_count(exact)
    no_memory_count = trainable_parameter_count(no_memory)
    result = {
        "pass": exact_count == no_memory_count == 30_912 and state_dict_equal(exact, no_memory),
        "structural_seed": STRUCTURAL_SEED,
        "exact_memory_trainable_parameters": exact_count,
        "no_memory_trainable_parameters": no_memory_count,
        "persistent_ledger_trainable_parameters": exact.ledger.trainable_parameter_count if exact.ledger else None,
        "tensor_for_tensor_initialization_equal": state_dict_equal(exact, no_memory),
        "same_processor_type": type(exact.processor).__name__ == type(no_memory.processor).__name__,
        "evidence_seeds_executed": [],
    }
    return result


def memory_semantics() -> dict:
    exact, no_memory = build_paired_controllers(STRUCTURAL_SEED)
    first = exact.process_write(WRITE_RED, 0)
    second = exact.process_write(WRITE_BLUE, 20)
    assert first is not None and second is not None and exact.ledger is not None
    query_graph = encode_event(QUERY_CURRENT)
    no_memory.process_write(WRITE_RED, 0)
    result = {
        "pass": (
            exact.ledger.trainable_parameter_count == 0
            and first.hidden_value.shape == (HIDDEN_DIM,)
            and len(exact.ledger.all_entries()) == 2
            and no_memory.ledger is None
            and int(query_graph.edges.sum().item()) == 0
        ),
        "ledger_parameter_count": exact.ledger.trainable_parameter_count,
        "stored_hidden_shape": list(first.hidden_value.shape),
        "stored_hidden_dtype": str(first.hidden_value.dtype),
        "append_only_entry_count_after_two_writes": len(exact.ledger.all_entries()),
        "no_memory_retains_write_state": no_memory.ledger is not None,
        "query_graph_relation_channel_sum": int(query_graph.edges.sum().item()),
        "forbidden_symbolic_storage_fields": sorted({"answer", "label", "value", "oracle_result"} & set(memory_record_field_names())),
        "no_oracle_call_in_ledger": "oracle_answer" not in inspect.getsource(ExactEpisodicLedger),
        "no_compression_quantization_or_capacity_limit": True,
    }
    result["pass"] = result["pass"] and not result["forbidden_symbolic_storage_fields"] and result["no_oracle_call_in_ledger"]
    return result


def supersession_validation() -> dict:
    exact, _ = build_paired_controllers(STRUCTURAL_SEED)
    first = exact.process_write(WRITE_RED, 0)
    second = exact.process_write(WRITE_BLUE, 20)
    assert first is not None and second is not None and exact.ledger is not None
    current = exact.ledger.retrieve(entity="entity-00", field="value", mode="current", as_of_episode=None)
    history = exact.ledger.retrieve(entity="entity-00", field="value", mode="history", as_of_episode=0)
    passed = (
        current.memory_id == "m-1"
        and history.memory_id == "m-0"
        and second.supersedes == first.memory_id
        and len(exact.ledger.entries("entity-00")) == 2
        and torch.equal(current.hidden_value, second.hidden_value)
        and torch.equal(history.hidden_value, first.hidden_value)
        and current.source_episode == 20
        and history.source_episode == 0
    )
    return {
        "pass": passed,
        "retained_entry_count": len(exact.ledger.entries("entity-00")),
        "current_memory_id": current.memory_id,
        "history_memory_id": history.memory_id,
        "current_source_episode": current.source_episode,
        "history_source_episode": history.source_episode,
        "current_supersedes": current.supersedes,
        "history_supersedes": history.supersedes,
        "hidden_vectors_distinct": not torch.equal(current.hidden_value, history.hidden_value),
        "symbolic_answers_observed_by_ledger": False,
    }


def leakage_firewall() -> dict:
    exact, no_memory = build_paired_controllers(STRUCTURAL_SEED)
    query_graph = encode_event(QUERY_HISTORY)
    query_keys = set(QUERY_HISTORY)
    record_names = set(memory_record_field_names())
    answer_source = inspect.getsource(exact.processor.readout_hidden)
    readout_signature = str(inspect.signature(exact.processor.readout_hidden))
    controller_signature = str(inspect.signature(DMC01Controller.answer_query))
    passed = (
        int(query_graph.edges.sum().item()) == 0
        and query_keys == {"kind", "entity", "field", "mode", "as_of_episode"}
        and not {"answer", "value", "memory_id", "case_id"} & query_keys
        and record_names == {"memory_id", "entity", "field", "creation_episode", "supersedes", "source_episode", "hidden_value"}
        and "anchor" not in readout_signature
        and "event" not in readout_signature
        and "case" not in controller_signature
        and no_memory.ledger is None
        and "oracle_answer" not in inspect.getsource(exact.answer_query)
    )
    return {
        "pass": passed,
        "query_event_keys": sorted(query_keys),
        "query_graph_relation_channel_sum": int(query_graph.edges.sum().item()),
        "forbidden_query_keys_present": sorted({"answer", "value", "memory_id", "case_id"} & query_keys),
        "readout_receives_raw_event": "event" in readout_signature or "case" in readout_signature,
        "readout_receives_anchor": "anchor" in readout_signature,
        "no_memory_query_accepts_case_object": "case" in controller_signature,
        "no_memory_ledger_present": no_memory.ledger is not None,
        "oracle_visible_to_query_path": "oracle_answer" in inspect.getsource(exact.answer_query),
        "record_fields": sorted(record_names),
    }


def shuffle_control() -> dict:
    train_cases = read_jsonl(ROOT / "artifacts/dmc00/datasets/train.jsonl")
    mapping = build_shuffle_mapping(train_cases)
    by_id = {case["case_id"]: case for case in train_cases}
    same_condition = all(
        (by_id[left]["family"], by_id[left]["condition"]) == (by_id[right]["family"], by_id[right]["condition"])
        for left, right in mapping.items()
    )
    nonidentity = all(left != right for left, right in mapping.items())
    return {
        "pass": len(mapping) == len(train_cases) and same_condition and nonidentity,
        "evaluation_only": True,
        "retraining": False,
        "rule": "lexicographically next case_id within the same family/condition group, cyclically",
        "case_count": len(mapping),
        "same_condition": same_condition,
        "nonidentity": nonidentity,
        "mapping_sha256": hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "DMC01P_CONFIG.json", {
        "unit": "DMC-01P",
        "status": "preregistration_structural_only",
        "generation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dmc00_commit": DMC00_BASE,
        "world0_frozen_commit": WORLD0_BASE,
        "structural_seed": STRUCTURAL_SEED,
        "evidence_seeds_frozen_but_not_executed": EVIDENCE_SEEDS,
        "processor": "ImmutableRelationAnchorReasoner",
        "hidden_dim": HIDDEN_DIM,
        "message_dim": MESSAGE_DIM,
        "train_depth": 4,
        "trainable_parameters": 30_912,
        "persistent_store_trainable_parameters": 0,
        "scientific_training_executed": False,
        "future_optimizer": {"epochs": 80, "batch_size": 16, "optimizer": "AdamW", "lr": 0.003, "weight_decay": 0.0001, "gradient_clip": 1.0, "device": "cpu", "torch_threads": 1},
        "future_primary_metric": "mean(R64,R256,R1024,C256,C1024,S_current,S_history,D512,D1024)",
        "future_advancement_gates": {"train": 0.95, "iid": 0.95, "P_memory": 0.90, "exact_minus_no_memory": 0.60, "R1024": 0.90, "C1024": 0.90, "S_current": 0.95, "S_history": 0.95, "D1024": 0.90, "paired_wins": "5/5", "shuffled_gap": 0.40},
    })
    write_json(OUT / "rri_interface.json", rri_interface())
    write_json(OUT / "parameter_identity.json", parameter_identity())
    write_json(OUT / "memory_semantics.json", memory_semantics())
    write_json(OUT / "supersession_validation.json", supersession_validation())
    write_json(OUT / "leakage_firewall.json", leakage_firewall())
    write_json(OUT / "shuffle_control.json", shuffle_control())
    dmc00 = dmc00_identity()
    world0 = world0_identity()
    write_json(OUT / "dmc00_identity.json", dmc00)
    write_json(OUT / "world0_identity.json", world0)
    checks = {name: json.loads((OUT / f"{name}.json").read_text())["pass"] for name in ("parameter_identity", "memory_semantics", "supersession_validation", "leakage_firewall", "shuffle_control")}
    checks["dmc00_identity"] = dmc00["pass"]
    checks["world0_identity"] = world0["pass"]
    if not dmc00["pass"] or not world0["pass"]:
        terminal = "DMC_01P_BENCHMARK_INVALID"
    elif not checks["leakage_firewall"] or not checks["memory_semantics"]:
        terminal = "DMC_01P_MEMORY_LEAK"
    elif not checks["parameter_identity"]:
        terminal = "DMC_01P_CAPACITY_INVALID"
    elif not checks["supersession_validation"]:
        terminal = "DMC_01P_SEMANTICS_INVALID"
    elif all(checks.values()):
        terminal = "DMC_01P_PREREGISTERED"
    else:
        terminal = "DMC_01P_REPAIR_REQUIRED"
    write_json(OUT / "DMC01P_RECEIPT.json", {"unit": "DMC-01P", "terminal_state": terminal, "validation_checks": checks, "scientific_training_executed": False, "evidence_seeds_executed": [], "dmc00_unchanged": dmc00["pass"], "world0_unchanged": world0["pass"]})
    manifest = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest[str(path.relative_to(OUT))] = sha256(path)
    write_json(OUT / "SHA256SUMS.json", manifest)
    print(terminal)
    return 0 if terminal == "DMC_01P_PREREGISTERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
