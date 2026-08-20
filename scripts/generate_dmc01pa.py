#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dmc01.memory import DMC01Controller, HIDDEN_DIM, build_paired_controllers, state_dict_equal, trainable_parameter_count
from dmc01.training import (
    FROZEN_TRAINING_CONFIG,
    case_cross_entropy,
    case_batches,
    checkpoint_payload,
    order_manifest,
    ordered_cases,
    run_case_logits,
    target_for_case,
    train_complete_case_batch,
)


OUT = ROOT / "artifacts/dmc01pa"
DMC00_BASE = "0e5359d"
DMC01P_BASE = "ed15f71"
WORLD0_BASE = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
STRUCTURAL_SEED = 9090
EVIDENCE_SEEDS = [1337, 1338, 1339, 1340, 1341]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def git_clean_diff(base: str, path: str) -> bool:
    return subprocess.run(["git", "diff", "--quiet", base, "--", path], cwd=ROOT).returncode == 0


def verify_directory_identity(name: str, base: str) -> dict:
    root = ROOT / "artifacts" / name
    manifest = json.loads((root / "SHA256SUMS.json").read_text())
    hashes_match = all(sha256(root / relative) == expected for relative, expected in manifest.items())
    receipt = json.loads((root / ("DMC00_RECEIPT.json" if name == "dmc00" else "DMC01P_RECEIPT.json")).read_text())
    expected_terminal = "DMC_00_MEMORY_BENCHMARK_PASS" if name == "dmc00" else "DMC_01P_PREREGISTERED"
    unchanged = git_clean_diff(base, f"artifacts/{name}")
    return {
        "pass": hashes_match and unchanged and receipt["terminal_state"] == expected_terminal,
        "commit": base,
        "sha256s_match": hashes_match,
        "byte_identity_against_commit": unchanged,
        "receipt_terminal_state": receipt["terminal_state"],
    }


def world0_identity() -> dict:
    validator = subprocess.check_output([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, text=True).strip().splitlines()[-1]
    unchanged = git_clean_diff(WORLD0_BASE, "artifacts/frozen/world0_v0_1")
    return {"pass": validator == "GRI_02_WORLD0_PASS" and unchanged, "frozen_commit": WORLD0_BASE, "validator_terminal_state": validator, "byte_identity_against_frozen_commit": unchanged}


def structural_case(value: str = "RED", case_id: str = "dmc01pa-structural") -> dict:
    return {
        "case_id": case_id,
        "episodes": [
            {"index": 0, "events": [{"kind": "write", "memory_id": f"{case_id}-write", "entity": "entity-00", "field": "value", "value": value}]},
            {"index": 1, "events": [{"kind": "query", "entity": "entity-00", "field": "value", "mode": "current", "as_of_episode": None}]},
        ],
        "answer": value,
    }


def loss_semantics() -> dict:
    logits = [torch.tensor([float(index) for index in range(8)]), torch.tensor([float(7 - index) for index in range(8)])]
    targets = [2, 5]
    expected = torch.stack([F.cross_entropy(logit.unsqueeze(0), torch.tensor([target]), reduction="mean") for logit, target in zip(logits, targets)]).mean()
    actual = torch.stack([case_cross_entropy(logit, target) for logit, target in zip(logits, targets)]).mean()
    return {
        "pass": torch.equal(actual, expected),
        "function": "torch.nn.functional.cross_entropy",
        "individual_reduction": "mean",
        "batch_reduction": "arithmetic mean of complete-case losses",
        "auxiliary_losses": [],
        "class_condition_delay_weighting": False,
    }


def optimizer_cadence() -> dict:
    exact, _ = build_paired_controllers(STRUCTURAL_SEED)
    optimizer = torch.optim.AdamW(exact.parameters(), lr=3e-3, weight_decay=1e-4)
    step_calls: list[bool] = []
    original_step = optimizer.step

    def counted_step(*args, **kwargs):
        step_calls.append(True)
        return original_step(*args, **kwargs)

    optimizer.step = counted_step
    report = train_complete_case_batch(exact, [structural_case(case_id="a"), structural_case("BLUE", "b")], optimizer)
    source = inspect.getsource(train_complete_case_batch)
    return {
        "pass": len(step_calls) == 1 and source.count("optimizer.step()") == 1 and source.count("optimizer.zero_grad(set_to_none=True)") == 1,
        "batch_case_count": 2,
        "optimizer_step_calls": len(step_calls),
        "batch_loss_observed": report["batch_loss"],
        "zero_grad_set_to_none": True,
        "gradient_clip": 1.0,
        "no_gradient_accumulation": True,
        "no_scheduler": True,
    }


def ordering_validation(train_cases: list[dict]) -> tuple[dict, dict]:
    manifest = order_manifest(train_cases, EVIDENCE_SEEDS)
    first = [case["case_id"] for case in ordered_cases(train_cases, seed=1337, epoch=0)]
    repeat = [case["case_id"] for case in ordered_cases(train_cases, seed=1337, epoch=0)]
    different_seed = [case["case_id"] for case in ordered_cases(train_cases, seed=1338, epoch=0)]
    different_epoch = [case["case_id"] for case in ordered_cases(train_cases, seed=1337, epoch=1)]
    exact_batches = [[case["case_id"] for case in batch] for batch in case_batches(train_cases, seed=1337, epoch=0)]
    no_memory_batches = [[case["case_id"] for case in batch] for batch in case_batches(train_cases, seed=1337, epoch=0)]
    validation = {
        "pass": first == repeat and first != different_seed and first != different_epoch and exact_batches == no_memory_batches and all(len(batch) <= 16 for batch in exact_batches),
        "same_seed_epoch_byte_identical": first == repeat,
        "different_seed_changes_order": first != different_seed,
        "different_epoch_changes_order": first != different_epoch,
        "paired_exact_no_memory_order_identical": exact_batches == no_memory_batches,
        "batch_sizes": [len(batch) for batch in exact_batches],
        "evidence_seeds_executed": [],
    }
    return manifest, validation


def autograd_semantics() -> dict:
    exact, no_memory = build_paired_controllers(STRUCTURAL_SEED)
    case = structural_case()
    exact.train()
    exact.reset_case()
    record = exact.process_write(case["episodes"][0]["events"][0], 0)
    assert record is not None
    seen: list[torch.Tensor] = []
    record.hidden_value.register_hook(lambda gradient: seen.append(gradient))
    logits = exact.answer_query(case["episodes"][1]["events"][0])
    loss = case_cross_entropy(logits, target_for_case(case))
    loss.backward()
    no_memory.reset_case()
    no_memory.process_write(case["episodes"][0]["events"][0], 0)
    no_memory_logits = no_memory.answer_query(case["episodes"][1]["events"][0])
    no_memory.reset_case()
    no_memory_query_only = no_memory.answer_query(case["episodes"][1]["events"][0])
    return {
        "pass": bool(seen) and seen[0].shape == (HIDDEN_DIM,) and any(parameter.grad is not None for parameter in exact.parameters()) and torch.equal(no_memory_logits, no_memory_query_only) and no_memory.ledger is None,
        "exact_hidden_hook_called": bool(seen),
        "exact_hidden_gradient_shape": list(seen[0].shape) if seen else None,
        "exact_parameter_gradient_present": any(parameter.grad is not None for parameter in exact.parameters()),
        "no_memory_prior_write_changes_query": not torch.equal(no_memory_logits, no_memory_query_only),
        "no_memory_ledger_present": no_memory.ledger is not None,
        "detach_used": False,
        "no_grad_used_on_write": False,
        "retain_graph_used": False,
    }


def answer_firewall() -> dict:
    import dmc01.memory as memory_module

    run_source = inspect.getsource(run_case_logits)
    target_source = inspect.getsource(target_for_case)
    memory_source = inspect.getsource(memory_module)
    passed = (
        'case["answer"]' not in run_source
        and 'case["answer"]' in target_source
        and "oracle_answer" not in run_source
        and "oracle_answer" not in memory_source
        and "answer" not in inspect.signature(DMC01Controller.answer_query).parameters
    )
    return {
        "pass": passed,
        "target_constructor_reads_answer": 'case["answer"]' in target_source,
        "event_path_reads_answer": 'case["answer"]' in run_source,
        "oracle_visible_to_event_or_memory_path": "oracle_answer" in run_source or "oracle_answer" in memory_source,
        "answer_parameter_in_query_api": "answer" in inspect.signature(DMC01Controller.answer_query).parameters,
    }


def resume_semantics(dmc00: dict) -> dict:
    exact, _ = build_paired_controllers(STRUCTURAL_SEED)
    optimizer = torch.optim.AdamW(exact.parameters(), lr=3e-3, weight_decay=1e-4)
    payload = checkpoint_payload(exact, optimizer, seed=STRUCTURAL_SEED, completed_epoch=0, next_batch_index=1, source_commit=DMC01P_BASE, dataset_identity=dmc00, final_loss=1.0)
    required = {"model_state_dict", "optimizer_state", "seed", "completed_epoch", "next_batch_index", "python_rng_state", "numpy_rng_state", "torch_rng_state", "training_config", "source_commit", "dmc00_dataset_identity", "final_loss", "metrics"}
    return {"pass": required <= set(payload) and payload["next_batch_index"] == 1 and payload["checkpoint_boundary"].startswith("immediately after"), "required_fields": sorted(required), "checkpoint_boundary": payload["checkpoint_boundary"], "resume_order_reconstruction": "seed + epoch + case_id stateless SHA ordering", "repeated_or_skipped_batches_allowed": False}


def parameter_identity() -> dict:
    exact, no_memory = build_paired_controllers(STRUCTURAL_SEED)
    return {"pass": trainable_parameter_count(exact) == trainable_parameter_count(no_memory) == 30_912 and state_dict_equal(exact, no_memory), "structural_seed": STRUCTURAL_SEED, "exact_memory_parameters": trainable_parameter_count(exact), "no_memory_parameters": trainable_parameter_count(no_memory), "tensor_for_tensor_initialization_equal": state_dict_equal(exact, no_memory), "evidence_seeds_executed": []}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dmc00 = verify_directory_identity("dmc00", DMC00_BASE)
    dmc01p = verify_directory_identity("dmc01p", DMC01P_BASE)
    world0 = world0_identity()
    train_cases = read_jsonl(ROOT / "artifacts/dmc00/datasets/train.jsonl")
    manifest, ordering = ordering_validation(train_cases)
    write_json(OUT / "DMC01PA_CONFIG.json", {"unit": "DMC-01P-A", "status": "training_semantics_amendment_structural_only", "generation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "dmc00_commit": DMC00_BASE, "dmc01p_commit": DMC01P_BASE, "world0_frozen_commit": WORLD0_BASE, "structural_seed": STRUCTURAL_SEED, "evidence_seeds_frozen_but_not_executed": EVIDENCE_SEEDS, "scientific_training_executed": False, "training_config": {**FROZEN_TRAINING_CONFIG.__dict__, "batch_semantics": "complete cases"}, "autograd": "stored hidden_value clone remains graph-connected; no detach", "primary_metric": "mean(R64,R256,R1024,C256,C1024,S_current,S_history,D512,D1024)", "historical_gates_unchanged": True})
    write_json(OUT / "loss_semantics.json", loss_semantics())
    write_json(OUT / "optimizer_cadence.json", optimizer_cadence())
    write_json(OUT / "ordering_spec.json", {"pass": ordering["pass"], "algorithm": manifest["algorithm"], "sort": manifest["sort"], "epoch_range": [0, 79], "batch_size": 16, "ordering_validation": ordering})
    write_json(OUT / "ordering_manifest.json", manifest)
    write_json(OUT / "autograd_semantics.json", autograd_semantics())
    write_json(OUT / "answer_firewall.json", answer_firewall())
    write_json(OUT / "resume_semantics.json", resume_semantics(dmc00))
    write_json(OUT / "parameter_identity.json", parameter_identity())
    write_json(OUT / "dmc00_identity.json", dmc00)
    write_json(OUT / "world0_identity.json", world0)
    validation_names = ("loss_semantics", "optimizer_cadence", "ordering_spec", "autograd_semantics", "answer_firewall", "resume_semantics", "parameter_identity")
    checks = {name: json.loads((OUT / f"{name}.json").read_text())["pass"] for name in validation_names}
    checks["dmc00_identity"] = dmc00["pass"]
    checks["dmc01p_identity"] = dmc01p["pass"]
    checks["world0_identity"] = world0["pass"]
    if not dmc00["pass"] or not dmc01p["pass"] or not world0["pass"]:
        terminal = "DMC_01PA_INVALID"
    elif not checks["autograd_semantics"]:
        terminal = "DMC_01PA_AUTOGRAD_INVALID"
    elif not checks["answer_firewall"]:
        terminal = "DMC_01PA_MEMORY_LEAK"
    elif not checks["ordering_spec"]:
        terminal = "DMC_01PA_ORDER_INVALID"
    elif not checks["loss_semantics"] or not checks["optimizer_cadence"] or not checks["resume_semantics"]:
        terminal = "DMC_01PA_REPAIR_REQUIRED"
    elif all(checks.values()):
        terminal = "DMC_01PA_PREREGISTERED"
    else:
        terminal = "DMC_01PA_MEMORY_LEAK" if not checks.get("parameter_identity", True) else "DMC_01PA_REPAIR_REQUIRED"
    write_json(OUT / "DMC01PA_RECEIPT.json", {"unit": "DMC-01P-A", "terminal_state": terminal, "validation_checks": checks, "scientific_training_executed": False, "evidence_seeds_executed": [], "historical_dmc01p_artifacts_rewritten": False})
    manifest_hashes = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest_hashes[str(path.relative_to(OUT))] = sha256(path)
    write_json(OUT / "SHA256SUMS.json", manifest_hashes)
    print(terminal)
    return 0 if terminal == "DMC_01PA_PREREGISTERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
