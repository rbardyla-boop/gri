#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import FIELD, HIDDEN_DIM, MESSAGE_DIM, TRAIN_DEPTH, encode_event  # noqa: E402
from dmc02a.benchmark import _bounded_admission  # noqa: E402
from dmc02p.controller import (  # noqa: E402
    CAPACITY,
    RANDOM_CONTROL_SEED,
    ExactRetention16Controller,
    FIFO16Controller,
    MemoryRecord,
    Random16Controller,
    load_dmc01_checkpoint,
)
from dmc03p.preregistration import (  # noqa: E402
    DMC01_DIR,
    DMC02A_DIR,
    ROOT as PREREG_ROOT,
    build_training_examples,
    canonical,
    load_cases,
    sha256_bytes,
    sha256_file,
    unchanged_since,
    verify_manifest,
)
from dmc03p.retention import (  # noqa: E402
    AFFINE_PARAMETER_COUNT,
    EVIDENCE_SEEDS,
    FEATURE_DIM,
    NON_EVIDENCE_SEED,
    AffineRetentionScorer,
    DMC03PController,
    LearnedRetention16Ledger,
    assert_processor_frozen,
    build_retention_optimizer,
    encode_hidden,
    freeze_processor,
    initialize_scorer,
    model_state_hash,
    record_metadata,
    retention_features,
    retention_loss,
    shuffled_order_batches,
    shuffle_metadata_permutation,
    stateless_order,
    training_protocol,
)


ARTIFACT_DIR = ROOT / "artifacts" / "dmc03"
DMC03P_DIR = ROOT / "artifacts" / "dmc03p"
DMC01_CHECKPOINT_DIR = ROOT / "artifacts" / "dmc01" / "checkpoints"
TRAINING_EXAMPLES_PATH = DMC03P_DIR / "training_examples.jsonl"
FEATURE_SPEC_PATH = DMC03P_DIR / "feature_spec.json"
EVIDENCE_COMMIT = "5d614a6"
DMC02_EVIDENCE_COMMIT = "4a9e2bf"
DMC02A_COMMIT = "f10394d"
DMC01_COMMIT = "48ae98f"
DMC00_COMMIT = "0e5359d"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
SOURCE_COMMIT = ""
FUTURE_PRIMARY = "mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)"
MODE_NAMES = ("oracle", "learned", "fifo", "random", "shuffled_metadata")
MODE_LABELS = {
    "oracle": "ORACLE_RETENTION_16",
    "learned": "LEARNED_RETENTION_16",
    "fifo": "FIFO_16",
    "random": "RANDOM_16",
    "shuffled_metadata": "SHUFFLED_METADATA_16",
}


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def canonical_hash(value: object) -> str:
    return sha256_bytes(canonical(value).encode("utf-8"))


def ordered_ids_hash(ids: list[str]) -> str:
    return canonical_hash(ids)


def read_frozen_training_examples() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((DMC03P_DIR / "training_example_manifest.json").read_text())
    actual_source_hash = sha256_file(DMC02A_DIR / "datasets" / "train.jsonl")
    actual_examples_hash = sha256_file(TRAINING_EXAMPLES_PATH)
    if actual_source_hash != manifest["source_dataset_sha256"]:
        raise RuntimeError("DMC-02A TRAIN dataset SHA-256 changed")
    if actual_examples_hash != manifest["training_examples_sha256"]:
        raise RuntimeError("DMC-03P training-example SHA-256 changed")
    examples = [json.loads(line) for line in TRAINING_EXAMPLES_PATH.read_text().splitlines() if line]
    if len(examples) != manifest["examples"]:
        raise RuntimeError("DMC-03P training-example count changed")
    if any(set(example) != {"example_id", "features", "target"} for example in examples):
        raise RuntimeError("DMC-03P training-example schema changed")
    return examples, manifest


def predecessor_identity() -> dict[str, Any]:
    specs = [
        ("WORLD-0", WORLD0_COMMIT, ROOT / "artifacts/frozen/world0_v0_1"),
        ("DMC-00", DMC00_COMMIT, ROOT / "artifacts/dmc00"),
        ("DMC-01", DMC01_COMMIT, ROOT / "artifacts/dmc01"),
        ("DMC-02A", DMC02A_COMMIT, ROOT / "artifacts/dmc02a"),
        ("DMC-02", DMC02_EVIDENCE_COMMIT, ROOT / "artifacts/dmc02"),
        ("DMC-03P", EVIDENCE_COMMIT, ROOT / "artifacts/dmc03p"),
    ]
    rows = []
    for name, commit, path in specs:
        manifest = verify_manifest(path)
        if name == "WORLD-0" and not (path / "SHA256SUMS.json").exists():
            manifest = {
                "root": str(path.relative_to(ROOT)),
                "entries": 0,
                "manifest_available": False,
                "errors": [],
                "pass": True,
                "verification_basis": "frozen_git_commit_boundary",
            }
        unchanged = unchanged_since(commit, str(path.relative_to(ROOT)))
        row = {
            "name": name,
            "expected_commit": commit,
            "path": str(path.relative_to(ROOT)),
            "unchanged_since_expected_commit": unchanged,
            "manifest": manifest,
        }
        if name == "DMC-03P":
            receipt = json.loads((path / "DMC03P_RECEIPT.json").read_text())
            row["receipt_terminal_state"] = receipt.get("terminal_state")
            row["receipt_valid"] = receipt.get("terminal_state") == "DMC_03P_LEARNED_RETENTION_PREREGISTERED"
        rows.append(row)
    validator = subprocess.run(
        [sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    validator_terminal = validator.stdout.strip().splitlines()[-1] if validator.stdout.strip() else ""
    passed = all(row["unchanged_since_expected_commit"] and row["manifest"]["pass"] for row in rows)
    passed = passed and validator.returncode == 0 and validator_terminal == "GRI_02_WORLD0_PASS"
    passed = passed and rows[-1].get("receipt_valid", False)
    return {"pass": passed, "world0_validator": validator_terminal, "predecessors": rows}


def training_order_identity(examples: list[dict[str, Any]], seeds: Iterable[int]) -> dict[str, Any]:
    ids = [example["example_id"] for example in examples]
    if len(ids) != len(set(ids)):
        raise RuntimeError("training example IDs are not unique")
    rows = []
    for seed in seeds:
        epoch_hashes = []
        for epoch in range(40):
            ordered = stateless_order(ids, seed=seed, epoch=epoch)
            if sorted(ordered) != sorted(ids):
                raise RuntimeError("stateless order is not a permutation")
            epoch_hashes.append(ordered_ids_hash(ordered))
        rows.append(
            {
                "seed": seed,
                "epochs": 40,
                "batch_size": 256,
                "epoch_order_sha256": epoch_hashes,
                "ordering_identity_sha256": canonical_hash(epoch_hashes),
                "epoch0_batch_count": len(shuffled_order_batches(ids, seed=seed, epoch=0, batch_size=256)),
                "pass": True,
            }
        )
    return {
        "algorithm": "ascending SHA256(DMC03P-order|seed|epoch|training_example_id), then training_example_id",
        "example_count": len(ids),
        "rows": rows,
        "pass": True,
    }


def scorer_values(scorer: AffineRetentionScorer) -> dict[str, Any]:
    return {
        "w_mission": float(scorer.linear.weight.detach().cpu()[0, 0].item()),
        "w_salience": float(scorer.linear.weight.detach().cpu()[0, 1].item()),
        "bias": float(scorer.linear.bias.detach().cpu()[0].item()),
    }


def train_scorer(seed: int, examples: list[dict[str, Any]], *, checkpoint_path: Path | None = None) -> dict[str, Any]:
    torch.set_num_threads(1)
    scorer = initialize_scorer(seed)
    initial_hash = model_state_hash(scorer)
    initial_values = scorer_values(scorer)
    optimizer = build_retention_optimizer(scorer)
    optimizer_parameter_ids = {id(parameter) for group in optimizer.param_groups for parameter in group["params"]}
    scorer_parameter_ids = {id(parameter) for parameter in scorer.parameters()}
    if optimizer_parameter_ids != scorer_parameter_ids:
        raise RuntimeError("retention optimizer does not contain exactly the scorer parameters")
    by_id = {example["example_id"]: example for example in examples}
    ids = list(by_id)
    epoch_losses: list[float] = []
    epoch_order_hashes: list[str] = []
    for epoch in range(40):
        ordered = stateless_order(ids, seed=seed, epoch=epoch)
        epoch_order_hashes.append(ordered_ids_hash(ordered))
        total_loss = 0.0
        total_examples = 0
        for batch_ids in (ordered[start : start + 256] for start in range(0, len(ordered), 256)):
            features = torch.tensor([by_id[item]["features"] for item in batch_ids], dtype=torch.float32)
            targets = torch.tensor([by_id[item]["target"] for item in batch_ids], dtype=torch.float32)
            logits = scorer(features)
            loss = retention_loss(logits, targets)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(scorer.parameters(), 1.0)
            optimizer.step()
            count = len(batch_ids)
            total_loss += float(loss.detach().item()) * count
            total_examples += count
        epoch_losses.append(total_loss / total_examples)
    scorer.eval()
    final_hash = model_state_hash(scorer)
    final_values = scorer_values(scorer)
    order_identity = {
        "seed": seed,
        "epochs": 40,
        "batch_size": 256,
        "epoch_order_sha256": epoch_order_hashes,
        "ordering_identity_sha256": canonical_hash(epoch_order_hashes),
    }
    result = {
        "seed": seed,
        "scorer": scorer,
        "optimizer": optimizer,
        "initial_state_hash": initial_hash,
        "initial_values": initial_values,
        "final_state_hash": final_hash,
        "final_values": final_values,
        "epoch_losses": epoch_losses,
        "final_loss": epoch_losses[-1],
        "order_identity": order_identity,
        "optimizer_parameter_count": sum(parameter.numel() for parameter in scorer.parameters()),
        "processor_trainable_parameter_count": 0,
    }
    if checkpoint_path is not None:
        processor_checkpoint_path = DMC01_CHECKPOINT_DIR / f"exact_seed{seed}_final.pt"
        processor_checkpoint = str(processor_checkpoint_path.relative_to(ROOT)) if processor_checkpoint_path.exists() else None
        processor_checkpoint_sha256 = sha256_file(processor_checkpoint_path) if processor_checkpoint_path.exists() else None
        payload = {
            "scorer_state_dict": scorer.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "seed": seed,
            "completed_epoch": 40,
            "feature_spec_path": str(FEATURE_SPEC_PATH.relative_to(ROOT)),
            "feature_spec_sha256": sha256_file(FEATURE_SPEC_PATH),
            "training_examples_path": str(TRAINING_EXAMPLES_PATH.relative_to(ROOT)),
            "training_examples_sha256": sha256_file(TRAINING_EXAMPLES_PATH),
            "training_order_identity": order_identity,
            "final_training_loss": epoch_losses[-1],
            "initial_state_hash": initial_hash,
            "final_state_hash": final_hash,
            "source_commit": git_commit(),
            "model_class": "AffineRetentionScorer",
            "parameter_count": AFFINE_PARAMETER_COUNT,
            "processor_checkpoint": processor_checkpoint,
            "processor_checkpoint_sha256": processor_checkpoint_sha256,
            "training_config": training_protocol(),
        }
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(payload, checkpoint_path)
        result["checkpoint"] = str(checkpoint_path.relative_to(ROOT)) if checkpoint_path.is_relative_to(ROOT) else str(checkpoint_path)
        result["checkpoint_sha256"] = sha256_file(checkpoint_path)
    return result


def replay_audit(examples: list[dict[str, Any]]) -> dict[str, Any]:
    first = train_scorer(NON_EVIDENCE_SEED, examples)
    second = train_scorer(NON_EVIDENCE_SEED, examples)
    with tempfile.TemporaryDirectory(prefix="dmc03-replay-") as directory:
        path = Path(directory) / "retention.pt"
        saved = train_scorer(NON_EVIDENCE_SEED, examples, checkpoint_path=path)
        payload = torch.load(path, map_location="cpu", weights_only=False)
        restored = AffineRetentionScorer()
        restored.load_state_dict(payload["scorer_state_dict"], strict=True)
        restore_hash = model_state_hash(restored)
    checks = {
        "same_initial_state_hash": first["initial_state_hash"] == second["initial_state_hash"],
        "same_order_identity": first["order_identity"] == second["order_identity"],
        "same_epoch_losses": first["epoch_losses"] == second["epoch_losses"],
        "same_final_loss": first["final_loss"] == second["final_loss"],
        "same_final_state_hash": first["final_state_hash"] == second["final_state_hash"],
        "checkpoint_round_trip_hash": saved["final_state_hash"] == restore_hash,
        "checkpoint_round_trip_loss": saved["final_loss"] == payload["final_training_loss"],
    }
    return {
        "seed": NON_EVIDENCE_SEED,
        "engineering_only": True,
        "evidence_seed_training_executed": False,
        "checks": checks,
        "pass": all(checks.values()),
        "final_state_hash": first["final_state_hash"],
        "final_loss": first["final_loss"],
    }


class ShuffledMetadataLedger(LearnedRetention16Ledger):
    """DMC-03 metadata control: same-condition feature sources are permuted."""

    def __init__(self, scorer: AffineRetentionScorer, *, family: str, feature_sources: dict[str, MemoryRecord]) -> None:
        super().__init__(scorer, family=family)
        self.feature_sources = feature_sources

    def _score(self, record: MemoryRecord) -> float:
        source = self.feature_sources[record.memory_id]
        metadata = record_metadata(source, self.family)
        features = retention_features(metadata, self.active_entities)
        key = tuple(float(value) for value in features.tolist())
        if key in self._score_cache:
            return self._score_cache[key]
        with torch.no_grad():
            score = float(self.scorer(features).item())
        self._score_cache[key] = score
        return score


def write_record_from_event(event: dict[str, Any], episode_index: int) -> MemoryRecord:
    return MemoryRecord(
        memory_id=event["memory_id"],
        entity=event["entity"],
        field=event["field"],
        creation_episode=episode_index,
        supersedes=event.get("supersedes"),
        source_episode=episode_index,
        hidden_value=torch.zeros(HIDDEN_DIM),
        salience=event.get("salience"),
    )


def shuffled_sources(case: dict[str, Any]) -> tuple[dict[str, MemoryRecord], dict[str, Any]]:
    writes = [(episode["index"], episode["events"][0]) for episode in case["episodes"][:-1] if episode["events"][0]["kind"] == "write"]
    records = [write_record_from_event(event, episode_index) for episode_index, event in writes]
    permutation = shuffle_metadata_permutation(case["family"], case["condition"], len(records))
    sources = {destination.memory_id: records[permutation[index]] for index, destination in enumerate(records)}
    mapping = [(destination.memory_id, sources[destination.memory_id].memory_id) for destination in records]
    return sources, {
        "family": case["family"],
        "condition": case["condition"],
        "width": len(records),
        "permutation_sha256": canonical_hash(list(permutation)),
        "mapping_sha256": canonical_hash(mapping),
        "is_permutation": sorted(permutation) == list(range(len(records))),
    }


def query_logits(processor: torch.nn.Module, query: dict[str, Any], hidden: torch.Tensor) -> torch.Tensor:
    graph = encode_event(query)
    h0 = processor.initialize(graph)
    anchor = processor.make_anchor(h0)
    h = h0.clone()
    h[graph.query_object] = h[graph.query_object] + hidden.to(h.device)
    for _ in range(TRAIN_DEPTH):
        h = processor.recurrent_step(h, graph.edges.to(h.device), anchor)
    return processor.readout_hidden(h, graph.query_subject, graph.query_object)


def hidden_cache(processor: torch.nn.Module) -> dict[str, torch.Tensor]:
    cache = {}
    for index, value in enumerate(VALUES):
        event = {
            "kind": "write",
            "memory_id": f"dmc03-hidden-cache-{index}",
            "entity": "dmc03-hidden-cache",
            "field": FIELD,
            "value": value,
        }
        cache[value] = encode_hidden(processor, event).detach().cpu().clone()
    return cache


def new_controller_set(seed: int, scorer: AffineRetentionScorer, processor: torch.nn.Module) -> dict[str, Any]:
    exact, _ = load_dmc01_checkpoint(DMC01_CHECKPOINT_DIR / f"exact_seed{seed}_final.pt", family="mission_set", mode="exact16", case_id=f"dmc03-{seed}-oracle")
    # Replace the loader-created processor with the shared, hash-audited one;
    # all mode controllers therefore consume the same frozen representation.
    exact.processor = processor
    fifo = FIFO16Controller(processor, family="mission_set", case_id=f"dmc03-{seed}-fifo")
    random = Random16Controller(processor, family="mission_set", case_id=f"dmc03-{seed}-random", seed=RANDOM_CONTROL_SEED)
    learned = DMC03PController(processor, scorer, family="mission_set")
    shuffled = DMC03PController(processor, scorer, family="mission_set")
    shuffled.ledger = ShuffledMetadataLedger(scorer, family="mission_set", feature_sources={})
    return {"oracle": exact, "learned": learned, "fifo": fifo, "random": random, "shuffled_metadata": shuffled}


def controller_reset(controller: Any, mode: str, family: str, sources: dict[str, MemoryRecord] | None) -> None:
    controller.reset_case()
    controller.family = family
    if mode == "oracle":
        controller.ledger.policy.family = family
        controller.ledger.policy.active_entities = None
    elif mode in {"learned", "shuffled_metadata"}:
        controller.ledger.family = family
        if mode == "shuffled_metadata":
            controller.ledger.feature_sources = sources or {}


def process_scope(controller: Any, mode: str, event: dict[str, Any]) -> None:
    if mode in {"oracle", "learned", "shuffled_metadata"}:
        controller.process_scope_event(event)


def retain(controller: Any, mode: str, record: MemoryRecord) -> bool:
    if mode in {"learned", "shuffled_metadata"}:
        kept = controller.ledger.consider(record)
    else:
        kept = controller.retain_record(record)
    if len(controller.ledger) > CAPACITY:
        raise AssertionError("DMC-03 capacity exceeded")
    return kept


def diagnostics_update(diag: dict[str, int], target: int, prediction: int) -> None:
    if target and prediction:
        diag["tp"] += 1
    elif not target and prediction:
        diag["fp"] += 1
    elif target and not prediction:
        diag["fn"] += 1
    else:
        diag["tn"] += 1


def diagnostics_finish(diag: dict[str, int]) -> dict[str, Any]:
    tp, fp, fn, tn = (diag[key] for key in ("tp", "fp", "fn", "tn"))
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {**diag, "total": total, "accuracy": (tp + tn) / total if total else 0.0, "precision": precision, "recall": recall, "F1": f1}


def metrics_from_hits(hits: dict[tuple[str, str, str], list[bool]]) -> dict[str, Any]:
    conditions = {f"{split}:{family}:{condition}": sum(values) / len(values) for (split, family, condition), values in sorted(hits.items())}

    def condition(family: str, condition_name: str) -> float:
        return conditions[f"extrapolation:{family}:{condition_name}"]

    components = {
        "M256": condition("mission_set", "load_256"),
        "M1024": condition("mission_set", "load_1024"),
        "SAL256": condition("salience", "load_256"),
        "SAL1024": condition("salience", "load_1024"),
        "SUP_current_1024": condition("supersession", "load_1024_current"),
        "SUP_history_1024": condition("supersession", "load_1024_history"),
        "SHIFT": statistics.mean(condition("utility_change", f"load_1024_overlap_{overlap}") for overlap in (0, 25, 50, 75, 100)),
        "FLOOD512": condition("distractor_flood", "distractors_512"),
        "FLOOD1024": condition("distractor_flood", "distractors_1024"),
    }
    components["P_bounded"] = statistics.mean(components.values())
    train_values = [value for key, value in conditions.items() if key.startswith("train:")]
    iid_values = [value for key, value in conditions.items() if key.startswith("iid:")]
    extrap_values = [value for key, value in conditions.items() if key.startswith("extrapolation:")]
    return {
        "conditions": conditions,
        "components": components,
        "P_bounded": components["P_bounded"],
        "train_accuracy": statistics.mean(train_values),
        "iid_accuracy": statistics.mean(iid_values),
        "extrapolation_accuracy": statistics.mean(extrap_values),
    }


def evaluate_seed(seed: int, scorer: AffineRetentionScorer, dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checkpoint_path = DMC01_CHECKPOINT_DIR / f"exact_seed{seed}_final.pt"
    loaded_controller, payload = load_dmc01_checkpoint(checkpoint_path, family="mission_set", mode="exact16", case_id=f"dmc03-loader-{seed}")
    processor = loaded_controller.processor
    freeze_processor(processor)
    assert_processor_frozen(processor)
    before_hash = model_state_hash(processor)
    controllers = new_controller_set(seed, scorer, processor)
    cache = hidden_cache(processor)
    condition_hits = {mode: defaultdict(list) for mode in MODE_NAMES}
    capacity_rows: list[dict[str, Any]] = []
    diagnostics = {split: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for split in ("train", "iid", "extrapolation")}
    hidden_total = 0
    hidden_mismatches = 0
    firewall = {"calls": 0, "shapes": set(), "feature_values": set(), "invalid_inputs": 0}

    def firewall_hook(_module: torch.nn.Module, args: tuple[Any, ...]) -> None:
        firewall["calls"] += 1
        if len(args) != 1 or not isinstance(args[0], torch.Tensor) or tuple(args[0].shape) != (FEATURE_DIM,):
            firewall["invalid_inputs"] += 1
            return
        values = tuple(float(item) for item in args[0].detach().cpu().tolist())
        firewall["shapes"].add(tuple(args[0].shape))
        firewall["feature_values"].add(values)
        if any(value not in {0.0, 1.0} for value in values):
            firewall["invalid_inputs"] += 1

    hook = scorer.register_forward_pre_hook(firewall_hook)
    try:
        processor.eval()
        scorer.eval()
        with torch.no_grad():
            for split, cases in dataset.items():
                for case in cases:
                    sources, shuffle_identity = shuffled_sources(case)
                    for mode, controller in controllers.items():
                        controller_reset(controller, mode, case["family"], sources if mode == "shuffled_metadata" else None)
                    oracle_records: list[MemoryRecord] = []
                    active_scope: set[str] | None = None
                    peaks = {mode: 0 for mode in MODE_NAMES}
                    violations = {mode: 0 for mode in MODE_NAMES}
                    for episode in case["episodes"]:
                        episode_index = episode["index"]
                        event = episode["events"][0]
                        if event["kind"] in {"mission_set", "mission_update"}:
                            active_scope = set(event["entities"])
                            if event["kind"] == "mission_update":
                                oracle_records = [record for record in oracle_records if record.entity in active_scope]
                            for mode, controller in controllers.items():
                                process_scope(controller, mode, event)
                        elif event["kind"] == "write":
                            oracle_admitted = _bounded_admission(case, event, active_scope)
                            oracle_record = write_record_from_event(event, episode_index)
                            if oracle_admitted:
                                if case["family"] == "utility_change":
                                    oracle_records = [old for old in oracle_records if old.entity != oracle_record.entity]
                                oracle_records.append(oracle_record)
                            oracle_target = int(any(old.memory_id == oracle_record.memory_id for old in oracle_records))
                            hidden = cache[event["value"]]
                            for mode, controller in controllers.items():
                                record = controller.make_record(event, episode_index, hidden_value=hidden.clone())
                                kept = retain(controller, mode, record)
                                hidden_total += 1
                                if not torch.equal(record.hidden_value, hidden):
                                    hidden_mismatches += 1
                                if mode == "learned":
                                    diagnostics_update(diagnostics[split], oracle_target, int(kept))
                        elif event["kind"] == "query":
                            for mode, controller in controllers.items():
                                try:
                                    retrieved = controller.retrieve(event)
                                except LookupError:
                                    retrieved = None
                                if retrieved is None:
                                    hit = False
                                else:
                                    logits = query_logits(processor, event, retrieved.hidden_value)
                                    hit = int(logits.argmax().item()) == VALUES.index(case["answer"])
                                condition_hits[mode][(split, case["family"], case["condition"])].append(hit)
                        else:
                            raise ValueError(f"unsupported DMC-02A event: {event['kind']}")
                        for mode, controller in controllers.items():
                            occupancy = len(controller.ledger)
                            peaks[mode] = max(peaks[mode], occupancy)
                            if occupancy > CAPACITY:
                                violations[mode] += 1
                    capacity_rows.append({
                        "split": split,
                        "family": case["family"],
                        "condition": case["condition"],
                        "case_id": case["case_id"],
                        "peak": peaks,
                        "violations": violations,
                        "shuffled_metadata": shuffle_identity,
                    })
    finally:
        hook.remove()
    after_hash = model_state_hash(processor)
    firewall_clean = {
        "calls": firewall["calls"],
        "shapes": sorted([list(shape) for shape in firewall["shapes"]]),
        "feature_values": sorted([list(values) for values in firewall["feature_values"]]),
        "invalid_inputs": firewall["invalid_inputs"],
        "forbidden_runtime_inputs": [],
        "pass": firewall["invalid_inputs"] == 0 and firewall["shapes"] == {(FEATURE_DIM,)} and firewall["calls"] > 0,
    }
    capacity = {
        mode: {
            "maximum_peak": max(row["peak"][mode] for row in capacity_rows),
            "mean_peak": statistics.mean(row["peak"][mode] for row in capacity_rows),
            "violations": sum(row["violations"][mode] for row in capacity_rows),
        }
        for mode in MODE_NAMES
    }
    return {
        "seed": seed,
        "processor_checkpoint": str(checkpoint_path.relative_to(ROOT)),
        "processor_checkpoint_sha256": sha256_file(checkpoint_path),
        "processor_payload_model_type": payload.get("model_type"),
        "processor_parameter_count": payload.get("parameter_count"),
        "model_state_hash_before": before_hash,
        "model_state_hash_after": after_hash,
        "processor_immutable": before_hash == after_hash,
        "metrics": {mode: metrics_from_hits(condition_hits[mode]) for mode in MODE_NAMES},
        "capacity": capacity,
        "capacity_rows": capacity_rows,
        "retention_diagnostics": {split: diagnostics_finish(value) for split, value in diagnostics.items()},
        "hidden_vector_integrity": {"stored_records_checked": hidden_total, "mismatches": hidden_mismatches, "pass": hidden_mismatches == 0},
        "metadata_firewall": firewall_clean,
    }


def load_trained_scorer(path: Path) -> tuple[AffineRetentionScorer, dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    scorer = AffineRetentionScorer()
    scorer.load_state_dict(payload["scorer_state_dict"], strict=True)
    scorer.eval()
    if payload.get("parameter_count") != AFFINE_PARAMETER_COUNT:
        raise RuntimeError("trained scorer parameter count changed")
    if payload.get("feature_spec_sha256") != sha256_file(FEATURE_SPEC_PATH):
        raise RuntimeError("trained scorer feature specification identity changed")
    if payload.get("training_examples_sha256") != sha256_file(TRAINING_EXAMPLES_PATH):
        raise RuntimeError("trained scorer training-example identity changed")
    return scorer, payload


def aggregate_results(seed_results: dict[int, dict[str, Any]]) -> dict[str, Any]:
    per_mode = {}
    for mode in MODE_NAMES:
        values = [seed_results[seed]["metrics"][mode]["P_bounded"] for seed in EVIDENCE_SEEDS]
        per_mode[mode] = {"label": MODE_LABELS[mode], "mean": statistics.mean(values), "stdev": statistics.stdev(values), "per_seed": values}
    components = ("M256", "M1024", "SAL256", "SAL1024", "SUP_current_1024", "SUP_history_1024", "SHIFT", "FLOOD512", "FLOOD1024")
    component_means = {component: {mode: statistics.mean(seed_results[seed]["metrics"][mode]["components"][component] for seed in EVIDENCE_SEEDS) for mode in MODE_NAMES} for component in components}
    learned = per_mode["learned"]["mean"]
    oracle = per_mode["oracle"]["mean"]
    fifo = per_mode["fifo"]["mean"]
    random = per_mode["random"]["mean"]
    shuffled = per_mode["shuffled_metadata"]["mean"]
    gates = {
        "A_primary": {"observed": learned, "threshold": 0.90, "pass": learned >= 0.90},
        "B_oracle_gap": {"observed": oracle - learned, "threshold": 0.10, "pass": oracle - learned <= 0.10},
        "C_M1024": {"observed": component_means["M1024"]["learned"], "threshold": 0.90, "pass": component_means["M1024"]["learned"] >= 0.90},
        "D_SAL1024": {"observed": component_means["SAL1024"]["learned"], "threshold": 0.90, "pass": component_means["SAL1024"]["learned"] >= 0.90},
        "E_SUP_current_1024": {"observed": component_means["SUP_current_1024"]["learned"], "threshold": 0.90, "pass": component_means["SUP_current_1024"]["learned"] >= 0.90},
        "F_SUP_history_1024": {"observed": component_means["SUP_history_1024"]["learned"], "threshold": 0.90, "pass": component_means["SUP_history_1024"]["learned"] >= 0.90},
        "G_SHIFT": {"observed": component_means["SHIFT"]["learned"], "threshold": 0.90, "pass": component_means["SHIFT"]["learned"] >= 0.90},
        "H_FLOOD1024": {"observed": component_means["FLOOD1024"]["learned"], "threshold": 0.90, "pass": component_means["FLOOD1024"]["learned"] >= 0.90},
        "I_seed_consistency": {"observed": sum(value >= 0.85 for value in per_mode["learned"]["per_seed"]), "threshold": "5/5", "pass": all(value >= 0.85 for value in per_mode["learned"]["per_seed"])},
        "J_FIFO_separation": {"observed": learned - fifo, "threshold": 0.60, "pass": learned - fifo >= 0.60},
        "K_RANDOM_separation": {"observed": learned - random, "threshold": 0.60, "pass": learned - random >= 0.60},
    }
    metadata_gate = {"observed": learned - shuffled, "threshold": 0.40, "pass": learned - shuffled >= 0.40}
    return {
        "primary_metric": FUTURE_PRIMARY,
        "per_mode": per_mode,
        "component_means": component_means,
        "differences": {
            "oracle_minus_learned": oracle - learned,
            "learned_minus_fifo": learned - fifo,
            "learned_minus_random": learned - random,
            "learned_minus_shuffled_metadata": learned - shuffled,
        },
        "gates": gates,
        "metadata_use_mechanism_gate": metadata_gate,
    }


def complete_evaluation_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "seed": result["seed"],
        "metrics": result["metrics"],
        "capacity": result["capacity"],
        "retention_diagnostics": result["retention_diagnostics"],
        "hidden_vector_integrity": result["hidden_vector_integrity"],
        "metadata_firewall": result["metadata_firewall"],
        "processor_immutable": result["processor_immutable"],
    }


def evaluate_replay(seed: int, scorer_path: Path, dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    scorer_a, _ = load_trained_scorer(scorer_path)
    scorer_b, _ = load_trained_scorer(scorer_path)
    first = evaluate_seed(seed, scorer_a, dataset)
    second = evaluate_seed(seed, scorer_b, dataset)
    first_payload = complete_evaluation_payload(first)
    second_payload = complete_evaluation_payload(second)
    first_hash = canonical_hash(first_payload)
    second_hash = canonical_hash(second_payload)
    return {
        "seed": seed,
        "scorer_checkpoint": str(scorer_path.relative_to(ROOT)),
        "complete_evaluation_repeated": True,
        "numeric_equal": first_payload == second_payload,
        "canonical_result_hash_first": first_hash,
        "canonical_result_hash_second": second_hash,
        "same_canonical_result_hash": first_hash == second_hash,
        "same_learned_retention_decisions": first_payload["retention_diagnostics"] == second_payload["retention_diagnostics"],
        "pass": first_payload == second_payload and first_hash == second_hash,
    }


def save_training_artifacts(training: dict[int, dict[str, Any]], order_identity: dict[str, Any]) -> None:
    initialization = {}
    optimizer = {}
    for seed, result in training.items():
        write_json(
            ARTIFACT_DIR / f"retention_seed{seed}_train.json",
            {
                "seed": seed,
                "checkpoint": result["checkpoint"],
                "checkpoint_sha256": result["checkpoint_sha256"],
                "initial_values": result["initial_values"],
                "initial_state_hash": result["initial_state_hash"],
                "final_values": result["final_values"],
                "final_state_hash": result["final_state_hash"],
                "epoch_losses": result["epoch_losses"],
                "final_loss": result["final_loss"],
                "parameter_count": AFFINE_PARAMETER_COUNT,
            },
        )
        initialization[str(seed)] = {"seed": seed, **result["initial_values"], "initial_state_hash": result["initial_state_hash"]}
        optimizer[str(seed)] = {
            "seed": seed,
            "optimizer": "AdamW",
            "optimizer_parameter_count": result["optimizer_parameter_count"],
            "processor_trainable_parameter_count": 0,
            "optimizer_contains_processor": False,
            "pass": result["optimizer_parameter_count"] == AFFINE_PARAMETER_COUNT,
        }
    write_json(ARTIFACT_DIR / "initialization_identity.json", {"per_seed": initialization, "pass": len(initialization) == 5})
    write_json(ARTIFACT_DIR / "optimizer_isolation.json", {"per_seed": optimizer, "pass": all(row["pass"] for row in optimizer.values())})
    write_json(ARTIFACT_DIR / "training_order_identity.json", order_identity)


def run_replay_audit() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    examples, _ = read_frozen_training_examples()
    audit = replay_audit(examples)
    write_json(ARTIFACT_DIR / "replay_audit_non_evidence.json", audit)
    print("DMC_03_NON_EVIDENCE_REPLAY_PASS" if audit["pass"] else "DMC_03_REPAIR_REQUIRED")
    return 0 if audit["pass"] else 1


def run_evidence() -> int:
    global SOURCE_COMMIT
    SOURCE_COMMIT = git_commit()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = ARTIFACT_DIR / "replay_audit_non_evidence.json"
    if not audit_path.exists() or not json.loads(audit_path.read_text()).get("pass", False):
        raise RuntimeError("non-evidence replay audit must pass before evidence training")
    identity = predecessor_identity()
    if not identity["pass"]:
        write_json(ARTIFACT_DIR / "predecessor_identity.json", identity)
        write_json(ARTIFACT_DIR / "DMC03_VERDICT.json", {"unit": "DMC-03", "terminal_state": "DMC_03_INVALID", "reason": "predecessor identity failure"})
        return 1
    examples, example_manifest = read_frozen_training_examples()
    dataset = {split: load_cases(DMC02A_DIR / "datasets" / f"{split}.jsonl") for split in ("train", "iid", "extrapolation")}
    order_identity = training_order_identity(examples, EVIDENCE_SEEDS)
    training: dict[int, dict[str, Any]] = {}
    checkpoint_paths = {}
    for seed in EVIDENCE_SEEDS:
        path = ARTIFACT_DIR / "checkpoints" / f"retention_seed{seed}_final.pt"
        training[seed] = train_scorer(seed, examples, checkpoint_path=path)
        checkpoint_paths[seed] = path
    save_training_artifacts(training, order_identity)
    processor_rows = []
    dmc01_manifest = json.loads((DMC01_DIR / "SHA256SUMS.json").read_text())
    for seed in EVIDENCE_SEEDS:
        path = DMC01_CHECKPOINT_DIR / f"exact_seed{seed}_final.pt"
        loaded_controller, _ = load_dmc01_checkpoint(path, family="mission_set", mode="exact16", case_id=f"dmc03-immutability-{seed}")
        processor = loaded_controller.processor
        freeze_processor(processor)
        before = model_state_hash(processor)
        processor_rows.append({
            "seed": seed,
            "checkpoint": str(path.relative_to(ROOT)),
            "checkpoint_sha256": sha256_file(path),
            "manifest_sha256": dmc01_manifest[f"checkpoints/{path.name}"],
            "manifest_match": sha256_file(path) == dmc01_manifest[f"checkpoints/{path.name}"],
            "processor_state_hash_before_training": before,
            "parameter_count": sum(parameter.numel() for parameter in processor.parameters()),
            "requires_grad_false": all(not parameter.requires_grad for parameter in processor.parameters()),
        })
    write_json(ARTIFACT_DIR / "predecessor_identity.json", identity)
    write_json(ARTIFACT_DIR / "training_example_identity.json", {
        "source_dataset_path": str((DMC02A_DIR / "datasets" / "train.jsonl").relative_to(ROOT)),
        "source_dataset_sha256": example_manifest["source_dataset_sha256"],
        "training_examples_path": str(TRAINING_EXAMPLES_PATH.relative_to(ROOT)),
        "training_examples_sha256": sha256_file(TRAINING_EXAMPLES_PATH),
        "examples": len(examples),
        "split": "train",
        "answer_or_query_serialized": False,
        "pass": sha256_file(TRAINING_EXAMPLES_PATH) == example_manifest["training_examples_sha256"] and len(examples) == 11776,
    })
    write_json(ARTIFACT_DIR / "processor_checkpoint_manifest.json", {
        "expected_dmc01_commit": DMC01_COMMIT,
        "rows": processor_rows,
        "pass": all(row["manifest_match"] and row["parameter_count"] == 30912 and row["requires_grad_false"] for row in processor_rows),
    })
    write_json(ARTIFACT_DIR / "processor_immutability.json", {"before": processor_rows, "after_checked_during_evaluation": True})

    all_results: dict[int, dict[str, Any]] = {}
    for seed in EVIDENCE_SEEDS:
        scorer, payload = load_trained_scorer(checkpoint_paths[seed])
        result = evaluate_seed(seed, scorer, dataset)
        result["trained_scorer_checkpoint"] = str(checkpoint_paths[seed].relative_to(ROOT))
        result["trained_scorer_checkpoint_sha256"] = sha256_file(checkpoint_paths[seed])
        result["trained_scorer_payload_final_state_hash"] = payload["final_state_hash"]
        all_results[seed] = result
        for mode in MODE_NAMES:
            write_json(ARTIFACT_DIR / f"{mode}_seed{seed}.json", {
                "seed": seed,
                "mode": MODE_LABELS[mode],
                "processor_checkpoint": result["processor_checkpoint"],
                "processor_checkpoint_sha256": result["processor_checkpoint_sha256"],
                "trained_scorer_checkpoint": result["trained_scorer_checkpoint"],
                "metrics": result["metrics"][mode],
                "capacity": result["capacity"][mode],
                "retention_diagnostics": result["retention_diagnostics"] if mode == "learned" else None,
                "processor_immutable": result["processor_immutable"],
                "hidden_vector_integrity": result["hidden_vector_integrity"],
                "metadata_firewall": result["metadata_firewall"] if mode in {"learned", "shuffled_metadata"} else None,
            })
    write_json(ARTIFACT_DIR / "capacity_audit.json", {
        "capacity": CAPACITY,
        "per_seed": {str(seed): all_results[seed]["capacity"] for seed in EVIDENCE_SEEDS},
        "maximum_occupancy": max(all_results[seed]["capacity"][mode]["maximum_peak"] for seed in EVIDENCE_SEEDS for mode in MODE_NAMES),
        "capacity_violations": sum(all_results[seed]["capacity"][mode]["violations"] for seed in EVIDENCE_SEEDS for mode in MODE_NAMES),
        "pass": all(all_results[seed]["capacity"][mode]["maximum_peak"] <= 16 and all_results[seed]["capacity"][mode]["violations"] == 0 for seed in EVIDENCE_SEEDS for mode in MODE_NAMES),
    })
    write_json(ARTIFACT_DIR / "metadata_firewall.json", {
        "per_seed": {str(seed): all_results[seed]["metadata_firewall"] for seed in EVIDENCE_SEEDS},
        "forbidden_inputs": ["answer", "answer_index", "final_query_target", "future_events", "oracle_result", "case_id", "future_query_choice", "hidden_value"],
        "pass": all(all_results[seed]["metadata_firewall"]["pass"] for seed in EVIDENCE_SEEDS),
    })
    final_processor_rows = []
    for seed in EVIDENCE_SEEDS:
        loaded_controller, _ = load_dmc01_checkpoint(DMC01_CHECKPOINT_DIR / f"exact_seed{seed}_final.pt", family="mission_set", mode="exact16", case_id=f"dmc03-final-{seed}")
        processor = loaded_controller.processor
        freeze_processor(processor)
        after = model_state_hash(processor)
        before = next(row["processor_state_hash_before_training"] for row in processor_rows if row["seed"] == seed)
        final_processor_rows.append({"seed": seed, "before": before, "after": after, "unchanged": before == after})
    write_json(ARTIFACT_DIR / "processor_immutability.json", {
        "per_seed": final_processor_rows,
        "pass": all(row["unchanged"] for row in final_processor_rows),
        "processor_trainable_parameters": 0,
    })
    replay = evaluate_replay(1337, checkpoint_paths[1337], dataset)
    replay["non_evidence_training_audit"] = json.loads(audit_path.read_text())
    write_json(ARTIFACT_DIR / "replay.json", replay)
    aggregate = aggregate_results(all_results)
    write_json(ARTIFACT_DIR / "aggregate.json", aggregate)
    write_json(ARTIFACT_DIR / "DMC03_CONFIG.json", {
        "unit": "DMC-03",
        "source_commit": SOURCE_COMMIT,
        "preregistration_commit": EVIDENCE_COMMIT,
        "evidence_seeds": list(EVIDENCE_SEEDS),
        "processor_pairing": {str(seed): str(seed) for seed in EVIDENCE_SEEDS},
        "processor": {"class": "ImmutableRelationAnchorReasoner", "hidden_dim": 49, "message_dim": 51, "train_depth": 4, "parameters": 30912, "frozen": True},
        "scorer": {"class": "AffineRetentionScorer", "features": ["mission_membership", "high_salience"], "parameters": 3, "hidden_value_input": False},
        "training": training_protocol(),
        "capacity": 16,
        "modes": [MODE_LABELS[mode] for mode in MODE_NAMES],
        "random_control_seed": RANDOM_CONTROL_SEED,
        "shuffle_algorithm": "DMC03P shuffle_metadata_permutation(seed=20260303, family, condition, width=case write count)",
        "primary_metric": FUTURE_PRIMARY,
        "gates": aggregate["gates"],
        "metadata_use_mechanism_gate": aggregate["metadata_use_mechanism_gate"],
        "training_examples_sha256": sha256_file(TRAINING_EXAMPLES_PATH),
        "evaluation_datasets": {split: sha256_file(DMC02A_DIR / "datasets" / f"{split}.jsonl") for split in ("iid", "extrapolation")},
        "evidence_training_executed": True,
    })
    environment = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "torch_threads": torch.get_num_threads(),
        "device": "cpu",
        "source_commit": SOURCE_COMMIT,
    }
    write_json(ARTIFACT_DIR / "environment.json", environment)
    checks = {
        "predecessors": identity["pass"],
        "processor_checkpoint_hashes": json.loads((ARTIFACT_DIR / "processor_checkpoint_manifest.json").read_text())["pass"],
        "processor_immutable": json.loads((ARTIFACT_DIR / "processor_immutability.json").read_text())["pass"],
        "training_examples": json.loads((ARTIFACT_DIR / "training_example_identity.json").read_text())["pass"],
        "optimizer_isolation": all(result["optimizer_parameter_count"] == 3 and result["processor_trainable_parameter_count"] == 0 for result in training.values()),
        "capacity": json.loads((ARTIFACT_DIR / "capacity_audit.json").read_text())["pass"],
        "metadata_firewall": json.loads((ARTIFACT_DIR / "metadata_firewall.json").read_text())["pass"],
        "replay": replay["pass"],
        "training_order": order_identity["pass"],
    }
    gates_pass = all(gate["pass"] for gate in aggregate["gates"].values())
    mechanism_pass = aggregate["metadata_use_mechanism_gate"]["pass"]
    if not checks["predecessors"]:
        terminal = "DMC_03_INVALID"
    elif not checks["processor_immutable"] or not checks["processor_checkpoint_hashes"]:
        terminal = "DMC_03_PROCESSOR_INVALID"
    elif not checks["capacity"]:
        terminal = "DMC_03_CAPACITY_INVALID"
    elif not checks["metadata_firewall"]:
        terminal = "DMC_03_RETENTION_LEAK"
    elif not all(checks.values()):
        terminal = "DMC_03_INVALID"
    elif gates_pass and mechanism_pass:
        terminal = "DMC_03_LEARNED_RETENTION_ADVANCES"
    elif gates_pass:
        terminal = "DMC_03_PERFORMANCE_ONLY_METADATA_USE_UNESTABLISHED"
    else:
        terminal = "DMC_03_LEARNED_RETENTION_NO_ADVANTAGE"
    verdict = {
        "unit": "DMC-03",
        "terminal_state": terminal,
        "checks": checks,
        "gates": aggregate["gates"],
        "metadata_use_mechanism_gate": aggregate["metadata_use_mechanism_gate"],
        "per_mode": aggregate["per_mode"],
        "differences": aggregate["differences"],
        "scientific_training_executed": True,
    }
    write_json(ARTIFACT_DIR / "DMC03_VERDICT.json", verdict)
    report = [
        "# DMC-03 — Learned Selective Retention Evidence",
        "",
        f"Terminal state: `{terminal}`",
        "",
        "| Seed | Oracle P | Learned P | FIFO P | Random P | Shuffled-meta P |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for seed in EVIDENCE_SEEDS:
        report.append("| {} | {:.8f} | {:.8f} | {:.8f} | {:.8f} | {:.8f} |".format(seed, *(all_results[seed]["metrics"][mode]["P_bounded"] for mode in MODE_NAMES)))
    report.extend(["", "| Seed | w_mission | w_salience | bias |", "|---:|---:|---:|---:|"])
    for seed in EVIDENCE_SEEDS:
        report.append("| {} | {:.8f} | {:.8f} | {:.8f} |".format(seed, training[seed]["final_values"]["w_mission"], training[seed]["final_values"]["w_salience"], training[seed]["final_values"]["bias"]))
    report.extend(["", "## Aggregate", ""])
    for mode in MODE_NAMES:
        report.append(f"- {MODE_LABELS[mode]} mean/stdev: `{aggregate['per_mode'][mode]['mean']:.8f}` / `{aggregate['per_mode'][mode]['stdev']:.8f}`")
    report.extend(["", "## Differences", ""])
    for name, value in aggregate["differences"].items():
        report.append(f"- {name}: `{value:.8f}`")
    report.extend(["", "## Gates", ""])
    for name, gate in aggregate["gates"].items():
        report.append(f"- {name}: **{'PASS' if gate['pass'] else 'FAIL'}** (observed `{gate['observed']}`, threshold `{gate['threshold']}`)")
    gate = aggregate["metadata_use_mechanism_gate"]
    report.append(f"- metadata-use mechanism: **{'PASS' if gate['pass'] else 'FAIL'}** (observed `{gate['observed']}`, threshold `{gate['threshold']}`)")
    (ARTIFACT_DIR / "DMC03_REPORT.md").write_text("\n".join(report) + "\n")
    hashes = {}
    for path in sorted(ARTIFACT_DIR.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            hashes[str(path.relative_to(ARTIFACT_DIR))] = sha256_file(path)
    write_json(ARTIFACT_DIR / "SHA256SUMS.json", hashes)
    print(terminal)
    return 0 if terminal in {"DMC_03_LEARNED_RETENTION_ADVANCES", "DMC_03_PERFORMANCE_ONLY_METADATA_USE_UNESTABLISHED", "DMC_03_LEARNED_RETENTION_NO_ADVANTAGE"} else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-audit", action="store_true")
    parser.add_argument("--evidence", action="store_true")
    args = parser.parse_args()
    if args.replay_audit == args.evidence:
        parser.error("choose exactly one of --replay-audit or --evidence")
    if args.replay_audit:
        return run_replay_audit()
    return run_evidence()


if __name__ == "__main__":
    raise SystemExit(main())
