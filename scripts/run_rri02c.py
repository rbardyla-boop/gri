#!/usr/bin/env python3
"""Replicate frozen RRI-01 archaeology on the RRI-02B checkpoints."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))

import run_rri01 as frozen
from gri_models.data import load_examples
from gri_models.gri05 import build_model
from gri_models.resume import load_checkpoint
from gri_models.rri01 import model_state_equal, tensor_state_hash, traced_forward
from gri_world0.serialization import read_jsonl


ARTIFACT_DIR = ROOT / "artifacts/frozen/world0_v0_1"
INPUT_DIR = ROOT / "artifacts/rri02b"
OUTPUT_DIR = ROOT / "artifacts/rri02c"
CHECKPOINT_DIR = INPUT_DIR / "checkpoints"
SEEDS = (1337, 1338, 1339, 1340, 1341)
LONG_DATASETS = {"d16", "d32", "d64"}
EXPECTED_BASELINE_ACCURACY = {
    1: 0.9472222222222222,
    4: 1.0,
    8: 0.975,
    16: 0.8111111111111111,
    32: 0.6555555555555556,
    64: 0.6027777777777777,
    128: 0.5333333333333333,
}
EXPECTED_BASELINE_SIGNATURES = {
    "relation_erasure": 5,
    "overthinking_state_erosion": 5,
    "update_stall": 4,
    "readout_mismatch": 1,
    "oversmoothing": 0,
    "dynamical_instability": 0,
    "gradient_influence_decay": 0,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def current_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def load_and_verify_checkpoints() -> dict[tuple[str, int], Path]:
    manifest = json.loads((INPUT_DIR / "SHA256SUMS.json").read_text())
    paths: dict[tuple[str, int], Path] = {}
    for kind in ("baseline", "anchor"):
        for seed in SEEDS:
            relative = f"artifacts/rri02b/checkpoints/{kind}_seed{seed}_final.pt"
            path = ROOT / relative
            expected = manifest.get(relative)
            if expected is None or sha256(path) != expected:
                raise RuntimeError(f"RRI-02C checkpoint hash mismatch: {relative}")
            payload = load_checkpoint(path)
            if payload.get("epoch") != 80 or payload.get("checkpoint_status") != "final":
                raise RuntimeError(f"RRI-02C checkpoint is not final: {relative}")
            if payload.get("model_kind") != kind or payload.get("seed") != seed:
                raise RuntimeError(f"RRI-02C checkpoint identity mismatch: {relative}")
            paths[(kind, seed)] = path
    return paths


class AnchorAnalysisAdapter(torch.nn.Module):
    """Expose the frozen RRI-01 call shape while carrying the current anchor."""

    def __init__(self, base: torch.nn.Module):
        super().__init__()
        self.base = base
        self._anchor: torch.Tensor | None = None

    @property
    def readout(self):
        return self.base.readout

    def initialize(self, example):
        h = self.base.initialize(example)
        self._anchor = self.base.make_anchor(h)
        return h

    def recurrent_step(self, h: torch.Tensor, edges: torch.Tensor) -> torch.Tensor:
        if self._anchor is None:
            raise RuntimeError("anchor analysis step called before initialize")
        return self.base.recurrent_step(h, edges, self._anchor)

    def forward(self, example, steps: int = 4):
        return self.base(example, steps=steps)


def custom_gradient_records(model, records: list[dict]) -> list[dict]:
    output = []
    for record in records:
        example = record["example"]
        path = set(record["path_indices"])
        with torch.enable_grad():
            for steps in frozen.GRADIENT_STEPS:
                h0 = model.base.initialize(example).detach().requires_grad_(True)
                anchor = model.base.make_anchor(h0)
                h = h0
                edges = example.edges.to(h.device)
                for _ in range(steps):
                    h = model.base.recurrent_step(h, edges, anchor)
                logits = model.base.readout(torch.cat([
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
                    "step": steps,
                    "total_norm": float(gradient.norm().item()),
                    "subject_norm": float(norms[example.query_subject].item()),
                    "object_norm": float(norms[example.query_object].item()),
                    "path_norm": float(norms[path_nodes].mean().item()) if path_nodes else None,
                    "off_path_norm": float(norms[off_nodes].mean().item()) if off_nodes else None,
                })
    return output


def answer_persistence(outcomes: list[dict]) -> dict:
    eligible = [o for o in outcomes if o["dataset"] in LONG_DATASETS]
    values = []
    for outcome in eligible:
        first = outcome["first_correct_step"]
        if first is None or first >= len(outcome["correct_flags"]):
            continue
        later = outcome["correct_flags"][first:]
        values.append(sum(later) / len(later))
    return {
        "eligible_long_trajectories": len(eligible),
        "trajectories_with_first_correct_and_later_steps": len(values),
        "mean_persistence_after_first_correct": statistics.mean(values) if values else None,
        "definition": "correct flags from the step after first_correct_step through step 128",
    }


def cti(outcomes: list[dict]) -> dict:
    eligible = [o for o in outcomes if o["dataset"] in LONG_DATASETS]
    events = sum(o["correct_to_wrong_transitions"] for o in eligible)
    trajectories = sum(o["correct_to_wrong_transitions"] > 0 for o in eligible)
    denominator = len(eligible)
    return {
        "eligible_long_trajectories": denominator,
        "correct_to_incorrect_transition_events": events,
        "trajectories_with_correct_to_incorrect_transition": trajectories,
        "cti_rate": events / denominator if denominator else 0.0,
        "cti_trajectory_fraction": trajectories / denominator if denominator else 0.0,
        "definition": "eligible trajectories are the unchanged RRI-01 d16/d32/d64 sample trajectories; primary CTI rate is transition events divided by eligible trajectories",
    }


def analyze_seed(kind: str, seed: int, checkpoint: Path, records: list[dict], output_root: Path) -> dict:
    base = build_model(kind, seed)
    payload = load_checkpoint(checkpoint)
    base.load_state_dict(payload["model_state"])
    base.eval()
    before = {k: v.detach().cpu().clone() for k, v in base.state_dict().items()}
    model = AnchorAnalysisAdapter(base) if kind == "anchor" else base
    model.eval()

    equivalence = frozen.trace_equivalence(model, records)
    if not equivalence["pass"]:
        raise RuntimeError(f"RRI-02C trace equivalence failed for {kind} seed {seed}")

    trace_path = output_root / f"{kind}_seed{seed}_trace.jsonl"
    relation_z: dict[int, list[torch.Tensor]] = {}
    relation_labels: dict[int, list[int]] = {}
    state_rows = []
    temporal_rows = []
    outcomes = []
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("w", encoding="utf-8") as raw_handle:
        with torch.no_grad():
            for record in records:
                example = record["example"]
                _, states = traced_forward(model, example, steps=128)
                readout = frozen.readout_trace(model, example, states, label=example.label)
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
                for t in frozen.ANALYSIS_STEPS:
                    sr = frozen.state_row(states, t, record["path_indices"])
                    tr = frozen.temporal_row(states, t)
                    rr = readout["steps"][t - 1]
                    z = torch.cat([
                        states[t][example.query_subject],
                        states[t][example.query_object],
                        states[t][example.query_subject] - states[t][example.query_object],
                    ])
                    relation_z.setdefault(t, []).append(z)
                    relation_labels.setdefault(t, []).append(example.label)
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

    gradients = frozen.gradient_records(base, records) if kind == "baseline" else custom_gradient_records(model, records)
    if any(p.grad is not None for p in base.parameters()):
        raise RuntimeError(f"parameter gradient leakage for {kind} seed {seed}")
    relation_curve = [{"step": t, **frozen.relation_stats(relation_z[t], relation_labels[t])} for t in frozen.ANALYSIS_STEPS]
    state_curve = {
        key: frozen.mean_curve(state_rows, key)
        for key in ("residual_abs", "residual_rel", "residual_rel_median", "mean_hidden_norm", "min_hidden_norm", "max_hidden_norm", "off_diagonal_cosine", "node_state_dispersion", "path_state_norm", "off_path_state_norm", "endpoint_cosine", "endpoint_distance")
    }
    state_curve["finite"] = [{"step": t, "all_finite": all(r["finite"] for r in state_rows if r["step"] == t)} for t in frozen.ANALYSIS_STEPS]
    temporal_curve = [{
        "step": t,
        **{
            key: statistics.mean([r[key] for r in temporal_rows if r["step"] == t and r[key] is not None])
            for key in ("cosine_lag_1", "cosine_lag_2", "cosine_lag_4", "cosine_lag_8")
            if any(r["step"] == t and r[key] is not None for r in temporal_rows)
        },
    } for t in frozen.ANALYSIS_STEPS]
    summary = {
        "unit": "RRI-02C",
        "model": kind,
        "seed": seed,
        "checkpoint_sha256": sha256(checkpoint),
        "model_state_hash_before": tensor_state_hash(before),
        "trace_equivalence": equivalence,
        "sample_count": len(records),
        "datasets": {dataset: sum(r["dataset"] == dataset for r in records) for dataset, _ in frozen.DATASETS},
        "sample_outcomes": outcomes,
        "accuracy_curve": frozen.accuracy_curve(outcomes),
        "state_curve": state_curve,
        "temporal_curve": temporal_curve,
        "relation_curve": relation_curve,
        "gradient_records": gradients,
        "gradient_curve": frozen.gradient_curve(gradients),
        "path_message_norm": "NOT_AVAILABLE",
        "diagnostic_signatures": None,
        "answer_persistence": answer_persistence(outcomes),
        "cti": cti(outcomes),
    }
    summary["diagnostic_signatures"] = frozen.signature_report(summary)
    after = {k: v.detach().cpu().clone() for k, v in base.state_dict().items()}
    summary["model_state_hash_after"] = tensor_state_hash(after)
    summary["model_immutable"] = model_state_equal(before, after) and summary["model_state_hash_before"] == summary["model_state_hash_after"]
    if not summary["model_immutable"]:
        raise RuntimeError(f"model mutated for {kind} seed {seed}")
    write_json(output_root / f"{kind}_seed{seed}_summary.json", summary)
    return summary


def replication_check(baseline_aggregate: dict) -> dict:
    selected = {}
    for step, expected in EXPECTED_BASELINE_ACCURACY.items():
        observed = next(row["mean"] for row in baseline_aggregate["accuracy_curve"] if row["step"] == step)
        selected[str(step)] = {"observed": observed, "expected": expected, "equal": math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12)}
    signatures = baseline_aggregate["signature_counts"]
    signature_check = {name: {"observed": signatures[name], "expected": value, "equal": signatures[name] == value} for name, value in EXPECTED_BASELINE_SIGNATURES.items()}
    passed = all(x["equal"] for x in selected.values()) and all(x["equal"] for x in signature_check.values()) and baseline_aggregate["model_immutability_all"] and baseline_aggregate["trace_equivalence_all"]
    return {"accuracy": selected, "signature_counts": signature_check, "model_immutability": baseline_aggregate["model_immutability_all"], "trace_equivalence": baseline_aggregate["trace_equivalence_all"], "pass": passed}


def cti_aggregate(baseline: list[dict], anchor: list[dict]) -> dict:
    rows = []
    for b, a in zip(sorted(baseline, key=lambda x: x["seed"]), sorted(anchor, key=lambda x: x["seed"])):
        rows.append({
            "seed": b["seed"],
            "baseline_cti_rate": b["cti"]["cti_rate"],
            "anchor_cti_rate": a["cti"]["cti_rate"],
            "baseline_cti_trajectory_fraction": b["cti"]["cti_trajectory_fraction"],
            "anchor_cti_trajectory_fraction": a["cti"]["cti_trajectory_fraction"],
            "cti_rate_anchor_minus_baseline": a["cti"]["cti_rate"] - b["cti"]["cti_rate"],
            "baseline_persistence_after_first_correct": b["answer_persistence"]["mean_persistence_after_first_correct"],
            "anchor_persistence_after_first_correct": a["answer_persistence"]["mean_persistence_after_first_correct"],
        })
    baseline_mean = statistics.mean(r["baseline_cti_rate"] for r in rows)
    anchor_mean = statistics.mean(r["anchor_cti_rate"] for r in rows)
    reduction = (baseline_mean - anchor_mean) / baseline_mean if baseline_mean else 0.0
    return {
        "paired": rows,
        "mean_baseline_cti_rate": baseline_mean,
        "mean_anchor_cti_rate": anchor_mean,
        "mean_reduction_fraction": reduction,
        "m1_pass": anchor_mean <= 0.80 * baseline_mean,
        "m2_anchor_lower_seed_count": sum(r["anchor_cti_rate"] < r["baseline_cti_rate"] for r in rows),
        "m2_pass": sum(r["anchor_cti_rate"] < r["baseline_cti_rate"] for r in rows) >= 4,
    }


def manifest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }


def report_markdown(config: dict, baseline_aggregate: dict, anchor_aggregate: dict, replication: dict, cti_report: dict, verdict: dict) -> str:
    rows = [
        "# RRI-02C — Immutable Anchor Mechanism Replication",
        "",
        f"Analysis commit: `{config['analysis_commit']}`",
        "",
        "## Baseline replication",
        "",
        f"Replication gate: **{'PASS' if replication['pass'] else 'FAIL'}**",
        "",
        "| Step | Baseline accuracy | Anchor accuracy |",
        "|---:|---:|---:|",
    ]
    for step in (1, 4, 8, 16, 32, 64, 128):
        b = next(x["mean"] for x in baseline_aggregate["accuracy_curve"] if x["step"] == step)
        a = next(x["mean"] for x in anchor_aggregate["accuracy_curve"] if x["step"] == step)
        rows.append(f"| {step} | {b:.8f} | {a:.8f} |")
    rows += ["", "## CTI mechanism gate", "", "| Seed | Baseline CTI | Anchor CTI | Anchor − baseline |", "|---:|---:|---:|---:|"]
    for row in cti_report["paired"]:
        rows.append(f"| {row['seed']} | {row['baseline_cti_rate']:.8f} | {row['anchor_cti_rate']:.8f} | {row['cti_rate_anchor_minus_baseline']:.8f} |")
    rows += [
        "",
        f"Mean baseline CTI: `{cti_report['mean_baseline_cti_rate']:.8f}`",
        f"Mean anchor CTI: `{cti_report['mean_anchor_cti_rate']:.8f}`",
        f"Mean reduction: `{cti_report['mean_reduction_fraction']:.8f}`",
        f"M1: **{'PASS' if cti_report['m1_pass'] else 'FAIL'}**",
        f"M2: **{'PASS' if cti_report['m2_pass'] else 'FAIL'}** ({cti_report['m2_anchor_lower_seed_count']}/5)",
        "",
        "## Signature counts",
        "",
        "| Signature | Baseline | Anchor |",
        "|---|---:|---:|",
    ]
    names = tuple(baseline_aggregate["signature_counts"])
    for name in names:
        rows.append(f"| {name} | {baseline_aggregate['signature_counts'][name]}/5 | {anchor_aggregate['signature_counts'][name]}/5 |")
    rows += ["", "## Seed 1341", "", "Seed 1341 was retained. Its paired CTI and persistence values are recorded in `paired_cti.json`; no post-hoc exclusion or tuning was performed.", "", "## Terminal verdict", "", f"`{verdict['terminal_verdict']}`", "", "No training, optimizer step, or RRI-02D work was performed."]
    return "\n".join(rows) + "\n"


def main() -> int:
    torch.set_num_threads(1)
    output = OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_paths = load_and_verify_checkpoints()
    records = frozen.load_records(ARTIFACT_DIR)
    analysis_commit = current_commit()
    config = {
        "unit": "RRI-02C",
        "analysis_commit": analysis_commit,
        "rri02b_code_commit": "ae0a0d34de1f97e842296e6dcb9af2acb9c34c84",
        "rri02b_evidence_commit": "2ffcf03",
        "rri01_preregistration": "8eb8a5f",
        "rri01_evidence": "0b0ebcb",
        "datasets": [name for name, _ in frozen.DATASETS],
        "analysis_steps": list(frozen.ANALYSIS_STEPS),
        "trace_steps": list(frozen.TRACE_STEPS),
        "gradient_steps": list(frozen.GRADIENT_STEPS),
        "trace_tolerance": frozen.TRACE_TOLERANCE,
        "device": "cpu",
        "torch_threads": 1,
        "no_training": True,
        "no_optimizer_steps": True,
        "seeds": list(SEEDS),
        "cti_definition": "correct-to-incorrect transition events divided by eligible d16/d32/d64 trajectories",
        "m1": "mean CTI anchor <= 0.80 * mean CTI baseline",
        "m2": "anchor CTI lower than baseline for at least 4/5 paired seeds",
    }
    write_json(output / "RRI02C_CONFIG.json", config)
    write_json(output / "checkpoint_manifest.json", {
        f"{kind}_seed{seed}": {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
        }
        for (kind, seed), path in sorted(checkpoint_paths.items())
    })

    baseline_summaries = [analyze_seed("baseline", seed, checkpoint_paths[("baseline", seed)], records, output) for seed in SEEDS]
    baseline_aggregate = frozen.aggregate_summaries(baseline_summaries)
    replication = replication_check(baseline_aggregate)
    write_json(output / "baseline_replication.json", replication)
    if not replication["pass"]:
        raise RuntimeError("RRI_02C_BASELINE_REPLICATION_FAIL")

    anchor_summaries = [analyze_seed("anchor", seed, checkpoint_paths[("anchor", seed)], records, output) for seed in SEEDS]
    anchor_aggregate = frozen.aggregate_summaries(anchor_summaries)
    cti_report = cti_aggregate(baseline_summaries, anchor_summaries)
    write_json(output / "paired_cti.json", cti_report)
    aggregate = {
        "baseline": baseline_aggregate,
        "anchor": anchor_aggregate,
        "paired_cti": cti_report,
        "baseline_replication": replication,
    }
    write_json(output / "aggregate.json", aggregate)

    replay_results = {}
    with tempfile.TemporaryDirectory(prefix="rri02c-replay-") as temp:
        replay_root = Path(temp)
        for kind in ("baseline", "anchor"):
            replay_summary = analyze_seed(kind, 1337, checkpoint_paths[(kind, 1337)], records, replay_root)
            original_summary = output / f"{kind}_seed1337_summary.json"
            original_trace = output / f"{kind}_seed1337_trace.jsonl"
            replay_summary_path = replay_root / f"{kind}_seed1337_summary.json"
            replay_trace_path = replay_root / f"{kind}_seed1337_trace.jsonl"
            replay_results[kind] = {
                "summary_byte_identical": original_summary.read_bytes() == replay_summary_path.read_bytes(),
                "trace_byte_identical": original_trace.read_bytes() == replay_trace_path.read_bytes(),
                "summary_sha256": sha256(replay_summary_path),
                "trace_sha256": sha256(replay_trace_path),
            }
    replay_pass = all(v["summary_byte_identical"] and v["trace_byte_identical"] for v in replay_results.values())
    replay_results["pass"] = replay_pass
    write_json(output / "replay.json", replay_results)
    if not replay_pass:
        raise RuntimeError("RRI_02C_REPLAY_INVALID")

    m1 = cti_report["m1_pass"]
    m2 = cti_report["m2_pass"]
    terminal = "RRI_02C_ANCHOR_MECHANISM_SUPPORTED" if m1 and m2 else "RRI_02C_PERFORMANCE_ONLY_MECHANISM_UNESTABLISHED"
    diagnosis = {
        "terminal_verdict": terminal,
        "baseline_replication": "PASS",
        "checkpoint_integrity": "PASS",
        "model_immutability": all(s["model_immutable"] for s in baseline_summaries + anchor_summaries),
        "replay": "PASS",
        "m1": m1,
        "m2": m2,
        "mean_cti_reduction_fraction": cti_report["mean_reduction_fraction"],
        "signature_counts": {
            "baseline": baseline_aggregate["signature_counts"],
            "anchor": anchor_aggregate["signature_counts"],
        },
        "no_training": True,
    }
    write_json(output / "RRI02C_DIAGNOSIS.json", diagnosis)
    (output / "RRI02C_REPORT.md").write_text(report_markdown(config, baseline_aggregate, anchor_aggregate, replication, cti_report, diagnosis), encoding="utf-8")
    write_json(output / "SHA256SUMS.json", manifest(output))
    print(terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
