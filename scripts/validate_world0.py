#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gri_world0.validation import ValidationError, validate_artifact_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    try:
        report = validate_artifact_dir(args.artifact_dir)
    except (ValidationError, ValueError, OSError) as exc:
        print(f"WORLD0 VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print("GRI_02_WORLD0_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
