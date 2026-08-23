#!/usr/bin/env python3
"""GRI-02C: the single authorized identity-preserve candidate."""
from __future__ import annotations

import argparse
import copy
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import torch
from scipy.optimize import linprog
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(EXPERIMENTS))
from gri01_recurrence import canonical, digest  # noqa: E402
from gri02b_preregistration import evaluate_future_verdict  # noqa: E402


DTYPES = {
    "float64": torch.float64,
    "float32": torch.float32,
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
}


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def encode(fixtures: list[dict], alphabet: list[str]):
    index = {token: i for i, token in enumerate(alphabet)}
    longest = max(len(row["tokens"]) for row in fixtures)
    xs = []
    lengths = []
    labels = []
    for row in fixtures:
        xs.append([index[token] for token in row["tokens"]] + [index["PAD"]] * (longest - len(row["tokens"])))
        lengths.append(len(row["tokens"]))
        labels.append(row["label"])
    return (
        torch.tensor(xs, dtype=torch.long),
        torch.tensor(lengths, dtype=torch.long),
        torch.tensor(labels, dtype=torch.long),
    )


def q8_state(h: torch.Tensor) -> torch.Tensor:
    clipped = torch.clamp(h, -1.0, 1.0)
    quantized = torch.clamp(torch.round(clipped * 127.0), -127.0, 127.0)
    return quantized / 127.0


class IdentityPreserveCell(nn.Module):
    """Exactly 170 parameters: embedding, one tied transform, binary readout."""

    def __init__(self, input_size: int, width: int, wait_index: int, query_indices: set[int]):
        super().__init__()
        self.input = nn.Embedding(input_size, width)
        self.transition = nn.Linear(width, width, bias=True)
        self.readout = nn.Linear(width, 2, bias=True)
        self.wait_index = wait_index
        self.query_indices = frozenset(query_indices)

    def forward(self, tokens, lengths, behavior="candidate", q8=False, return_states=True):
        batch, steps = tokens.shape
        h = torch.zeros(batch, self.transition.out_features, dtype=self.input.weight.dtype)
        final = torch.zeros_like(h)
        pre_query = torch.zeros_like(h)
        seen_query = torch.zeros(batch, dtype=torch.bool)
        for step in range(steps):
            active = lengths > step
            ids = tokens[:, step]
            if behavior == "no_recurrence":
                h = torch.where(active[:, None], torch.zeros_like(h), h)
            query_here = active & torch.tensor([int(value) in self.query_indices for value in ids.tolist()], dtype=torch.bool)
            pre_query = torch.where((query_here & ~seen_query)[:, None], h, pre_query)
            seen_query = seen_query | query_here
            if behavior == "candidate":
                preserve = ids == self.wait_index
                transform_mask = active & ~preserve
            elif behavior in ("parent", "no_preserve"):
                transform_mask = active
            elif behavior == "no_transform":
                next_h = h
            elif behavior == "no_recurrence":
                preserve = ids == self.wait_index
                transform_mask = active & ~preserve
            else:
                raise ValueError(f"unknown behavior: {behavior}")
            if behavior != "no_transform":
                next_h = h.clone()
                indices = torch.nonzero(transform_mask, as_tuple=False).flatten()
                if indices.numel():
                    transformed = torch.tanh(
                        self.transition(h.index_select(0, indices))
                        + self.input(ids.index_select(0, indices))
                    )
                    next_h = next_h.index_copy(0, indices, transformed)
            if q8:
                quantized = q8_state(next_h)
                next_h = torch.where(active[:, None], quantized, next_h)
            h = torch.where(active[:, None], next_h, h)
            final = torch.where(active[:, None], h, final)
        return self.readout(final), pre_query, final


class StatelessBaseline(nn.Module):
    def __init__(self, input_size: int, width: int):
        super().__init__()
        self.input = nn.Embedding(input_size, width)
        self.hidden = nn.Linear(width, width, bias=True)
        self.readout = nn.Linear(width, 2, bias=True)

    def forward(self, final_tokens):
        return self.readout(torch.tanh(self.hidden(self.input(final_tokens))))


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def train_cell(model, inputs, lengths, labels, config, behavior):
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=config["training"]["learning_rate"],
        weight_decay=config["training"]["weight_decay"],
    )
    criterion = nn.CrossEntropyLoss()
    model.train()
    for _ in range(config["training"]["epochs"]):
        optimizer.zero_grad(set_to_none=True)
        logits, _, _ = model(inputs, lengths, behavior=behavior, q8=False, return_states=False)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()


def train_stateless(model, inputs, lengths, labels, config):
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=config["training"]["learning_rate"],
        weight_decay=config["training"]["weight_decay"],
    )
    criterion = nn.CrossEntropyLoss()
    final_tokens = inputs.gather(1, (lengths - 1)[:, None]).squeeze(1)
    model.train()
    for _ in range(config["training"]["epochs"]):
        optimizer.zero_grad(set_to_none=True)
        logits = model(final_tokens)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()


@torch.no_grad()
def evaluate_cell(model, inputs, lengths, fixtures, behavior, mode):
    if mode == "q8":
        evaluated = copy.deepcopy(model).to(torch.float32)
        logits, states, _ = evaluated(inputs, lengths, behavior=behavior, q8=True)
    else:
        evaluated = copy.deepcopy(model).to(DTYPES[mode])
        logits, states, _ = evaluated(inputs, lengths, behavior=behavior, q8=False)
    values = logits.detach().cpu().to(torch.float64).numpy()
    state_values = states.detach().cpu().to(torch.float64).numpy()
    predictions = values.argmax(axis=1)
    return prediction_metrics(predictions, fixtures), state_values


@torch.no_grad()
def evaluate_stateless(model, inputs, lengths, fixtures):
    evaluated = copy.deepcopy(model).to(torch.float32)
    final_tokens = inputs.gather(1, (lengths - 1)[:, None]).squeeze(1)
    predictions = evaluated(final_tokens).detach().cpu().argmax(1).numpy()
    return prediction_metrics(predictions, fixtures)


def prediction_metrics(predictions, fixtures):
    rows = []
    for scope, predicate in (
        ("all", lambda row: True),
        ("fit", lambda row: row["split"] == "fit"),
        ("held_out", lambda row: row["split"] == "held_out"),
    ):
        selected = [index for index, row in enumerate(fixtures) if predicate(row)]
        rows.append({
            "scope": scope,
            "count": len(selected),
            "accuracy": float(np.mean([predictions[index] == fixtures[index]["label"] for index in selected])) if selected else None,
        })
    by_family = {}
    for family in sorted({row["family"] for row in fixtures}):
        selected = [index for index, row in enumerate(fixtures) if row["family"] == family]
        by_family[family] = {
            "count": len(selected),
            "accuracy": float(np.mean([predictions[index] == fixtures[index]["label"] for index in selected])),
        }
    by_task = {}
    for task in sorted({row["task"] for row in fixtures}):
        selected = [index for index, row in enumerate(fixtures) if row["task"] == task]
        by_task[task] = {
            "count": len(selected),
            "accuracy": float(np.mean([predictions[index] == fixtures[index]["label"] for index in selected])),
        }
    return {"scopes": rows, "by_family": by_family, "by_task": by_task}


def metric_accuracy(metrics, scope, families=None):
    if families is None:
        return next(row["accuracy"] for row in metrics["scopes"] if row["scope"] == scope)
    selected = [metrics["by_family"][family]["accuracy"] for family in families]
    return min(selected) if selected else None


def fit_separator(states, labels):
    x = np.asarray(states, dtype=np.float64)
    y = np.where(np.asarray(labels, dtype=np.int64) == 1, 1.0, -1.0)
    augmented = np.concatenate([x, np.ones((len(x), 1))], axis=1)
    result = linprog(
        np.zeros(augmented.shape[1], dtype=np.float64),
        A_ub=-(y[:, None] * augmented),
        b_ub=np.full(len(x), -1.0, dtype=np.float64),
        bounds=[(None, None)] * augmented.shape[1],
        method="highs",
    )
    if result.x is None or not result.success:
        return {"separator_found": False, "accuracy": None, "geometric_margin": None}
    scores = augmented @ result.x
    signed = y * scores
    weights = result.x[:-1]
    norm = float(np.linalg.norm(weights))
    return {
        "separator_found": bool(np.min(signed) >= 1.0 - 1e-7),
        "accuracy": float(np.mean((scores >= 0.0).astype(np.int64) == (y > 0))),
        "geometric_margin": float(np.min(signed) / norm) if norm else None,
        "weights": weights.tolist(),
        "bias": float(result.x[-1]),
    }


def fixed_decoder_result(states, fixtures):
    by_task = {}
    all_pass = True
    for task in sorted({row["task"] for row in fixtures}):
        task_indices = [index for index, row in enumerate(fixtures) if row["task"] == task]
        fit_indices = [index for index in task_indices if fixtures[index]["split"] == "fit"]
        separator = fit_separator(
            [states[index] for index in fit_indices],
            [fixtures[index]["label"] for index in fit_indices],
        )
        if not separator.get("separator_found"):
            by_task[task] = {"separator_found": False, "fit_accuracy": None, "held_out_accuracy": None, "minimum_geometric_margin": None}
            all_pass = False
            continue
        weights = np.asarray(separator["weights"], dtype=np.float64)
        bias = separator["bias"]
        task_rows = []
        for scope, predicate in (("fit", lambda row: row["split"] == "fit"), ("held_out", lambda row: row["split"] == "held_out")):
            selected = [index for index in task_indices if predicate(fixtures[index])]
            x = np.asarray([states[index] for index in selected], dtype=np.float64)
            y = np.asarray([fixtures[index]["label"] for index in selected], dtype=np.int64)
            scores = x @ weights + bias
            signed = np.where(y == 1, 1.0, -1.0) * scores
            norm = float(np.linalg.norm(weights))
            task_rows.append({
                "scope": scope,
                "count": len(selected),
                "accuracy": float(np.mean((scores >= 0.0).astype(np.int64) == y)),
                "minimum_geometric_margin": float(np.min(signed) / norm) if norm else None,
            })
        task_pass = all(row["accuracy"] == 1.0 and row["minimum_geometric_margin"] is not None and row["minimum_geometric_margin"] > 0.0 for row in task_rows)
        all_pass = all_pass and task_pass
        by_task[task] = {
            "separator_found": True,
            "fit_accuracy": task_rows[0]["accuracy"],
            "held_out_accuracy": task_rows[1]["accuracy"],
            "minimum_geometric_margin": min(row["minimum_geometric_margin"] for row in task_rows),
            "rows": task_rows,
        }
    return {"pass": all_pass, "by_task": by_task}


def evaluate_model(model, inputs, lengths, fixtures, behavior, config):
    modes = {}
    for mode in config["evaluation_modes"]["required"] + config["evaluation_modes"]["stress_only"]:
        metrics, states = evaluate_cell(model, inputs, lengths, fixtures, behavior, mode)
        modes[mode] = {
            "output": metrics,
            "fixed_decoder": fixed_decoder_result(states, fixtures),
        }
    return modes


def all_output_pass(modes, families, scope="all", required_modes=("float64", "float32", "q8")):
    for mode in required_modes:
        if metric_accuracy(modes[mode]["output"], scope, families) != 1.0:
            return False
    return True


def held_out_fails(modes, families, required_modes=("float64", "float32", "q8")):
    return any(metric_accuracy(modes[mode]["output"], "held_out", families) < 1.0 for mode in required_modes)


def seed_run(seed, config, fixtures, fit_inputs, fit_lengths, fit_labels, all_inputs, all_lengths):
    alphabet = config["input_alphabet"]
    index = {token: value for value, token in enumerate(alphabet)}
    wait_index = index["WAIT"]
    query_indices = {index[token] for token in ("QUERY_DELAY", "QUERY_CORRECTION", "QUERY_ORDER")}
    input_size = len(alphabet)
    width = config["state_width"]

    set_seed(seed)
    candidate = IdentityPreserveCell(input_size, width, wait_index, query_indices)
    train_cell(candidate, fit_inputs, fit_lengths, fit_labels, config, "candidate")
    set_seed(seed)
    parent = IdentityPreserveCell(input_size, width, wait_index, query_indices)
    train_cell(parent, fit_inputs, fit_lengths, fit_labels, config, "parent")
    set_seed(seed)
    stateless = StatelessBaseline(input_size, width)
    train_stateless(stateless, fit_inputs, fit_lengths, fit_labels, config)

    candidate_modes = evaluate_model(candidate, all_inputs, all_lengths, fixtures, "candidate", config)
    parent_modes = evaluate_model(parent, all_inputs, all_lengths, fixtures, "parent", config)
    ablation_modes = {
        "no_preserve": evaluate_model(candidate, all_inputs, all_lengths, fixtures, "no_preserve", config),
        "no_transform": evaluate_model(candidate, all_inputs, all_lengths, fixtures, "no_transform", config),
        "no_recurrence": evaluate_model(candidate, all_inputs, all_lengths, fixtures, "no_recurrence", config),
    }
    stateless_metrics = evaluate_stateless(stateless, all_inputs, all_lengths, fixtures)

    preserve_families = ["preserve_delayed_bit", "preserve_correction", "preserve_order"]
    transform_families = ["transform_correction", "transform_order"]
    candidate_preserve_pass = all_output_pass(candidate_modes, preserve_families)
    candidate_transform_pass = all_output_pass(candidate_modes, transform_families)
    candidate_fixed_decoder_pass = all(candidate_modes[mode]["fixed_decoder"]["pass"] for mode in config["evaluation_modes"]["required"])
    candidate_precision_pass = candidate_preserve_pass and candidate_transform_pass and candidate_fixed_decoder_pass
    candidate_held_out_pass = all_output_pass(candidate_modes, None, scope="held_out")
    parent_held_out_fails = any(metric_accuracy(parent_modes[mode]["output"], "held_out") < 1.0 for mode in config["evaluation_modes"]["required"])
    stateless_held_out_fails = metric_accuracy(stateless_metrics, "held_out") < 1.0
    no_preserve_failed = all(held_out_fails(ablation_modes["no_preserve"], preserve_families + transform_families) for _ in [0])
    no_transform_failed = held_out_fails(ablation_modes["no_transform"], transform_families)
    no_recurrence_failed = held_out_fails(ablation_modes["no_recurrence"], preserve_families + transform_families)

    return {
        "seed": seed,
        "candidate_parameter_count": parameter_count(candidate),
        "stateless_parameter_count": parameter_count(stateless),
        "candidate": {"modes": candidate_modes, "preserve_pass": candidate_preserve_pass, "transform_pass": candidate_transform_pass, "fixed_decoder_pass": candidate_fixed_decoder_pass, "precision_pass": candidate_precision_pass},
        "parent": {"modes": parent_modes, "held_out_fails": parent_held_out_fails},
        "stateless": {"output": stateless_metrics, "held_out_fails": stateless_held_out_fails},
        "ablations": {
            name: {"modes": modes}
            for name, modes in ablation_modes.items()
        },
        "verdict_inputs": {
            "candidate_preserve_pass": candidate_preserve_pass,
            "candidate_transform_pass": candidate_transform_pass,
            "candidate_fixed_decoder_pass": candidate_fixed_decoder_pass,
            "candidate_precision_pass": candidate_precision_pass,
            "parent_opponent_pass": candidate_held_out_pass and parent_held_out_fails,
            "stateless_opponent_pass": candidate_held_out_pass and stateless_held_out_fails,
            "no_preserve_ablation_failed": no_preserve_failed,
            "no_transform_ablation_failed": no_transform_failed,
            "no_recurrence_ablation_failed": no_recurrence_failed,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=EXPERIMENTS / "gri02c_config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/results/gri02c_identity_preserve_receipt.json")
    parser.add_argument("--replay-verified", action="store_true", help="set only after an independent receipt replay matches")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("status") != "IMPLEMENTATION_AUTHORIZED_BEFORE_RUN":
        raise SystemExit("GRI-02C is not in authorized-before-run state")
    b_config_path = args.config.with_name(config["parent_b_config"])
    b_receipt_path = (args.config.parent / config["parent_b_receipt"]).resolve()
    b_harness_path = args.config.with_name(config["parent_b_harness"])
    if digest(b_config_path) != config["parent_b_config_sha256"]:
        raise SystemExit("GRI-02B config hash mismatch")
    if digest(b_receipt_path) != config["parent_b_receipt_sha256"]:
        raise SystemExit("GRI-02B receipt hash mismatch")
    if digest(b_harness_path) != config["parent_b_harness_sha256"]:
        raise SystemExit("GRI-02B harness hash mismatch")
    b_config = json.loads(b_config_path.read_text(encoding="utf-8"))
    b_receipt = json.loads(b_receipt_path.read_text(encoding="utf-8"))
    b_rules_path = b_config_path.with_name(b_config["operation_rules_file"])
    if digest(b_rules_path) != b_config["operation_rules_sha256"]:
        raise SystemExit("GRI-02B operation rules hash mismatch")
    b_rules = json.loads(b_rules_path.read_text(encoding="utf-8"))
    if b_receipt.get("status") != "GRI02B_PREREGISTRATION_READY" or b_receipt.get("candidate_present") is not False:
        raise SystemExit("GRI-02B is not ready or candidate contamination detected")
    fixture_path = b_config_path.with_name(b_config["fixture_bank_file"])
    if digest(fixture_path) != b_config["fixture_bank_sha256"]:
        raise SystemExit("GRI-02B fixture hash mismatch")
    fixture_bank = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixtures = fixture_bank["fixtures"]
    alphabet = config["input_alphabet"]
    if alphabet != fixture_bank["alphabet"]:
        raise SystemExit("candidate alphabet differs from frozen B alphabet")
    if config["transition_class"]["preserve_tokens"] != ["WAIT"]:
        raise SystemExit("identity-preserve class is not frozen to WAIT")
    if set(config["transition_class"]["transform_tokens"]) != set(alphabet) - {"WAIT"}:
        raise SystemExit("transform token class is not the complement of WAIT")
    fit_fixtures = [row for row in fixtures if row["split"] == "fit"]
    fit_inputs, fit_lengths, fit_labels = encode(fit_fixtures, alphabet)
    all_inputs, all_lengths, _ = encode(fixtures, alphabet)

    seed_results = [seed_run(seed, config, fixtures, fit_inputs, fit_lengths, fit_labels, all_inputs, all_lengths) for seed in config["training"]["seeds"]]
    aggregate = {field: all(result["verdict_inputs"][field] for result in seed_results) for field in seed_results[0]["verdict_inputs"]}
    aggregate["harness_pass"] = True
    aggregate["oracle_pass"] = b_receipt["oracle"]["status"] == "PASS"
    aggregate["replay_pass"] = True if args.replay_verified else None
    operation_budget = config["operation_counting"]
    budget_pass = all(
        result["candidate_parameter_count"] == config["architecture"]["parameter_count"]
        and operation_budget["preserve_state_operations"] <= b_rules["parent_gri01_d8"]["recurrent_step"]["total_counted_operations"]
        and operation_budget["transform_state_operations"] <= b_rules["parent_gri01_d8"]["recurrent_step"]["total_counted_operations"]
        and operation_budget["transform_plus_query_operations"] <= b_rules["parent_gri01_d8"]["recurrent_plus_query_total"]
        for result in seed_results
    )
    aggregate["budget_pass"] = budget_pass
    final_verdict = evaluate_future_verdict({field: value for field, value in aggregate.items() if isinstance(value, bool)}, b_config)
    receipt = {
        "unit": config["unit"],
        "status": "EXECUTED",
        "candidate_present": True,
        "candidate_verdict": final_verdict,
        "replay_status": "PASS" if args.replay_verified else "EXTERNAL_REPLAY_REQUIRED",
        "config_sha256": digest(args.config),
        "parent_b_config_sha256": digest(b_config_path),
        "parent_b_receipt_sha256": digest(b_receipt_path),
        "parent_b_harness_sha256": digest(b_harness_path),
        "implementation_sha256": digest(Path(__file__)),
        "scipy_version": scipy.__version__,
        "candidate_declaration": {
            "state_width": config["state_width"],
            "persistent_state_slots": config["persistent_state_slots"],
            "hidden_auxiliary_state": config["hidden_auxiliary_state"],
            "history_buffer": config["history_buffer"],
            "step_counter": config["step_counter"],
            "phase_variable": config["phase_variable"],
            "preserve_parameters": config["preserve_parameters"],
            "transition_class": config["transition_class"],
            "architecture": config["architecture"],
            "selector_accounting": "frozen token-semantic dispatch; external protocol classification, no learned or persistent operation",
        },
        "training": config["training"],
        "operation_counting": config["operation_counting"],
        "evaluation_modes": config["evaluation_modes"],
        "seeds": seed_results,
        "aggregate_verdict_inputs": aggregate,
        "verdict_logic": {"source": "GRI-02B executable verdict function", "result": final_verdict},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(receipt))
    print(json.dumps({
        "unit": receipt["unit"],
        "candidate_verdict": final_verdict,
        "replay_status": receipt["replay_status"],
        "aggregate_verdict_inputs": aggregate,
        "seed_summary": [
            {"seed": result["seed"], "candidate_preserve": result["candidate"]["preserve_pass"], "candidate_transform": result["candidate"]["transform_pass"], "candidate_precision": result["candidate"]["precision_pass"]}
            for result in seed_results
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
