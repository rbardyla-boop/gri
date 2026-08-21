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

from dmc02a.benchmark import VALUES  # noqa: E402
from dmc02p.controller import (  # noqa: E402
    CAPACITY,
    RANDOM_CONTROL_SEED,
    ExactRetention16Controller,
    ExactRetentionPolicy,
    FIFO16Controller,
    Random16Controller,
    build_processor,
    load_dmc01_checkpoint,
    memory_record_field_names,
    retention_metadata_field_names,
    trainable_parameter_count,
)


OUT = ROOT / "artifacts/dmc02p"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC01_COMMIT = "48ae98f"
DMC02A_COMMIT = "f10394d"
EVIDENCE_SEEDS: tuple[int, ...] = (1337, 1338, 1339, 1340, 1341)
FUTURE_PRIMARY = "mean(M256,M1024,SAL256,SAL1024,SUP_current_1024,SUP_history_1024,SHIFT,FLOOD512,FLOOD1024)"

CONTRACT = r"""# DMC-02P — 16-Slot Bounded Exact-Retention Preregistration

Status: **PREREGISTERED; STRUCTURAL CONTROL ONLY; NO SCIENTIFIC EVALUATION**

## Scientific question

Can the DMC-01 learned hidden representations remain usable when physical
storage is capped at exactly 16 hidden records, while retention decisions and
exact addressing remain perfect? This is an upper-bound control that removes
unlimited storage but does not yet learn importance or retrieval.

The future DMC-02 evidence unit must use the five frozen DMC-01
`EXACT_MEMORY` checkpoints without retraining. This preregistration performs
no accuracy evaluation and executes no evidence seeds.

## Frozen processor

The trainable processor is unchanged:

```text
ImmutableRelationAnchorReasoner
hidden_dim = 49
message_dim = 51
train_depth = 4
trainable parameters = 30,912
```

The memory controller adds zero trainable parameters.

## Hard physical budget

Every controller mode has exactly 16 physical record slots. The runtime
invariant is checked after every scope and write event:

```text
len(memory) <= 16
```

There is no archive, overflow buffer, compressed spill, disk side channel, or
recomputation from raw prior episodes.

## Memory modes

1. `EXACT_RETENTION_16`: mission membership, salience, explicit mission
   updates, supersession metadata, and creation episode are the only
   retention inputs.
2. `FIFO_16`: deterministic first-in-first-out eviction.
3. `RANDOM_16`: the DMC-02A deterministic reservoir rule with independent
   seed `20260202`.

All three modes use the same frozen neural processor. None has trainable
memory-management parameters.

The exact policy receives a metadata-only `RetentionMetadata` object. It has
no answer value, hidden vector, final query, case ID, future event, or oracle
answer. The final queried key is never supplied to retention.

## Retention and retrieval

Every write first produces the DMC-01 hidden representation. The authorized
metadata policy then decides whether that record is stored. Irrelevant records
may be discarded immediately. Utility-change eviction occurs only after the
explicit mission-update event. Supersession retains both historical and
current records when both are query-eligible.

Retrieval is exact `(entity, field)` lookup. Current retrieval returns the
latest retained record; history retrieval returns the latest retained record
whose creation episode is no later than `as_of_episode`. No learned search,
attention, cosine similarity, semantic address, compression, or quantization
is present.

## Future evidence protocol

The future unit uses DMC-02A data byte-for-byte and the frozen primary metric:

```text
P_bounded = mean(
    M256, M1024,
    SAL256, SAL1024,
    SUP_current_1024, SUP_history_1024,
    SHIFT,
    FLOOD512, FLOOD1024
)
```

`EXACT_RETENTION_16` advances only if all of the following pass:

- mean `P_bounded >= .95`;
- mean `M1024 >= .95`;
- mean `SAL1024 >= .95`;
- mean `SUP_current_1024 >= .95`;
- mean `SUP_history_1024 >= .95`;
- mean `SHIFT >= .95`;
- mean `FLOOD1024 >= .95`;
- `P_bounded >= .90` for all five checkpoints;
- mean exact-minus-FIFO primary metric `>= .40`;
- mean exact-minus-random primary metric `>= .40`.

These gates are recorded now and are not evaluated in DMC-02P.

## Structural checks performed here

- 16-slot invariant and absence of overflow fields;
- metadata-only retention firewall;
- FIFO and deterministic random behavior;
- exact current/history retrieval;
- supersession preservation;
- utility-update eviction timing;
- hidden-vector identity before and after storage;
- compatibility with all five frozen DMC-01 checkpoints;
- DMC-02A, DMC-01, and WORLD-0 identity/hash boundaries.

## Explicit non-actions

This unit performs no optimizer steps, backward passes, retraining, evidence
evaluation, benchmark scoring, learned retention, learned eviction, learned
retrieval, DMC-03 work, or language experiments.

## Terminal state

`DMC_02P_PREREGISTERED`
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def verify_manifest(root: Path, manifest_name: str = "SHA256SUMS.json") -> dict:
    manifest = json.loads((root / manifest_name).read_text())
    errors = []
    for relative, expected in manifest.items():
        path = root / relative
        if not path.exists():
            errors.append({"path": relative, "error": "missing"})
        elif sha256(path) != expected:
            errors.append({"path": relative, "error": "sha256_mismatch", "expected": expected, "observed": sha256(path)})
    return {"root": str(root.relative_to(ROOT)), "manifest": manifest_name, "entries": len(manifest), "pass": not errors, "errors": errors}


def read_first_write() -> tuple[dict, dict]:
    path = ROOT / "artifacts/dmc02a/datasets/train.jsonl"
    case = json.loads(path.read_text().splitlines()[0])
    scope = case["episodes"][0]["events"][0]
    event = next(episode["events"][0] for episode in case["episodes"] if episode["events"][0]["kind"] == "write")
    return scope, event


def synthetic_write(index: int, entity: str, *, value: str = "RED", supersedes: str | None = None) -> dict:
    return {"kind": "write", "memory_id": f"structural-{index}", "entity": entity, "field": "value", "value": value, "salience": None, "supersedes": supersedes}


def structural_memory_budget() -> dict:
    controller = ExactRetention16Controller(build_processor(), family="mission_set", case_id="budget")
    entities = [f"mission-{index}" for index in range(CAPACITY)]
    controller.process_scope_event({"kind": "mission_set", "entities": entities})
    peaks = []
    with torch.no_grad():
        for index, entity in enumerate(entities):
            controller.process_write(synthetic_write(index, entity, value=VALUES[index % len(VALUES)]), index + 1)
            peaks.append(len(controller.ledger))
        for index in range(CAPACITY, 32):
            controller.process_write(synthetic_write(index, f"distractor-{index}"), index + 1)
            peaks.append(len(controller.ledger))
    forbidden_attributes = [name for name in ("archive", "overflow", "spill", "raw_events") if hasattr(controller, name) or hasattr(controller.ledger, name)]
    return {"capacity": CAPACITY, "max_observed_records": max(peaks), "all_peaks_at_or_below_capacity": max(peaks) <= CAPACITY, "forbidden_side_channel_attributes": forbidden_attributes, "pass": max(peaks) <= CAPACITY and not forbidden_attributes}


def structural_retention_semantics() -> dict:
    policy = ExactRetentionPolicy("mission_set")
    fields_ok = set(retention_metadata_field_names()).isdisjoint({"value", "answer", "query", "case_id", "future_event", "oracle_answer"})
    signature = list(inspect.signature(ExactRetentionPolicy.admits).parameters)
    source = inspect.getsource(ExactRetentionPolicy.admits)
    source_clean = "oracle_answer" not in source and "case_id" not in source
    return {
        "exact_policy": "EXACT_RETENTION_16",
        "allowed_metadata": ["family", "entity", "field", "creation_episode", "salience", "supersedes"],
        "forbidden_retention_inputs": ["value", "answer", "final_query", "case_id", "future_event", "oracle_answer"],
        "retention_metadata_fields": list(retention_metadata_field_names()),
        "policy_admits_signature": signature,
        "metadata_fields_firewall_pass": fields_ok,
        "policy_source_firewall_pass": source_clean,
        "memory_parameter_count": 0,
        "pass": fields_ok and signature == ["self", "metadata"] and source_clean and policy.family == "mission_set",
    }


def supersession_validation() -> dict:
    controller = ExactRetention16Controller(build_processor(), family="supersession", case_id="supersession")
    entities = [f"entity-{index}" for index in range(8)]
    controller.process_scope_event({"kind": "mission_set", "entities": entities})
    original_ids = {}
    with torch.no_grad():
        for index, entity in enumerate(entities):
            original = synthetic_write(index, entity, value="RED")
            original_ids[entity] = original["memory_id"]
            controller.retain_record(controller.make_record(original, index + 1, hidden_value=torch.full((49,), float(index))))
            current = synthetic_write(100 + index, entity, value="BLUE", supersedes=original_ids[entity])
            controller.retain_record(controller.make_record(current, 100 + index, hidden_value=torch.full((49,), float(index + 100))))
    history = controller.retrieve(entity_query(entities[0], mode="history", as_of_episode=1))
    current = controller.retrieve(entity_query(entities[0], mode="current"))
    passed = len(controller.ledger) == 16 and history.memory_id == original_ids[entities[0]] and current.supersedes == history.memory_id
    return {"capacity": CAPACITY, "records_after_16_versions": len(controller.ledger), "history_memory_id": history.memory_id, "current_memory_id": current.memory_id, "history_and_current_distinct": history.memory_id != current.memory_id, "pass": passed}


def entity_query(entity: str, *, mode: str, as_of_episode: int | None = None) -> dict:
    return {"kind": "query", "entity": entity, "field": "value", "mode": mode, "as_of_episode": as_of_episode}


def utility_shift_validation() -> dict:
    controller = ExactRetention16Controller(build_processor(), family="utility_change", case_id="utility")
    phase_a = [f"a-{index}" for index in range(16)]
    phase_b = phase_a[:8] + [f"b-{index}" for index in range(8)]
    controller.process_scope_event({"kind": "mission_set", "entities": phase_a})
    for index, entity in enumerate(phase_a):
        controller.retain_record(controller.make_record(synthetic_write(index, entity), index, hidden_value=torch.zeros(49)))
    before_update = {record.entity for record in controller.ledger.records()}
    controller.process_scope_event({"kind": "mission_update", "entities": phase_b})
    after_update = {record.entity for record in controller.ledger.records()}
    for index, entity in enumerate(phase_b, start=100):
        controller.retain_record(controller.make_record(synthetic_write(index, entity, value="BLUE"), index, hidden_value=torch.ones(49)))
    after_phase_b = {record.entity for record in controller.ledger.records()}
    return {"before_update_all_phase_a": before_update == set(phase_a), "obsolete_phase_a_evicted_after_update": after_update == set(phase_a[:8]), "after_phase_b_exact_active_set": after_phase_b == set(phase_b), "capacity": len(controller.ledger), "pass": before_update == set(phase_a) and after_update == set(phase_a[:8]) and after_phase_b == set(phase_b) and len(controller.ledger) == 16}


def hidden_vector_identity() -> dict:
    checkpoint = ROOT / "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
    controller, _ = load_dmc01_checkpoint(checkpoint, family="mission_set", mode="exact16", case_id="hidden-identity")
    scope, event = read_first_write()
    controller.process_scope_event(scope)
    with torch.no_grad():
        hidden_before = controller.encode_hidden(event)
        record = controller.make_record(event, 1, hidden_value=hidden_before)
        controller.retain_record(record)
    hidden_after = controller.ledger.records()[0].hidden_value
    equal = torch.equal(hidden_before, hidden_after)
    return {"checkpoint": str(checkpoint.relative_to(ROOT)), "shape": list(hidden_before.shape), "dtype": str(hidden_before.dtype), "value_equal": equal, "same_tensor_storage": hidden_before.data_ptr() == hidden_after.data_ptr(), "compression": False, "quantization": False, "pass": equal and hidden_before.data_ptr() == hidden_after.data_ptr() and tuple(hidden_before.shape) == (49,)}


def checkpoint_manifest_and_parameters() -> tuple[dict, dict]:
    root = ROOT / "artifacts/dmc01"
    manifest_status = verify_manifest(root)
    rows = []
    for seed in EVIDENCE_SEEDS:
        path = root / "checkpoints" / f"exact_seed{seed}_final.pt"
        payload = torch.load(path, map_location="cpu", weights_only=False)
        controllers = [
            load_dmc01_checkpoint(path, family="mission_set", mode="exact16", case_id=f"seed-{seed}-exact")[0],
            load_dmc01_checkpoint(path, family="mission_set", mode="fifo16", case_id=f"seed-{seed}-fifo")[0],
            load_dmc01_checkpoint(path, family="mission_set", mode="random16", case_id=f"seed-{seed}-random")[0],
        ]
        state_equal = all(list(controllers[0].state_dict()) == list(controller.state_dict()) and all(torch.equal(controllers[0].state_dict()[key], controller.state_dict()[key]) for key in controllers[0].state_dict()) for controller in controllers[1:])
        row = {
            "seed": seed,
            "checkpoint": str(path.relative_to(ROOT)),
            "checkpoint_sha256": sha256(path),
            "manifest_sha256_match": manifest_status["pass"] and sha256(path) == json.loads((root / "SHA256SUMS.json").read_text())[str(path.relative_to(root))],
            "payload_model_type": payload.get("model_type"),
            "completed_epoch": payload.get("completed_epoch"),
            "parameter_count_in_checkpoint": payload.get("parameter_count"),
            "processor_parameters": [trainable_parameter_count(controller.processor) for controller in controllers],
            "controller_parameters": [trainable_parameter_count(controller) for controller in controllers],
            "memory_parameters": [controller.trainable_memory_parameter_count for controller in controllers],
            "same_processor_state_across_modes": state_equal,
        }
        row["pass"] = row["manifest_sha256_match"] and row["payload_model_type"] == "EXACT_MEMORY" and row["completed_epoch"] == 80 and row["parameter_count_in_checkpoint"] == 30_912 and row["processor_parameters"] == [30_912] * 3 and row["controller_parameters"] == [30_912] * 3 and row["memory_parameters"] == [0] * 3 and state_equal
        rows.append(row)
    return ({"expected_dmc01_commit": DMC01_COMMIT, "manifest_verification": manifest_status, "exact_checkpoint_count": len(rows), "rows": rows, "pass": manifest_status["pass"] and all(row["pass"] for row in rows)}, {"pass": all(row["pass"] for row in rows), "rows": rows, "trainable_parameters": 30_912, "memory_controller_parameters": 0})


def predecessor_identity(expected_commit: str, path: str) -> dict:
    result = subprocess.run(["git", "diff", "--exit-code", expected_commit, "--", path], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {"expected_commit": expected_commit, "path": path, "unchanged": result.returncode == 0}


def identities() -> tuple[dict, dict, dict]:
    dmc02a_root = ROOT / "artifacts/dmc02a"
    dmc02a_manifest = verify_manifest(dmc02a_root)
    dmc02a_dataset_manifest = json.loads((dmc02a_root / "dataset_manifest.json").read_text())
    dataset_hashes_ok = all(sha256(ROOT / value["path"]) == value["sha256"] for value in dmc02a_dataset_manifest.values())
    dmc02a = {"expected_commit": DMC02A_COMMIT, "artifact_manifest": dmc02a_manifest, "dataset_manifest_hashes_match": dataset_hashes_ok, "terminal_state": json.loads((dmc02a_root / "DMC02A_RECEIPT.json").read_text())["terminal_state"], "unchanged": predecessor_identity(DMC02A_COMMIT, "artifacts/dmc02a")["unchanged"]}
    dmc02a["pass"] = dmc02a["artifact_manifest"]["pass"] and dataset_hashes_ok and dmc02a["terminal_state"] == "DMC_02A_SELECTIVE_RETENTION_BENCHMARK_PASS" and dmc02a["unchanged"]
    dmc01 = predecessor_identity(DMC01_COMMIT, "artifacts/dmc01")
    dmc01["checkpoint_manifest"] = verify_manifest(ROOT / "artifacts/dmc01")
    dmc01["pass"] = dmc01["unchanged"] and dmc01["checkpoint_manifest"]["pass"]
    world = predecessor_identity(WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    validation = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    world["validator_terminal"] = validation.stdout.strip().splitlines()[-1] if validation.stdout.strip() else ""
    world["pass"] = world["unchanged"] and world["validator_terminal"] == "GRI_02_WORLD0_PASS"
    return dmc02a, dmc01, world


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dmc02a, dmc01, world = identities()
    checkpoint_manifest, parameter_identity = checkpoint_manifest_and_parameters()
    budget = structural_memory_budget()
    retention = structural_retention_semantics()
    supersession = supersession_validation()
    utility = utility_shift_validation()
    hidden = hidden_vector_identity()
    metadata = {
        "retention_metadata_fields": list(retention_metadata_field_names()),
        "memory_record_fields": list(memory_record_field_names()),
        "forbidden_fields_absent": retention["metadata_fields_firewall_pass"],
        "policy_signature": retention["policy_admits_signature"],
        "no_final_query_argument": retention["policy_admits_signature"] == ["self", "metadata"],
        "oracle_answer_source_absent": retention["policy_source_firewall_pass"],
        "pass": retention["pass"],
    }
    config = {
        "unit": "DMC-02P",
        "status": "preregistered_structural_control_only",
        "generation_commit": git_commit(),
        "dmc01_commit": DMC01_COMMIT,
        "dmc02a_commit": DMC02A_COMMIT,
        "world0_commit": WORLD0_COMMIT,
        "evidence_seeds": [],
        "frozen_dmc01_evidence_seeds_for_future_unit": list(EVIDENCE_SEEDS),
        "processor": {"name": "ImmutableRelationAnchorReasoner", "hidden_dim": 49, "message_dim": 51, "train_depth": 4, "trainable_parameters": 30_912},
        "memory": {"capacity": CAPACITY, "controller_trainable_parameters": 0, "modes": ["EXACT_RETENTION_16", "FIFO_16", "RANDOM_16"], "random_seed": RANDOM_CONTROL_SEED},
        "future_primary_metric": FUTURE_PRIMARY,
        "future_gates": {"A_primary": 0.95, "B_M1024": 0.95, "C_SAL1024": 0.95, "D_SUP_current_1024": 0.95, "E_SUP_history_1024": 0.95, "F_SHIFT": 0.95, "G_FLOOD1024": 0.95, "H_seed_consistency": {"minimum_P_bounded": 0.90, "required_checkpoints": "5/5"}, "fifo_gap": 0.40, "random_gap": 0.40},
        "scientific_training": False,
        "scientific_evaluation": False,
        "optimizer": None,
        "backward_passes": 0,
    }
    (OUT / "DMC02P_CONTRACT.md").write_text(CONTRACT)
    write_json(OUT / "DMC02P_CONFIG.json", config)
    write_json(OUT / "dmc01_checkpoint_manifest.json", checkpoint_manifest)
    write_json(OUT / "dmc02a_identity.json", dmc02a)
    write_json(OUT / "memory_budget.json", budget)
    write_json(OUT / "retention_semantics.json", retention)
    write_json(OUT / "metadata_firewall.json", metadata)
    write_json(OUT / "supersession_validation.json", supersession)
    write_json(OUT / "utility_shift_validation.json", utility)
    write_json(OUT / "hidden_vector_identity.json", hidden)
    write_json(OUT / "parameter_identity.json", parameter_identity)
    write_json(OUT / "world0_identity.json", world)

    checks = {
        "memory_budget": budget["pass"],
        "retention_semantics": retention["pass"],
        "metadata_firewall": metadata["pass"],
        "supersession": supersession["pass"],
        "utility_shift": utility["pass"],
        "hidden_vector_identity": hidden["pass"],
        "checkpoint_compatibility": checkpoint_manifest["pass"],
        "parameter_identity": parameter_identity["pass"],
        "dmc02a_identity": dmc02a["pass"],
        "dmc01_identity": dmc01["pass"],
        "world0_identity": world["pass"],
        "no_evidence": config["scientific_evaluation"] is False and config["evidence_seeds"] == [] and config["backward_passes"] == 0,
    }
    terminal = "DMC_02P_PREREGISTERED" if all(checks.values()) else "DMC_02P_REPAIR_REQUIRED"
    write_json(OUT / "DMC02P_RECEIPT.json", {"unit": "DMC-02P", "terminal_state": terminal, "checks": checks, "scientific_training": False, "scientific_evaluation": False, "evidence_seeds_executed": [], "future_primary_metric": FUTURE_PRIMARY})
    manifest = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest[str(path.relative_to(OUT))] = sha256(path)
    write_json(OUT / "SHA256SUMS.json", manifest)
    print(terminal)
    return 0 if terminal == "DMC_02P_PREREGISTERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

