from __future__ import annotations

import argparse
import json
from pathlib import Path

from wildflower0.sim import aggregate, run_seed, stable_hash


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--train-steps", type=int, default=220)
    p.add_argument("--out", type=Path, default=Path("artifacts/shakeout.json"))
    args = p.parse_args()
    if args.seeds <= 0 or args.train_steps <= 0:
        raise SystemExit("seeds and train-steps must be positive")

    metrics = [run_seed(i, train_steps=args.train_steps) for i in range(args.seeds)]
    report = {
        "status": "ENGINEERING_SHAKEOUT_ONLY",
        "scientific_claim_authorized": False,
        "metrics": [m.__dict__ for m in metrics],
        "aggregate": aggregate(metrics),
    }
    report["receipt_sha256"] = stable_hash(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))
    print("receipt_sha256", report["receipt_sha256"])
    gates = report["aggregate"]["engineering_gates"]
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
