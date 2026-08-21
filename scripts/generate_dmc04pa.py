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

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import build_paired_controllers  # noqa: E402
from dmc04a.benchmark import (  # noqa: E402
    DMC01_CHECKPOINT,
    DMC01_CHECKPOINT_SHA256,
    oracle_retrieval,
    validate_case,
)
from dmc04p.matcher import (  # noqa: E402
    EVIDENCE_SEEDS,
    NON_EVIDENCE_SEED,
    FactorizedAssociativeMatcher,
    build_optimizer,
    trainable_parameter_count,
)


OUT = ROOT / "artifacts/dmc04pa"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC01_COMMIT = "48ae98f"
DMC03_COMMIT = "489ec45"
DMC04A_COMMIT = "90a30cb"
DMC04P_COMMIT = "61c9ab9"
DMC04_INVALID_COMMIT = "d6c9bb5"
DMC04A_TERMINAL = "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS"
DMC04P_TERMINAL = "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED"
DMC04_INVALID_TERMINAL = "DMC_04_INVALID"
CHECKPOINT_PATH = ROOT / DMC01_CHECKPOINT


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_diff_clean(commit: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "diff", "--exit-code", commit, "--", path],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode == 0


def manifest_for(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path)
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
    for relative, digest in expected.items():
        path = root / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif actual.get(relative) != digest:
            errors.append(f"hash:{relative}")
    errors.extend(f"unexpected:{relative}" for relative in sorted(set(actual) - set(expected)))
    return {"pass": not errors, "manifest_available": True, "entries": len(expected), "errors": errors}


def receipt_terminals(root: Path) -> list[str]:
    terminals: list[str] = []
    for path in sorted(root.glob("*RECEIPT.json")) + sorted(root.glob("*PREFLIGHT.json")) + sorted(root.glob("*VERDICT.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload.get("terminal_state"), str):
            terminals.append(payload["terminal_state"])
    return terminals


def predecessor_identity(name: str, commit: str, artifact_path: str, terminal: str | None = None) -> dict[str, Any]:
    root = ROOT / artifact_path
    manifest = verify_manifest(root)
    if name == "WORLD-0" and not manifest["manifest_available"]:
        manifest = {"pass": True, "manifest_available": False, "entries": 0, "errors": [], "verification_basis": "frozen_git_commit_boundary"}
    result: dict[str, Any] = {
        "name": name,
        "expected_commit": commit,
        "artifact_path": artifact_path,
        "unchanged_since_expected_commit": git_diff_clean(commit, artifact_path),
        "manifest": manifest,
    }
    if terminal is not None:
        observed = receipt_terminals(root)
        result.update({"expected_terminal_state": terminal, "observed_terminal_states": observed, "receipt_valid": terminal in observed})
    result["pass"] = bool(result["unchanged_since_expected_commit"] and manifest["pass"] and result.get("receipt_valid", True))
    return result


def world0_identity() -> dict[str, Any]:
    identity = predecessor_identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    run = subprocess.run(
        [sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines = run.stdout.strip().splitlines()
    terminal = lines[-1] if lines else ""
    identity.update({"validator_command": "python3 scripts/validate_world0.py artifacts/frozen/world0_v0_1", "validator_terminal": terminal, "validator_pass": terminal == "GRI_02_WORLD0_PASS"})
    identity["pass"] = bool(identity["pass"] and identity["validator_pass"] and run.returncode == 0)
    return identity


def load_cases() -> dict[str, list[dict[str, Any]]]:
    dataset: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "iid", "extrapolation"):
        path = ROOT / "artifacts/dmc04a/datasets" / f"{split}.jsonl"
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        for case in cases:
            validate_case(case)
        dataset[split] = cases
    return dataset


def load_fixed_decoder() -> tuple[torch.nn.Module, dict[str, Any]]:
    before = sha256(CHECKPOINT_PATH)
    if before != DMC01_CHECKPOINT_SHA256:
        raise RuntimeError("native seed-1337 checkpoint hash mismatch")
    payload = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    if int(payload["seed"]) != 1337:
        raise RuntimeError("native decoder checkpoint is not seed 1337")
    model, _ = build_paired_controllers(1337)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model, {"before_sha256": before, "payload_seed": int(payload["seed"]), "after_sha256": sha256(CHECKPOINT_PATH)}


def query_event(case: dict[str, Any]) -> dict[str, Any]:
    query = case["neural_view"]["query"]
    return {
        "kind": "query",
        "entity": "opaque",
        "field": "value",
        "mode": query["mode"],
        "as_of_episode": query["as_of_episode"],
    }


def hidden_vector_compatibility(dataset: dict[str, list[dict[str, Any]]], decoder: torch.nn.Module) -> dict[str, Any]:
    rows = []
    failures: list[dict[str, Any]] = []
    total = 0
    correct = 0
    with torch.no_grad():
        for split, cases in dataset.items():
            split_total = 0
            split_correct = 0
            for case in cases:
                records = case["oracle_view"]["records"]
                for index, (memory, record) in enumerate(zip(case["neural_view"]["memory"], records)):
                    total += 1
                    split_total += 1
                    vector = torch.tensor(memory["hidden_value"], dtype=torch.float32)
                    logits = decoder.answer_query_with_hidden(query_event(case), vector)
                    predicted = VALUES[int(torch.argmax(logits).item())]
                    hit = predicted == record["answer"]
                    correct += int(hit)
                    split_correct += int(hit)
                    if not hit:
                        failures.append({"split": split, "case_id": case["case_id"], "record_id": record["record_id"], "memory_index": index, "expected": record["answer"], "predicted": predicted})
            rows.append({"split": split, "hidden_vectors_checked": split_total, "correctly_decoded": split_correct, "incorrectly_decoded": split_total - split_correct, "accuracy": split_correct / split_total})
    return {
        "pass": total > 0 and correct == total and not failures,
        "processor": "DMC-01 exact seed 1337",
        "checkpoint": DMC01_CHECKPOINT,
        "checkpoint_sha256": DMC01_CHECKPOINT_SHA256,
        "total_hidden_vectors_checked": total,
        "correctly_decoded": correct,
        "incorrectly_decoded": total - correct,
        "accuracy": correct / total if total else 0.0,
        "rows": rows,
        "failures": failures,
    }


def oracle_end_to_end(dataset: dict[str, list[dict[str, Any]]], decoder: torch.nn.Module) -> dict[str, Any]:
    rows = []
    with torch.no_grad():
        for split, cases in dataset.items():
            retrieval_hits = 0
            answer_hits = 0
            for case in cases:
                target_id = oracle_retrieval(case)
                records = case["oracle_view"]["records"]
                selected_index = next(index for index, record in enumerate(records) if record["record_id"] == target_id)
                record = records[selected_index]
                hidden = torch.tensor(case["neural_view"]["memory"][selected_index]["hidden_value"], dtype=torch.float32)
                logits = decoder.answer_query_with_hidden(query_event(case), hidden)
                predicted = VALUES[int(torch.argmax(logits).item())]
                retrieval_hits += int(target_id == case["oracle_view"]["target_record_id"])
                answer_hits += int(predicted == record["answer"] == case["oracle_view"]["answer"])
            rows.append({"split": split, "case_count": len(cases), "retrieval_hit_at_1": retrieval_hits / len(cases), "final_answer_accuracy": answer_hits / len(cases)})
    return {"pass": all(row["retrieval_hit_at_1"] == 1.0 and row["final_answer_accuracy"] == 1.0 for row in rows), "rows": rows, "scientific_learned_retrieval_not_measured": True}


def fixed_decoder_identity(checkpoint_info: dict[str, Any], decoder: torch.nn.Module) -> dict[str, Any]:
    trainable = trainable_parameter_count(decoder)
    all_frozen = all(not parameter.requires_grad for parameter in decoder.parameters())
    mapping = {str(seed): {"decoder_seed": 1337, "checkpoint": DMC01_CHECKPOINT, "checkpoint_sha256": DMC01_CHECKPOINT_SHA256} for seed in EVIDENCE_SEEDS}
    return {
        "pass": checkpoint_info["before_sha256"] == DMC01_CHECKPOINT_SHA256 and checkpoint_info["after_sha256"] == DMC01_CHECKPOINT_SHA256 and checkpoint_info["before_sha256"] == checkpoint_info["after_sha256"] and checkpoint_info["payload_seed"] == 1337 and trainable == 0 and all_frozen,
        "retrieval_seed_to_decoder": mapping,
        "single_decoder_seed": 1337,
        "checkpoint": DMC01_CHECKPOINT,
        "checkpoint_sha256_before": checkpoint_info["before_sha256"],
        "checkpoint_sha256_after": checkpoint_info["after_sha256"],
        "processor_parameters_trainable": trainable,
        "all_parameters_requires_grad_false": all_frozen,
    }


def retriever_identity() -> dict[str, Any]:
    model = FactorizedAssociativeMatcher(seed=NON_EVIDENCE_SEED)
    optimizer = build_optimizer(model)
    names = tuple(name for group in optimizer.param_groups for parameter in group["params"] for name, candidate in model.named_parameters() if parameter is candidate)
    shapes = {name: list(parameter.shape) for name, parameter in model.named_parameters()}
    return {
        "pass": type(model).__name__ == "FactorizedAssociativeMatcher" and shapes == {"W_A": [8, 8], "W_B": [8, 8]} and trainable_parameter_count(model) == 128 and names == ("W_A", "W_B"),
        "model_class": "factorized_atomic_bilinear",
        "matrices": shapes,
        "trainable_parameter_count": trainable_parameter_count(model),
        "optimizer_parameter_names": list(names),
        "optimizer_parameter_group_count": len(optimizer.param_groups),
        "processor_parameters_in_optimizer": False,
        "memory_parameters_in_optimizer": False,
        "structural_seed": NON_EVIDENCE_SEED,
        "evidence_seeds_consumed": [],
    }


def evidence_seed_semantics() -> dict[str, Any]:
    return {
        "pass": True,
        "retrieval_evidence_seeds": list(EVIDENCE_SEEDS),
        "seed_controls": ["W_A/W_B initialization", "frozen stateless training order", "retrieval optimizer trajectory"],
        "seed_does_not_select_decoder": True,
        "all_decoder_seed": 1337,
        "evidence_training_executed": False,
        "evidence_seeds_executed": [],
        "non_evidence_structural_seed": NON_EVIDENCE_SEED,
    }


def supersession_record() -> dict[str, Any]:
    return {
        "pass": True,
        "amendment": "DMC-04P-A",
        "superseded_only": "DMC-04P clause requiring retrieval evidence seed N to use DMC-01 processor checkpoint N",
        "replacement": "all retrieval evidence seeds use frozen DMC-01 seed-1337 processor",
        "unchanged_requirements": [
            "DMC-04A candidate sets and hidden vectors",
            "factorized matcher W_A/W_B, 128 trainable parameters",
            "retrieval evidence seeds 1337-1341",
            "80 epochs, batch size 64, AdamW lr 1e-2, weight decay 0, clip 1.0",
            "CPU and Torch threads 1",
            "stateless SHA-256 training order",
            "primary retrieval and answer metrics",
            "all DMC-04P gates and ablations",
        ],
        "regenerate_hidden_vectors": False,
        "learn_alignment": False,
        "dmc03_integration": False,
    }


def main() -> int:
    torch.set_num_threads(1)
    dataset = load_cases()
    world = world0_identity()
    predecessors = {
        "DMC-01": predecessor_identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01", "DMC_01_EXACT_MEMORY_ADVANCES"),
        "DMC-03": predecessor_identity("DMC-03", DMC03_COMMIT, "artifacts/dmc03", "DMC_03_LEARNED_RETENTION_ADVANCES"),
        "DMC-04A": predecessor_identity("DMC-04A", DMC04A_COMMIT, "artifacts/dmc04a", DMC04A_TERMINAL),
        "DMC-04P": predecessor_identity("DMC-04P", DMC04P_COMMIT, "artifacts/dmc04p", DMC04P_TERMINAL),
        "DMC-04 invalid preflight": predecessor_identity("DMC-04 invalid preflight", DMC04_INVALID_COMMIT, "artifacts/dmc04", DMC04_INVALID_TERMINAL),
    }
    predecessor_pass = all(row["pass"] for row in predecessors.values())
    decoder, checkpoint_info = load_fixed_decoder()
    freeze = fixed_decoder_identity(checkpoint_info, decoder)
    compatibility = hidden_vector_compatibility(dataset, decoder)
    oracle = oracle_end_to_end(dataset, decoder)
    retriever = retriever_identity()
    seeds = evidence_seed_semantics()
    supersession = supersession_record()
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    full_tests = {"command": "python3 -m pytest -q", "pass": tests.returncode == 0, "returncode": tests.returncode, "last_output": tests.stdout[-2000:]}
    world_payload = {"pass": world["pass"], "expected_commit": WORLD0_COMMIT, "validator_terminal": world["validator_terminal"], "validator_pass": world["validator_pass"], "unchanged_since_expected_commit": world["unchanged_since_expected_commit"]}
    invalid_identity = predecessors["DMC-04 invalid preflight"]
    dmc04a_identity = predecessors["DMC-04A"]
    dmc04p_identity = predecessors["DMC-04P"]

    checks = {
        "world0_identity": world["pass"],
        "predecessor_identity": predecessor_pass,
        "original_dmc04a_identity": dmc04a_identity["pass"],
        "original_dmc04p_identity": dmc04p_identity["pass"],
        "original_invalid_preflight_identity": invalid_identity["pass"],
        "fixed_decoder_identity": freeze["pass"],
        "processor_freeze": freeze["pass"],
        "all_hidden_vector_compatibility": compatibility["pass"],
        "oracle_end_to_end_validation": oracle["pass"],
        "retriever_identity": retriever["pass"],
        "evidence_seed_semantics": seeds["pass"],
        "supersession_record": supersession["pass"],
        "full_tests": full_tests["pass"],
        "evidence_training_not_executed": seeds["evidence_training_executed"] is False and not seeds["evidence_seeds_executed"],
    }
    if not dmc04a_identity["pass"]:
        terminal = "DMC_04PA_BENCHMARK_INVALID"
    elif not dmc04p_identity["pass"] or not retriever["pass"]:
        terminal = "DMC_04PA_RETRIEVER_INVALID"
    elif not invalid_identity["pass"] or not predecessor_pass or not world["pass"]:
        terminal = "DMC_04PA_INVALID"
    elif not freeze["pass"] or not compatibility["pass"] or not oracle["pass"]:
        terminal = "DMC_04PA_DECODER_INVALID"
    elif seeds["evidence_seeds_executed"] or seeds["evidence_training_executed"]:
        terminal = "DMC_04PA_EVIDENCE_INVALID"
    elif all(checks.values()):
        terminal = "DMC_04PA_FIXED_DECODER_PREREGISTERED"
    else:
        terminal = "DMC_04PA_REPAIR_REQUIRED"

    contract = """# DMC-04P-A — Fixed Decoder Interface Amendment\n\nStatus: **STRUCTURAL PREREGISTRATION ONLY; NO EVIDENCE TRAINING**\n\nDMC-04A hidden memory vectors are frozen seed-1337 DMC-01 representations.\nDMC-04P-A fixes the downstream decoder to that native seed-1337 processor for\nall five future retrieval seeds. It supersedes only the original processor\npairing clause; it does not regenerate vectors, align latent spaces, change\nthe retriever, or change any metric, gate, optimizer, or evidence seed.\n\n## Fixed interface\n\n```text\nretrieval seed 1337 ─┐\nretrieval seed 1338 ─┤\nretrieval seed 1339 ─┼─> frozen DMC-01 exact seed-1337 decoder\nretrieval seed 1340 ─┤\nretrieval seed 1341 ─┘\n```\n\nThe decoder checkpoint is `artifacts/dmc01/checkpoints/exact_seed1337_final.pt`\nwith SHA-256 `4d7dd38a53216b6c010fbfbea27c5e382b572ba229db7fadaf9dd125c99b35a6`.\nIt is frozen, has zero trainable parameters, and is the only decoder loaded.\n\n## Structural gates\n\nEvery stored hidden vector in DMC-04A train, IID, and extrapolation datasets\nmust decode to its oracle answer through the fixed processor. The symbolic\noracle must achieve retrieval Hit@1 and final-answer accuracy of 1.0 on every\nsplit. The matcher remains the exact 128-parameter factorized model with\n`W_A: 8x8` and `W_B: 8x8`; only those parameters may enter a future optimizer.\n\nThe future DMC-04 protocol remains unchanged: 80 epochs, batch size 64,\nAdamW, learning rate `1e-2`, weight decay `0`, gradient clip `1.0`, CPU with\nTorch threads `1`, stateless SHA-256 ordering, seeds `1337..1341`, and all\noriginal retrieval/answer metrics and gates. No evidence training is executed\nin this amendment.\n\n## Terminal states\n\n- `DMC_04PA_FIXED_DECODER_PREREGISTERED`\n- `DMC_04PA_DECODER_INVALID`\n- `DMC_04PA_BENCHMARK_INVALID`\n- `DMC_04PA_RETRIEVER_INVALID`\n- `DMC_04PA_EVIDENCE_INVALID`\n- `DMC_04PA_INVALID`\n- `DMC_04PA_REPAIR_REQUIRED`\n\nThe original `DMC_04_INVALID` result remains preserved as the correct terminal\nstate of the superseded DMC-04 protocol.\n"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "DMC04PA_CONTRACT.md").write_text(contract, encoding="utf-8")
    write_json(OUT / "DMC04PA_CONFIG.json", {
        "unit": "DMC-04P-A",
        "status": "fixed_decoder_interface_structural_preregistration",
        "terminal_state": terminal,
        "original_invalid_preflight_commit": DMC04_INVALID_COMMIT,
        "fixed_decoder": {"seed": 1337, "checkpoint": DMC01_CHECKPOINT, "checkpoint_sha256": DMC01_CHECKPOINT_SHA256, "trainable_parameters": 0},
        "retriever": {"model_class": "factorized_atomic_bilinear", "W_A": [8, 8], "W_B": [8, 8], "trainable_parameters": 128},
        "evidence_seeds": list(EVIDENCE_SEEDS),
        "future_primary_retrieval": "mean(ALIAS16_H1,COMP16_H1,HARD16_H1,CURRENT16_H1,HISTORY16_H1,NOISE8_H1,NOISE32_H1)",
        "future_primary_answer": "mean(ALIAS16_A,COMP16_A,HARD16_A,CURRENT16_A,HISTORY16_A,NOISE8_A,NOISE32_A)",
        "training_unchanged": {"epochs": 80, "batch_size": 64, "optimizer": "AdamW", "learning_rate": 0.01, "weight_decay": 0.0, "gradient_clip": 1.0, "device": "cpu", "torch_threads": 1, "no_early_stopping": True, "no_scheduler": True},
        "training_executed": False,
        "scientific_accuracy_measured": False,
    })
    write_json(OUT / "invalid_preflight_identity.json", invalid_identity)
    write_json(OUT / "fixed_decoder_identity.json", freeze)
    write_json(OUT / "all_hidden_vector_compatibility.json", compatibility)
    write_json(OUT / "oracle_end_to_end_validation.json", oracle)
    write_json(OUT / "processor_freeze.json", freeze)
    write_json(OUT / "retriever_identity.json", retriever)
    write_json(OUT / "evidence_seed_semantics.json", seeds)
    write_json(OUT / "supersession_record.json", supersession)
    write_json(OUT / "predecessor_identity.json", {"pass": predecessor_pass, "rows": predecessors})
    write_json(OUT / "world0_identity.json", world_payload)
    receipt = {"unit": "DMC-04P-A", "terminal_state": terminal, "checks": checks, "evidence_seeds": list(EVIDENCE_SEEDS), "evidence_seeds_executed": [], "evidence_training_executed": False, "scientific_retrieval_accuracy_measured": False, "dmc03_integration_executed": False, "cross_seed_latent_alignment_not_established": True, "fixed_decoder_seed": 1337, "total_hidden_vectors_checked": compatibility["total_hidden_vectors_checked"], "all_hidden_vector_accuracy": compatibility["accuracy"], "full_tests": full_tests}
    write_json(OUT / "DMC04PA_RECEIPT.json", receipt)
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 0 if terminal == "DMC_04PA_FIXED_DECODER_PREREGISTERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
