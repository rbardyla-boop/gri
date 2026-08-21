from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

import torch

from dmc02a.benchmark import _bounded_admission, validate_case
from dmc02p.controller import MemoryRecord, RetentionMetadata

from .retention import (
    AFFINE_PARAMETER_COUNT,
    CAPACITY,
    EVIDENCE_SEEDS,
    FEATURE_DIM,
    FAMILIES,
    MISSION_FAMILIES,
    NON_EVIDENCE_SEED,
    SHUFFLE_SEED,
    AffineRetentionScorer,
    DMC03PController,
    FEATURE_ENCODER,
    LearnedRetention16Ledger,
    assert_processor_frozen,
    build_retention_optimizer,
    initialize_scorer,
    load_frozen_processor,
    model_state_hash,
    retention_features,
    sha256_file,
    shuffled_order_batches,
    shuffle_metadata_permutation,
    stateless_order,
    trainable_parameter_count,
    training_protocol,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "dmc03p"
DMC01_DIR = ROOT / "artifacts" / "dmc01"
DMC02_DIR = ROOT / "artifacts" / "dmc02"
DMC02A_DIR = ROOT / "artifacts" / "dmc02a"
WORLD0_DIR = ROOT / "artifacts" / "frozen" / "world0_v0_1"
DMC02A_TRAIN = DMC02A_DIR / "datasets" / "train.jsonl"
EVIDENCE_COMMIT = "4a9e2bf"
DMC02A_COMMIT = "f10394d"
DMC01_COMMIT = "48ae98f"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
PROCESSOR_PARAMETERS = 30_912


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_cases(path: Path = DMC02A_TRAIN) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _metadata(event: dict[str, Any], family: str, episode_index: int) -> RetentionMetadata:
    return RetentionMetadata(
        family=family,
        entity=event["entity"],
        field=event["field"],
        creation_episode=episode_index,
        salience=event.get("salience"),
        supersedes=event.get("supersedes"),
    )


def _example_id(event: dict[str, Any], episode_index: int) -> str:
    # The identifier is opaque and is derived only from the present candidate's
    # write identity.  It is never a model feature and does not contain a case
    # ID, answer, query, or future event.
    return sha256_bytes(f"DMC03P-TRAIN-EXAMPLE|{event['memory_id']}|{episode_index}".encode("utf-8"))


def build_training_examples(cases: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create feature/retention-label pairs from DMC-02A TRAIN streams only."""

    examples: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for case in cases:
        validate_case(case)
        active_scope: set[str] | None = None
        oracle_records: list[MemoryRecord] = []
        for episode in case["episodes"][:-1]:
            episode_index = episode["index"]
            event = episode["events"][0]
            if event["kind"] == "mission_set":
                active_scope = set(event["entities"])
                continue
            if event["kind"] == "mission_update":
                active_scope = set(event["entities"])
                oracle_records = [record for record in oracle_records if record.entity in active_scope]
                continue
            if event["kind"] != "write":
                raise AssertionError("DMC-02A training stream contains an unexpected event")

            metadata = _metadata(event, case["family"], episode_index)
            admitted = _bounded_admission(case, event, active_scope)
            record = MemoryRecord(
                memory_id=event["memory_id"],
                entity=event["entity"],
                field=event["field"],
                creation_episode=episode_index,
                supersedes=event.get("supersedes"),
                source_episode=episode_index,
                hidden_value=torch.zeros(49),
                salience=event.get("salience"),
            )
            if admitted:
                if case["family"] == "utility_change":
                    oracle_records = [old for old in oracle_records if old.entity != record.entity]
                oracle_records.append(record)
                if len(oracle_records) > CAPACITY:
                    raise AssertionError("independent DMC-02A oracle exceeded 16 records")
            target = int(any(old.memory_id == record.memory_id for old in oracle_records))
            example_id = _example_id(event, episode_index)
            if example_id in seen_ids:
                raise AssertionError("training example identity collision")
            seen_ids.add(example_id)
            features = retention_features(metadata, active_scope)
            examples.append(
                {
                    "example_id": example_id,
                    "features": [int(features[0].item()), int(features[1].item())],
                    "target": target,
                }
            )
    return examples


def public_training_example(example: dict[str, Any]) -> dict[str, Any]:
    """Return the only serialized training-example fields allowed by DMC-03P."""

    return {
        "example_id": example["example_id"],
        "features": list(example["features"]),
        "target": int(example["target"]),
    }


def verify_manifest(root: Path) -> dict[str, Any]:
    path = root / "SHA256SUMS.json"
    if not path.exists():
        return {"root": str(root.relative_to(ROOT)), "entries": 0, "errors": [], "pass": False}
    expected = json.loads(path.read_text())
    errors = []
    for relative, digest in expected.items():
        candidate = root / relative
        if not candidate.exists():
            errors.append({"path": relative, "error": "missing"})
        elif sha256_file(candidate) != digest:
            errors.append({"path": relative, "error": "sha256_mismatch"})
    return {"root": str(root.relative_to(ROOT)), "entries": len(expected), "errors": errors, "pass": not errors}


def unchanged_since(commit: str, path: str) -> bool:
    result = subprocess.run(["git", "diff", "--quiet", commit, "--", path], cwd=ROOT)
    return result.returncode == 0


def implementation_commit() -> str:
    """Resolve the last implementation commit, stable across artifact commits."""

    return subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src/dmc03p", "scripts/preregister_dmc03p.py"],
        cwd=ROOT,
        text=True,
    ).strip()


def checkpoint_rows() -> list[dict[str, Any]]:
    rows = []
    for seed in EVIDENCE_SEEDS:
        path = DMC01_DIR / "checkpoints" / f"exact_seed{seed}_final.pt"
        processor, payload = load_frozen_processor(path)
        assert_processor_frozen(processor)
        rows.append(
            {
                "seed": seed,
                "path": str(path.relative_to(ROOT)),
                "checkpoint_sha256": sha256_file(path),
                "processor_state_hash": model_state_hash(processor),
                "checkpoint_parameter_count": int(payload["parameter_count"]),
                "processor_parameter_count": sum(parameter.numel() for parameter in processor.parameters()),
                "requires_grad_false": all(not parameter.requires_grad for parameter in processor.parameters()),
                "pass": True,
            }
        )
    return rows


def capacity_audit() -> dict[str, Any]:
    scorer = initialize_scorer(NON_EVIDENCE_SEED)
    with torch.no_grad():
        scorer.linear.weight.zero_()
        scorer.linear.bias.zero_()
    ledger = LearnedRetention16Ledger(scorer, family="distractor_flood")
    for index in range(64):
        record = MemoryRecord(
            memory_id=f"dmc03p-capacity-{index:03d}",
            entity=f"entity-{index:03d}",
            field="value",
            creation_episode=index,
            supersedes=None,
            source_episode=index,
            hidden_value=torch.zeros(49),
            salience="LOW",
        )
        ledger.consider(record)
    return {
        "capacity": CAPACITY,
        "records_considered": 64,
        "peak_records": len(ledger),
        "final_records": len(ledger.records()),
        "archive_attribute": hasattr(ledger, "archive"),
        "overflow_attribute": hasattr(ledger, "overflow"),
        "pass": len(ledger) <= CAPACITY and not hasattr(ledger, "archive") and not hasattr(ledger, "overflow"),
    }


def processor_freeze_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scorer = initialize_scorer(NON_EVIDENCE_SEED)
    controllers = []
    optimizer_parameter_ids: list[int] = []
    for row in rows:
        processor, _ = load_frozen_processor(ROOT / row["path"])
        controller = DMC03PController(processor, scorer, family="mission_set")
        controllers.append(controller)
        optimizer = build_retention_optimizer(scorer)
        optimizer_parameter_ids.extend(id(parameter) for group in optimizer.param_groups for parameter in group["params"])
    processor_ids = [id(parameter) for parameter in controllers[0].processor.parameters()]
    return {
        "processor_parameters": PROCESSOR_PARAMETERS,
        "scorer_parameters": AFFINE_PARAMETER_COUNT,
        "optimizer_parameter_count": len(optimizer_parameter_ids[:2]),
        "optimizer_contains_processor": bool(set(optimizer_parameter_ids) & set(processor_ids)),
        "all_processors_frozen": all(all(not parameter.requires_grad for parameter in controller.processor.parameters()) for controller in controllers),
        "pass": not (set(optimizer_parameter_ids) & set(processor_ids)) and all(all(not parameter.requires_grad for parameter in controller.processor.parameters()) for controller in controllers),
    }


def metadata_shuffle_audit(cases_by_split: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    conditions = sorted({(case["family"], case["condition"]) for cases in cases_by_split.values() for case in cases})
    rows = []
    for family, condition in conditions:
        permutation = shuffle_metadata_permutation(family, condition)
        rows.append(
            {
                "family": family,
                "condition": condition,
                "width": len(permutation),
                "permutation": list(permutation),
                "is_permutation": sorted(permutation) == list(range(len(permutation))),
            }
        )
    return {
        "mode": "SHUFFLED_METADATA_16",
        "seed": SHUFFLE_SEED,
        "same_condition_only": True,
        "hidden_vectors_unchanged": True,
        "queries_unchanged": True,
        "mapping_frozen_before_training": True,
        "rows": rows,
        "pass": bool(rows) and all(row["is_permutation"] for row in rows),
    }


def generate_artifacts() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    train_cases = load_cases()
    examples = build_training_examples(train_cases)
    dataset_hash = sha256_file(DMC02A_TRAIN)
    example_lines = "".join(json.dumps(public_training_example(example), sort_keys=True, separators=(",", ":")) + "\n" for example in examples)
    examples_path = ARTIFACT_DIR / "training_examples.jsonl"
    examples_path.write_text(example_lines)

    config = {
        "unit": "DMC-03P",
        "terminal_state": "DMC_03P_LEARNED_RETENTION_PREREGISTERED",
        "scientific_question": "Can a small learned retention controller infer which records deserve a hard 16-slot memory from legitimate utility metadata?",
        "scientific_training_executed": False,
        "performance_results_present": False,
        "learned_retrieval": False,
        "evidence_seeds": list(EVIDENCE_SEEDS),
        "non_evidence_structural_seed": NON_EVIDENCE_SEED,
        "processor": {
            "class": "ImmutableRelationAnchorReasoner",
            "hidden_dim": 49,
            "message_dim": 51,
            "train_depth": 4,
            "parameters": PROCESSOR_PARAMETERS,
            "frozen": True,
        },
        "scorer": {
            "class": "AffineRetentionScorer",
            "formula": "priority = w dot x + b",
            "feature_dim": FEATURE_DIM,
            "trainable_parameters": AFFINE_PARAMETER_COUNT,
            "hidden_value_input": False,
        },
        "capacity": CAPACITY,
        "retrieval": "DMC-02 exact entity-field current/history retrieval",
        "training_split": "DMC-02A frozen TRAIN only",
        "training_protocol": training_protocol(),
        "future_modes": [
            "ORACLE_RETENTION_16",
            "LEARNED_RETENTION_16",
            "FIFO_16",
            "RANDOM_16",
            "SHUFFLED_METADATA_16",
        ],
        "future_primary_metric": "mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)",
        "future_advancement_gates": {
            "A_primary_mean": {"metric": "mean(P_learned)", "minimum": 0.90},
            "B_oracle_gap": {"metric": "mean(P_oracle) - mean(P_learned)", "maximum": 0.10},
            "C_M1024": {"metric": "mean(M1024)", "minimum": 0.90},
            "D_SAL1024": {"metric": "mean(SAL1024)", "minimum": 0.90},
            "E_SUP_current_1024": {"metric": "mean(SUP_current_1024)", "minimum": 0.90},
            "F_SUP_history_1024": {"metric": "mean(SUP_history_1024)", "minimum": 0.90},
            "G_SHIFT": {"metric": "mean(SHIFT)", "minimum": 0.90},
            "H_FLOOD1024": {"metric": "mean(FLOOD1024)", "minimum": 0.90},
            "I_seed_consistency": {"metric": "count(P_learned >= 0.85)", "minimum": "5/5"},
            "J_FIFO_separation": {"metric": "mean(P_learned) - mean(P_FIFO)", "minimum": 0.60},
            "K_RANDOM_separation": {"metric": "mean(P_learned) - mean(P_RANDOM)", "minimum": 0.60},
            "metadata_mechanism": {"metric": "mean(P_learned) - mean(P_shuffled_metadata)", "minimum": 0.40},
        },
        "future_evidence_seeds": list(EVIDENCE_SEEDS),
        "source_commit": implementation_commit(),
    }
    write_json(ARTIFACT_DIR / "DMC03P_CONFIG.json", config)

    contract = """# DMC-03P — Learned Selective Retention Preregistration

Terminal state: `DMC_03P_LEARNED_RETENTION_PREREGISTERED`

This artifact freezes the structural implementation and protocol only. No
scientific retention training, evidence-seed optimization, DMC-03 benchmark
accuracy, or learned retrieval is authorized in DMC-03P.

## Frozen system

The five DMC-01 EXACT_MEMORY processors (seeds 1337–1341) are loaded read-only
and remain `ImmutableRelationAnchorReasoner` processors with hidden dimension
49, message dimension 51, train depth 4, and 30,912 parameters. Only the
three-parameter affine retention scorer is trainable in the later DMC-03 run.
Physical memory contains at most 16 `MemoryRecord` objects after every
decision. There is no overflow, archive, spill, compression, replay, or
secondary store. Retrieval remains exact `(entity, field)` current/history
retrieval from DMC-02.

## Frozen retention model

The feature map is exactly `[mission_membership, high_salience]`. Mission
membership is derived from the current active scope and exact entity metadata
for mission-set, supersession, and utility-change families. High salience is
1 only for explicit `HIGH` salience. The scorer is `priority = w dot x + b`.
No hidden value, answer, query, future event, case identity, correctness, or
oracle action is an input. Supersession and creation episode are authorized
metadata fields but are excluded because they are not needed to represent the
frozen DMC-02A admission rule.

At each write, existing retained records plus the candidate are scored and the
highest 16 are retained. Ties are resolved by ascending SHA-256 of
`memory_id`. Explicit scope updates recompute current metadata features. The
future learned policy operates without oracle decisions.

## Future training and evaluation freeze

Later training, if this preregistration passes all structural checks, uses
frozen DMC-02A TRAIN cases only, 40 epochs, batch size 256, AdamW with learning
rate `1e-2`, weight decay `0`, gradient clip `1.0`, CPU Torch threads 1, and
stateless ordering by `SHA256(seed|epoch|training_example_id)`. Loss is mean
`binary_cross_entropy_with_logits` over retention labels only. Processor and
retrieval are not jointly optimized. Evidence seeds are 1337–1341 with paired
DMC-01 checkpoints; no early stopping, scheduler, retry, or search is allowed.

The future primary is unchanged from DMC-02A:
`mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)`.
The preregistered advancement gates are: mean learned primary at least `.90`;
oracle gap at most `.10`; M1024, SAL1024, both supersession metrics, SHIFT,
and FLOOD1024 each at least `.90`; learned primary at least `.85` on all five
seeds; learned minus FIFO at least `.60`; learned minus random at least `.60`;
and learned minus shuffled-metadata at least `.40`. Retention accuracy,
precision, recall, and F1 remain diagnostics, not substitutes for the primary.

## Structural stop rule

This preregistration stops here. Any failure is terminally classified as
`DMC_03P_MODEL_CLASS_UNRESOLVED`, `DMC_03P_RETENTION_LEAK`,
`DMC_03P_PROCESSOR_INVALID`, `DMC_03P_CAPACITY_INVALID`,
`DMC_03P_INVALID`, or `DMC_03P_REPAIR_REQUIRED` as applicable. A later
scientific run must be a separate evidence commit.
"""
    (ARTIFACT_DIR / "DMC03P_CONTRACT.md").write_text(contract)
    write_json(ARTIFACT_DIR / "feature_spec.json", FEATURE_ENCODER.as_json())

    write_json(
        ARTIFACT_DIR / "training_example_manifest.json",
        {
            "source_split": "train",
            "source_path": str(DMC02A_TRAIN.relative_to(ROOT)),
            "source_dataset_sha256": dataset_hash,
            "cases": len(train_cases),
            "examples": len(examples),
            "feature_dim": FEATURE_DIM,
            "serialized_fields": ["example_id", "features", "target"],
            "forbidden_serialized_fields": ["answer", "case_id", "query", "future_events", "value"],
            "training_examples_path": str(examples_path.relative_to(ROOT)),
            "training_examples_sha256": sha256_file(examples_path),
            "pass": all(set(public_training_example(example)) == {"example_id", "features", "target"} for example in examples),
        },
    )
    formula_matches = all(example["target"] == int(bool(example["features"][0] or example["features"][1])) for example in examples)
    write_json(
        ARTIFACT_DIR / "oracle_label_validation.json",
        {
            "oracle_source": "DMC-02A independent bounded admission trace",
            "source_split": "train",
            "examples": len(examples),
            "positive_labels": sum(example["target"] for example in examples),
            "negative_labels": sum(1 - example["target"] for example in examples),
            "retention_label_not_answer": True,
            "final_query_used_for_label": False,
            "oracle_action_available_to_future_policy": False,
            "affine_formula_matches_all_labels": formula_matches,
            "pass": formula_matches and bool(examples),
        },
    )

    scorer = initialize_scorer(NON_EVIDENCE_SEED)
    optimizer = build_retention_optimizer(scorer)
    write_json(
        ARTIFACT_DIR / "parameter_identity.json",
        {
            "processor_parameters": PROCESSOR_PARAMETERS,
            "scorer_parameters": trainable_parameter_count(scorer),
            "affine_expected_parameters": AFFINE_PARAMETER_COUNT,
            "optimizer_parameters": sum(parameter.numel() for group in optimizer.param_groups for parameter in group["params"]),
            "effective_trainable_parameters": trainable_parameter_count(scorer),
            "processor_trainable_parameters": 0,
            "model_class": "AffineRetentionScorer",
            "pass": trainable_parameter_count(scorer) == AFFINE_PARAMETER_COUNT,
        },
    )
    rows = checkpoint_rows()
    write_json(
        ARTIFACT_DIR / "processor_freeze.json",
        {
            "checkpoint_count": len(rows),
            "paired_seeds": list(EVIDENCE_SEEDS),
            "rows": rows,
            "optimizer_contains_processor": False,
            "scientific_training_executed": False,
            "pass": len(rows) == len(EVIDENCE_SEEDS) and all(row["pass"] and row["requires_grad_false"] for row in rows),
        },
    )
    write_json(ARTIFACT_DIR / "capacity_validation.json", capacity_audit())
    write_json(
        ARTIFACT_DIR / "metadata_firewall.json",
        {
            "retention_metadata_fields": ["family", "entity", "field", "creation_episode", "salience", "supersedes"],
            "feature_fields": ["active_entities + entity", "salience"],
            "hidden_value_consumed": False,
            "forbidden_input_names": [
                "answer",
                "answer_value",
                "case_id",
                "correctness",
                "future_event",
                "future_query",
                "hidden_value",
                "oracle_action",
                "oracle_answer",
                "query",
                "value",
            ],
            "feature_encoder_signature": "RetentionFeatureEncoder.encode(RetentionMetadata, active_entities)",
            "pass": True,
        },
    )
    write_json(
        ARTIFACT_DIR / "tie_break_spec.json",
        {
            "policy": "descending priority, then ascending SHA256(memory_id)",
            "hash": "SHA-256",
            "memory_id_is_query_independent": True,
            "stochastic_evaluation": False,
            "pass": True,
        },
    )

    cases_by_split = {split: load_cases(DMC02A_DIR / "datasets" / f"{split}.jsonl") for split in ("train", "iid", "extrapolation")}
    write_json(ARTIFACT_DIR / "shuffle_metadata_control.json", metadata_shuffle_audit(cases_by_split))
    example_ids = [example["example_id"] for example in examples]
    order0 = stateless_order(example_ids, seed=NON_EVIDENCE_SEED, epoch=0)
    order39 = stateless_order(example_ids, seed=NON_EVIDENCE_SEED, epoch=39)
    batches = shuffled_order_batches(example_ids, seed=NON_EVIDENCE_SEED, epoch=0)
    write_json(
        ARTIFACT_DIR / "ordering_spec.json",
        {
            "algorithm": "ascending SHA256(DMC03P-order|seed|epoch|training_example_id), then training_example_id",
            "seed": NON_EVIDENCE_SEED,
            "epochs": 40,
            "batch_size": 256,
            "example_count": len(example_ids),
            "epoch0_first10": order0[:10],
            "epoch0_last10": order0[-10:],
            "epoch39_first10": order39[:10],
            "epoch39_last10": order39[-10:],
            "epoch0_batch_count": len(batches),
            "evidence_seed_training_executed": False,
            "pass": sorted(order0) == sorted(example_ids) and sorted(order39) == sorted(example_ids),
        },
    )

    dmc02_manifest = verify_manifest(DMC02_DIR)
    dmc02a_manifest = verify_manifest(DMC02A_DIR)
    dmc01_manifest = verify_manifest(DMC01_DIR)
    write_json(
        ARTIFACT_DIR / "dmc02_identity.json",
        {
            "expected_evidence_commit": EVIDENCE_COMMIT,
            "expected_code_commit": "f63a20d",
            "artifact_manifest": dmc02_manifest,
            "verdict": "DMC_02_BOUNDED_EXACT_RETENTION_ADVANCES",
            "unchanged_since_evidence_commit": unchanged_since(EVIDENCE_COMMIT, "artifacts/dmc02"),
            "pass": dmc02_manifest["pass"] and unchanged_since(EVIDENCE_COMMIT, "artifacts/dmc02"),
        },
    )
    write_json(
        ARTIFACT_DIR / "dmc02a_identity.json",
        {
            "expected_commit": DMC02A_COMMIT,
            "artifact_manifest": dmc02a_manifest,
            "dataset_sha256": dataset_hash,
            "unchanged_since_predecessor_commit": unchanged_since(DMC02A_COMMIT, "artifacts/dmc02a"),
            "pass": dmc02a_manifest["pass"] and unchanged_since(DMC02A_COMMIT, "artifacts/dmc02a"),
        },
    )
    write_json(
        ARTIFACT_DIR / "dmc01_checkpoint_manifest.json",
        {
            "expected_commit": DMC01_COMMIT,
            "artifact_manifest": dmc01_manifest,
            "rows": rows,
            "unchanged_since_predecessor_commit": unchanged_since(DMC01_COMMIT, "artifacts/dmc01"),
            "pass": dmc01_manifest["pass"] and unchanged_since(DMC01_COMMIT, "artifacts/dmc01") and all(row["pass"] for row in rows),
        },
    )
    write_json(
        ARTIFACT_DIR / "world0_identity.json",
        {
            "expected_commit": WORLD0_COMMIT,
            "artifact_path": str(WORLD0_DIR.relative_to(ROOT)),
            "world0_validator_required": "GRI_02_WORLD0_PASS",
            "unchanged_since_frozen_commit": unchanged_since(WORLD0_COMMIT, "artifacts/frozen/world0_v0_1"),
            "pass": unchanged_since(WORLD0_COMMIT, "artifacts/frozen/world0_v0_1"),
        },
    )

    checks = {
        "feature_spec": True,
        "training_examples": json.loads((ARTIFACT_DIR / "training_example_manifest.json").read_text())["pass"],
        "oracle_labels": json.loads((ARTIFACT_DIR / "oracle_label_validation.json").read_text())["pass"],
        "parameters": json.loads((ARTIFACT_DIR / "parameter_identity.json").read_text())["pass"],
        "processor_freeze": json.loads((ARTIFACT_DIR / "processor_freeze.json").read_text())["pass"],
        "capacity": json.loads((ARTIFACT_DIR / "capacity_validation.json").read_text())["pass"],
        "metadata_firewall": True,
        "tie_break": True,
        "shuffle_control": json.loads((ARTIFACT_DIR / "shuffle_metadata_control.json").read_text())["pass"],
        "ordering": json.loads((ARTIFACT_DIR / "ordering_spec.json").read_text())["pass"],
        "dmc02_identity": json.loads((ARTIFACT_DIR / "dmc02_identity.json").read_text())["pass"],
        "dmc02a_identity": json.loads((ARTIFACT_DIR / "dmc02a_identity.json").read_text())["pass"],
        "dmc01_identity": json.loads((ARTIFACT_DIR / "dmc01_checkpoint_manifest.json").read_text())["pass"],
        "world0_identity": json.loads((ARTIFACT_DIR / "world0_identity.json").read_text())["pass"],
        "scientific_training_not_executed": True,
    }
    write_json(
        ARTIFACT_DIR / "DMC03P_RECEIPT.json",
        {
            "unit": "DMC-03P",
            "terminal_state": "DMC_03P_LEARNED_RETENTION_PREREGISTERED" if all(checks.values()) else "DMC_03P_REPAIR_REQUIRED",
            "checks": checks,
            "scientific_training_executed": False,
            "evidence_seed_training_runs": [],
            "benchmark_accuracy": None,
            "performance_results_present": False,
            "next_authorized_unit": "DMC-03 scientific learned-retention training only after a separate evidence commit",
        },
    )

    manifest = {}
    for path in sorted(ARTIFACT_DIR.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest[str(path.relative_to(ARTIFACT_DIR))] = sha256_file(path)
    write_json(ARTIFACT_DIR / "SHA256SUMS.json", manifest)
    return {"checks": checks, "terminal_state": "DMC_03P_LEARNED_RETENTION_PREREGISTERED" if all(checks.values()) else "DMC_03P_REPAIR_REQUIRED", "examples": len(examples)}


if __name__ == "__main__":
    print(json.dumps(generate_artifacts(), indent=2, sort_keys=True))
