#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_models.resume_audit import audit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts/frozen/world0_v0_1")
    args = ap.parse_args()
    reports = [audit(kind, args.artifact_dir) for kind in ("baseline", "so4")]
    passed = all(
        r["model_state_equal"] and r["optimizer_state_equal"] and r["rng_state_equal"] and r["final_loss_equal"]
        for r in reports
    )
    out = {"verdict": "GRI_RESUME_EQUIVALENCE_PASS" if passed else "GRI_RESUME_EQUIVALENCE_FAIL", "reports": reports}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
