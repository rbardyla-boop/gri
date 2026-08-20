#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_models.data import GraphExample, load_examples
from gri_models.gri05 import build_model
from gri_models.rri01 import (
    ANALYSIS_STEPS,
    GRADIENT_STEPS,
    TRACE_STEPS,
    TRACE_TOLERANCE,
    model_state_equal,
    tensor_state_hash,
    traced_forward,
)
from gri_models.resume import load_checkpoint
from gri_models.train import accuracy
from gri_world0.serialization import read_jsonl

SEEDS = (1337, 1338, 1339, 1340, 1341)
DATASETS = (
    ("iid", "test_iid.jsonl"),
    ("d5", "test_depth_5.jsonl"),
    ("d8", "test_depth_8.jsonl"),
    ("d16", "test_depth_16.jsonl"),
    ("d32", "test_depth_32.jsonl"),
    ("d64", "test_depth_64.jsonl"),
)
LONG_DATASETS = {"d16", "d32", "d64"}
CHECKPOINT_SHA = {
    1337: "5089d045a92ce5423fdcb5fdfaf1f709b6165a77261e6cd74881459a3322d408",
    1338: "e6d493c6ae7a1c7723997257110167d4756e703f2e26ca1f7783186f05622928",
    1339: "f87f61d044fb8e48a5afaa6ca6147251f160170366a1b88b807ff2b7f7d876d0",
    1340: "a47149aa1ee287644836e4a716db09bd45520ef3299ad5ccf11b39923c7c2100",
    1341: "a0cb42e30ef6f75b0ccc9585e0ce2b326f51f09064a817e9b690e001240fa944",
}
CODE_COMMIT = "1fa9208d3b5b2d61eb35cf117d61d5e0a4622693"
WORLD0_MANIFEST_SHA = "611dd85bc3c6bcae0738f0ac040408266ca985dcb62ab9f046937ebed7e4c87e"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cosine(a: torch.Tensor, b: torch.Tensor) -> float:
    denom = float(a.norm().item() * b.norm().item())
    return float(torch.dot(a, b).item() / denom) if denom else 0.0


def path_indices(sample) -> list[int]:
    entities = tuple(sorted(sample.entities))
    local = {entity: i for i, entity in enumerate(entities)}
    graph: dict[int, set[int]] = {entity: set() for entity in entities}
    for fact in sample.facts:
        graph[fact.subject].add(fact.object)
        graph[fact.object].add(fact.subject)
    start, goal = sample.query.subject, sample.query.object
    queue = deque([start])
    previous: dict[int, int | None] = {start: None}
    while queue:
        node = queue.popleft()
        if node == goal:
            break
        for nxt in sorted(graph[node]):
            if nxt not in previous:
                previous[nxt] = node
                queue.append(nxt)
    if goal not in previous:
        return [local[start], local[goal]]
    path = []
    node: int | None = goal
    while node is not None:
        path.append(local[node])
        node = previous[node]
    return list(reversed(path))


def load_records(artifact_dir: Path) -> list[dict]:
    records = []
    for dataset, filename in DATASETS:
        samples = [s for s in read_jsonl(artifact_dir / filename) if not s.contradiction_label]
        examples = load_examples(artifact_dir / filename)
        if len(samples) != len(examples):
            raise RuntimeError(f"sample/example count mismatch for {dataset}")
        for sample, example in zip(samples, examples):
            records.append({
                "dataset": dataset,
                "sample": sample,
                "example": example,
                "path_indices": path_indices(sample),
            })
    return records


def readout_trace(model, example: GraphExample, states: list[torch.Tensor], *, label: int) -> dict:
    predictions = []
    rows = []
    for t in range(1, len(states)):
        logits = model.readout(torch.cat([
            states[t][example.query_subject],
            states[t][example.query_object],
            states[t][example.query_subject] - states[t][example.query_object],
            states[t][example.query_subject] * states[t][example.query_object],
        ], dim=-1))
        probs = torch.softmax(logits, dim=-1)
        pred = int(logits.argmax().item())
        predictions.append(pred)
        true_prob = float(probs[label].item())
        pred_prob = float(probs[pred].item())
        top2 = torch.topk(logits, k=2).values
        entropy = float(-(probs * torch.log(probs.clamp_min(1e-12))).sum().item())
        rows.append({
            "step": t,
            "prediction": pred,
            "correct": pred == label,
            "true_label_probability": true_prob,
            "predicted_label_probability": pred_prob,
            "logit_margin": float((top2[0] - top2[1]).item()),
            "entropy": entropy,
        })
    correct_steps = [i + 1 for i, pred in enumerate(predictions) if pred == label]
    first = min(correct_steps) if correct_steps else None
    last = max(correct_steps) if correct_steps else None
    transitions = [(i + 1, predictions[i], predictions[i + 1]) for i in range(len(predictions) - 1)]
    correct_to_wrong = sum(a == label and b != label for _, a, b in transitions)
    wrong_to_correct = sum(a != label and b == label for _, a, b in transitions)
    longest = current = 0
    for pred in predictions:
        current = current + 1 if pred == label else 0
        longest = max(longest, current)
    stable = None
    for t in correct_steps:
        if all(pred == label for pred in predictions[t - 1:]):
            stable = t
            break
    return {
        "steps": rows,
        "predictions": predictions,
        "first_correct_step": first,
        "last_correct_step": last,
        "correct_to_wrong_transitions": correct_to_wrong,
        "wrong_to_correct_transitions": wrong_to_correct,
        "longest_correct_run": longest,
        "stable_correct_step": stable,
    }


def state_row(states: list[torch.Tensor], t: int, path: list[int]) -> dict:
    current = states[t]
    previous = states[t - 1]
    delta = current - previous
    norms = current.norm(dim=-1)
    residuals = delta.norm(dim=-1)
    relative = residuals / (previous.norm(dim=-1) + 1e-12)
    pairs = []
    for i in range(current.shape[0]):
        for j in range(current.shape[0]):
            if i != j:
                pairs.append(cosine(current[i], current[j]))
    dispersion = float(current.var(dim=0, unbiased=False).mean().item())
    path_set = set(path)
    off = [i for i in range(current.shape[0]) if i not in path_set]
    return {
        "step": t,
        "residual_abs": float(residuals.mean().item()),
        "residual_rel": float(relative.mean().item()),
        "residual_rel_median": float(relative.median().item()),
        "mean_hidden_norm": float(norms.mean().item()),
        "min_hidden_norm": float(norms.min().item()),
        "max_hidden_norm": float(norms.max().item()),
        "finite": bool(torch.isfinite(current).all().item()),
        "off_diagonal_cosine": float(statistics.mean(pairs)) if pairs else 1.0,
        "node_state_dispersion": dispersion,
        "path_state_norm": float(current[path].norm(dim=-1).mean().item()) if path else None,
        "off_path_state_norm": float(current[off].norm(dim=-1).mean().item()) if off else None,
        "endpoint_cosine": cosine(current[0], current[-1]) if current.shape[0] == 2 else cosine(current[path[0]], current[path[-1]]),
        "endpoint_distance": float((current[path[0]] - current[path[-1]]).norm().item()),
    }


def temporal_row(states: list[torch.Tensor], t: int) -> dict:
    flat = states[t].flatten()
    out = {"step": t}
    for lag in (1, 2, 4, 8):
        out[f"cosine_lag_{lag}"] = cosine(flat, states[t - lag].flatten()) if t >= lag else None
    return out


def relation_stats(z_values: list[torch.Tensor], labels: list[int]) -> dict:
    by_class: dict[int, list[torch.Tensor]] = defaultdict(list)
    for z, label in zip(z_values, labels):
        by_class[label].append(z)
    all_z = torch.stack(z_values)
    global_centroid = all_z.mean(dim=0)
    centroids = {label: torch.stack(values).mean(dim=0) for label, values in by_class.items()}
    between = torch.stack([(centroid - global_centroid).pow(2).mean() for centroid in centroids.values()]).mean()
    within_values = []
    for label, values in by_class.items():
        within_values.extend([(value - centroids[label]).pow(2).mean() for value in values])
    within = torch.stack(within_values).mean() if within_values else torch.tensor(0.0)
    return {
        "between_class_variance": float(between.item()),
        "within_class_variance": float(within.item()),
        "separation": float((between / (within + 1e-12)).item()),
        "class_count": len(by_class),
    }


def trace_equivalence(model, records: list[dict]) -> dict:
    checks = []
    with torch.no_grad():
        for record in records[:6]:
            example = record["example"]
            for t in TRACE_STEPS:
                ordinary = model(example, steps=t)
                traced, states = traced_forward(model, example, steps=t)
                checks.append({
                    "sample_id": example.sample_id,
                    "steps": t,
                    "state_count": len(states),
                    "max_abs_error": float((ordinary - traced).abs().max().item()),
                    "equal": bool(torch.allclose(ordinary, traced, atol=TRACE_TOLERANCE, rtol=TRACE_TOLERANCE)),
                })
    return {"tolerance": TRACE_TOLERANCE, "checks": checks, "pass": all(c["equal"] for c in checks)}


def gradient_records(model, records: list[dict]) -> list[dict]:
    output = []
    for record in records:
        example = record["example"]
        path = set(record["path_indices"])
        with torch.enable_grad():
            for t in GRADIENT_STEPS:
                h0 = model.initialize(example).detach().requires_grad_(True)
                h = h0
                edges = example.edges.to(h.device)
                for _ in range(t):
                    h = model.recurrent_step(h, edges)
                logits = model.readout(torch.cat([
                    h[example.query_subject], h[example.query_object],
                    h[example.query_subject] - h[example.query_object],
                    h[example.query_subject] * h[example.query_object],
                ], dim=-1))
                gradient = torch.autograd.grad(logits[example.label], h0, retain_graph=False, create_graph=False)[0]
                norms = gradient.norm(dim=-1)
                path_nodes = sorted(path)
                off_nodes = [i for i in range(h0.shape[0]) if i not in path]
                output.append({
                    "sample_id": example.sample_id,
                    "dataset": record["dataset"],
                    "step": t,
                    "total_norm": float(gradient.norm().item()),
                    "subject_norm": float(norms[example.query_subject].item()),
                    "object_norm": float(norms[example.query_object].item()),
                    "path_norm": float(norms[path_nodes].mean().item()) if path_nodes else None,
                    "off_path_norm": float(norms[off_nodes].mean().item()) if off_nodes else None,
                })
    return output


def mean_curve(rows: list[dict], key: str) -> list[dict]:
    out = []
    for t in ANALYSIS_STEPS:
        values = [r[key] for r in rows if r["step"] == t and r[key] is not None]
        out.append({"step": t, "mean": statistics.mean(values) if values else None, "count": len(values)})
    return out


def gradient_curve(rows: list[dict], key: str = "total_norm") -> list[dict]:
    out = []
    for t in GRADIENT_STEPS:
        values = [r[key] for r in rows if r["step"] == t]
        out.append({"step": t, "mean": statistics.mean(values), "count": len(values)})
    return out


def accuracy_curve(outcomes: list[dict]) -> list[dict]:
    return [{"step": t, "accuracy": statistics.mean(o["predictions"][t - 1] == o["label"] for o in outcomes)} for t in ANALYSIS_STEPS]


def signature_report(summary: dict) -> dict:
    accuracy = [r["accuracy"] for r in summary["accuracy_curve"]]
    peak = max(accuracy)
    peak_step = accuracy.index(peak) + 1
    final = accuracy[-1]
    degradation = peak - final
    long_outcomes = [o for o in summary["sample_outcomes"] if o["dataset"] in LONG_DATASETS]
    overthinking_count = sum(o["first_correct_step"] is not None and o["correct_to_wrong_transitions"] > 0 for o in long_outcomes)
    overthinking = degradation >= 0.20 and overthinking_count / max(1, len(long_outcomes)) >= 0.25

    state = summary["state_curve"]
    ref_dispersion = next(r["mean"] for r in state["node_state_dispersion"] if r["step"] == 1)
    oversmooth = any(
        r["mean"] >= 0.90 and r["mean"] <= ref_dispersion * 0 + 1.0 and
        next(a["accuracy"] for a in summary["accuracy_curve"] if a["step"] == r["step"]) <= peak - 0.20 and
        next(d["mean"] for d in state["node_state_dispersion"] if d["step"] == r["step"]) <= ref_dispersion * 0.5
        for r in state["off_diagonal_cosine"]
    )

    stall_steps = []
    for r in state["residual_rel_median"]:
        t = r["step"]
        if r["mean"] < 1e-3 and t <= 112:
            unresolved = sum(
                o["dataset"] in LONG_DATASETS and all(not x for x in o["correct_flags"][t - 1:t + 15])
                for o in long_outcomes
            )
            if unresolved / max(1, len(long_outcomes)) >= 0.25:
                stall_steps.append(t)
    stall = bool(stall_steps)

    early_norm = next(r["mean"] for r in state["mean_hidden_norm"] if r["step"] == 1)
    early_residual = next(r["mean"] for r in state["residual_abs"] if r["step"] == 1)
    instability = any(not r["all_finite"] for r in state["finite"]) or any(
        r["mean"] >= early_norm * 10 or r["mean"] >= early_residual * 10 for r in state["mean_hidden_norm"] + state["residual_abs"]
    )

    sep = summary["relation_curve"]
    peak_sep = max(r["separation"] for r in sep)
    relation_erase = any(
        r["separation"] <= peak_sep * 0.5 and
        next(a["accuracy"] for a in summary["accuracy_curve"] if a["step"] == r["step"]) <= peak - 0.20
        for r in sep
    )
    readout_mismatch = any(
        next(a["accuracy"] for a in summary["accuracy_curve"] if a["step"] == r["step"]) <= peak - 0.20 and
        r["separation"] >= peak_sep * 0.8
        for r in sep
    )
    gradient = summary["gradient_curve"]
    grad_ref = gradient[0]["mean"]
    gradient_decay = any(r["mean"] <= grad_ref / 100 and next(a["accuracy"] for a in summary["accuracy_curve"] if a["step"] == r["step"]) <= peak - 0.20 for r in gradient)
    signatures = {
        "overthinking_state_erosion": overthinking,
        "oversmoothing": oversmooth,
        "update_stall": stall,
        "dynamical_instability": instability,
        "relation_erasure": relation_erase and not oversmooth,
        "readout_mismatch": readout_mismatch,
        "gradient_influence_decay": gradient_decay,
    }
    return {
        "peak_accuracy": peak,
        "peak_step": peak_step,
        "final_accuracy": final,
        "degradation": degradation,
        "long_sample_correct_to_wrong_fraction": overthinking_count / max(1, len(long_outcomes)),
        "stall_steps": stall_steps,
        "peak_separation": peak_sep,
        "signatures": signatures,
    }


def analyze_seed(seed: int, artifact_dir: Path, output_root: Path) -> dict:
    checkpoint = output_root.parent.parent / "rri01r" / "checkpoints" / f"baseline_seed{seed}_final.pt"
    if not checkpoint.exists():
        checkpoint = ROOT / "artifacts/rri01r/checkpoints" / f"baseline_seed{seed}_final.pt"
    observed_checkpoint_sha = sha256(checkpoint)
    if observed_checkpoint_sha != CHECKPOINT_SHA[seed]:
        raise RuntimeError(f"checkpoint hash mismatch for {seed}")
    payload = load_checkpoint(checkpoint)
    model = build_model("baseline", seed)
    model.load_state_dict(payload["model_state"])
    model.eval()
    before_state = {k: v.clone() for k, v in model.state_dict().items()}
    records = load_records(artifact_dir)
    equivalence = trace_equivalence(model, records)
    if not equivalence["pass"]:
        raise RuntimeError(f"trace equivalence failed for seed {seed}")

    trace_path = output_root / f"seed{seed}_trace.jsonl"
    summaries = []
    relation_z: dict[int, list[torch.Tensor]] = defaultdict(list)
    relation_labels: dict[int, list[int]] = defaultdict(list)
    state_rows = []
    temporal_rows = []
    outcomes = []
    raw_handle = trace_path.open("w", encoding="utf-8")
    try:
        with torch.no_grad():
            for record in records:
                example = record["example"]
                _, states = traced_forward(model, example, steps=128)
                readout = readout_trace(model, example, states, label=example.label)
                outcomes.append({
                    "sample_id": example.sample_id,
                    "dataset": record["dataset"],
                    "chain_length": example.chain_length,
                    "label": example.label,
                    "predictions": readout["predictions"],
                    "correct_flags": [s["correct"] for s in readout["steps"]],
                    "first_correct_step": readout["first_correct_step"],
                    "last_correct_step": readout["last_correct_step"],
                    "correct_to_wrong_transitions": readout["correct_to_wrong_transitions"],
                    "wrong_to_correct_transitions": readout["wrong_to_correct_transitions"],
                    "longest_correct_run": readout["longest_correct_run"],
                    "stable_correct_step": readout["stable_correct_step"],
                })
                for t in ANALYSIS_STEPS:
                    sr = state_row(states, t, record["path_indices"])
                    tr = temporal_row(states, t)
                    rr = readout["steps"][t - 1]
                    z = torch.cat([states[t][example.query_subject], states[t][example.query_object], states[t][example.query_subject] - states[t][example.query_object]])
                    relation_z[t].append(z)
                    relation_labels[t].append(example.label)
                    state_rows.append(sr)
                    temporal_rows.append(tr)
                    raw_handle.write(json.dumps({
                        "sample_id": example.sample_id,
                        "dataset": record["dataset"],
                        "chain_length": example.chain_length,
                        "step": t,
                        "prediction": rr["prediction"],
                        "correct": rr["correct"],
                        "true_label_probability": rr["true_label_probability"],
                        "predicted_label_probability": rr["predicted_label_probability"],
                        "logit_margin": rr["logit_margin"],
                        "entropy": rr["entropy"],
                        **sr,
                        **tr,
                    }, sort_keys=True, separators=(",", ":")) + "\n")
    finally:
        raw_handle.close()

    gradients = gradient_records(model, records)
    assert all(p.grad is None for p in model.parameters())
    relation_curve = []
    for t in ANALYSIS_STEPS:
        relation_curve.append({"step": t, **relation_stats(relation_z[t], relation_labels[t])})
    state_curve = {key: mean_curve(state_rows, key) for key in ("residual_abs", "residual_rel", "residual_rel_median", "mean_hidden_norm", "min_hidden_norm", "max_hidden_norm", "off_diagonal_cosine", "node_state_dispersion", "path_state_norm", "off_path_state_norm", "endpoint_cosine", "endpoint_distance")}
    state_curve["finite"] = [{"step": t, "all_finite": all(r["finite"] for r in state_rows if r["step"] == t)} for t in ANALYSIS_STEPS]
    summary = {
        "seed": seed,
        "checkpoint_sha256": observed_checkpoint_sha,
        "model_state_hash_before": tensor_state_hash(before_state),
        "trace_equivalence": equivalence,
        "sample_count": len(records),
        "datasets": {dataset: sum(r["dataset"] == dataset for r in records) for dataset, _ in DATASETS},
        "sample_outcomes": outcomes,
        "accuracy_curve": accuracy_curve(outcomes),
        "state_curve": state_curve,
        "temporal_curve": [{"step": t, **{k: statistics.mean([r[k] for r in temporal_rows if r["step"] == t and r[k] is not None]) for k in ("cosine_lag_1", "cosine_lag_2", "cosine_lag_4", "cosine_lag_8") if any(r["step"] == t and r[k] is not None for r in temporal_rows)}} for t in ANALYSIS_STEPS],
        "relation_curve": relation_curve,
        "gradient_records": gradients,
        "gradient_curve": gradient_curve(gradients),
        "path_message_norm": "NOT_AVAILABLE",
    }
    summary["diagnostic_signatures"] = signature_report(summary)
    after_state = model.state_dict()
    summary["model_state_hash_after"] = tensor_state_hash(after_state)
    summary["model_immutable"] = model_state_equal(before_state, after_state) and summary["model_state_hash_before"] == summary["model_state_hash_after"]
    if not summary["model_immutable"]:
        raise RuntimeError(f"model mutated for seed {seed}")
    path = output_root / f"seed{seed}_summary.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def aggregate_summaries(summaries: list[dict]) -> dict:
    signature_names = tuple(summaries[0]["diagnostic_signatures"]["signatures"])
    counts = {name: sum(s["diagnostic_signatures"]["signatures"][name] for s in summaries) for name in signature_names}
    primary_candidates = [
        ("overthinking_state_erosion", "RRI_01_OVERTHINKING_STATE_EROSION"),
        ("oversmoothing", "RRI_01_OVERSMOOTHING"),
        ("update_stall", "RRI_01_UPDATE_STALL"),
        ("dynamical_instability", "RRI_01_DYNAMICAL_INSTABILITY"),
        ("relation_erasure", "RRI_01_RELATION_ERASURE"),
        ("readout_mismatch", "RRI_01_READOUT_MISMATCH"),
        ("gradient_influence_decay", "RRI_01_GRADIENT_INFLUENCE_DECAY"),
    ]
    eligible = [(count, name, verdict) for name, verdict in primary_candidates if (count := counts[name]) >= 4]
    terminal = max(eligible)[2] if eligible else "RRI_01_FAILURE_MODE_UNRESOLVED"
    def avg_curve(curves: list[list[dict]], value_key: str):
        rows = []
        for t in ANALYSIS_STEPS:
            values = [next(x for x in curve if x["step"] == t)[value_key] for curve in curves]
            rows.append({"step": t, "mean": statistics.mean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0})
        return rows
    return {
        "seed_count": len(summaries),
        "seeds": [s["seed"] for s in summaries],
        "signature_counts": counts,
        "signature_fractions": {k: v / len(summaries) for k, v in counts.items()},
        "terminal_verdict": terminal,
        "model_immutability_all": all(s["model_immutable"] for s in summaries),
        "trace_equivalence_all": all(s["trace_equivalence"]["pass"] for s in summaries),
        "accuracy_curve": avg_curve([s["accuracy_curve"] for s in summaries], "accuracy"),
        "residual_abs_curve": avg_curve([s["state_curve"]["residual_abs"] for s in summaries], "mean"),
        "per_seed_peak_and_final": [{"seed": s["seed"], **{k: s["diagnostic_signatures"][k] for k in ("peak_accuracy", "peak_step", "final_accuracy", "degradation")}} for s in summaries],
        "per_seed_signatures": [{"seed": s["seed"], **s["diagnostic_signatures"]["signatures"]} for s in summaries],
    }


def write_manifest(root: Path) -> None:
    entries = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            entries[str(path.relative_to(ROOT))] = sha256(path)
    (root / "SHA256SUMS.json").write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/frozen/world0_v0_1")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/rri01")
    parser.add_argument("--seed", type=int, choices=SEEDS, action="append")
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.output_root.mkdir(parents=True, exist_ok=True)
    seeds = tuple(args.seed) if args.seed else SEEDS
    records = load_records(args.artifact_dir)
    config = {
        "unit": "RRI-01", "code_commit": CODE_COMMIT, "seeds": list(seeds),
        "datasets": [name for name, _ in DATASETS], "analysis_steps": list(ANALYSIS_STEPS),
        "trace_steps": list(TRACE_STEPS), "gradient_steps": list(GRADIENT_STEPS),
        "trace_tolerance": TRACE_TOLERANCE, "device": "cpu", "torch_threads": 1,
        "no_training": True, "primary_threshold_requires_4_of_5": True,
    }
    (args.output_root / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checkpoint_manifest = {str(seed): {"path": str((ROOT / "artifacts/rri01r/checkpoints" / f"baseline_seed{seed}_final.pt").relative_to(ROOT)), "sha256": CHECKPOINT_SHA[seed]} for seed in seeds}
    (args.output_root / "checkpoint_manifest.json").write_text(json.dumps(checkpoint_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summaries = [analyze_seed(seed, args.artifact_dir, args.output_root) for seed in seeds]
    if len(summaries) == len(SEEDS):
        aggregate = aggregate_summaries(summaries)
        (args.output_root / "aggregate.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        diagnosis = {"terminal_verdict": aggregate["terminal_verdict"], "signature_counts": aggregate["signature_counts"], "per_seed_signatures": aggregate["per_seed_signatures"], "primary_requires_4_of_5": True}
        (args.output_root / "RRI01_DIAGNOSIS.json").write_text(json.dumps(diagnosis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lines = ["# RRI-01 — Depth-Failure Archaeology", "", f"Terminal verdict: `{aggregate['terminal_verdict']}`", "", "## Per-seed diagnostic signatures", ""]
        for row in aggregate["per_seed_signatures"]:
            active = [key for key, value in row.items() if key != "seed" and value]
            lines.append(f"- Seed {row['seed']}: {', '.join(active) if active else 'none'}")
        lines.extend(["", "## Signature counts", ""])
        for name, count in aggregate["signature_counts"].items():
            lines.append(f"- `{name}`: {count}/5")
        lines.extend(["", "## Controls", "", f"- Trace equivalence: `{aggregate['trace_equivalence_all']}`", f"- Model immutable: `{aggregate['model_immutability_all']}`", "- Training/optimizer updates: none", "", "RRI-01 is diagnostic only. No repair or RRI-02 work is authorized by this report."])
        (args.output_root / "RRI01_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        write_manifest(args.output_root)
        print(aggregate["terminal_verdict"])
    else:
        print(f"RRI01_SINGLE_SEED_ANALYSIS_COMPLETE {seeds[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
