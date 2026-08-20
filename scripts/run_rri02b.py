#!/usr/bin/env python3
"""Run the preregistered RRI-02B baseline/immutable-anchor comparison."""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_models.gri05 import build_model, primary_metric
from gri_models.resume import (
    begin_training,
    checkpoint_payload,
    load_checkpoint,
    make_optimizer,
    restore_checkpoint,
    save_checkpoint,
    train_epoch_range,
)
from gri_models.resume_audit import audit as resume_audit
from gri_models.train import accuracy
from gri_world0.serialization import read_jsonl
from gri_models.data import load_examples


ARTIFACT_DIR = ROOT / "artifacts/frozen/world0_v0_1"
OUT_DIR = ROOT / "artifacts/rri02b"
CHECKPOINT_DIR = OUT_DIR / "checkpoints"
SEEDS = (1337, 1338, 1339, 1340, 1341)
DEPTHS = (5, 8, 16, 32, 64)
PRIMARY_DEPTHS = (8, 16, 32, 64)
EPOCHS = 80
TRAIN_STEPS = 4
BATCH_SIZE = 16
LEARNING_RATE = 3e-3
WEIGHT_DECAY = 1e-4
GRADIENT_CLIP = 1.0
THREADS = 1
PARAMETERS = 30_912
CHUNK_EPOCHS = 20


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tensor_state_hash(state: dict[str, torch.Tensor]) -> str:
    import io

    buffer = io.BytesIO()
    torch.save(state, buffer)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def params(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def config(source_commit: str) -> dict[str, Any]:
    return {
        "unit": "RRI-02B",
        "status": "performance_evidence",
        "source_commit": source_commit,
        "baseline": {"hidden_dim": 49, "message_dim": 51, "trainable_parameters": PARAMETERS},
        "anchor": {
            "class": "gri_models.rri02pa.ImmutableRelationAnchorReasoner",
            "hidden_dim": 49,
            "message_dim": 51,
            "trainable_parameters": PARAMETERS,
            "formula": "h_anchor = (h + a) / 2",
            "readout": "mutable h only",
        },
        "epochs": EPOCHS,
        "train_steps": TRAIN_STEPS,
        "batch_size": BATCH_SIZE,
        "optimizer": "AdamW",
        "learning_rate": LEARNING_RATE,
        "weight_decay": WEIGHT_DECAY,
        "gradient_clip": GRADIENT_CLIP,
        "device": "CPU",
        "torch_threads": THREADS,
        "seeds": list(SEEDS),
        "evaluation_depths": list(DEPTHS),
        "primary_metric": "mean(D8,D16,D32,D64)",
        "primary_depths": list(PRIMARY_DEPTHS),
        "chunk_epochs": CHUNK_EPOCHS,
        "tuning": False,
        "evidence_seeds_reused": False,
    }


def evaluate(model: torch.nn.Module, train: list, validation: list, tests: dict[str, list]) -> dict[str, Any]:
    train_accuracy = accuracy(model, train, steps=TRAIN_STEPS)
    validation_accuracy = accuracy(model, validation, steps=TRAIN_STEPS)
    extrapolation = {depth: accuracy(model, examples, steps=int(depth)) for depth, examples in tests.items()}
    return {
        "train_accuracy": train_accuracy,
        "iid_validation_accuracy": validation_accuracy,
        "extrapolation": extrapolation,
        "primary_metric": primary_metric(extrapolation),
    }


def run_one(
    kind: str,
    seed: int,
    initial_hash: str,
    model: torch.nn.Module,
    train: list,
    validation: list,
    tests: dict[str, list],
    source_commit: str,
    frozen_config: dict[str, Any],
) -> dict[str, Any]:
    checkpoint_path = CHECKPOINT_DIR / f"{kind}_seed{seed}_final.pt"
    events: list[dict[str, Any]] = []
    started = time.time()
    optimizer = make_optimizer(model, learning_rate=LEARNING_RATE)
    start_epoch = 0

    if checkpoint_path.exists():
        payload = load_checkpoint(checkpoint_path)
        if payload.get("model_kind") != kind or int(payload.get("seed", -1)) != seed:
            raise RuntimeError(f"checkpoint identity mismatch: {checkpoint_path}")
        if payload.get("source_commit") != source_commit:
            raise RuntimeError(f"checkpoint source mismatch: {checkpoint_path}")
        start_epoch, rng_state = restore_checkpoint(payload, model, optimizer)
        if start_epoch > EPOCHS:
            raise RuntimeError(f"checkpoint epoch exceeds protocol: {checkpoint_path}")
        events.append({"type": "resume", "from_epoch": start_epoch, "path": str(checkpoint_path)})
    else:
        rng_state = begin_training(seed)
        events.append({"type": "fresh_start", "from_epoch": 0})

    final_loss = None
    while start_epoch < EPOCHS:
        end_epoch = min(start_epoch + CHUNK_EPOCHS, EPOCHS)
        final_loss, rng_state = train_epoch_range(
            model,
            optimizer,
            train,
            start_epoch=start_epoch,
            end_epoch=end_epoch,
            steps=TRAIN_STEPS,
            batch_size=BATCH_SIZE,
            rng_state=rng_state,
        )
        partial = checkpoint_payload(
            model,
            optimizer,
            epoch=end_epoch,
            rng_state=rng_state,
            model_kind=kind,
            seed=seed,
        )
        partial.update(
            {
                "checkpoint_status": "in_progress" if end_epoch < EPOCHS else "finalizing",
                "source_commit": source_commit,
                "world0_identity": "GRI_02_WORLD0_PASS",
                "parameter_count": params(model),
                "training_config": frozen_config,
                "initial_state_hash": initial_hash,
                "final_loss": final_loss,
                "final_metrics": None,
                "resume_events": events,
            }
        )
        save_checkpoint(checkpoint_path, partial)
        events.append({"type": "checkpoint", "epoch": end_epoch, "path": str(checkpoint_path)})
        start_epoch = end_epoch

    metrics = evaluate(model, train, validation, tests)
    final_payload = checkpoint_payload(
        model,
        optimizer,
        epoch=EPOCHS,
        rng_state=rng_state,
        model_kind=kind,
        seed=seed,
    )
    final_payload.update(
        {
            "checkpoint_status": "final",
            "source_commit": source_commit,
            "world0_identity": "GRI_02_WORLD0_PASS",
            "parameter_count": params(model),
            "training_config": frozen_config,
            "initial_state_hash": initial_hash,
            "final_loss": final_loss,
            "final_metrics": metrics,
            "resume_events": events,
        }
    )
    save_checkpoint(checkpoint_path, final_payload)
    elapsed = time.time() - started
    report = {
        "model": kind,
        "seed": seed,
        "epochs": EPOCHS,
        "train_steps": TRAIN_STEPS,
        "batch_size": BATCH_SIZE,
        "optimizer": "AdamW",
        "learning_rate": LEARNING_RATE,
        "weight_decay": WEIGHT_DECAY,
        "gradient_clip": GRADIENT_CLIP,
        "parameters": params(model),
        "initial_state_hash": initial_hash,
        "final_state_hash": tensor_state_hash(model.state_dict()),
        "final_loss": final_loss,
        **metrics,
        "checkpoint": str(checkpoint_path.relative_to(ROOT)),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "resume_events": events,
        "elapsed_seconds": elapsed,
        "source_commit": source_commit,
    }
    write_json(OUT_DIR / f"{kind}_seed{seed}.json", report)
    print(json.dumps({"model": kind, "seed": seed, "metrics": metrics, "checkpoint": str(checkpoint_path)}, sort_keys=True), flush=True)
    return report


def aggregate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {"baseline": [], "anchor": []}
    for report in reports:
        grouped[report["model"]].append(report)

    def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        values = {
            "train": [r["train_accuracy"] for r in rows],
            "iid": [r["iid_validation_accuracy"] for r in rows],
            "D5": [r["extrapolation"]["5"] for r in rows],
            "D8": [r["extrapolation"]["8"] for r in rows],
            "D16": [r["extrapolation"]["16"] for r in rows],
            "D32": [r["extrapolation"]["32"] for r in rows],
            "D64": [r["extrapolation"]["64"] for r in rows],
            "Primary": [r["primary_metric"] for r in rows],
        }
        out: dict[str, Any] = {"n": len(rows)}
        for key, numbers in values.items():
            out[f"mean_{key}"] = statistics.mean(numbers)
            out[f"stdev_{key}"] = statistics.stdev(numbers) if len(numbers) > 1 else 0.0
        return out

    base = {r["seed"]: r for r in grouped["baseline"]}
    anch = {r["seed"]: r for r in grouped["anchor"]}
    paired = []
    for seed in SEEDS:
        paired.append(
            {
                "seed": seed,
                "primary_anchor_minus_baseline": anch[seed]["primary_metric"] - base[seed]["primary_metric"],
                "d64_anchor_minus_baseline": anch[seed]["extrapolation"]["64"] - base[seed]["extrapolation"]["64"],
            }
        )
    return {
        "baseline": summary(grouped["baseline"]),
        "anchor": summary(grouped["anchor"]),
        "paired": paired,
        "mean_primary_anchor_minus_baseline": statistics.mean(x["primary_anchor_minus_baseline"] for x in paired),
        "mean_d64_anchor_minus_baseline": statistics.mean(x["d64_anchor_minus_baseline"] for x in paired),
        "primary_anchor_wins": sum(x["primary_anchor_minus_baseline"] > 0 for x in paired),
    }


def verdict(agg: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "A_mean_anchor_train_at_least_0.95": {
            "observed": agg["anchor"]["mean_train"],
            "pass": agg["anchor"]["mean_train"] >= 0.95,
        },
        "B_mean_anchor_iid_at_least_0.95": {
            "observed": agg["anchor"]["mean_iid"],
            "pass": agg["anchor"]["mean_iid"] >= 0.95,
        },
        "C_mean_primary_improvement_at_least_0.05": {
            "observed": agg["mean_primary_anchor_minus_baseline"],
            "pass": agg["mean_primary_anchor_minus_baseline"] >= 0.05,
        },
        "D_mean_d64_improvement_at_least_0.10": {
            "observed": agg["mean_d64_anchor_minus_baseline"],
            "pass": agg["mean_d64_anchor_minus_baseline"] >= 0.10,
        },
        "E_paired_primary_wins_at_least_4": {
            "observed": agg["primary_anchor_wins"],
            "pass": agg["primary_anchor_wins"] >= 4,
        },
    }
    passed = all(item["pass"] for item in gates.values())
    return {
        "unit": "RRI-02B",
        "gates": gates,
        "terminal_verdict": "RRI_02B_ANCHOR_PERFORMANCE_ADVANCES" if passed else "RRI_02B_ANCHOR_NO_ADVANTAGE",
        "evidence_seeds": list(SEEDS),
        "archaeology_run": False,
    }


def report_markdown(reports: list[dict[str, Any]], agg: dict[str, Any], final_verdict: dict[str, Any]) -> str:
    rows = [
        "# RRI-02B — Parameter-Neutral Immutable Anchor",
        "",
        f"Source commit: `{reports[0]['source_commit']}`",
        "",
        "| Model | Seed | Train | IID | D5 | D8 | D16 | D32 | D64 | Primary |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(reports, key=lambda x: (x["model"], x["seed"])):
        e = r["extrapolation"]
        rows.append(
            f"| {r['model']} | {r['seed']} | {r['train_accuracy']:.5f} | {r['iid_validation_accuracy']:.5f} | "
            f"{e['5']:.5f} | {e['8']:.5f} | {e['16']:.5f} | {e['32']:.5f} | {e['64']:.5f} | {r['primary_metric']:.5f} |"
        )
    rows += [
        "",
        "## Aggregates",
        "",
        "| Model | Mean Train | Mean IID | Mean D5 | Mean D8 | Mean D16 | Mean D32 | Mean D64 | Mean Primary | Primary SD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for kind in ("baseline", "anchor"):
        s = agg[kind]
        rows.append(
            f"| {kind} | {s['mean_train']:.5f} | {s['mean_iid']:.5f} | {s['mean_D5']:.5f} | "
            f"{s['mean_D8']:.5f} | {s['mean_D16']:.5f} | {s['mean_D32']:.5f} | {s['mean_D64']:.5f} | "
            f"{s['mean_Primary']:.5f} | {s['stdev_Primary']:.5f} |"
        )
    rows += ["", "## Paired differences", "", "| Seed | Primary anchor − baseline | D64 anchor − baseline |", "|---:|---:|---:|"]
    for pair in agg["paired"]:
        rows.append(f"| {pair['seed']} | {pair['primary_anchor_minus_baseline']:.5f} | {pair['d64_anchor_minus_baseline']:.5f} |")
    rows += ["", "## Gates", ""]
    for name, gate in final_verdict["gates"].items():
        rows.append(f"- {name}: **{'PASS' if gate['pass'] else 'FAIL'}** (`{gate['observed']}`)")
    rows += ["", "## Terminal verdict", "", f"`{final_verdict['terminal_verdict']}`", "", "RRI-01 archaeology was not run."]
    return "\n".join(rows) + "\n"


def manifest() -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted(OUT_DIR.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            entries[str(path.relative_to(ROOT))] = sha256_file(path)
    return entries


def main() -> int:
    torch.set_num_threads(THREADS)
    source_commit = git_commit()
    frozen_config = config(source_commit)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    train = load_examples(ARTIFACT_DIR / "train.jsonl")
    validation = load_examples(ARTIFACT_DIR / "validation.jsonl")
    tests = {str(depth): load_examples(ARTIFACT_DIR / f"test_depth_{depth}.jsonl") for depth in DEPTHS}

    resume_reports = [resume_audit(kind, ARTIFACT_DIR, total_epochs=3, split_epoch=1) for kind in ("baseline", "anchor")]
    if not all(
        r["model_state_equal"] and r["optimizer_state_equal"] and r["rng_state_equal"]
        and r["final_loss_equal"] and r["uninterrupted_model_hash"] == r["resumed_model_hash"]
        for r in resume_reports
    ):
        raise RuntimeError("RRI-02B resume equivalence failed")

    baseline, anchor = (build_model(kind, SEEDS[0]) for kind in ("baseline", "anchor"))
    baseline_count, anchor_count = params(baseline), params(anchor)
    if (baseline_count, anchor_count) != (PARAMETERS, PARAMETERS):
        raise RuntimeError(f"RRI-02B capacity invalid: {baseline_count}, {anchor_count}")

    write_json(OUT_DIR / "RRI02B_CONFIG.json", frozen_config)
    write_json(
        OUT_DIR / "parameter_identity.json",
        {
            "baseline_parameters": baseline_count,
            "anchor_parameters": anchor_count,
            "exact_match": True,
            "evidence_seeds": list(SEEDS),
        },
    )
    write_json(
        OUT_DIR / "environment.json",
        {
            "source_commit": source_commit,
            "python": platform.python_version(),
            "pytorch": torch.__version__,
            "os": platform.platform(),
            "cpu": platform.processor(),
            "cuda_available": torch.cuda.is_available(),
            "selected_device": "CPU",
            "torch_threads": THREADS,
            "world0_validator": "GRI_02_WORLD0_PASS",
            "resume_audit": resume_reports,
            "repository_status": "pre-existing untracked user files preserved",
        },
    )

    initialization: dict[str, Any] = {"evidence_seeds": {}, "all_equal": True}
    reports: list[dict[str, Any]] = []
    for seed in SEEDS:
        baseline, anchor = build_model("baseline", seed), build_model("anchor", seed)
        baseline_hash = tensor_state_hash(baseline.state_dict())
        anchor_hash = tensor_state_hash(anchor.state_dict())
        equal = baseline_hash == anchor_hash and all(
            torch.equal(x, y) for x, y in zip(baseline.state_dict().values(), anchor.state_dict().values())
        )
        initialization["evidence_seeds"][str(seed)] = {
            "baseline_initial_hash": baseline_hash,
            "anchor_initial_hash": anchor_hash,
            "tensor_for_tensor_equal": equal,
        }
        initialization["all_equal"] = initialization["all_equal"] and equal
        if not equal:
            write_json(OUT_DIR / "initialization_identity.json", initialization)
            raise RuntimeError(f"RRI-02B initialization identity failed for seed {seed}")
        reports.append(run_one("baseline", seed, baseline_hash, baseline, train, validation, tests, source_commit, frozen_config))
        reports.append(run_one("anchor", seed, anchor_hash, anchor, train, validation, tests, source_commit, frozen_config))

    write_json(OUT_DIR / "initialization_identity.json", initialization)
    agg = aggregate(reports)
    final_verdict = verdict(agg)
    write_json(OUT_DIR / "aggregate.json", agg)
    write_json(OUT_DIR / "RRI02B_VERDICT.json", final_verdict)
    (OUT_DIR / "RRI02B_REPORT.md").write_text(report_markdown(reports, agg, final_verdict))
    write_json(OUT_DIR / "SHA256SUMS.json", manifest())
    print(json.dumps(final_verdict, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
