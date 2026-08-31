"""Design-only scientific runner for Predictive Authority 0.1.

The runner is fully specified but fail-closed: no execution authorization file
exists in this prelock pass, so ``--seed`` cannot run.  ``--profile-only``
performs synthetic engineering diagnostics and reads the frozen 0.3 artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from . import design
from .diagnostics import run_engineering_profile
from .gates import classify_h8_origin, evaluate_gates
from .legacy import LEGACY_ROOT, load_legacy
from .qualification_guard import assert_seed_authorized
from .rollout import generate_origin_trace
from .trace import ERROR_FIELD_BY_PATH, origin_trace_to_dict

OUTPUT_ROOT = Path(__file__).resolve().parent / "artifacts"


def _finite(value: object, path: str = "result") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite value at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _finite(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _finite(child, f"{path}[{index}]")


def _canonical_bytes(value: object) -> bytes:
    _finite(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    """Hash successor code and the fixed historical numeric dependencies."""

    package_root = Path(__file__).resolve().parent
    paths: dict[str, Path] = {
        f"successor/{path.relative_to(package_root)}": path
        for path in package_root.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    paths.update(
        {
            "historical/probe_innovation_model.py": LEGACY_ROOT
            / "probe_innovation_model.py",
            "historical/qualify_authority190.py": LEGACY_ROOT
            / "qualify_authority190.py",
            "historical/wildflower0/nursery1.py": LEGACY_ROOT
            / "wildflower0"
            / "nursery1.py",
        }
    )
    return {name: _sha256(path) for name, path in sorted(paths.items())}


def _selection(model_seed: int) -> dict[str, dict[int, tuple[int, ...]]]:
    if model_seed not in design.MODEL_SEEDS:
        raise ValueError(f"unregistered predictive-authority seed: {model_seed}")
    legacy = load_legacy()
    starts = design.selector_starts(model_seed)
    selector = legacy["select_balanced_episode_seeds"]
    return {
        "training": selector(
            model_seed + design.SELECTOR_ROOT,
            design.TRAIN_PER_MODE,
            start=starts["training"],
        ),
        "ordinary_test": selector(
            model_seed + design.SELECTOR_ROOT + 100_000,
            design.ORDINARY_TEST_PER_MODE,
            start=starts["ordinary_test"],
        ),
    }


def _selector_payload(
    model_seed: int,
    selection: dict[str, dict[int, tuple[int, ...]]],
) -> dict[str, object]:
    return {
        "starts": design.selector_starts(model_seed),
        "ranges": design.selector_ranges()[model_seed],
        "selected_episode_seeds": {
            name: {str(mode): list(seeds) for mode, seeds in modes.items()}
            for name, modes in selection.items()
        },
    }


def _train_model(model_seed: int, selection: dict[str, dict[int, tuple[int, ...]]]) -> Any:
    legacy = load_legacy()
    legacy["set_seed"](model_seed)
    model = legacy["InnovationModel"]()
    order = [
        selection["training"][mode][index]
        for index in range(design.TRAIN_PER_MODE)
        for mode in legacy["MODES"]
    ]
    for index, episode_seed in enumerate(order):
        pairs = legacy["collect_pairs"](episode_seed, design.TRAINING_EPISODE_LENGTH)
        legacy["train"](
            model,
            pairs,
            design.TRAINING_STEPS_PER_EPISODE,
            model_seed + 10_000 + index,
            horizon=8,
            burn=design.BURN,
        )
    model.eval()
    return model


def _aggregate_origins(origins: list[dict[str, object]]) -> dict[str, object]:
    error_keys = ERROR_FIELD_BY_PATH
    result: dict[str, object] = {}
    for horizon in design.HORIZONS:
        rows = [row["rollout_horizons"][str(horizon)] for row in origins]
        terminal = [row[-1] for row in rows]
        for name in ("null", "learned_only", "gated"):
            key = f"{name}_h{horizon}_error_evaluator_only"
            result[key] = float(
                np.mean([item[error_keys[name]] for item in terminal])
            )
        null_error = result[f"null_h{horizon}_error_evaluator_only"]
        for name in ("learned_only", "gated"):
            result[f"{name}_h{horizon}_null_ratio"] = float(
                result[f"{name}_h{horizon}_error_evaluator_only"]
                / max(null_error, 1e-8)
            )
    event_origins = [
        origin
        for origin in origins
        if any(
            origin["step"] <= event < origin["step"] + 8
            for event in origin["event_locations_evaluator_only"]
        )
    ]
    if event_origins:
        event_terminal = [
            origin["rollout_horizons"]["8"][-1] for origin in event_origins
        ]
        result["event_gated_h8_error_evaluator_only"] = float(
            np.mean(
                [item["gated_local_error_evaluator_only"] for item in event_terminal]
            )
        )
        result["event_null_h8_error_evaluator_only"] = float(
            np.mean(
                [item["null_local_error_evaluator_only"] for item in event_terminal]
            )
        )
        result["event_gated_h8_null_ratio"] = float(
            result["event_gated_h8_error_evaluator_only"]
            / max(result["event_null_h8_error_evaluator_only"], 1e-8)
        )
    else:
        result["event_gated_h8_null_ratio"] = None
    result["origin_count"] = len(origins)
    result["event_origin_count"] = len(event_origins)
    return result


def _run_authorized_scientific_seed(model_seed: int) -> dict[str, object]:
    """Build the future scientific artifact; guard is checked by the caller."""

    selection = _selection(model_seed)
    model = _train_model(model_seed, selection)
    legacy = load_legacy()
    traces: list[dict[str, object]] = []
    episode_rows: list[dict[str, object]] = []
    for mode in legacy["MODES"]:
        for episode_seed in selection["ordinary_test"][mode]:
            pairs = legacy["collect_pairs"](
                episode_seed, design.ORDINARY_EVALUATION_LENGTH
            )
            episode_traces = [
                generate_origin_trace(model, pairs, mode, episode_seed, index)
                for index in range(
                    design.BURN + 2,
                    len(pairs) - max(design.HORIZONS),
                )
            ]
            serialized = [origin_trace_to_dict(trace) for trace in episode_traces]
            for trace in serialized:
                trace["h8_quality_classification_evaluator_only"] = (
                    classify_h8_origin(trace)
                )
            traces.extend(serialized)
            row = _aggregate_origins(serialized)
            row.update(
                {
                    "mode_evaluator_only": mode,
                    "episode_seed_evaluator_only": episode_seed,
                }
            )
            episode_rows.append(row)
    gated_h1 = [row["gated_h1_null_ratio"] for row in episode_rows]
    gated_h8 = [row["gated_h8_null_ratio"] for row in episode_rows]
    gated_h32 = [row["gated_h32_null_ratio"] for row in episode_rows]
    event_h8 = [
        row["event_gated_h8_null_ratio"]
        for row in episode_rows
        if row["event_gated_h8_null_ratio"] is not None
    ]
    old_aggregate = {
        "h1_ratio_mean": float(np.mean(gated_h1)),
        "h1_ratio_max": float(np.max(gated_h1)),
        "h8_ratio_mean": float(np.mean(gated_h8)),
        "h8_ratio_max": float(np.max(gated_h8)),
        "h32_ratio_mean": float(np.mean(gated_h32)),
        "h32_ratio_max": float(np.max(gated_h32)),
        "event_h8_ratio_mean": float(np.mean(event_h8)) if event_h8 else None,
        "event_h8_ratio_max": float(np.max(event_h8)) if event_h8 else None,
    }
    old_gates = {
        "h1_noninferior_all": design.gate_passes(
            "old_h1_max", old_aggregate["h1_ratio_max"]
        ),
        "h8_better_all": design.gate_passes(
            "old_h8_max", old_aggregate["h8_ratio_max"]
        ),
        "h8_mean_10pct": design.gate_passes(
            "old_h8_mean", old_aggregate["h8_ratio_mean"]
        ),
        "h32_better_all": design.gate_passes(
            "old_h32_max", old_aggregate["h32_ratio_max"]
        ),
        "h32_mean_15pct": design.gate_passes(
            "old_h32_mean", old_aggregate["h32_ratio_mean"]
        ),
        "event_h8_mean_10pct": (
            bool(event_h8)
            and design.gate_passes(
                "old_event_h8_mean", old_aggregate["event_h8_ratio_mean"]
            )
        ),
    }
    predictive = {
        "episodes": episode_rows,
        "aggregate": {
            key: float(np.mean([row[key] for row in episode_rows]))
            for key in episode_rows[0]
            if key.endswith("null_ratio")
        },
        "old_frozen_gates": old_gates,
        "old_frozen_gate_aggregate": old_aggregate,
        "successor_gates": evaluate_gates(traces),
        "trace_origin_count": len(traces),
    }
    result: dict[str, object] = {
        "experiment": "WILDFLOWER Predictive Authority",
        "version": "0.1",
        "status": "DEVELOPMENT_RUN",
        "model_seed": model_seed,
        "selectors": _selector_payload(model_seed, selection),
        "source_hashes": source_hashes(),
        "predictive_authority": predictive,
        "predictive_trace": traces,
        "policies": {
            "scientific_candidate": design.PRIMARY_CANDIDATE,
            "diagnostic_comparators": list(design.DIAGNOSTIC_COMPARATORS),
        },
        "epistemic_integration": {
            "consumer": "frozen Dual-Authority-0.3 only",
            "executed": False,
        },
        "scientific_authorization": False,
    }
    result["semantic_receipt_sha256"] = hashlib.sha256(
        _canonical_bytes(result)
    ).hexdigest()
    _finite(result)
    return result


def run_seed(model_seed: int) -> dict[str, object]:
    """Run only after an explicit future authorization is supplied."""

    assert_seed_authorized(model_seed)
    return _run_authorized_scientific_seed(model_seed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--profile-only",
        action="store_true",
        help="run synthetic diagnostics only; never a scientific seed",
    )
    args = parser.parse_args(argv)
    if args.profile_only:
        if args.seed is not None:
            parser.error("--profile-only cannot be combined with --seed")
        result = run_engineering_profile()
        result["source_hashes"] = source_hashes()
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.seed is None:
        parser.error("--seed is required unless --profile-only is used")
    result = run_seed(args.seed)
    output = args.output or OUTPUT_ROOT / f"development_seed{args.seed}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical_bytes(result) + b"\n")
    print(json.dumps({"output": str(output), "seed": args.seed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
