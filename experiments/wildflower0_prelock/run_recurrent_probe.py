from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
import torch

from wildflower0.recurrent import (
    RecurrentWorldModel,
    kinematic_baseline_rollout,
    online_corrected_error,
    rollout_recurrent,
    train_recurrent,
)
from wildflower0.sim import collect_pairs, copy_baseline_error, set_seed, stable_hash


@dataclass(frozen=True)
class Result:
    seed: int
    online_corrected: float
    h1: float
    h4: float
    h8: float
    h16: float
    h32: float
    copy_h1: float
    kinematic_h1: float
    kinematic_h8: float
    kinematic_h32: float
    model_copy_ratio: float
    model_kinematic_ratio_h1: float
    growth_h32_over_h1: float
    surprise_h8: float
    surprise_h32: float
    finite: bool


def run(seed: int) -> Result:
    set_seed(seed)
    train_pairs = collect_pairs(seed * 101 + 1, 420, (0, 1, 2, 3), switch_period=None)
    test_pairs = collect_pairs(seed * 101 + 2, 300, (0, 1, 2, 3), switch_period=None)
    surprise_pairs = collect_pairs(seed * 101 + 3, 300, (0, 1, 2, 3), switch_period=19)

    model = RecurrentWorldModel()
    train_recurrent(model, train_pairs, 280, seed + 500, horizon=8)

    hs = {h: rollout_recurrent(model, test_pairs, h) for h in (1, 4, 8, 16, 32)}
    copy_h1 = copy_baseline_error(test_pairs)
    kin1 = kinematic_baseline_rollout(test_pairs, 1)
    kin8 = kinematic_baseline_rollout(test_pairs, 8)
    kin32 = kinematic_baseline_rollout(test_pairs, 32)
    return Result(
        seed=seed,
        online_corrected=online_corrected_error(model, test_pairs),
        h1=hs[1],
        h4=hs[4],
        h8=hs[8],
        h16=hs[16],
        h32=hs[32],
        copy_h1=copy_h1,
        kinematic_h1=kin1,
        kinematic_h8=kin8,
        kinematic_h32=kin32,
        model_copy_ratio=hs[1] / max(copy_h1, 1e-8),
        model_kinematic_ratio_h1=hs[1] / max(kin1, 1e-8),
        growth_h32_over_h1=hs[32] / max(hs[1], 1e-8),
        surprise_h8=rollout_recurrent(model, surprise_pairs, 8),
        surprise_h32=rollout_recurrent(model, surprise_pairs, 32),
        finite=all(bool(torch.isfinite(p).all()) for p in model.parameters()),
    )


def main() -> int:
    results = [run(s) for s in (40, 41, 42)]
    numeric = [k for k, v in asdict(results[0]).items() if k not in {"seed", "finite"}]
    agg: dict[str, object] = {
        "seeds": [r.seed for r in results],
        "all_finite": all(r.finite for r in results),
    }
    for key in numeric:
        vals = np.asarray([getattr(r, key) for r in results], dtype=float)
        agg[key] = {
            "mean": float(vals.mean()),
            "min": float(vals.min()),
            "max": float(vals.max()),
        }
    agg["engineering_gates"] = {
        "finite": bool(agg["all_finite"]),
        "beats_copy_h1": max(r.model_copy_ratio for r in results) < 1.0,
        "open_loop_growth_h32_under_10x": max(r.growth_h32_over_h1 for r in results) < 10.0,
        "h32_absolute_under_0_30": max(r.h32 for r in results) < 0.30,
    }
    report = {
        "status": "ENGINEERING_RECURRENT_PROBE_ONLY",
        "scientific_claim_authorized": False,
        "metrics": [asdict(r) for r in results],
        "aggregate": agg,
    }
    report["receipt_sha256"] = stable_hash(report)
    out = Path("artifacts/recurrent_probe_fresh_seeds.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(agg, indent=2, sort_keys=True))
    print("receipt_sha256", report["receipt_sha256"])
    return 0 if all(agg["engineering_gates"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
