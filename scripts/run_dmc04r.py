from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402

from dmc00.benchmark import VALUES  # noqa: E402
from dmc01.memory import build_paired_controllers  # noqa: E402
from dmc04a.benchmark import (  # noqa: E402
    DMC01_CHECKPOINT,
    DMC01_CHECKPOINT_SHA256,
    exact_token_retrieval,
    oracle_retrieval,
    random_retrieval,
)
from dmc04p.matcher import (  # noqa: E402
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
    descriptor_groups,
    encode_query_descriptor,
    encode_write_descriptor,
    order_case_ids,
    resolver,
    scorer_view,
    state_hash,
    target_group,
    trainable_parameter_count,
    validate_scorer_view,
)
from generate_dmc04pa import (  # noqa: E402
    hidden_vector_compatibility,
    load_cases,
    load_fixed_decoder,
    oracle_end_to_end,
)


CORRECTED_EVALUATOR = os.environ.get("DMC04R_CORRECTED_EVALUATOR") == "1"
OUT = ROOT / ("artifacts/dmc04r2" if CORRECTED_EVALUATOR else "artifacts/dmc04r")
ARTIFACT_PREFIX = "DMC04R2" if CORRECTED_EVALUATOR else "DMC04R"
UNIT = "DMC-04R2" if CORRECTED_EVALUATOR else "DMC-04R"
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC01_COMMIT = "48ae98f"
DMC03_COMMIT = "489ec45"
DMC04A_COMMIT = "90a30cb"
DMC04P_COMMIT = "61c9ab9"
DMC04_INVALID_COMMIT = "d6c9bb5"
DMC04PA_COMMIT = "c98e0a0"
DMC04A_TERMINAL = "DMC_04A_ASSOCIATIVE_RETRIEVAL_BENCHMARK_PASS"
DMC04P_TERMINAL = "DMC_04P_LEARNED_RETRIEVAL_PREREGISTERED"
DMC04_INVALID_TERMINAL = "DMC_04_INVALID"
DMC04PA_TERMINAL = "DMC_04PA_FIXED_DECODER_PREREGISTERED"
FIELD = "value"
PRIMARY_COMPONENTS = (
    ("ALIAS16", "alias", "candidate_16"),
    ("COMP16", "compositional", "candidate_16"),
    ("HARD16", "hard_negative", "candidate_16"),
    ("CURRENT16", "versioned", "current_candidate_16"),
    ("HISTORY16", "versioned", "history_candidate_16"),
    ("NOISE8", "cue_noise", "noise_8"),
    ("NOISE32", "cue_noise", "noise_32"),
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    payload = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


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
    for relative, expected_hash in expected.items():
        path = root / relative
        if not path.exists():
            errors.append(f"missing:{relative}")
        elif actual.get(relative) != expected_hash:
            errors.append(f"hash:{relative}")
    errors.extend(f"unexpected:{relative}" for relative in sorted(set(actual) - set(expected)))
    return {"pass": not errors, "manifest_available": True, "entries": len(expected), "errors": errors}


def receipt_terminals(root: Path) -> list[str]:
    terminals = []
    for path in sorted(root.glob("*RECEIPT.json")) + sorted(root.glob("*VERDICT.json")) + sorted(root.glob("*PREFLIGHT.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload.get("terminal_state"), str):
            terminals.append(payload["terminal_state"])
    return terminals


def identity(name: str, commit: str, artifact_path: str, terminal: str | None = None) -> dict[str, Any]:
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
    result = identity("WORLD-0", WORLD0_COMMIT, "artifacts/frozen/world0_v0_1")
    run = subprocess.run(
        [sys.executable, "scripts/validate_world0.py", "artifacts/frozen/world0_v0_1"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines = run.stdout.strip().splitlines()
    terminal = lines[-1] if lines else ""
    result.update({"validator_command": "python3 scripts/validate_world0.py artifacts/frozen/world0_v0_1", "validator_terminal": terminal, "validator_pass": terminal == "GRI_02_WORLD0_PASS"})
    result["pass"] = bool(result["pass"] and result["validator_pass"] and run.returncode == 0)
    return result


def run_tests() -> dict[str, Any]:
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {"command": "python3 -m pytest -q", "pass": result.returncode == 0, "returncode": result.returncode, "last_output": result.stdout[-3000:]}


def training_manifest_identity(train_cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in train_cases:
        target = target_group(case)
        rows.append({"case_id": case["case_id"], "content_hash": case["content_hash"], "candidate_count": len(case["neural_view"]["memory"]), **target})
    raw = canonical(rows)
    frozen = json.loads((ROOT / "artifacts/dmc04p/training_example_manifest.json").read_text(encoding="utf-8"))
    train_bytes_hash = sha256(ROOT / "artifacts/dmc04a/datasets/train.jsonl")
    return {
        "pass": len(rows) == 128 and frozen["pass"] and frozen["manifest_sha256"] == digest(raw) and frozen["rows"] == rows,
        "split": "train",
        "case_count": len(rows),
        "frozen_manifest_sha256": frozen["manifest_sha256"],
        "observed_manifest_sha256": digest(raw),
        "train_dataset_jsonl_sha256": train_bytes_hash,
        "target_type": "retrieval_descriptor_group",
        "train_only": True,
        "non_train_cases_used_for_training": 0,
    }


def capacity_audit(cases: list[dict[str, Any]]) -> dict[str, Any]:
    violations = []
    maximum = 0
    for case in cases:
        count = len(case["neural_view"]["memory"])
        maximum = max(maximum, count)
        if count < 1 or count > 16:
            violations.append({"case_id": case["case_id"], "candidate_count": count})
    return {"pass": not violations and maximum <= 16, "case_count": len(cases), "max_candidate_count": maximum, "violations": violations, "all_candidates_scored": True}


def dmc04p_protocol_identity() -> dict[str, Any]:
    config = json.loads((ROOT / "artifacts/dmc04p/DMC04P_CONFIG.json").read_text(encoding="utf-8"))
    receipt = json.loads((ROOT / "artifacts/dmc04p/DMC04P_RECEIPT.json").read_text(encoding="utf-8"))
    checks = {
        "model_class": config.get("model_class") == "factorized_atomic_bilinear",
        "model_parameters": config.get("model_parameters") == 128,
        "evidence_seeds": config.get("evidence_seeds") == list(EVIDENCE_SEEDS),
        "training": config.get("training") == {"batch_size": 64, "device": "cpu", "epochs": 80, "gradient_clip": 1.0, "group_level_cross_entropy": True, "learning_rate": 0.01, "optimizer": "AdamW", "torch_threads": 1, "train_split_only": True, "weight_decay": 0.0},
        "no_evidence_training": config.get("evidence_training_executed") is False and receipt.get("evidence_training_executed") is False,
        "terminal": receipt.get("terminal_state") == DMC04P_TERMINAL,
    }
    return {"pass": all(checks.values()) and identity("DMC-04P", DMC04P_COMMIT, "artifacts/dmc04p", DMC04P_TERMINAL)["pass"], "checks": checks, "config_sha256": sha256(ROOT / "artifacts/dmc04p/DMC04P_CONFIG.json"), "receipt_sha256": sha256(ROOT / "artifacts/dmc04p/DMC04P_RECEIPT.json")}


def runtime_firewall() -> dict[str, Any]:
    return {"calls": 0, "candidate_count_max": 0, "forbidden_fields_union": [], "query_fields_observed": [], "candidate_fields_observed": [], "hidden_value_in_actual_scorer": False, "answer_in_actual_scorer": False, "logical_key_in_actual_scorer": False, "record_id_in_actual_scorer": False, "all_candidates_scored": True}


def audit_scorer_input(view: dict[str, Any], audit: dict[str, Any]) -> None:
    validation = validate_scorer_view(view)
    forbidden = validation["forbidden_fields"]
    audit["calls"] += 1
    audit["candidate_count_max"] = max(audit["candidate_count_max"], len(view["candidates"]))
    audit["forbidden_fields_union"] = sorted(set(audit["forbidden_fields_union"]).union(forbidden))
    audit["query_fields_observed"] = sorted(set(audit["query_fields_observed"]).union(view["query"].keys()))
    candidate_fields = set(audit["candidate_fields_observed"])
    for candidate in view["candidates"]:
        candidate_fields.update(candidate.keys())
    audit["candidate_fields_observed"] = sorted(candidate_fields)
    audit["hidden_value_in_actual_scorer"] = audit["hidden_value_in_actual_scorer"] or "hidden_value" in canonical(view)
    audit["answer_in_actual_scorer"] = audit["answer_in_actual_scorer"] or "answer" in canonical(view)
    audit["logical_key_in_actual_scorer"] = audit["logical_key_in_actual_scorer"] or "logical_key" in canonical(view)
    audit["record_id_in_actual_scorer"] = audit["record_id_in_actual_scorer"] or "record_id" in canonical(view)


def score_variant(model: FactorizedAssociativeMatcher, case: dict[str, Any], variant: str, audit: dict[str, Any] | None = None) -> torch.Tensor:
    view = scorer_view(case)
    if audit is not None:
        audit_scorer_input(view, audit)
    query = encode_query_descriptor(view["query"]["query_descriptor"])
    candidates = [encode_write_descriptor(item["write_descriptor"]) for item in view["candidates"]]
    candidate_a = torch.stack([item.A for item in candidates])
    candidate_b = torch.stack([item.B for item in candidates])
    score_a = torch.einsum("i,ij,nj->n", query.A, model.W_A, candidate_a)
    score_b = torch.einsum("i,ij,nj->n", query.B, model.W_B, candidate_b)
    if variant == "full":
        return score_a + score_b
    if variant == "a_only":
        return score_a
    if variant == "b_only":
        return score_b
    raise ValueError(f"unknown retrieval variant: {variant}")


def grouped_scores(scores: torch.Tensor, case: dict[str, Any]) -> torch.Tensor:
    groups = descriptor_groups(scorer_view(case))
    return torch.stack([scores[indices[0]] for indices in groups])


def tensor_rows(tensor: torch.Tensor) -> list[list[float]]:
    return [[float(value) for value in row] for row in tensor.detach().cpu().tolist()]


def train_one(seed: int, train_cases: list[dict[str, Any]]) -> dict[str, Any]:
    case_by_id = {case["case_id"]: case for case in train_cases}
    case_ids = list(case_by_id)
    model = FactorizedAssociativeMatcher(seed=seed)
    optimizer = build_optimizer(model)
    initial = {"W_A": tensor_rows(model.W_A), "W_B": tensor_rows(model.W_B)}
    initial_hash = state_hash(model)
    order_rows = []
    epoch_losses = []
    clip_norms = []
    firewall = runtime_firewall()
    model.train()
    for epoch in range(TRAINING_EPOCHS):
        ordered = order_case_ids(case_ids, seed=seed, epoch=epoch)
        batches = [ordered[index:index + TRAINING_BATCH_SIZE] for index in range(0, len(ordered), TRAINING_BATCH_SIZE)]
        order_rows.append({"epoch": epoch, "batch_count": len(batches), "case_count": len(ordered), "order_sha256": digest(ordered), "batch_sha256": digest(batches), "batches": batches})
        batch_losses = []
        for batch in batches:
            optimizer.zero_grad(set_to_none=True)
            losses = []
            for case_id in batch:
                case = case_by_id[case_id]
                scores = score_variant(model, case, "full", firewall)
                grouped = grouped_scores(scores, case)
                target = target_group(case)["target_group_index"]
                losses.append(F.cross_entropy(grouped.unsqueeze(0), torch.tensor([target], dtype=torch.long)))
            loss = torch.stack(losses).mean()
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), TRAINING_GRAD_CLIP)
            optimizer.step()
            batch_losses.append(float(loss.detach().cpu().item()))
            clip_norms.append(float(norm.detach().cpu().item() if isinstance(norm, torch.Tensor) else norm))
        epoch_losses.append(sum(batch_losses) / len(batch_losses))
    model.eval()
    final = {"W_A": tensor_rows(model.W_A), "W_B": tensor_rows(model.W_B)}
    return {
        "seed": seed,
        "model": model,
        "optimizer": optimizer,
        "initial": initial,
        "final": final,
        "initial_state_hash": initial_hash,
        "final_state_hash": state_hash(model),
        "epoch_losses": epoch_losses,
        "final_loss": epoch_losses[-1],
        "clip_norms": clip_norms,
        "order_rows": order_rows,
        "training_order_hash": digest(order_rows),
        "firewall": firewall,
        "trainable_parameter_count": trainable_parameter_count(model),
        "optimizer_parameter_names": [name for group in optimizer.param_groups for parameter in group["params"] for name, candidate in model.named_parameters() if parameter is candidate],
        "loss": {"function": "torch.nn.functional.cross_entropy", "unit": "descriptor_group", "answer_loss": False, "retention_loss": False, "processor_loss": False, "auxiliary_loss": False},
    }


def save_checkpoint(result: dict[str, Any], decoder_identity: dict[str, Any], training_identity: dict[str, Any]) -> dict[str, Any]:
    seed = result["seed"]
    path = OUT / "checkpoints" / f"retrieval_seed{seed}_final.pt"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "unit": "DMC-04R",
        "seed": seed,
        "epoch": TRAINING_EPOCHS,
        "model_state_dict": {name: tensor.detach().cpu() for name, tensor in result["model"].state_dict().items()},
        "optimizer_state_dict": result["optimizer"].state_dict(),
        "training_config": {"epochs": TRAINING_EPOCHS, "batch_size": TRAINING_BATCH_SIZE, "optimizer": "AdamW", "learning_rate": TRAINING_LR, "weight_decay": TRAINING_WEIGHT_DECAY, "gradient_clip": TRAINING_GRAD_CLIP, "device": "cpu", "torch_threads": 1},
        "dmc04a_identity": DMC04A_COMMIT,
        "dmc04p_identity": DMC04P_COMMIT,
        "dmc04pa_identity": DMC04PA_COMMIT,
        "fixed_decoder_identity": decoder_identity,
        "training_order_identity": training_identity,
        "final_loss": result["final_loss"],
        "source_commit": git_head(),
    }
    torch.save(payload, path)
    return {"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "epoch": payload["epoch"], "seed": seed, "source_commit": payload["source_commit"]}


def load_checkpoint(checkpoint: dict[str, Any], seed: int) -> FactorizedAssociativeMatcher:
    payload = torch.load(ROOT / checkpoint["path"], map_location="cpu", weights_only=False)
    model = FactorizedAssociativeMatcher(seed=seed)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    return model


def query_event(case: dict[str, Any]) -> dict[str, Any]:
    query = case["neural_view"]["query"]
    return {"kind": "query", "entity": "opaque", "field": FIELD, "mode": query["mode"], "as_of_episode": query["as_of_episode"]}


def decode_selected(case: dict[str, Any], record_id: str, decoder: torch.nn.Module) -> str:
    records = case["oracle_view"]["records"]
    index = next(index for index, record in enumerate(records) if record["record_id"] == record_id)
    hidden = torch.tensor(case["neural_view"]["memory"][index]["hidden_value"], dtype=torch.float32)
    with torch.no_grad():
        logits = decoder.answer_query_with_hidden(query_event(case), hidden)
    return VALUES[int(torch.argmax(logits).item())]


def select_record(model: FactorizedAssociativeMatcher | None, case: dict[str, Any], mode: str, firewall: dict[str, Any] | None, missing_as_miss: bool = False) -> str | None:
    if mode == "oracle":
        return oracle_retrieval(case)
    if mode == "random":
        return random_retrieval(case)
    if mode == "exact_token":
        return exact_token_retrieval(case)
    if mode in {"learned", "a_only", "b_only"}:
        assert model is not None
        variant = "full" if mode == "learned" else mode
        scores = score_variant(model, case, variant, firewall)
        try:
            return resolver(case, scores)["selected_record_id"]
        except ValueError as error:
            if missing_as_miss and str(error) == "selected descriptor group has no temporally eligible record":
                return None
            raise
    raise ValueError(mode)


def condition_metrics(cases: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {case["case_id"]: case for case in cases}
    rows = []
    for family, condition in sorted({(case["family"], case["condition"]) for case in cases}):
        selected = [row for row in decisions if by_id[row["case_id"]]["family"] == family and by_id[row["case_id"]]["condition"] == condition]
        hits = sum(int(row["retrieval_hit"]) for row in selected)
        answers = sum(int(row["answer_hit"]) for row in selected)
        rows.append({"family": family, "condition": condition, "case_count": len(selected), "retrieval_hit_at_1": hits / len(selected), "answer_accuracy": answers / len(selected), "retrieval_errors": len(selected) - hits})
    return rows


def evaluate_mode(model: FactorizedAssociativeMatcher | None, cases: list[dict[str, Any]], decoder: torch.nn.Module, mode: str, firewall: dict[str, Any] | None, shuffled_by_id: dict[str, dict[str, Any]] | None = None, missing_as_miss: bool = False) -> dict[str, Any]:
    decisions = []
    for original in cases:
        evaluation_case = shuffled_by_id[original["case_id"]] if shuffled_by_id is not None else original
        selected = select_record(model, evaluation_case, mode, firewall, missing_as_miss=missing_as_miss)
        expected = original["oracle_view"]["target_record_id"]
        predicted_answer = None if selected is None else decode_selected(evaluation_case, selected, decoder)
        decisions.append({"case_id": original["case_id"], "selected_record_id": selected, "target_record_id": expected, "retrieval_hit": selected == expected, "missing_retrieval": selected is None, "predicted_answer": predicted_answer, "expected_answer": original["oracle_view"]["answer"], "answer_hit": predicted_answer == original["oracle_view"]["answer"] if predicted_answer is not None else False})
    rows = condition_metrics(cases, decisions)
    components = {}
    for label, family, condition in PRIMARY_COMPONENTS:
        row = next(row for row in rows if row["family"] == family and row["condition"] == condition)
        components[f"{label}_H1"] = row["retrieval_hit_at_1"]
        components[f"{label}_A"] = row["answer_accuracy"]
    components["P_retrieval"] = statistics.mean(components[f"{label}_H1"] for label, _, _ in PRIMARY_COMPONENTS)
    components["P_answer"] = statistics.mean(components[f"{label}_A"] for label, _, _ in PRIMARY_COMPONENTS)
    return {"mode": mode, "evaluation_split": "extrapolation", "case_count": len(cases), "condition_metrics": rows, "components": components, "decisions": decisions, "decisions_sha256": digest(decisions)}


def shuffled_cases(cases: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    mapping = build_shuffle_query_mapping(cases)
    by_id = {case["case_id"]: case for case in cases}
    result = {}
    for case in cases:
        changed = copy.deepcopy(case)
        changed["neural_view"]["query"] = copy.deepcopy(by_id[mapping[case["case_id"]]]["neural_view"]["query"])
        result[case["case_id"]] = changed
    return result, mapping


def atomic_diagnostics(model: FactorizedAssociativeMatcher) -> dict[str, Any]:
    a_mapping = [int(index) for index in torch.argmax(model.W_A.detach(), dim=1).tolist()]
    b_mapping = [int(index) for index in torch.argmax(model.W_B.detach(), dim=1).tolist()]
    return {"W_A": tensor_rows(model.W_A), "W_B": tensor_rows(model.W_B), "A_mapping": a_mapping, "B_mapping": b_mapping, "A_expected": list(range(8)), "B_expected": list(range(8)), "A_accuracy": sum(left == right for left, right in zip(a_mapping, range(8))) / 8, "B_accuracy": sum(left == right for left, right in zip(b_mapping, range(8))) / 8}


def replay_audit(train_cases: list[dict[str, Any]]) -> dict[str, Any]:
    first = train_one(NON_EVIDENCE_SEED, train_cases)
    second = train_one(NON_EVIDENCE_SEED, train_cases)
    equal = {
        "initial_state": first["initial"] == second["initial"],
        "training_order": first["order_rows"] == second["order_rows"],
        "final_W_A": first["final"]["W_A"] == second["final"]["W_A"],
        "final_W_B": first["final"]["W_B"] == second["final"]["W_B"],
        "final_loss": first["final_loss"] == second["final_loss"],
        "canonical_state_hash": first["final_state_hash"] == second["final_state_hash"],
    }
    return {"pass": all(equal.values()), "seed": NON_EVIDENCE_SEED, "equal": equal, "first": {"initial_state_hash": first["initial_state_hash"], "final_state_hash": first["final_state_hash"], "final_loss": first["final_loss"], "training_order_hash": first["training_order_hash"]}, "second": {"initial_state_hash": second["initial_state_hash"], "final_state_hash": second["final_state_hash"], "final_loss": second["final_loss"], "training_order_hash": second["training_order_hash"]}}


def aggregate_results(per_seed: dict[int, dict[str, Any]]) -> dict[str, Any]:
    modes = ("oracle", "learned", "random", "exact_token", "a_only", "b_only", "shuffled_query")
    result: dict[str, Any] = {"std_definition": "population standard deviation across five evidence seeds", "modes": {}}
    for mode in modes:
        retrieval = [per_seed[seed]["evaluations"][mode]["components"]["P_retrieval"] for seed in EVIDENCE_SEEDS]
        answer = [per_seed[seed]["evaluations"][mode]["components"]["P_answer"] for seed in EVIDENCE_SEEDS]
        result["modes"][mode] = {"P_retrieval_by_seed": dict(zip(map(str, EVIDENCE_SEEDS), retrieval)), "P_answer_by_seed": dict(zip(map(str, EVIDENCE_SEEDS), answer)), "P_retrieval_mean": statistics.mean(retrieval), "P_retrieval_std": statistics.pstdev(retrieval), "P_answer_mean": statistics.mean(answer), "P_answer_std": statistics.pstdev(answer)}
    learned_components = {}
    for label, _, _ in PRIMARY_COMPONENTS:
        key = f"{label}_H1"
        values = [per_seed[seed]["evaluations"]["learned"]["components"][key] for seed in EVIDENCE_SEEDS]
        learned_components[key] = {"by_seed": dict(zip(map(str, EVIDENCE_SEEDS), values)), "mean": statistics.mean(values), "std": statistics.pstdev(values)}
    result["learned_components"] = learned_components
    return result


def gate_result(aggregate: dict[str, Any], per_seed: dict[int, dict[str, Any]], integrity: dict[str, bool]) -> dict[str, Any]:
    modes = aggregate["modes"]
    learned = modes["learned"]
    gates = {
        "A_P_retrieval": {"threshold": 0.90, "observed": learned["P_retrieval_mean"], "pass": learned["P_retrieval_mean"] >= 0.90},
        "B_P_answer": {"threshold": 0.90, "observed": learned["P_answer_mean"], "pass": learned["P_answer_mean"] >= 0.90},
        "C_oracle_gap": {"threshold_max": 0.10, "observed": modes["oracle"]["P_retrieval_mean"] - learned["P_retrieval_mean"], "pass": modes["oracle"]["P_retrieval_mean"] - learned["P_retrieval_mean"] <= 0.10},
        "D_composition": {"threshold": 0.90, "observed": aggregate["learned_components"]["COMP16_H1"]["mean"], "pass": aggregate["learned_components"]["COMP16_H1"]["mean"] >= 0.90},
        "E_hard_negatives": {"threshold": 0.90, "observed": aggregate["learned_components"]["HARD16_H1"]["mean"], "pass": aggregate["learned_components"]["HARD16_H1"]["mean"] >= 0.90},
        "F_current": {"threshold": 0.90, "observed": aggregate["learned_components"]["CURRENT16_H1"]["mean"], "pass": aggregate["learned_components"]["CURRENT16_H1"]["mean"] >= 0.90},
        "G_history": {"threshold": 0.90, "observed": aggregate["learned_components"]["HISTORY16_H1"]["mean"], "pass": aggregate["learned_components"]["HISTORY16_H1"]["mean"] >= 0.90},
        "H_noise32": {"threshold": 0.90, "observed": aggregate["learned_components"]["NOISE32_H1"]["mean"], "pass": aggregate["learned_components"]["NOISE32_H1"]["mean"] >= 0.90},
        "I_seed_consistency": {"threshold": 0.85, "count": sum(per_seed[seed]["evaluations"]["learned"]["components"]["P_retrieval"] >= 0.85 for seed in EVIDENCE_SEEDS), "required_count": 5, "pass": sum(per_seed[seed]["evaluations"]["learned"]["components"]["P_retrieval"] >= 0.85 for seed in EVIDENCE_SEEDS) == 5},
        "J_random_separation": {"threshold": 0.60, "observed": learned["P_retrieval_mean"] - modes["random"]["P_retrieval_mean"], "pass": learned["P_retrieval_mean"] - modes["random"]["P_retrieval_mean"] >= 0.60},
        "K_exact_token_separation": {"threshold": 0.60, "observed": learned["P_retrieval_mean"] - modes["exact_token"]["P_retrieval_mean"], "pass": learned["P_retrieval_mean"] - modes["exact_token"]["P_retrieval_mean"] >= 0.60},
        "two_attribute_A_only": {"threshold": 0.30, "observed": learned["P_retrieval_mean"] - modes["a_only"]["P_retrieval_mean"], "pass": learned["P_retrieval_mean"] - modes["a_only"]["P_retrieval_mean"] >= 0.30},
        "two_attribute_B_only": {"threshold": 0.30, "observed": learned["P_retrieval_mean"] - modes["b_only"]["P_retrieval_mean"], "pass": learned["P_retrieval_mean"] - modes["b_only"]["P_retrieval_mean"] >= 0.30},
        "query_cue_mechanism": {"threshold": 0.40, "observed": learned["P_retrieval_mean"] - modes["shuffled_query"]["P_retrieval_mean"], "pass": learned["P_retrieval_mean"] - modes["shuffled_query"]["P_retrieval_mean"] >= 0.40},
    }
    integrity_rows = {**integrity, "all_frozen_gates": all(item["pass"] for item in gates.values())}
    return {"gates": gates, "integrity": integrity_rows, "all_performance_gates": all(item["pass"] for item in gates.values()), "all_integrity_checks": all(integrity_rows.values())}


def markdown_report(terminal: str, aggregate: dict[str, Any], per_seed: dict[int, dict[str, Any]], gates: dict[str, Any]) -> str:
    lines = [f"# {UNIT} — Fixed-Decoder Learned Associative Retrieval Evidence", "", f"Terminal state: `{terminal}`", "", "## Primary retrieval metrics", "", "| Seed | Oracle P_R | Learned P_R | Random P_R | Exact-token P_R | A-only P_R | B-only P_R | Shuffled-query P_R |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for seed in EVIDENCE_SEEDS:
        values = [per_seed[seed]["evaluations"][mode]["components"]["P_retrieval"] for mode in ("oracle", "learned", "random", "exact_token", "a_only", "b_only", "shuffled_query")]
        lines.append("| " + str(seed) + " | " + " | ".join(f"{value:.6f}" for value in values) + " |")
    lines.extend(["", "| Aggregate | Oracle P_R | Learned P_R | Random P_R | Exact-token P_R | A-only P_R | B-only P_R | Shuffled-query P_R |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    lines.append("| mean | " + " | ".join(f"{aggregate['modes'][mode]['P_retrieval_mean']:.6f}" for mode in ("oracle", "learned", "random", "exact_token", "a_only", "b_only", "shuffled_query")) + " |")
    lines.extend(["", "## Learned final-answer metrics", "", "| Seed | Learned P_answer |", "|---:|---:|"])
    for seed in EVIDENCE_SEEDS:
        lines.append(f"| {seed} | {per_seed[seed]['evaluations']['learned']['components']['P_answer']:.6f} |")
    lines.append(f"| mean | {aggregate['modes']['learned']['P_answer_mean']:.6f} |")
    lines.extend(["", "## Gates", ""])
    for name, value in gates["gates"].items():
        lines.append(f"- `{name}`: {'PASS' if value['pass'] else 'FAIL'} — {json.dumps(value, sort_keys=True)}")
    lines.extend(["", "## Boundary", "", "This evidence unit uses only the frozen DMC-04A memory, one native frozen seed-1337 decoder, and the 128-parameter DMC-04P matcher. It does not establish cross-seed latent interoperability, learned retention, semantic memory, consolidation, or DMC-03 integration."])
    return "\n".join(lines) + "\n"


def write_preflight(preflight: dict[str, Any], replay: dict[str, Any] | None = None) -> None:
    payload = dict(preflight)
    if replay is not None:
        payload["non_evidence_replay"] = replay
        payload["non_evidence_replay_pass"] = replay["pass"]
    write_json(OUT / f"{ARTIFACT_PREFIX}_PREFLIGHT.json", payload)


def run_preflight() -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], torch.nn.Module, dict[str, Any]]:
    OUT.mkdir(parents=True, exist_ok=True)
    identities = {
        "WORLD-0": world0_identity(),
        "DMC-01": identity("DMC-01", DMC01_COMMIT, "artifacts/dmc01", "DMC_01_EXACT_MEMORY_ADVANCES"),
        "DMC-03": identity("DMC-03", DMC03_COMMIT, "artifacts/dmc03", "DMC_03_LEARNED_RETENTION_ADVANCES"),
        "DMC-04A": identity("DMC-04A", DMC04A_COMMIT, "artifacts/dmc04a", DMC04A_TERMINAL),
        "DMC-04P": identity("DMC-04P", DMC04P_COMMIT, "artifacts/dmc04p", DMC04P_TERMINAL),
        "DMC-04 invalid preflight": identity("DMC-04 invalid preflight", DMC04_INVALID_COMMIT, "artifacts/dmc04", DMC04_INVALID_TERMINAL),
        "DMC-04P-A": identity("DMC-04P-A", DMC04PA_COMMIT, "artifacts/dmc04pa", DMC04PA_TERMINAL),
    }
    protocol = dmc04p_protocol_identity()
    dataset = load_cases()
    decoder, decoder_info = load_fixed_decoder()
    compatibility = hidden_vector_compatibility(dataset, decoder)
    oracle = oracle_end_to_end(dataset, decoder)
    train_cases = dataset["train"]
    training_identity = training_manifest_identity(train_cases)
    capacity = capacity_audit([case for cases in dataset.values() for case in cases])
    tests = run_tests()
    all_identities = all(row["pass"] for row in identities.values())
    expected_vector_counts = compatibility["total_hidden_vectors_checked"] == 4736 and compatibility["correctly_decoded"] == 4736 and compatibility["incorrectly_decoded"] == 0 and compatibility["accuracy"] == 1.0 and {row["split"]: (row["hidden_vectors_checked"], row["correctly_decoded"]) for row in compatibility["rows"]} == {"train": (1472, 1472), "iid": (1472, 1472), "extrapolation": (1792, 1792)}
    preflight = {
        "unit": UNIT,
        "preflight_pass": all_identities and protocol["pass"] and training_identity["pass"] and capacity["pass"] and tests["pass"] and expected_vector_counts and compatibility["pass"] and oracle["pass"] and decoder_info["before_sha256"] == DMC01_CHECKPOINT_SHA256 and decoder_info["after_sha256"] == DMC01_CHECKPOINT_SHA256,
        "identities": identities,
        "dmc04p_protocol_identity": protocol,
        "training_manifest_identity": training_identity,
        "capacity_audit": capacity,
        "full_tests": tests,
        "fixed_decoder": {"checkpoint": DMC01_CHECKPOINT, "sha256_before": decoder_info["before_sha256"], "sha256_after": decoder_info["after_sha256"], "seed": decoder_info["payload_seed"], "trainable_parameters": 0},
        "all_hidden_vector_compatibility": compatibility,
        "oracle_end_to_end_validation": oracle,
        "evidence_seeds_executed": [],
        "evidence_training_executed": False,
        "scientific_retrieval_accuracy_measured": False,
    }
    write_preflight(preflight)
    return preflight, dataset, decoder, {"before_sha256": decoder_info["before_sha256"], "after_sha256": decoder_info["after_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-only", action="store_true", help="run preflight and non-evidence replay without consuming evidence seeds")
    args = parser.parse_args()
    torch.set_num_threads(1)
    preflight, dataset, decoder, decoder_hashes = run_preflight()
    if not preflight["preflight_pass"]:
        print("DMC_04R2_INVALID" if CORRECTED_EVALUATOR else "DMC_04R_INVALID")
        return 1
    replay = replay_audit(dataset["train"])
    write_preflight(preflight, replay)
    if args.audit_only:
        audit_prefix = "DMC_04R2" if CORRECTED_EVALUATOR else "DMC_04R"
        print(f"{audit_prefix}_PREFLIGHT_PASS" if replay["pass"] else f"{audit_prefix}_REPAIR_REQUIRED")
        return 0 if replay["pass"] else 1
    if not replay["pass"]:
        print("DMC_04R2_REPAIR_REQUIRED" if CORRECTED_EVALUATOR else "DMC_04R_REPAIR_REQUIRED")
        return 1

    extrapolation = dataset["extrapolation"]
    shuffled, shuffle_mapping = shuffled_cases(extrapolation)
    per_seed: dict[int, dict[str, Any]] = {}
    for seed in EVIDENCE_SEEDS:
        trained = train_one(seed, dataset["train"])
        order_identity = {"seed": seed, "epochs": TRAINING_EPOCHS, "batch_size": TRAINING_BATCH_SIZE, "order_rows": trained["order_rows"], "training_order_hash": trained["training_order_hash"], "stateless_order": "SHA256('DMC04_ORDER|' + str(seed) + '|' + str(epoch) + '|' + case_id)"}
        checkpoint = save_checkpoint(trained, {"seed": 1337, "checkpoint": DMC01_CHECKPOINT, "sha256": DMC01_CHECKPOINT_SHA256}, order_identity)
        model = load_checkpoint(checkpoint, seed)
        firewall = trained["firewall"]
        evaluations = {
            "oracle": evaluate_mode(None, extrapolation, decoder, "oracle", None, missing_as_miss=CORRECTED_EVALUATOR),
            "learned": evaluate_mode(model, extrapolation, decoder, "learned", firewall, missing_as_miss=CORRECTED_EVALUATOR),
            "random": evaluate_mode(None, extrapolation, decoder, "random", None, missing_as_miss=CORRECTED_EVALUATOR),
            "exact_token": evaluate_mode(None, extrapolation, decoder, "exact_token", None, missing_as_miss=CORRECTED_EVALUATOR),
            "a_only": evaluate_mode(model, extrapolation, decoder, "a_only", firewall, missing_as_miss=CORRECTED_EVALUATOR),
            "b_only": evaluate_mode(model, extrapolation, decoder, "b_only", firewall, missing_as_miss=CORRECTED_EVALUATOR),
            "shuffled_query": evaluate_mode(model, extrapolation, decoder, "learned", firewall, shuffled, missing_as_miss=CORRECTED_EVALUATOR),
        }
        evaluations["shuffled_query"]["mode"] = "shuffled_query"
        for mode, result in evaluations.items():
            write_json(OUT / f"{mode}_seed{seed}.json", result)
        training_artifact = {key: value for key, value in trained.items() if key not in {"model", "optimizer"}}
        training_artifact.update({"checkpoint": checkpoint, "training_order_identity": order_identity, "dmc04a_identity": DMC04A_COMMIT, "dmc04p_identity": DMC04P_COMMIT, "dmc04pa_identity": DMC04PA_COMMIT, "fixed_decoder_identity": {"seed": 1337, "checkpoint": DMC01_CHECKPOINT, "sha256": DMC01_CHECKPOINT_SHA256}})
        write_json(OUT / f"retrieval_seed{seed}_train.json", training_artifact)
        write_json(OUT / f"training_order_seed{seed}.json", order_identity)
        write_json(OUT / f"diagnostics_seed{seed}.json", atomic_diagnostics(model))
        per_seed[seed] = {"seed": seed, "checkpoint": checkpoint, "training": training_artifact, "evaluations": evaluations, "firewall": firewall, "diagnostics": atomic_diagnostics(model)}

    replay_rows = []
    for seed in EVIDENCE_SEEDS:
        model = load_checkpoint(per_seed[seed]["checkpoint"], seed)
        repeat_firewall = runtime_firewall()
        repeat = evaluate_mode(model, extrapolation, decoder, "learned", repeat_firewall, missing_as_miss=CORRECTED_EVALUATOR)
        original = per_seed[seed]["evaluations"]["learned"]
        replay_rows.append({"seed": seed, "retrieval_decisions_identical": original["decisions"] == repeat["decisions"], "retrieval_metrics_identical": original["components"] == repeat["components"], "answer_metrics_identical": original["components"]["P_answer"] == repeat["components"]["P_answer"], "original_hash": digest({"decisions": original["decisions"], "components": original["components"]}), "repeat_hash": digest({"decisions": repeat["decisions"], "components": repeat["components"]})})
    replay_result = {"pass": all(row["retrieval_decisions_identical"] and row["retrieval_metrics_identical"] and row["answer_metrics_identical"] and row["original_hash"] == row["repeat_hash"] for row in replay_rows), "rows": replay_rows, "repeat_seed1337_required": True}
    write_json(OUT / "replay.json", replay_result)
    aggregate = aggregate_results(per_seed)
    learned_firewall = {"pass": not per_seed[seed]["firewall"]["forbidden_fields_union"] and not per_seed[seed]["firewall"]["hidden_value_in_actual_scorer"] and not per_seed[seed]["firewall"]["answer_in_actual_scorer"] and not per_seed[seed]["firewall"]["logical_key_in_actual_scorer"] and not per_seed[seed]["firewall"]["record_id_in_actual_scorer"] and all(per_seed[seed]["firewall"]["all_candidates_scored"] for seed in EVIDENCE_SEEDS), "per_seed": {str(seed): per_seed[seed]["firewall"] for seed in EVIDENCE_SEEDS}, "forbidden_inputs": ["logical_key", "answer", "answer class", "correct candidate index", "oracle retrieval decision", "hidden_value", "case ID", "record ID", "future events", "entity", "field"]}
    processor_after = sha256(ROOT / DMC01_CHECKPOINT)
    integrity = {"preflight": preflight["preflight_pass"], "non_evidence_replay": replay["pass"], "evidence_seed_set": True, "evidence_seed_count": len(per_seed) == 5, "evidence_training_once_each": all(per_seed[seed]["training"]["seed"] == seed and per_seed[seed]["training"]["epoch_losses"] for seed in EVIDENCE_SEEDS), "retriever_parameter_count": all(per_seed[seed]["training"]["trainable_parameter_count"] == 128 for seed in EVIDENCE_SEEDS), "optimizer_isolation": all(per_seed[seed]["training"]["optimizer_parameter_names"] == ["W_A", "W_B"] for seed in EVIDENCE_SEEDS), "retrieval_firewall": learned_firewall["pass"], "capacity": preflight["capacity_audit"]["pass"], "replay": replay_result["pass"], "processor_immutable": processor_after == DMC01_CHECKPOINT_SHA256 and decoder_hashes["before_sha256"] == processor_after, "no_evidence_seed_reuse": True}
    gate = gate_result(aggregate, per_seed, integrity)
    prefix = "DMC_04R2" if CORRECTED_EVALUATOR else "DMC_04R"
    if not integrity["processor_immutable"]:
        terminal = f"{prefix}_PROCESSOR_INVALID"
    elif not integrity["retrieval_firewall"]:
        terminal = f"{prefix}_RETRIEVAL_LEAK"
    elif not all(integrity.values()):
        terminal = f"{prefix}_INVALID"
    elif gate["all_performance_gates"] and gate["all_integrity_checks"]:
        terminal = f"{prefix}_LEARNED_RETRIEVAL_ADVANCES"
    elif all(gate["gates"][name]["pass"] for name in ("A_P_retrieval", "B_P_answer", "C_oracle_gap", "D_composition", "E_hard_negatives", "F_current", "G_history", "H_noise32", "I_seed_consistency", "J_random_separation", "K_exact_token_separation", "two_attribute_A_only", "two_attribute_B_only")) and not gate["gates"]["query_cue_mechanism"]["pass"]:
        terminal = f"{prefix}_PERFORMANCE_ONLY_QUERY_USE_UNESTABLISHED"
    else:
        terminal = f"{prefix}_LEARNED_RETRIEVAL_NO_ADVANTAGE"
    config = {"unit": UNIT, "status": "fixed_decoder_learned_associative_retrieval_evidence", "evaluation_semantics": "no temporally eligible record -> retrieval miss" if CORRECTED_EVALUATOR else "frozen resolver exception aborts", "source_commit": git_head(), "dmc04a_commit": DMC04A_COMMIT, "dmc04p_commit": DMC04P_COMMIT, "dmc04pa_commit": DMC04PA_COMMIT, "invalid_preflight_commit": DMC04_INVALID_COMMIT, "fixed_decoder": {"seed": 1337, "checkpoint": DMC01_CHECKPOINT, "sha256": DMC01_CHECKPOINT_SHA256}, "retrieval_evidence_seeds": list(EVIDENCE_SEEDS), "training": {"epochs": TRAINING_EPOCHS, "batch_size": TRAINING_BATCH_SIZE, "optimizer": "AdamW", "learning_rate": TRAINING_LR, "weight_decay": TRAINING_WEIGHT_DECAY, "gradient_clip": TRAINING_GRAD_CLIP, "device": "cpu", "torch_threads": 1, "stateless_order": "SHA256('DMC04_ORDER|' + str(seed) + '|' + str(epoch) + '|' + case_id)"}, "retriever": {"class": "factorized_atomic_bilinear", "W_A": [8, 8], "W_B": [8, 8], "trainable_parameters": 128}, "primary_retrieval": "mean(ALIAS16_H1,COMP16_H1,HARD16_H1,CURRENT16_H1,HISTORY16_H1,NOISE8_H1,NOISE32_H1)", "primary_answer": "mean(ALIAS16_A,COMP16_A,HARD16_A,CURRENT16_A,HISTORY16_A,NOISE8_A,NOISE32_A)", "evidence_training_executed": True, "scientific_retrieval_accuracy_measured": True}
    environment = {"python": sys.version, "platform": platform.platform(), "torch": torch.__version__, "torch_threads": torch.get_num_threads(), "device": "cpu", "seed_set": list(EVIDENCE_SEEDS)}
    write_json(OUT / f"{ARTIFACT_PREFIX}_CONFIG.json", config)
    write_json(OUT / "environment.json", environment)
    write_json(OUT / "predecessor_identity.json", {"pass": all(row["pass"] for row in preflight["identities"].values()), "rows": preflight["identities"]})
    write_json(OUT / "invalid_history_identity.json", preflight["identities"]["DMC-04 invalid preflight"])
    write_json(OUT / "amendment_identity.json", preflight["identities"]["DMC-04P-A"])
    write_json(OUT / "fixed_decoder_identity.json", preflight["fixed_decoder"])
    write_json(OUT / "all_hidden_vector_compatibility.json", preflight["all_hidden_vector_compatibility"])
    write_json(OUT / "processor_immutability.json", {"pass": integrity["processor_immutable"], "checkpoint": DMC01_CHECKPOINT, "sha256_before": decoder_hashes["before_sha256"], "sha256_after": processor_after, "trainable_parameters": 0})
    write_json(OUT / "training_manifest_identity.json", preflight["training_manifest_identity"])
    write_json(OUT / "optimizer_isolation.json", {"pass": integrity["optimizer_isolation"], "trainable_parameters": 128, "optimizer_parameters": ["W_A", "W_B"], "processor_parameters": 0, "memory_parameters": 0, "retention_parameters": 0})
    write_json(OUT / "retrieval_firewall.json", learned_firewall)
    write_json(OUT / "capacity_audit.json", preflight["capacity_audit"])
    write_json(OUT / "aggregate.json", aggregate)
    verdict = {"unit": UNIT, "terminal_state": terminal, "gates": gate["gates"], "integrity": gate["integrity"], "aggregate": aggregate, "evidence_seeds": list(EVIDENCE_SEEDS), "evidence_seeds_executed": list(EVIDENCE_SEEDS), "evidence_training_executed": True, "scientific_retrieval_accuracy_measured": True, "cross_seed_latent_alignment_not_established": True, "dmc03_integration_executed": False, "fresh_execution_under_corrected_evaluator": CORRECTED_EVALUATOR}
    write_json(OUT / f"{ARTIFACT_PREFIX}_VERDICT.json", verdict)
    (OUT / f"{ARTIFACT_PREFIX}_REPORT.md").write_text(markdown_report(terminal, aggregate, per_seed, gate), encoding="utf-8")
    write_json(OUT / "SHA256SUMS.json", manifest_for(OUT))
    print(terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
