#!/usr/bin/env python3
"""GRI-SC-1L development-only learnability grid for immutable Candidate B.

This runner is deliberately separate from the earlier SC-1 smoke runner.  It
does not alter the candidate, fixtures, budgets, or scientific ledger, and it
never emits a scientific verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from scipy.optimize import linprog
from torch import nn


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent / "branchfree_residual.py"
MANIFEST = Path(__file__).resolve().parent / "branchfree_residual_manifest.json"
FIXTURES = ROOT / "experiments" / "gri02b_fixture_bank.json"
RULES = ROOT / "experiments" / "gri02b_operation_rules.json"
SIM = ROOT / "sim" / "gri_sim0.py"
SIM_EXPERIMENT = ROOT / "sim" / "experiment_manifest.json"
REPRESENTABILITY = Path(__file__).resolve().parent / "representability_solver.py"

SEEDS = [20260820, 20260821, 20260822]
SGD_RATES = [0.003, 0.01, 0.03, 0.1]
ADAM_RATES = [0.0003, 0.001, 0.003]
EPOCHS = 400
LBFGS_ITERATIONS = 100
RESTART_FIXTURE_LIMIT = 32

EXPECTED_SOURCE_SHA256 = "64732bbaebc5c52de3344c7c9387f0a688c6210e5638dd61736dcadc0f5af218"
EXPECTED_MANIFEST_SHA256 = "f7e6e9617ef810a22aed9c097021ab41a88b32609cfaac2857e0d63fd65f9584"
EXPECTED_FIXTURE_SHA256 = "f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960"
EXPECTED_RULES_SHA256 = "166f269d77c0e9f7bb95daa2a4bc376418c43ed59666bdd5d9ee90c47b1442d3"
SC1L_AUTHORIZATION_SHA256 = "25142cc2d044d3d07c1459ea9e345d6c2f87141876c6ac8588c8149d420712d4"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_candidate():
    spec = importlib.util.spec_from_file_location("gri_sc1l_candidate", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import candidate: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BranchFreeResidualCell


def set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def run_preflight() -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SIM),
            "validate-candidate",
            "--experiment",
            str(SIM_EXPERIMENT),
            "--candidate",
            str(MANIFEST),
            "--source",
            str(SOURCE),
        ],
        cwd=SIM.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    if not result.stdout.strip():
        raise RuntimeError(f"simulator preflight emitted no JSON: {result.stderr}")
    return {"returncode": result.returncode, "result": json.loads(result.stdout)}


def validate_anchors() -> dict:
    actual = {
        "source": sha256(SOURCE),
        "manifest": sha256(MANIFEST),
        "fixture_bank": sha256(FIXTURES),
        "operation_rules": sha256(RULES),
    }
    expected = {
        "source": EXPECTED_SOURCE_SHA256,
        "manifest": EXPECTED_MANIFEST_SHA256,
        "fixture_bank": EXPECTED_FIXTURE_SHA256,
        "operation_rules": EXPECTED_RULES_SHA256,
    }
    if actual != expected:
        raise RuntimeError(json.dumps({"expected": expected, "actual": actual}, indent=2))
    return actual


def prepare_batch(rows: list[dict], index: dict[str, int]) -> tuple[torch.Tensor, torch.Tensor]:
    longest = max(len(row["tokens"]) for row in rows)
    padded = torch.full((len(rows), longest), index["PAD"], dtype=torch.long)
    lengths = torch.zeros(len(rows), dtype=torch.long)
    for row_index, row in enumerate(rows):
        token_ids = [index[token] for token in row["tokens"]]
        padded[row_index, : len(token_ids)] = torch.tensor(token_ids, dtype=torch.long)
        lengths[row_index] = len(token_ids)
    return padded, lengths


def batched_final_states(
    model: nn.Module,
    rows: list[dict],
    index: dict[str, int],
    prepared: tuple[torch.Tensor, torch.Tensor] | None = None,
) -> torch.Tensor:
    padded, lengths = prepared if prepared is not None else prepare_batch(rows, index)
    longest = padded.shape[1]
    state = model.initial_state(len(rows), dtype=torch.float32, device=torch.device("cpu"))
    for step in range(longest):
        next_state = model.step(padded[:, step], state)
        active = (lengths > step)[:, None]
        state = torch.where(active, next_state, state)
    return state


def states_before_query(model: nn.Module, rows: list[dict], index: dict[str, int]) -> torch.Tensor:
    prefixes = [{**row, "tokens": row["tokens"][:-1]} for row in rows]
    return batched_final_states(model, prefixes, index)


def accuracy(model: nn.Module, rows: list[dict], index: dict[str, int]) -> float:
    with torch.no_grad():
        logits = model.readout(batched_final_states(model, rows, index))
        labels = torch.tensor([row["label"] for row in rows], dtype=torch.long)
        return float((logits.argmax(dim=1) == labels).double().mean())


def task_accuracies(model: nn.Module, rows: list[dict], index: dict[str, int]) -> dict[str, float]:
    return {
        task: accuracy(model, [row for row in rows if row["task"] == task], index)
        for task in ("delayed_bit", "correction", "order")
    }


def restart_check(model: nn.Module, rows: list[dict], index: dict[str, int]) -> dict:
    checked = 0
    failures = []
    model.eval()
    with torch.no_grad():
        for row in rows:
            tokens = row["tokens"]
            prefix_states = [model.initial_state(1, dtype=torch.float32, device=torch.device("cpu"))]
            for token in tokens:
                ids = torch.tensor([index[token]], dtype=torch.long)
                prefix_states.append(model.step(ids, prefix_states[-1]))
            full = prefix_states[-1]
            for split in range(len(tokens) + 1):
                payload = model.serialize_state(prefix_states[split])
                resumed = model.restore_state(payload, dtype=torch.float32, device=torch.device("cpu"))
                for token in tokens[split:]:
                    ids = torch.tensor([index[token]], dtype=torch.long)
                    resumed = model.step(ids, resumed)
                checked += 1
                if not torch.equal(full, resumed):
                    failures.append({"fixture_id": row["fixture_id"], "split": split})
    return {"status": "PASS" if not failures else "FAIL", "cases": checked, "failures": failures[:10]}


def fixed_decoder_diagnostic(model: nn.Module, rows: list[dict], index: dict[str, int]) -> dict:
    """Fit one linear decoder/task on fit prefix states; evaluate held-out."""
    result = {}
    for task in ("delayed_bit", "correction", "order"):
        task_rows = [row for row in rows if row["task"] == task]
        fit_rows = [row for row in task_rows if row["split"] == "fit"]
        states = states_before_query(model, fit_rows, index).detach().cpu().numpy()
        labels = np.array([row["label"] for row in fit_rows], dtype=np.int64)
        signed = 2.0 * labels.astype(np.float64) - 1.0
        features = np.concatenate([states, np.ones((len(states), 1))], axis=1)
        lp = linprog(
            np.zeros(features.shape[1]),
            A_ub=-signed[:, None] * features,
            b_ub=-np.ones(len(features)),
            bounds=[(None, None)] * features.shape[1],
            method="highs",
        )
        if not lp.success:
            result[task] = {"separator_found": False, "reason": lp.message}
            continue
        weights = lp.x
        all_states = states_before_query(model, task_rows, index).detach().cpu().numpy()
        all_labels = np.array([row["label"] for row in task_rows], dtype=np.int64)
        scores = np.concatenate([all_states, np.ones((len(all_states), 1))], axis=1) @ weights
        fit_mask = np.array([row["split"] == "fit" for row in task_rows])
        held_mask = ~fit_mask
        margins = (2.0 * all_labels.astype(np.float64) - 1.0) * scores
        result[task] = {
            "separator_found": True,
            "fit_accuracy": float(np.mean((scores[fit_mask] >= 0).astype(np.int64) == all_labels[fit_mask])),
            "held_out_accuracy": float(np.mean((scores[held_mask] >= 0).astype(np.int64) == all_labels[held_mask])),
            "all_accuracy": float(np.mean((scores >= 0).astype(np.int64) == all_labels)),
            "minimum_geometric_margin": float(np.min(margins) / np.linalg.norm(weights[:-1])),
        }
    return result


def train(model: nn.Module, rows: list[dict], index: dict[str, int], optimizer_name: str, learning_rate: float) -> list[float]:
    if optimizer_name == "SGD":
        optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate)
    elif optimizer_name == "Adam":
        optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    else:
        raise ValueError(f"unsupported optimizer: {optimizer_name}")
    criterion = nn.CrossEntropyLoss()
    labels = torch.tensor([row["label"] for row in rows], dtype=torch.long)
    prepared = prepare_batch(rows, index)
    losses = []
    model.train()
    for _ in range(EPOCHS):
        optimizer.zero_grad(set_to_none=True)
        logits = model.readout(batched_final_states(model, rows, index, prepared))
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))
    return losses


def one_run(candidate_class, fit: list[dict], held_out: list[dict], fixtures: list[dict], index: dict[str, int], optimizer_name: str, learning_rate: float, seed: int) -> dict:
    set_seed(seed)
    model = candidate_class(alphabet_size=len(index), state_width=8)
    losses = train(model, fit, index, optimizer_name, learning_rate)
    model.eval()
    return {
        "optimizer": optimizer_name,
        "learning_rate": learning_rate,
        "seed": seed,
        "initialization": "torch.manual_seed(seed); Candidate B module defaults; fixed semantic-code coordinate; no representability witness",
        "loss": {"name": "torch.nn.CrossEntropyLoss", "reduction": "mean", "initial": losses[0], "final": losses[-1], "epochs": EPOCHS},
        "train_accuracy": accuracy(model, fit, index),
        "held_out_accuracy": accuracy(model, held_out, index),
        "all_accuracy": accuracy(model, fixtures, index),
        "task_train_accuracy": task_accuracies(model, fit, index),
        "task_held_out_accuracy": task_accuracies(model, held_out, index),
        "fixed_decoder": fixed_decoder_diagnostic(model, fixtures, index),
        "restart": restart_check(model, fixtures[:RESTART_FIXTURE_LIMIT], index),
    }


def summarize(runs: list[dict]) -> str:
    successful = []
    for run in runs:
        if run["restart"]["status"] != "PASS":
            continue
        if all(run[key] == 1.0 for key in ("train_accuracy", "held_out_accuracy", "all_accuracy")):
            successful.append((run["optimizer"], run["learning_rate"]))
    if successful:
        return "LEARNABILITY_SIGNAL"
    return "NO_LEARNABILITY_SIGNAL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri_sc1l_learnability_grid_receipt.json")
    parser.add_argument("--lbfgs-output", type=Path, default=ROOT / "artifacts/results/gri_sc1l_lbfgs_diagnostic_receipt.json")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.lbfgs_output = args.lbfgs_output.resolve()

    anchors = validate_anchors()
    preflight = run_preflight()
    if preflight["returncode"] != 0 or preflight["result"].get("status") != "PASS":
        raise RuntimeError(f"candidate preflight failed: {preflight}")

    fixture_bank = json.loads(FIXTURES.read_text(encoding="utf-8"))
    alphabet = fixture_bank["alphabet"]
    index = {token: i for i, token in enumerate(alphabet)}
    fixtures = fixture_bank["fixtures"]
    fit = [row for row in fixtures if row["split"] == "fit"]
    held_out = [row for row in fixtures if row["split"] == "held_out"]
    Candidate = load_candidate()

    runs = []
    run_number = 0
    for optimizer_name, rates in (("SGD", SGD_RATES), ("Adam", ADAM_RATES)):
        for learning_rate in rates:
            for seed in SEEDS:
                run_number += 1
                print(f"starting run {run_number}/21: {optimizer_name} lr={learning_rate} seed={seed}", flush=True)
                runs.append(one_run(Candidate, fit, held_out, fixtures, index, optimizer_name, learning_rate, seed))

    lbfgs = subprocess.run(
        [sys.executable, str(REPRESENTABILITY), "--output", str(args.lbfgs_output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if lbfgs.returncode != 0:
        raise RuntimeError(f"LBFGS diagnostic failed: {lbfgs.stderr}")
    lbfgs_receipt = json.loads(args.lbfgs_output.read_text(encoding="utf-8"))
    if lbfgs_receipt.get("scientific_verdict") != "FORBIDDEN":
        raise RuntimeError("LBFGS diagnostic did not remain scientific-verdict forbidden")

    output = {
        "unit": "GRI-SC-1L-LEARNABILITY-GRID",
        "status": "DEV_LEARNABILITY_ONLY",
        "scientific_verdict": "FORBIDDEN",
        "candidate_freeze": False,
        "scientific_run": False,
        "candidate_id": "GRI-SC-1-B-BRANCHFREE-RESIDUAL",
        "authorization_sha256": SC1L_AUTHORIZATION_SHA256,
        "candidate_source_sha256": anchors["source"],
        "candidate_manifest_sha256": anchors["manifest"],
        "fixture_bank_sha256": anchors["fixture_bank"],
        "operation_rules_sha256": anchors["operation_rules"],
        "candidate_declaration": json.loads(MANIFEST.read_text(encoding="utf-8")),
        "grid": {
            "seeds": SEEDS,
            "training_split": "fit only",
            "sgd_learning_rates": SGD_RATES,
            "adam_learning_rates": ADAM_RATES,
            "epoch_cap": EPOCHS,
            "lbfgs_iteration_cap": LBFGS_ITERATIONS,
            "post_result_tuning": "forbidden",
        },
        "training_protocol": {
            "loss": "torch.nn.CrossEntropyLoss(reduction='mean')",
            "sgd": {"momentum": 0.0, "weight_decay": 0.0, "nesterov": False},
            "adam": {"betas": [0.9, 0.999], "eps": 1e-8, "weight_decay": 0.0, "amsgrad": False},
            "determinism": "torch.manual_seed(seed), one CPU thread, torch.use_deterministic_algorithms(True)",
            "initialization": "Candidate B module defaults after fixed seed; no representability-witness initialization",
        },
        "sim_preflight": preflight,
        "fixture_counts": {
            "fit": len(fit),
            "held_out": len(held_out),
            "all": len(fixtures),
            "restart_smoke": RESTART_FIXTURE_LIMIT,
        },
        "runs": runs,
        "lbfgs_constructive_diagnostic": {
            "status": "ANALYSIS_ONLY",
            "scientific_verdict": "FORBIDDEN",
            "iterations": LBFGS_ITERATIONS,
            "receipt_path": str(args.lbfgs_output),
            "receipt_sha256": sha256(args.lbfgs_output),
            "representability_result": lbfgs_receipt.get("representability_result"),
            "runs": lbfgs_receipt.get("runs"),
        },
        "development_result": summarize(runs),
        "interpretation": "Development signal only; no candidate promotion, SC-2 authorization, or scientific claim.",
        "next_state": {"sc2": "NOT AUTHORIZED", "scientific_ledger": "UNCHANGED"},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "unit": output["unit"],
        "status": output["status"],
        "development_result": output["development_result"],
        "runs": len(runs),
        "lbfgs": lbfgs_receipt.get("representability_result"),
        "scientific_verdict": output["scientific_verdict"],
        "sc2": output["next_state"]["sc2"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
