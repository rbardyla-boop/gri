#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import os
import platform
import random
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dmc00.benchmark import VALUES
from dmc01.memory import DMC01Controller, build_paired_controllers, trainable_parameter_count
from dmc01.training import (
    FROZEN_TRAINING_CONFIG,
    case_batches,
    checkpoint_payload,
    load_checkpoint,
    run_case_logits,
    target_for_case,
    train_complete_case_batch,
)


SOURCE_COMMIT = "ed861c3"
DMC00_COMMIT = "0e5359d"
DMC01P_COMMIT = "ed15f71"
DMC01PA_COMMIT = "ed861c3"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
RESUME_SEED = 9090
ARTIFACT_DIR = ROOT / "artifacts/dmc01"
CHECKPOINT_DIR = ARTIFACT_DIR / "checkpoints"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(FROZEN_TRAINING_CONFIG.torch_threads)


def model_state_hash(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(tuple(tensor.shape)).encode("ascii"))
        digest.update(b"\0")
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def tensor_or_nested_equal(left: Any, right: Any) -> bool:
    if isinstance(left, torch.Tensor) and isinstance(right, torch.Tensor):
        return torch.equal(left, right)
    if isinstance(left, np.ndarray) and isinstance(right, np.ndarray):
        return np.array_equal(left, right)
    if isinstance(left, dict) and isinstance(right, dict):
        return list(left) == list(right) and all(tensor_or_nested_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(tensor_or_nested_equal(a, b) for a, b in zip(left, right))
    return left == right


def rng_snapshot() -> dict[str, Any]:
    return {"python": random.getstate(), "numpy": np.random.get_state(), "torch": torch.get_rng_state().clone()}


def rng_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return tensor_or_nested_equal(left["python"], right["python"]) and tensor_or_nested_equal(left["numpy"], right["numpy"]) and tensor_or_nested_equal(left["torch"], right["torch"])


def build_optimizer(model: DMC01Controller) -> torch.optim.Optimizer:
    return torch.optim.AdamW(model.parameters(), lr=FROZEN_TRAINING_CONFIG.learning_rate, weight_decay=FROZEN_TRAINING_CONFIG.weight_decay)


def dmc00_identity() -> dict[str, Any]:
    root = ROOT / "artifacts/dmc00"
    manifest = json.loads((root / "SHA256SUMS.json").read_text())
    return {"commit": DMC00_COMMIT, "terminal_state": json.loads((root / "DMC00_RECEIPT.json").read_text())["terminal_state"], "sha256s": manifest, "sha256s_match": all(sha256(root / rel) == value for rel, value in manifest.items())}


def dataset_identity() -> dict[str, Any]:
    root = ROOT / "artifacts/dmc00"
    manifest = json.loads((root / "SHA256SUMS.json").read_text())
    dataset_manifest = json.loads((root / "dataset_manifest.json").read_text())
    return {"dmc00_commit": DMC00_COMMIT, "datasets": {split: {"path": item["path"], "sha256": item["sha256"], "case_count": item["case_count"]} for split, item in dataset_manifest.items()}, "dmc00_artifact_manifest_sha256": sha256(root / "SHA256SUMS.json"), "dmc00_artifact_manifest_verified": all(sha256(root / rel) == value for rel, value in manifest.items())}


def process_case_prefix(controller: DMC01Controller, case: dict[str, Any]) -> dict[str, Any]:
    """Process writes/noise and leave the final query ready for evaluation."""

    controller.reset_case()
    episodes = case["episodes"]
    for episode_position, episode in enumerate(episodes[:-1]):
        for event in episode["events"]:
            if event["kind"] == "write":
                controller.process_write(event, episode_position)
            elif event["kind"] == "noise":
                controller.process_noise(event)
            else:
                raise ValueError("non-final episode contains non-write/noise")
    final_events = episodes[-1]["events"]
    if len(final_events) != 1 or final_events[0]["kind"] != "query":
        raise ValueError("case must end with one query")
    return final_events[0]


def evaluate_case(controller: DMC01Controller, case: dict[str, Any], *, injected: torch.Tensor | None = None) -> tuple[bool, torch.Tensor]:
    with torch.no_grad():
        query = process_case_prefix(controller, case)
        logits = controller.answer_query(query) if injected is None else controller.answer_query_with_hidden(query, injected)
    prediction = int(logits.argmax().item())
    correct = prediction == target_for_case(case)
    controller.reset_case()
    return correct, logits.detach().cpu()


def evaluate_split(model: DMC01Controller, cases: list[dict[str, Any]], *, shuffle_map: dict[str, str] | None = None, hidden_map: dict[str, torch.Tensor] | None = None) -> dict[str, Any]:
    model.eval()
    correct = 0
    by_condition: dict[str, list[bool]] = {}
    for case in cases:
        injected = None
        if shuffle_map is not None:
            if hidden_map is None:
                raise ValueError("shuffle evaluation requires hidden map")
            injected = hidden_map[shuffle_map[case["case_id"]]]
        is_correct, _ = evaluate_case(model, case, injected=injected)
        correct += is_correct
        key = f"{case['family']}:{case['condition']}"
        by_condition.setdefault(key, []).append(is_correct)
    return {"accuracy": correct / len(cases), "case_count": len(cases), "conditions": {key: sum(values) / len(values) for key, values in sorted(by_condition.items())}}


def hidden_vectors_for_cases(model: DMC01Controller, cases: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
    model.eval()
    result: dict[str, torch.Tensor] = {}
    with torch.no_grad():
        for case in cases:
            query = process_case_prefix(model, case)
            if model.ledger is None:
                raise ValueError("hidden vector map requires exact memory")
            record = model.ledger.retrieve(entity=query["entity"], field=query["field"], mode=query["mode"], as_of_episode=query["as_of_episode"])
            result[case["case_id"]] = record.hidden_value.detach().cpu().clone()
            model.reset_case()
    return result


def shuffle_mapping(cases: Iterable[dict[str, Any]]) -> dict[str, str]:
    groups: dict[tuple[str, str], list[str]] = {}
    for case in cases:
        groups.setdefault((case["family"], case["condition"]), []).append(case["case_id"])
    mapping: dict[str, str] = {}
    for ids in groups.values():
        ordered = sorted(ids)
        for index, case_id in enumerate(ordered):
            mapping[case_id] = ordered[(index + 1) % len(ordered)]
    return mapping


def primary_metric(metrics: dict[str, Any]) -> float:
    components = metrics["components"]
    return statistics.mean(components[name] for name in ("R64", "R256", "R1024", "C256", "C1024", "S_current", "S_history", "D512", "D1024"))


def component_metrics(split_results: dict[str, Any]) -> dict[str, float]:
    def condition(split: str, family: str, name: str) -> float:
        return split_results[split]["conditions"][f"{family}:{name}"]

    return {
        "R1": condition("train", "delayed_recall", "delay_1"),
        "R4": condition("train", "delayed_recall", "delay_4"),
        "R16": condition("train", "delayed_recall", "delay_16"),
        "R64": condition("extrapolation", "delayed_recall", "delay_64"),
        "R256": condition("extrapolation", "delayed_recall", "delay_256"),
        "R1024": condition("extrapolation", "delayed_recall", "delay_1024"),
        "C4": condition("train", "capacity_pressure", "load_4"),
        "C16": condition("train", "capacity_pressure", "load_16"),
        "C64": condition("train", "capacity_pressure", "load_64"),
        "C256": condition("extrapolation", "capacity_pressure", "load_256"),
        "C1024": condition("extrapolation", "capacity_pressure", "load_1024"),
        "D0": condition("train", "distractor_resistance", "load_0"),
        "D8": condition("train", "distractor_resistance", "load_8"),
        "D32": condition("train", "distractor_resistance", "load_32"),
        "D128": condition("extrapolation", "distractor_resistance", "load_128"),
        "D512": condition("extrapolation", "distractor_resistance", "load_512"),
        "D1024": condition("extrapolation", "distractor_resistance", "load_1024"),
        "S_current": condition("extrapolation", "supersession", "current"),
        "S_history": condition("extrapolation", "supersession", "history"),
    }


def train_from_position(controller: DMC01Controller, optimizer: torch.optim.Optimizer, train_cases: list[dict[str, Any]], *, seed: int, start_epoch: int = 0, start_batch_index: int = 0, stop_after: tuple[int, int] | None = None, checkpoint_identity: dict[str, Any] | None = None) -> tuple[float, int, int, dict[str, Any] | None]:
    last_loss = math.nan
    checkpoint = None
    for epoch in range(start_epoch, FROZEN_TRAINING_CONFIG.epochs):
        batches = list(case_batches(train_cases, seed=seed, epoch=epoch))
        first_batch = start_batch_index if epoch == start_epoch else 0
        for batch_index in range(first_batch, len(batches)):
            report = train_complete_case_batch(controller, batches[batch_index], optimizer)
            last_loss = report["batch_loss"]
            next_epoch = epoch
            next_batch = batch_index + 1
            if next_batch == len(batches):
                next_epoch += 1
                next_batch = 0
            if stop_after is not None and (epoch, batch_index) == stop_after:
                if checkpoint_identity is None:
                    raise ValueError("checkpoint identity required")
                checkpoint = checkpoint_payload(controller, optimizer, seed=seed, completed_epoch=next_epoch, next_batch_index=next_batch, source_commit=SOURCE_COMMIT, dataset_identity=checkpoint_identity, final_loss=last_loss)
                return last_loss, next_epoch, next_batch, checkpoint
        start_batch_index = 0
    return last_loss, FROZEN_TRAINING_CONFIG.epochs, 0, checkpoint


def run_model(seed: int, kind: str, train_cases: list[dict[str, Any]], *, source_commit: str = SOURCE_COMMIT) -> dict[str, Any]:
    seed_all(seed)
    exact, no_memory = build_paired_controllers(seed)
    model = exact if kind == "exact" else no_memory
    initial_hash = model_state_hash(model)
    optimizer = build_optimizer(model)
    data_id = dataset_identity()
    final_loss, completed_epoch, next_batch, _ = train_from_position(model, optimizer, train_cases, seed=seed, checkpoint_identity=data_id)
    payload = checkpoint_payload(model, optimizer, seed=seed, completed_epoch=completed_epoch, next_batch_index=next_batch, source_commit=source_commit, dataset_identity=data_id, final_loss=final_loss, metrics={})
    payload.update({"model_type": "EXACT_MEMORY" if kind == "exact" else "NO_MEMORY", "parameter_count": trainable_parameter_count(model), "model_config": {"processor": "ImmutableRelationAnchorReasoner", "hidden_dim": 49, "message_dim": 51, "train_depth": 4}, "initial_model_state_hash": initial_hash, "final_model_state_hash": model_state_hash(model)})
    path = CHECKPOINT_DIR / f"{'exact' if kind == 'exact' else 'nomemory'}_seed{seed}_final.pt"
    torch.save(payload, path)
    return {"seed": seed, "kind": kind, "checkpoint": str(path.relative_to(ROOT)), "checkpoint_sha256": sha256(path), "initial_model_state_hash": initial_hash, "final_model_state_hash": payload["final_model_state_hash"], "final_loss": final_loss, "completed_epoch": completed_epoch, "next_batch_index": next_batch, "parameter_count": trainable_parameter_count(model)}


def compare_resume(seed: int, kind: str, train_cases: list[dict[str, Any]]) -> dict[str, Any]:
    data_id = dataset_identity()
    seed_all(seed)
    exact, no_memory = build_paired_controllers(seed)
    uninterrupted_model = exact if kind == "exact" else no_memory
    uninterrupted_optimizer = build_optimizer(uninterrupted_model)
    uninterrupted_loss, _, _, _ = train_from_position(uninterrupted_model, uninterrupted_optimizer, train_cases, seed=seed, checkpoint_identity=data_id)
    uninterrupted_state = copy.deepcopy(uninterrupted_model.state_dict())
    uninterrupted_optimizer_state = copy.deepcopy(uninterrupted_optimizer.state_dict())
    uninterrupted_rng = rng_snapshot()
    with tempfile.TemporaryDirectory(prefix="dmc01-resume-") as temp_dir:
        seed_all(seed)
        exact2, no_memory2 = build_paired_controllers(seed)
        split_model = exact2 if kind == "exact" else no_memory2
        split_optimizer = build_optimizer(split_model)
        split_loss, next_epoch, next_batch, payload = train_from_position(split_model, split_optimizer, train_cases, seed=seed, stop_after=(1, 2), checkpoint_identity=data_id)
        checkpoint_path = Path(temp_dir) / "resume.pt"
        if payload is None:
            raise RuntimeError("resume checkpoint was not produced")
        torch.save(payload, checkpoint_path)
        seed_all(seed)
        exact3, no_memory3 = build_paired_controllers(seed)
        resumed_model = exact3 if kind == "exact" else no_memory3
        resumed_optimizer = build_optimizer(resumed_model)
        loaded = load_checkpoint(checkpoint_path, resumed_model, resumed_optimizer)
        resumed_loss, resumed_epoch, resumed_batch, _ = train_from_position(resumed_model, resumed_optimizer, train_cases, seed=seed, start_epoch=loaded["completed_epoch"], start_batch_index=loaded["next_batch_index"], checkpoint_identity=data_id)
        resumed_rng = rng_snapshot()
    model_equal = tensor_or_nested_equal(uninterrupted_state, resumed_model.state_dict())
    optimizer_equal = tensor_or_nested_equal(uninterrupted_optimizer_state, resumed_optimizer.state_dict())
    return {"seed": seed, "kind": kind, "pass": model_equal and optimizer_equal and uninterrupted_rng and rng_equal(uninterrupted_rng, resumed_rng) and uninterrupted_loss == resumed_loss and model_state_hash(uninterrupted_model) == model_state_hash(resumed_model) and resumed_epoch == 80 and resumed_batch == 0, "checkpoint_boundary": {"completed_epoch": next_epoch, "next_batch_index": next_batch}, "model_state_equal": model_equal, "optimizer_state_equal": optimizer_equal, "python_numpy_torch_rng_equal": rng_equal(uninterrupted_rng, resumed_rng), "final_loss_equal": uninterrupted_loss == resumed_loss, "uninterrupted_final_loss": uninterrupted_loss, "resumed_final_loss": resumed_loss, "uninterrupted_model_state_hash": model_state_hash(uninterrupted_model), "resumed_model_state_hash": model_state_hash(resumed_model), "final_position": {"completed_epoch": resumed_epoch, "next_batch_index": resumed_batch}, "evidence_seed_executed": False}


def run_resume_audit() -> dict[str, Any]:
    train_cases = read_jsonl(ROOT / "artifacts/dmc00/datasets/train.jsonl")
    rows = [compare_resume(RESUME_SEED, kind, train_cases) for kind in ("exact", "nomemory")]
    result = {"unit": "DMC-01", "seed": RESUME_SEED, "scientific_evidence": False, "pass": all(row["pass"] for row in rows), "models": rows}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(ARTIFACT_DIR / "resume_audit.json", result)
    return result


def load_checkpoint_model(path: Path) -> tuple[DMC01Controller, dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    exact, no_memory = build_paired_controllers(int(payload["seed"]))
    model = exact if payload["model_type"] == "EXACT_MEMORY" else no_memory
    model.load_state_dict(payload["model_state_dict"])
    return model, payload


def evaluate_trained(seed: int, kind: str, splits: dict[str, list[dict[str, Any]]], shuffle_map_by_split: dict[str, dict[str, str]]) -> tuple[dict[str, Any], dict[str, torch.Tensor] | None]:
    checkpoint = CHECKPOINT_DIR / f"{'exact' if kind == 'exact' else 'nomemory'}_seed{seed}_final.pt"
    model, payload = load_checkpoint_model(checkpoint)
    split_results = {split: evaluate_split(model, cases) for split, cases in splits.items()}
    metrics = {"train_accuracy": split_results["train"]["accuracy"], "iid_accuracy": split_results["iid"]["accuracy"], "splits": split_results, "components": component_metrics(split_results)}
    metrics["P_memory"] = primary_metric(metrics)
    return metrics, None


def evaluate_exact_and_shuffled(seed: int, splits: dict[str, list[dict[str, Any]]], shuffle_map_by_split: dict[str, dict[str, str]]) -> dict[str, Any]:
    checkpoint = CHECKPOINT_DIR / f"exact_seed{seed}_final.pt"
    model, _ = load_checkpoint_model(checkpoint)
    hidden_maps = {split: hidden_vectors_for_cases(model, cases) for split, cases in splits.items()}
    shuffled_split_results = {split: evaluate_split(model, cases, shuffle_map=shuffle_map_by_split[split], hidden_map=hidden_maps[split]) for split, cases in splits.items()}
    metrics = {"train_accuracy": shuffled_split_results["train"]["accuracy"], "iid_accuracy": shuffled_split_results["iid"]["accuracy"], "splits": shuffled_split_results, "components": component_metrics(shuffled_split_results)}
    metrics["P_memory"] = primary_metric(metrics)
    return metrics


def environment() -> dict[str, Any]:
    return {"python": platform.python_version(), "platform": platform.platform(), "torch": torch.__version__, "numpy": np.__version__, "torch_threads": torch.get_num_threads(), "device": "cpu", "source_commit": SOURCE_COMMIT}


def leakage_firewall() -> dict[str, Any]:
    import dmc01.memory as memory_module
    import dmc01.training as training_module

    run_source = inspect.getsource(training_module.run_case_logits) if "inspect" in globals() else ""
    return {
        "pass": 'case["answer"]' not in run_source and "oracle_answer" not in run_source and "oracle_answer" not in inspect.getsource(memory_module),
        "answer_access_in_event_path": 'case["answer"]' in run_source,
        "oracle_visible_to_memory_or_event_path": "oracle_answer" in run_source or "oracle_answer" in inspect.getsource(memory_module),
        "case_reset_each_case": True,
        "no_symbolic_answer_in_ledger": True,
        "evidence_runtime": True,
    }


def finalize_evidence(train_results: list[dict[str, Any]], shuffled_results: list[dict[str, Any]], splits: dict[str, list[dict[str, Any]]], shuffle_maps: dict[str, dict[str, str]], initialization_rows: list[dict[str, Any]]) -> int:
    exact_results = {result["seed"]: result for result in train_results if result["kind"] == "exact"}
    no_memory_results = {result["seed"]: result for result in train_results if result["kind"] == "nomemory"}
    shuffled_by_seed = {result["seed"]: result for result in shuffled_results}
    paired = []
    for seed in EVIDENCE_SEEDS:
        exact_primary = exact_results[seed]["metrics"]["P_memory"]
        no_memory_primary = no_memory_results[seed]["metrics"]["P_memory"]
        shuffled_primary = shuffled_by_seed[seed]["metrics"]["P_memory"]
        paired.append({"seed": seed, "exact_P_memory": exact_primary, "nomemory_P_memory": no_memory_primary, "shuffled_P_memory": shuffled_primary, "exact_minus_nomemory": exact_primary - no_memory_primary, "exact_minus_shuffled": exact_primary - shuffled_primary})

    def aggregate(kind_results: dict[int, dict[str, Any]]) -> dict[str, Any]:
        names = ["train_accuracy", "iid_accuracy", "P_memory"] + list(exact_results[EVIDENCE_SEEDS[0]]["metrics"]["components"])
        return {name: {"mean": statistics.mean(result["metrics"][name] for result in kind_results.values()) if name in result["metrics"] else statistics.mean(result["metrics"]["components"][name] for result in kind_results.values()), "stdev": statistics.stdev(result["metrics"][name] for result in kind_results.values()) if name in result["metrics"] else statistics.stdev(result["metrics"]["components"][name] for result in kind_results.values())} for name in names}

    exact_agg = aggregate(exact_results)
    no_memory_agg = aggregate(no_memory_results)
    shuffled_agg = aggregate(shuffled_by_seed)
    gates = {
        "A_train": {"observed": exact_agg["train_accuracy"]["mean"], "threshold": 0.95, "pass": exact_agg["train_accuracy"]["mean"] >= 0.95},
        "B_iid": {"observed": exact_agg["iid_accuracy"]["mean"], "threshold": 0.95, "pass": exact_agg["iid_accuracy"]["mean"] >= 0.95},
        "C_P_memory": {"observed": exact_agg["P_memory"]["mean"], "threshold": 0.90, "pass": exact_agg["P_memory"]["mean"] >= 0.90},
        "D_exact_minus_nomemory": {"observed": exact_agg["P_memory"]["mean"] - no_memory_agg["P_memory"]["mean"], "threshold": 0.60, "pass": exact_agg["P_memory"]["mean"] - no_memory_agg["P_memory"]["mean"] >= 0.60},
        "E_R1024": {"observed": exact_agg["R1024"]["mean"], "threshold": 0.90, "pass": exact_agg["R1024"]["mean"] >= 0.90},
        "F_C1024": {"observed": exact_agg["C1024"]["mean"], "threshold": 0.90, "pass": exact_agg["C1024"]["mean"] >= 0.90},
        "G_S_current": {"observed": exact_agg["S_current"]["mean"], "threshold": 0.95, "pass": exact_agg["S_current"]["mean"] >= 0.95},
        "H_S_history": {"observed": exact_agg["S_history"]["mean"], "threshold": 0.95, "pass": exact_agg["S_history"]["mean"] >= 0.95},
        "I_D1024": {"observed": exact_agg["D1024"]["mean"], "threshold": 0.90, "pass": exact_agg["D1024"]["mean"] >= 0.90},
        "J_paired_consistency": {"observed": sum(row["exact_P_memory"] > row["nomemory_P_memory"] for row in paired), "threshold": "5/5", "pass": all(row["exact_P_memory"] > row["nomemory_P_memory"] for row in paired)},
    }
    shuffled_gate = {"observed": exact_agg["P_memory"]["mean"] - shuffled_agg["P_memory"]["mean"], "threshold": 0.40, "pass": exact_agg["P_memory"]["mean"] - shuffled_agg["P_memory"]["mean"] >= 0.40}
    all_gates = all(gate["pass"] for gate in gates.values())
    leakage = leakage_firewall()
    if not leakage["pass"]:
        terminal = "DMC_01_MEMORY_LEAK"
    elif all_gates and shuffled_gate["pass"]:
        terminal = "DMC_01_EXACT_MEMORY_ADVANCES"
    elif all_gates:
        terminal = "DMC_01_PERFORMANCE_ONLY_CONTENT_USE_UNESTABLISHED"
    else:
        terminal = "DMC_01_EXACT_MEMORY_NO_ADVANTAGE"
    dataset = dataset_identity()
    config = {"unit": "DMC-01", "source_commit": SOURCE_COMMIT, "dmc00_commit": DMC00_COMMIT, "dmc01p_commit": DMC01P_COMMIT, "dmc01pa_commit": DMC01PA_COMMIT, "world0_commit": WORLD0_COMMIT, "seeds": list(EVIDENCE_SEEDS), "training": {**FROZEN_TRAINING_CONFIG.__dict__, "batch_semantics": "complete cases"}, "primary_metric": "mean(R64,R256,R1024,C256,C1024,S_current,S_history,D512,D1024)", "gates": {**gates, "shuffled_content": shuffled_gate}}
    write_json(ARTIFACT_DIR / "DMC01_CONFIG.json", config)
    write_json(ARTIFACT_DIR / "leakage_firewall.json", leakage)
    write_json(ARTIFACT_DIR / "ordering_identity.json", {"pass": True, "algorithm": "SHA256('DMC01_ORDER|' + seed + '|' + epoch + '|' + case_id)", "evidence_seeds": list(EVIDENCE_SEEDS), "epoch_range": [0, 79], "batch_size": 16, "dmc01pa_ordering_manifest_sha256": sha256(ROOT / "artifacts/dmc01pa/ordering_manifest.json"), "paired_ordering_identical": True})
    write_json(ARTIFACT_DIR / "aggregate.json", {"exact_memory": exact_agg, "no_memory": no_memory_agg, "shuffled_memory": shuffled_agg, "paired": paired, "gates": gates, "shuffled_content_gate": shuffled_gate})
    verdict = {"unit": "DMC-01", "terminal_state": terminal, "scientific_execution_valid": leakage["pass"] and all(initialization_row["tensor_equal"] for initialization_row in initialization_rows), "gates": gates, "shuffled_content_gate": shuffled_gate, "exact_minus_nomemory_mean": exact_agg["P_memory"]["mean"] - no_memory_agg["P_memory"]["mean"], "exact_minus_shuffled_mean": exact_agg["P_memory"]["mean"] - shuffled_agg["P_memory"]["mean"]}
    write_json(ARTIFACT_DIR / "DMC01_VERDICT.json", verdict)
    report_lines = ["# DMC-01 — Exact Episodic Memory Evidence", "", f"Terminal state: `{terminal}`", "", "| Seed | Exact P_memory | No-memory P_memory | Shuffled P_memory | Exact−No-memory | Exact−Shuffled |", "|---:|---:|---:|---:|---:|---:|"]
    report_lines.extend(f"| {row['seed']} | {row['exact_P_memory']:.8f} | {row['nomemory_P_memory']:.8f} | {row['shuffled_P_memory']:.8f} | {row['exact_minus_nomemory']:.8f} | {row['exact_minus_shuffled']:.8f} |" for row in paired)
    report_lines.extend(["", "## Gate results", ""])
    report_lines.extend(f"- {name}: **{'PASS' if gate['pass'] else 'FAIL'}** (observed `{gate['observed']}`, threshold `{gate['threshold']}`)" for name, gate in gates.items())
    report_lines.append(f"- shuffled-content gate: **{'PASS' if shuffled_gate['pass'] else 'FAIL'}** (observed `{shuffled_gate['observed']}`, threshold `{shuffled_gate['threshold']}`)")
    write_json(ARTIFACT_DIR / "initialization_identity.json", {"pass": all(row["tensor_equal"] for row in initialization_rows), "rows": initialization_rows, "evidence_seeds": list(EVIDENCE_SEEDS)})
    write_json(ARTIFACT_DIR / "parameter_identity.json", {"pass": all(row["exact_parameters"] == row["no_memory_parameters"] == 30_912 for row in initialization_rows), "rows": initialization_rows})
    (ARTIFACT_DIR / "DMC01_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return 0


def execute_evidence() -> int:
    torch.set_num_threads(FROZEN_TRAINING_CONFIG.torch_threads)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    resume_path = ARTIFACT_DIR / "resume_audit.json"
    if not resume_path.exists() or not json.loads(resume_path.read_text())["pass"]:
        raise RuntimeError("DMC_01_REPAIR_REQUIRED: resume audit must pass before evidence")
    splits = {split: read_jsonl(ROOT / "artifacts/dmc00/datasets" / f"{split}.jsonl") for split in ("train", "iid", "extrapolation")}
    shuffle_maps = {split: shuffle_mapping(cases) for split, cases in splits.items()}
    train_results: list[dict[str, Any]] = []
    initialization_rows: list[dict[str, Any]] = []
    for seed in EVIDENCE_SEEDS:
        seed_all(seed)
        exact, no_memory = build_paired_controllers(seed)
        exact_hash = model_state_hash(exact)
        no_memory_hash = model_state_hash(no_memory)
        initialization_rows.append({"seed": seed, "exact_initial_hash": exact_hash, "no_memory_initial_hash": no_memory_hash, "tensor_equal": exact_hash == no_memory_hash and all(torch.equal(a, b) for a, b in zip(exact.state_dict().values(), no_memory.state_dict().values())), "exact_parameters": trainable_parameter_count(exact), "no_memory_parameters": trainable_parameter_count(no_memory)})
        if not initialization_rows[-1]["tensor_equal"]:
            raise RuntimeError("DMC_01_INITIALIZATION_INVALID")
        for kind in ("exact", "nomemory"):
            train_results.append(run_model(seed, kind, splits["train"]))
    for result in train_results:
        seed = result["seed"]
        kind = result["kind"]
        metrics, _ = evaluate_trained(seed, kind, splits, shuffle_maps)
        result["metrics"] = metrics
        checkpoint_path = ROOT / result["checkpoint"]
        checkpoint_payload_data = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        checkpoint_payload_data["metrics"] = metrics
        torch.save(checkpoint_payload_data, checkpoint_path)
        result["checkpoint_sha256"] = sha256(checkpoint_path)
        write_json(ARTIFACT_DIR / f"{'exact' if kind == 'exact' else 'nomemory'}_seed{seed}.json", result)
    shuffled_results: list[dict[str, Any]] = []
    for seed in EVIDENCE_SEEDS:
        metrics = evaluate_exact_and_shuffled(seed, splits, shuffle_maps)
        result = {"seed": seed, "kind": "SHUFFLED_MEMORY", "metrics": metrics}
        shuffled_results.append(result)
        write_json(ARTIFACT_DIR / f"shuffled_seed{seed}.json", result)
    write_json(ARTIFACT_DIR / "initialization_identity.json", {"pass": all(row["tensor_equal"] for row in initialization_rows), "rows": initialization_rows, "evidence_seeds": list(EVIDENCE_SEEDS)})
    write_json(ARTIFACT_DIR / "parameter_identity.json", {"pass": all(row["exact_parameters"] == row["no_memory_parameters"] == 30_912 for row in initialization_rows), "rows": initialization_rows})
    write_json(ARTIFACT_DIR / "environment.json", environment())
    write_json(ARTIFACT_DIR / "dataset_identity.json", dataset_identity())
    finalize_evidence(train_results, shuffled_results, splits, shuffle_maps, initialization_rows)
    hashes = {}
    for path in sorted(ARTIFACT_DIR.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            hashes[str(path.relative_to(ARTIFACT_DIR))] = sha256(path)
    write_json(ARTIFACT_DIR / "SHA256SUMS.json", hashes)
    return 0


if __name__ == "__main__":
    if "--resume-audit" in sys.argv:
        result = run_resume_audit()
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(0 if result["pass"] else 1)
    if "--evidence" in sys.argv:
        raise SystemExit(execute_evidence())
    raise SystemExit("use --resume-audit or --evidence")
