from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

from wildflower0.nursery1 import run_balanced_probe


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 160
    result = run_balanced_probe(seed)
    report = {
        "status": "NURSERY1_PRELOCK_BALANCED_ENGINEERING_PROBE",
        "architecture_freeze_authorized": False,
        "scientific_claim_authorized": False,
        "result": asdict(result),
    }
    out = Path("artifacts") / f"nursery1_balanced_probe_seed{seed}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
