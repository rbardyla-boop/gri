from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from wildflower0.variants import aggregate_pixel_probe, run_pixel_probe


def main() -> int:
    metrics = [run_pixel_probe(seed) for seed in (20, 21, 22)]
    report = {
        "status": "ENGINEERING_VARIANT_PROBE_ONLY",
        "scientific_claim_authorized": False,
        "variant": "direct_pixel_dynamics",
        "metrics": [asdict(m) for m in metrics],
        "aggregate": aggregate_pixel_probe(metrics),
    }
    out = Path("artifacts/pixel_variant_fresh_seeds.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))
    gates = report["aggregate"]["engineering_gates"]
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
