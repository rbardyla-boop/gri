#!/usr/bin/env python3
"""GRI-SC-1R deterministic representability analysis for Candidate B.

This is a constructive analysis of a declared DEV_SMOKE formula. It is not a
scientific training run and cannot emit a scientific verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import torch
from scipy.optimize import linprog
from torch import nn


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "experiments" / "gri02b_fixture_bank.json"
SOURCE = Path(__file__).resolve().parent / "branchfree_residual.py"
MANIFEST = Path(__file__).resolve().parent / "branchfree_residual_manifest.json"
RULES = ROOT / "experiments" / "gri02b_operation_rules.json"
CONTRACT = ROOT / "docs" / "GRI-SC-0-SELECTOR-COST-AUTHORIZATION-CONTRACT.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_candidate():
    spec = importlib.util.spec_from_file_location("gri_sc1_residual", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate source cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.BranchFreeResidualCell


def set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def batch_states(model: nn.Module, rows: list[dict], index: dict[str, int]) -> torch.Tensor:
    longest = max(len(row["tokens"]) for row in rows)
    padded = torch.full((len(rows), longest), index["PAD"], dtype=torch.long)
    active = torch.zeros((len(rows), longest), dtype=torch.bool)
    for row_index, row in enumerate(rows):
        ids = torch.tensor([index[token] for token in row["tokens"]], dtype=torch.long)
        padded[row_index, :len(ids)] = ids
        active[row_index, :len(ids)] = True
    state = model.initial_state(len(rows), dtype=torch.float64, device=torch.device("cpu"))
    for step in range(longest):
        next_state = model.step(padded[:, step], state)
        state = torch.where(active[:, step, None], next_state, state)
    return state


def fit_decoder_lp(states: np.ndarray, labels: np.ndarray) -> dict:
    signed = 2.0 * labels.astype(np.float64) - 1.0
    features = np.concatenate([states, np.ones((len(states), 1))], axis=1)
    result = linprog(
        np.zeros(features.shape[1]),
        A_ub=-signed[:, None] * features,
        b_ub=-np.ones(len(features)),
        bounds=[(None, None)] * features.shape[1],
        method="highs",
    )
    if not result.success:
        return {"separator_found": False, "reason": result.message}
    weights = result.x
    margins = signed * (features @ weights)
    predictions = (features @ weights >= 0).astype(np.int64)
    return {
        "separator_found": True,
        "weights": weights.tolist(),
        "accuracy": float(np.mean(predictions == labels)),
        "minimum_geometric_margin": float(np.min(margins) / np.linalg.norm(weights[:-1])),
    }


def evaluate(model: nn.Module, decoder_params: dict[str, torch.Tensor], rows: list[dict], index: dict[str, int]) -> dict:
    states_by_task = {}
    for task in ("delayed_bit", "correction", "order"):
        task_rows = [row for row in rows if row["task"] == task]
        states = batch_states(model, task_rows, index).detach().cpu().numpy()
        labels = np.array([row["label"] for row in task_rows], dtype=np.int64)
        decoder = decoder_params[task].detach().cpu().numpy()
        scores = np.concatenate([states, np.ones((len(states), 1))], axis=1) @ decoder
        states_by_task[task] = {
            "rows": task_rows,
            "states": states,
            "labels": labels,
            "scores": scores,
        }
    result = {}
    for scope, predicate in (("fit", lambda row: row["split"] == "fit"), ("held_out", lambda row: row["split"] == "held_out"), ("all", lambda row: True)):
        accuracies = []
        for task, values in states_by_task.items():
            mask = np.array([predicate(row) for row in values["rows"]])
            accuracies.extend((values["scores"][mask] >= 0).astype(np.int64) == values["labels"][mask])
        result[scope] = float(np.mean(accuracies))
    return result


def solve(start: int, rows: list[dict], index: dict[str, int]) -> dict:
    set_seed(start)
    Candidate = load_candidate()
    model = Candidate(alphabet_size=len(index), state_width=8).double()
    decoder_params = nn.ParameterDict({task: nn.Parameter(torch.randn(9, dtype=torch.float64) * 0.2) for task in ("delayed_bit", "correction", "order")})
    params = [model.input.weight, model.diagonal] + list(decoder_params.parameters())
    optimizer = torch.optim.LBFGS(
        params,
        lr=0.5,
        max_iter=100,
        tolerance_grad=1e-7,
        tolerance_change=1e-9,
        line_search_fn="strong_wolfe",
    )
    fit_rows = [row for row in rows if row["split"] == "fit"]

    def closure():
        optimizer.zero_grad()
        losses = []
        for task in ("delayed_bit", "correction", "order"):
            task_rows = [row for row in fit_rows if row["task"] == task]
            states = batch_states(model, task_rows, index)
            labels = torch.tensor([1.0 if row["label"] else -1.0 for row in task_rows], dtype=torch.float64)
            decoder = decoder_params[task]
            scores = torch.cat([states, torch.ones((len(states), 1), dtype=torch.float64)], dim=1) @ decoder
            losses.append(torch.nn.functional.softplus(-labels * scores).mean())
        loss = sum(losses)
        loss.backward()
        return loss

    final_loss = float(optimizer.step(closure).detach())
    model.eval()
    with torch.no_grad():
        metrics = evaluate(model, decoder_params, rows, index)

    lp_decoders = {}
    for task in ("delayed_bit", "correction", "order"):
        task_rows = [row for row in rows if row["task"] == task]
        states = batch_states(model, [row for row in task_rows if row["split"] == "fit"], index).detach().cpu().numpy()
        labels = np.array([row["label"] for row in task_rows if row["split"] == "fit"], dtype=np.int64)
        decoder = fit_decoder_lp(states, labels)
        if decoder.get("separator_found"):
            all_states = batch_states(model, task_rows, index).detach().cpu().numpy()
            all_labels = np.array([row["label"] for row in task_rows], dtype=np.int64)
            w = np.array(decoder["weights"])
            all_scores = np.concatenate([all_states, np.ones((len(all_states), 1))], axis=1) @ w
            fit_mask = np.array([row["split"] == "fit" for row in task_rows])
            decoder["fit_accuracy"] = float(np.mean((all_scores[fit_mask] >= 0).astype(np.int64) == all_labels[fit_mask]))
            held_mask = np.array([row["split"] == "held_out" for row in task_rows])
            decoder["held_out_accuracy"] = float(np.mean((all_scores[held_mask] >= 0).astype(np.int64) == all_labels[held_mask]))
        lp_decoders[task] = decoder

    witness = {
        "diagonal": model.diagonal.detach().cpu().tolist(),
        "embedding": model.input.weight.detach().cpu().tolist(),
        "task_decoders": {task: decoder_params[task].detach().cpu().tolist() for task in decoder_params},
    }
    return {"start": start, "final_loss": final_loss, "solver_metrics": metrics, "lp_decoders": lp_decoders, "witness": witness}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri_sc1r_branchfree_residual_receipt.json")
    args = parser.parse_args()
    fixture_bank = json.loads(FIXTURES.read_text(encoding="utf-8"))
    if sha256(FIXTURES) != "f555336cc86745a5a28c17fee1d7886f8ed78a277d1fe9f00df7aa0ce43a7960":
        raise SystemExit("fixture bank hash mismatch")
    alphabet = fixture_bank["alphabet"]
    index = {token: i for i, token in enumerate(alphabet)}
    rows = [{**row, "tokens": row["tokens"][:-1]} for row in fixture_bank["fixtures"]]
    starts = [0, 1, 2]
    runs = [solve(start, rows, index) for start in starts]
    passing = [run for run in runs if all(run["solver_metrics"][scope] == 1.0 for scope in ("fit", "held_out", "all")) and all(run["lp_decoders"][task].get("held_out_accuracy") == 1.0 for task in ("delayed_bit", "correction", "order"))]
    result = "REPRESENTABLE" if passing else "INCONCLUSIVE"
    best = passing[0] if passing else runs[0]
    output = {
        "unit": "GRI-SC-1R-BRANCH-FREE-REPRESENTABILITY-ANALYSIS",
        "status": "ANALYSIS_ONLY",
        "representability_result": result,
        "scientific_verdict": "FORBIDDEN",
        "candidate_freeze": False,
        "scientific_run": False,
        "candidate_id": "GRI-SC-1-B-BRANCHFREE-RESIDUAL",
        "formula": "u=tanh(D⊙h+E[token]); h_next=h+E[token][semantic_code]·(u-h); semantic_code(WAIT)=0; semantic_code(other)=1",
        "source_sha256": sha256(SOURCE),
        "manifest_sha256": sha256(MANIFEST),
        "sc0_contract_sha256": sha256(CONTRACT),
        "operation_rules_sha256": sha256(RULES),
        "fixture_bank_sha256": sha256(FIXTURES),
        "solver": {"method": "deterministic float64 LBFGS", "starts": starts, "max_iter": 100, "decoder": "one fixed linear decoder per task, fit states only"},
        "runs": [{"start": run["start"], "final_loss": run["final_loss"], "solver_metrics": run["solver_metrics"], "lp_decoder_summary": {task: {key: value for key, value in run["lp_decoders"][task].items() if key != "weights"} for task in run["lp_decoders"]}} for run in runs],
        "constructive_witness": best["witness"],
        "interpretation": "This establishes representability of the declared branch-free form under the bounded fixture/state-decoder test. It does not establish learnability, scientific advantage, minimality, or authorization for SC-2.",
        "next_state": {"sc2": "NOT AUTHORIZED", "scientific_ledger": "UNCHANGED"},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"unit": output["unit"], "representability_result": result, "scientific_verdict": output["scientific_verdict"], "sc2": output["next_state"]["sc2"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
