#!/usr/bin/env python3
"""Development-only smoke runner for GRI-SC-1 candidate formulations.

This runner reports engineering signals only. It never emits a scientific
verdict and never changes frozen GRI-02B artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import torch
from torch import nn


ROOT = Path(__file__).resolve().parents[3]
SIM = ROOT / "sim" / "gri_sim0.py"
EXPERIMENT = ROOT / "sim" / "experiment_manifest.json"
FIXTURES = ROOT / "experiments" / "gri02b_fixture_bank.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("gri_sc1_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def run_preflight(manifest: Path, source: Path) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SIM),
            "validate-candidate",
            "--experiment",
            str(EXPERIMENT),
            "--candidate",
            str(manifest),
            "--source",
            str(source),
        ],
        cwd=SIM.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(result.stdout)
    return {"returncode": result.returncode, "result": payload}


def final_state(model: nn.Module, tokens: list[str], index: dict[str, int]) -> torch.Tensor:
    state = model.initial_state(1, dtype=torch.float32, device=torch.device("cpu"))
    for token in tokens:
        ids = torch.tensor([index[token]], dtype=torch.long)
        state = model.step(ids, state)
    return state.squeeze(0)


def batched_final_states(model: nn.Module, rows: list[dict], index: dict[str, int]) -> torch.Tensor:
    longest = max(len(row["tokens"]) for row in rows)
    padded = torch.full((len(rows), longest), index["PAD"], dtype=torch.long)
    lengths = torch.zeros(len(rows), dtype=torch.long)
    for row_index, row in enumerate(rows):
        token_ids = [index[token] for token in row["tokens"]]
        padded[row_index, :len(token_ids)] = torch.tensor(token_ids, dtype=torch.long)
        lengths[row_index] = len(token_ids)
    state = model.initial_state(len(rows), dtype=torch.float32, device=torch.device("cpu"))
    for step in range(longest):
        next_state = model.step(padded[:, step], state)
        active = (lengths > step)[:, None]
        state = torch.where(active, next_state, state)
    return state


def logits_for_rows(model: nn.Module, rows: list[dict], index: dict[str, int]) -> torch.Tensor:
    return model.readout(batched_final_states(model, rows, index))


def accuracy(model: nn.Module, rows: list[dict], index: dict[str, int]) -> float:
    with torch.no_grad():
        logits = logits_for_rows(model, rows, index)
        labels = torch.tensor([row["label"] for row in rows], dtype=torch.long)
        return float((logits.argmax(dim=1) == labels).double().mean())


def train(model: nn.Module, rows: list[dict], index: dict[str, int], epochs: int, learning_rate: float) -> None:
    optimizer = torch.optim.SGD(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss()
    labels = torch.tensor([row["label"] for row in rows], dtype=torch.long)
    model.train()
    for _ in range(epochs):
        optimizer.zero_grad(set_to_none=True)
        logits = logits_for_rows(model, rows, index)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()


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
                if not torch.equal(full.squeeze(0), resumed.squeeze(0)):
                    failures.append({"fixture_id": row["fixture_id"], "split": split})
    return {"status": "PASS" if not failures else "FAIL", "cases": checked, "failures": failures[:10]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--restart-fixtures", type=int, default=32)
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.manifest = args.manifest.resolve()
    args.output = args.output.resolve()

    fixture_bank = json.loads(FIXTURES.read_text(encoding="utf-8"))
    candidate_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    fixtures = fixture_bank["fixtures"]
    alphabet = fixture_bank["alphabet"]
    index = {token: i for i, token in enumerate(alphabet)}
    fit = [row for row in fixtures if row["split"] == "fit"]
    held_out = [row for row in fixtures if row["split"] == "held_out"]
    module = load_module(args.source)
    candidate_class = getattr(module, args.class_name)
    preflight = run_preflight(args.manifest, args.source)

    seed_results = []
    for seed in [20260820]:
        set_seed(seed)
        model = candidate_class(alphabet_size=len(alphabet), state_width=8)
        train(model, fit, index, args.epochs, 0.03)
        model.eval()
        seed_results.append({
            "seed": seed,
            "train_accuracy": accuracy(model, fit, index),
            "held_out_accuracy": accuracy(model, held_out, index),
            "all_accuracy": accuracy(model, fixtures, index),
            "restart": restart_check(model, fixtures[:args.restart_fixtures], index),
        })

    output = {
        "unit": "GRI-SC-1-BOUNDED-DEV-SMOKE-SEARCH",
        "status": "DEV_SMOKE_ONLY",
        "scientific_verdict": "FORBIDDEN",
        "candidate_id": candidate_manifest["candidate_id"],
        "candidate_formula_source": str(args.source),
        "source_sha256": sha256(args.source),
        "manifest_sha256": sha256(args.manifest),
        "parent_contract_sha256": candidate_manifest["parent_contract_sha256"],
        "candidate_declaration": {
            "state": candidate_manifest["state"],
            "parameters": candidate_manifest["parameters"],
            "operations": candidate_manifest["operations"],
            "transition_class": candidate_manifest["transition_class"],
            "serialization_fields": candidate_manifest["serialization_fields"],
        },
        "fixture_bank_sha256": sha256(FIXTURES),
        "sim_preflight": preflight,
        "training": {"mode": "DEV_SMOKE", "seed": 20260820, "epochs": args.epochs, "learning_rate": 0.03},
        "fixture_smoke": {"fit_count": len(fit), "held_out_count": len(held_out), "all_count": len(fixtures), "seeds": seed_results},
        "restart_smoke_scope": {"fixtures_checked": min(args.restart_fixtures, len(fixtures)), "scope": "development subset only; not a scientific replay claim"},
        "search_interpretation": "engineering signal only; no promotion or scientific verdict",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate_id": output["candidate_id"],
        "status": output["status"],
        "sim_preflight": preflight["result"]["status"],
        "train_accuracy": seed_results[0]["train_accuracy"],
        "held_out_accuracy": seed_results[0]["held_out_accuracy"],
        "restart": seed_results[0]["restart"]["status"],
        "scientific_verdict": output["scientific_verdict"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
