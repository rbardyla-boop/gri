from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from dmc04a.benchmark import CAPACITY as DMC04A_CAPACITY  # noqa: E402
from dmc04p.matcher import (  # noqa: E402
    ATOM_SIZE,
    CODEBOOKS,
    EVIDENCE_SEEDS,
    NON_EVIDENCE_SEED,
    TRAINING_BATCH_SIZE,
    TRAINING_EPOCHS,
    TRAINING_GRAD_CLIP,
    TRAINING_LR,
    TRAINING_WEIGHT_DECAY,
    FactorizedAssociativeMatcher,
    build_optimizer,
    build_shuffle_query_mapping,
    candidate_scores,
    canonical,
    group_scores,
    load_training_cases,
    resolver,
    scorer_view,
    state_hash,
    target_group,
    trainable_parameter_count,
    training_order,
    validate_scorer_view,
)


OUT = ROOT / "artifacts/dmc04p"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC01_COMMIT = "48ae98f"
DMC03_COMMIT = "489ec45"
DMC04A_COMMIT = "90a30cb"
DMC01_CHECKPOINT_DIR = ROOT / "artifacts/dmc01/checkpoints"

CONTRACT = r"""# DMC-04P — Factorized Associative Retrieval Preregistration

Status: **STRUCTURAL PREREGISTRATION ONLY; NO EVIDENCE TRAINING**

## Claim under test

The frozen DMC-04A descriptor interface is compatible with a 128-parameter
factorized associative matcher that learns independent atomic write/query
correspondences for A and B. DMC-04P defines the future retrieval experiment;
it does not measure retrieval accuracy or produce a DMC-04 verdict.

## Frozen DMC-04A interface

The raw write descriptor has exactly `tokens` and `attribute_order` fields.
Its order is A,B and its codebooks are `write_A_token_0..7` and
`write_B_token_0..7`. The raw query descriptor has exactly `tokens`,
`attribute_order`, and `noise_token_count`; its order is B,A and its codebooks
are `query_A_token_0..7` and `query_B_token_0..7`. These vocabularies are
disjoint. The benchmark-only logical key is never passed to the matcher.

The matcher input contains only the query descriptor, CURRENT/HISTORY mode,
as_of_episode, each candidate write descriptor, and creation_episode. It does
not receive hidden values, answers, logical keys, record IDs, case IDs, or
oracle decisions. It scores every candidate in the frozen DMC-04A candidate
set, whose capacity remains at most 16.

## Model class

For each atomic attribute:

```text
score = q_A^T W_A w_A + q_B^T W_B w_B
W_A, W_B in R^(8x8)
```

There are exactly 128 trainable parameters, no bias, no MLP, no whole-pair
embedding, no cross-attribute term, and no attention. Each atomic matrix can
represent an arbitrary correspondence between its disjoint query and write
codebooks. The sum distinguishes complete A+B matches from A-only and B-only
matches.

For versioned records, the zero-parameter resolver first selects the highest-
scoring raw descriptor group, then chooses the latest eligible creation
episode for CURRENT or HISTORY. Equal-score ties use ascending SHA-256 of the
raw frozen record ID. Record IDs are resolver metadata, never matcher input.

## Future evidence protocol

Training uses only frozen DMC-04A TRAIN cases, group-level retrieval
cross-entropy, 80 epochs, complete-case batches of 64, AdamW at 1e-2, zero
weight decay, gradient clip 1.0, CPU, and one Torch thread. Ordering is
`SHA256("DMC04_ORDER|" + seed + "|" + epoch + "|" + case_id)` sorted ascending.
Evidence seeds are 1337–1341. No evidence seed is executed in DMC-04P.

The five DMC-01 processors are frozen and paired by seed for the later final
answer path. They are not in the retrieval optimizer. Hidden values are used
only after retrieval by the frozen processor.

Future primary metrics and gates are frozen in `DMC04P_CONFIG.json`; this
preregistration does not report them.

## Terminal states

- `DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED`
- `DMC_04P_MODEL_CLASS_UNRESOLVED`
- `DMC_04P_RETRIEVAL_LEAK`
- `DMC_04P_PROCESSOR_INVALID`
- `DMC_04P_CAPACITY_INVALID`
- `DMC_04P_INVALID`
- `DMC_04P_REPAIR_REQUIRED`

This unit stops after its structural commit. It does not train retrieval,
measure scientific accuracy, integrate DMC-03 retention, or begin DMC-05.
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
    result: dict[str, Any] = {
        "name": name,
        "expected_commit": expected_commit,
        "artifact_path": artifact_path,
        "unchanged_since_expected_commit": diff.returncode == 0,
        "manifest": manifest,
    }
    if terminal is not None:
        receipts = []
        for path_candidate in sorted(path.glob("*RECEIPT.json")) + sorted(path.glob("*VERDICT.json")):
            try:
                data = json.loads(path_candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if "terminal_state" in data:
                receipts.append(data["terminal_state"])
        result["expected_terminal_state"] = terminal
        result["observed_terminal_states"] = receipts
        result["receipt_valid"] = terminal in receipts
    result["pass"] = bool(result["unchanged_since_expected_commit"] and result["manifest"]["pass"] and result.get("receipt_valid", True))
    return result


def predecessor_validation() -> dict[str, Any]:
    world = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    world_run = subprocess.run([sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    world["validator_terminal"] = world_run.stdout.strip().splitlines()[-1] if world_run.stdout.strip() else ""
    world["validator_pass"] = world["validator_terminal"] == "GRI_02_WORLD0_PASS"
    world["pass"] = bool(world["pass"] and world["validator_pass"])
    rows = [
        world,
        predecessor_identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01", "DMC_01_EXACT_MEMORY_ADVANCES"),
        predecessor_identity("DMC-03", DMC03_COMMIT, "artifacts/dmc03", "DMC_03_LEARNED_RETENTION_ADVANCES"),
        predecessor_identity("DMC-04A", DMC04A_COMMIT, "artifacts/dmc04a", "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS"),
    ]
    return {"pass": all(row["pass"] for row in rows), "predecessors": rows}


def load_all_dmc04a_cases() -> list[dict[str, Any]]:
    cases = []
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / "artifacts/dmc04a/datasets" / f"{split}.jsonl"
        cases.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return cases


def validate_frozen_dmc04a(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        neural = case["neural_view"]
        query_descriptor = neural["query"]["query_descriptor"]
        write_descriptors = [memory["write_descriptor"] for memory in neural["memory"]]
        rows.append({
            "case_id": case["case_id"],
            "candidate_count": len(write_descriptors),
            "write_fields": sorted(write_descriptors[0]),
            "query_fields": sorted(query_descriptor),
            "scorer_view_pass": validate_scorer_view(scorer_view(case))["pass"],
            "target_separate": "oracle_view" not in scorer_view(case),
        })
    expected_write = ["attribute_order", "tokens"]
    expected_query = ["attribute_order", "noise_token_count", "tokens"]
    return {
        "pass": all(row["candidate_count"] <= DMC04A_CAPACITY and row["write_fields"] == expected_write and row["query_fields"] == expected_query and row["scorer_view_pass"] and row["target_separate"] for row in rows),
        "case_count": len(rows),
        "expected_write_fields": expected_write,
        "expected_query_fields": expected_query,
        "rows": rows,
    }


def model_class_validation() -> dict[str, Any]:
    model = FactorizedAssociativeMatcher(seed=NON_EVIDENCE_SEED)
    return {
        "pass": tuple((name, list(parameter.shape)) for name, parameter in model.named_parameters()) == (("W_A", [8, 8]), ("W_B", [8, 8])) and trainable_parameter_count(model) == 128,
        "class": "factorized_atomic_bilinear",
        "matrices": {"W_A": [8, 8], "W_B": [8, 8]},
        "bias": False,
        "cross_attribute_term": False,
        "whole_pair_embedding": False,
        "mlp": False,
        "attention": False,
        "trainable_parameter_count": trainable_parameter_count(model),
        "initial_state_sha256": state_hash(model),
        "structural_seed": NON_EVIDENCE_SEED,
    }


def parameter_validation() -> dict[str, Any]:
    model = FactorizedAssociativeMatcher(seed=NON_EVIDENCE_SEED)
    optimizer = build_optimizer(model)
    optimizer_names = tuple(name for group in optimizer.param_groups for parameter in group["params"] for name, candidate in model.named_parameters() if candidate is parameter)
    return {
        "pass": trainable_parameter_count(model) == 128 and optimizer_names == ("W_A", "W_B") and len(optimizer.param_groups) == 1,
        "retriever_parameters": ["W_A", "W_B"],
        "parameter_count": trainable_parameter_count(model),
        "optimizer_parameter_names": list(optimizer_names),
        "optimizer_param_group_count": len(optimizer.param_groups),
        "processor_parameters_in_optimizer": False,
        "memory_parameters_in_optimizer": False,
    }


def processor_validation() -> tuple[dict[str, Any], dict[str, Any]]:
    from dmc01.memory import build_paired_controllers

    before = {}
    after = {}
    rows = []
    for seed in EVIDENCE_SEEDS:
        path = DMC01_CHECKPOINT_DIR / f"exact_seed{seed}_final.pt"
        before_hash = sha256(path)
        before[seed] = before_hash
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model, _ = build_paired_controllers(seed)
        model.load_state_dict(payload["model_state_dict"])
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        after_hash = sha256(path)
        after[seed] = after_hash
        rows.append({"seed": seed, "checkpoint": str(path.relative_to(ROOT)), "before_sha256": before_hash, "after_sha256": after_hash, "file_unchanged": before_hash == after_hash, "trainable_parameters": trainable, "requires_grad_all_false": trainable == 0, "model_type": type(model.processor).__name__})
    manifest = {"pass": all(row["file_unchanged"] and row["requires_grad_all_false"] and row["model_type"] == "ImmutableRelationAnchorReasoner" for row in rows), "rows": rows, "processor_parameters_trainable": 0, "paired_by_seed": {str(seed): f"exact_seed{seed}_final.pt" for seed in EVIDENCE_SEEDS}}
    checkpoint_manifest = {str(seed): {"path": row["checkpoint"], "sha256_before": row["before_sha256"], "sha256_after": row["after_sha256"]} for seed, row in zip(EVIDENCE_SEEDS, rows)}
    return manifest, checkpoint_manifest


def target_manifest(cases: list[dict[str, Any]]) -> dict[str, Any]:
    train = [case for case in cases if case["split"] == "train"]
    rows = []
    for case in train:
        target = target_group(case)
        rows.append({"case_id": case["case_id"], "content_hash": case["content_hash"], "candidate_count": len(case["neural_view"]["memory"]), **target})
    raw = canonical(rows)
    forbidden = {key for key in ("answer", "logical_key", "hidden_value", "oracle_view") if key in raw}
    return {"pass": not forbidden and len(rows) == 128, "split": "train", "case_count": len(rows), "target_type": "retrieval_descriptor_group", "rows": rows, "forbidden_fields_found": sorted(forbidden), "manifest_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def ordering_validation(case_ids: list[str]) -> dict[str, Any]:
    first = training_order(case_ids, seed=NON_EVIDENCE_SEED, epoch=0)
    second = training_order(case_ids, seed=NON_EVIDENCE_SEED, epoch=0)
    last = training_order(case_ids, seed=NON_EVIDENCE_SEED, epoch=TRAINING_EPOCHS - 1)
    return {"pass": first == second and len(first["batches"]) == 2 and first["batches"][-1] and last["epoch"] == 79, "algorithm": "SHA256('DMC04_ORDER|' + str(seed) + '|' + str(epoch) + '|' + case_id), ascending raw digest", "structural_seed": NON_EVIDENCE_SEED, "evidence_seeds_frozen_but_not_executed": list(EVIDENCE_SEEDS), "epochs": [0, TRAINING_EPOCHS - 1], "batch_size": TRAINING_BATCH_SIZE, "replay": {"same": first == second, "epoch0": first, "epoch79": last}}


def resolver_validation(cases: list[dict[str, Any]]) -> dict[str, Any]:
    structural_rows = []
    tie_rows = []
    for case in cases:
        view = scorer_view(case)
        target = target_group(case)
        groups = []
        for indices in []:
            groups.append(indices)
        from dmc04p.matcher import descriptor_groups
        groups = descriptor_groups(view)
        scores = torch.zeros(len(view["candidates"]), dtype=torch.float32)
        scores[groups[target["target_group_index"]]] = 1.0
        resolved = resolver(case, scores)
        tie_scores = torch.zeros_like(scores) if case["neural_view"]["query"]["mode"] == "current" else scores
        tie = resolver(case, tie_scores)
        structural_rows.append({"case_id": case["case_id"], "resolved_target": resolved["selected_record_id"] == case["oracle_view"]["target_record_id"], "selected_group_indices": resolved["selected_group_indices"]})
        tie_rows.append({"case_id": case["case_id"], "same_replay": tie == resolver(case, tie_scores)})
    return {"pass": all(row["resolved_target"] for row in structural_rows) and all(row["same_replay"] for row in tie_rows), "scientific_accuracy_not_measured": True, "resolver_semantics": "select highest associative descriptor group, then latest eligible version", "rows": structural_rows, "tie_replay": tie_rows}


def shuffle_validation(cases: list[dict[str, Any]]) -> dict[str, Any]:
    first = build_shuffle_query_mapping(cases)
    second = build_shuffle_query_mapping(cases)
    return {"pass": first == second and len(first) == len(cases) and all(source != target for source, target in first.items()), "mapping_algorithm": "lexicographically sorted case IDs within (split,family,condition), cyclic next source", "case_count": len(cases), "mapping_sha256": hashlib.sha256(canonical(first).encode()).hexdigest(), "same_replay": first == second, "all_nonidentity": all(source != target for source, target in first.items()), "evaluation_only": True, "retraining": False}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = load_all_dmc04a_cases()
    frozen_dmc04a = validate_frozen_dmc04a(cases)
    model_class = model_class_validation()
    parameters = parameter_validation()
    processor_freeze, processor_manifest = processor_validation()
    targets = target_manifest(cases)
    train_ids = [case["case_id"] for case in cases if case["split"] == "train"]
    ordering = ordering_validation(train_ids)
    resolver = resolver_validation(cases)
    shuffle = shuffle_validation(cases)
    predecessors = predecessor_validation()
    dmc04a_identity = predecessors["predecessors"][-1]

    retrieval_firewall = {
        "pass": frozen_dmc04a["pass"],
        "scorer_input_fields": ["query.query_descriptor", "query.mode", "query.as_of_episode", "candidates[].write_descriptor", "candidates[].creation_episode"],
        "forbidden_fields": ["logical_key", "correct_candidate_index", "answer", "answer_class", "hidden_value", "final_correctness", "oracle_retrieval_decision", "case_id", "record_id", "future_event_information", "entity", "field"],
        "case_count": len(cases),
        "hidden_value_in_scorer": False,
        "logical_key_in_scorer": False,
        "answer_in_scorer": False,
        "oracle_decision_in_scorer": False,
    }
    target_firewall = {
        "pass": targets["pass"],
        "target_supervision_separate_from_scorer": True,
        "target_type": "retrieval candidate/group only",
        "answer_target": False,
        "hidden_reconstruction_target": False,
        "retention_target": False,
        "rows": targets["rows"],
    }
    version_spec = {
        "pass": resolver["pass"],
        "learned_matcher_temporal_parameters": 0,
        "group_selection": "highest factorized score among raw write descriptors",
        "current": "latest creation_episode within selected descriptor group",
        "history": "latest creation_episode <= as_of_episode within selected descriptor group",
        "allowed_fields": ["raw write descriptor equality", "creation_episode", "query mode", "as_of_episode"],
        "forbidden_fields": ["logical_key", "answer", "hidden_value", "oracle decision"],
        "structural_validation": {"scientific_accuracy_not_measured": True, "resolver_replay_pass": resolver["pass"]},
    }
    tie_spec = {
        "pass": resolver["pass"],
        "group_tie_break": "ascending SHA256(raw oracle record_id), external zero-parameter resolver metadata",
        "version_tie_break": "ascending SHA256(raw oracle record_id) after descending creation_episode",
        "scorer_visibility_of_record_id": False,
        "deterministic_replay": resolver["pass"],
    }
    ablation_spec = {
        "pass": model_class["pass"],
        "full": "q_A^T W_A w_A + q_B^T W_B w_B",
        "A_ONLY_LEARNED": "q_A^T W_A w_A",
        "B_ONLY_LEARNED": "q_B^T W_B w_B",
        "trained_parameters_unchanged": True,
        "scientific_ablation_accuracy_not_measured": True,
    }

    write_json(OUT / "DMC04P_CONFIG.json", {
        "unit": "DMC-04P",
        "status": "factorized_associative_retrieval_structural_preregistration",
        "generation_commit": git_commit(),
        "dmc04a_commit": DMC04A_COMMIT,
        "dmc03_commit": DMC03_COMMIT,
        "model_class": "factorized_atomic_bilinear",
        "model_parameters": 128,
        "codebook_atom_count": ATOM_SIZE,
        "capacity": DMC04A_CAPACITY,
        "training": {"epochs": TRAINING_EPOCHS, "batch_size": TRAINING_BATCH_SIZE, "optimizer": "AdamW", "learning_rate": TRAINING_LR, "weight_decay": TRAINING_WEIGHT_DECAY, "gradient_clip": TRAINING_GRAD_CLIP, "device": "cpu", "torch_threads": 1, "train_split_only": True, "group_level_cross_entropy": True},
        "evidence_seeds": list(EVIDENCE_SEEDS),
        "evidence_training_executed": False,
        "non_evidence_structural_seed": NON_EVIDENCE_SEED,
        "future_primary_retrieval": "mean(ALIAS16_H1,COMP16_H1,HARD16_H1,CURRENT16_H1,HISTORY16_H1,NOISE8_H1,NOISE32_H1)",
        "future_primary_answer": "mean(ALIAS16_A,COMP16_A,HARD16_A,CURRENT16_A,HISTORY16_A,NOISE8_A,NOISE32_A)",
        "future_gates": {"A_P_retrieval": 0.90, "B_P_answer": 0.90, "C_oracle_gap_max": 0.10, "D_composition": 0.90, "E_hard_negatives": 0.90, "F_current": 0.90, "G_history": 0.90, "H_noise32": 0.90, "I_seed_consistency": {"threshold": 0.85, "seeds": 5}, "J_random_separation": 0.60, "K_exact_token_separation": 0.60, "two_attribute_A_only_gap": 0.30, "two_attribute_B_only_gap": 0.30, "query_cue_shuffle_gap": 0.40},
        "no_dmc03_integration": True,
        "no_scientific_accuracy_reported": True,
    })
    (OUT / "DMC04P_CONTRACT.md").write_text(CONTRACT, encoding="utf-8")
    write_json(OUT / "descriptor_spec.json", {"source": "artifacts/dmc04a/codebook_spec.json", "write_descriptor_fields": ["tokens", "attribute_order"], "write_attribute_order": ["A", "B"], "query_descriptor_fields": ["tokens", "attribute_order", "noise_token_count"], "query_attribute_order": ["B", "A"], "candidate_fields_authorized": ["write_descriptor", "creation_episode"], "query_fields_authorized": ["query_descriptor", "mode", "as_of_episode"], "logical_key_excluded": True, "hidden_value_excluded": True, "raw_structure_validation": frozen_dmc04a})
    write_json(OUT / "vocabulary_spec.json", {"codebooks": {key: list(value) for key, value in CODEBOOKS.items()}, "local_ordering": "numeric suffix 0 through 7", "write_query_disjoint": True, "dimensions": {key: len(value) for key, value in CODEBOOKS.items()}})
    write_json(OUT / "model_class.json", model_class)
    write_json(OUT / "parameter_identity.json", parameters)
    write_json(OUT / "model_class_proof.json", {"pass": model_class["pass"], "statement": "Independent full 8x8 matrices represent arbitrary atomic codebook correspondences; their sum distinguishes full A+B matches from A-only/B-only matches.", "formula": "q_A^T W_A w_A + q_B^T W_B w_B", "matrices": {"W_A": [8, 8], "W_B": [8, 8]}, "cross_attribute_interaction": False, "fit_performed": False})
    write_json(OUT / "training_example_manifest.json", targets)
    write_json(OUT / "training_order_spec.json", ordering)
    write_json(OUT / "target_firewall.json", target_firewall)
    write_json(OUT / "retrieval_firewall.json", retrieval_firewall)
    write_json(OUT / "version_resolver.json", version_spec)
    write_json(OUT / "tie_break_spec.json", tie_spec)
    write_json(OUT / "ablation_spec.json", ablation_spec)
    write_json(OUT / "shuffle_query_control.json", shuffle)
    write_json(OUT / "processor_freeze.json", processor_freeze)
    write_json(OUT / "processor_checkpoint_manifest.json", processor_manifest)
    write_json(OUT / "dmc04a_identity.json", dmc04a_identity)
    write_json(OUT / "dmc03_identity.json", predecessors["predecessors"][2])
    write_json(OUT / "dmc01_identity.json", predecessors["predecessors"][1])
    write_json(OUT / "world0_identity.json", predecessors["predecessors"][0])

    checks = {
        "dmc04a_structure": frozen_dmc04a["pass"],
        "model_class": model_class["pass"],
        "parameter_identity": parameters["pass"],
        "target_firewall": target_firewall["pass"],
        "retrieval_firewall": retrieval_firewall["pass"],
        "processor_freeze": processor_freeze["pass"],
        "capacity": frozen_dmc04a["pass"],
        "version_resolver": version_spec["pass"],
        "tie_break": tie_spec["pass"],
        "ordering": ordering["pass"],
        "shuffle_control": shuffle["pass"],
        "predecessors": predecessors["pass"],
        "no_evidence_training": True,
    }
    if not checks["dmc04a_structure"] or not checks["model_class"]:
        terminal = "DMC_04P_MODEL_CLASS_UNRESOLVED"
    elif not checks["retrieval_firewall"] or not checks["target_firewall"]:
        terminal = "DMC_04P_RETRIEVAL_LEAK"
    elif not checks["processor_freeze"]:
        terminal = "DMC_04P_PROCESSOR_INVALID"
    elif not checks["capacity"]:
        terminal = "DMC_04P_CAPACITY_INVALID"
    elif not checks["predecessors"]:
        terminal = "DMC_04P_INVALID"
    elif all(checks.values()):
        terminal = "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED"
    else:
        terminal = "DMC_04P_REPAIR_REQUIRED"
    write_json(OUT / "DMC04P_RECEIPT.json", {"unit": "DMC-04P", "terminal_state": terminal, "checks": checks, "evidence_seeds": list(EVIDENCE_SEEDS), "evidence_training_executed": False, "scientific_retrieval_accuracy_measured": False, "dmc03_integration_executed": False})
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 0 if terminal == "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
