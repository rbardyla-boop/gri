from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .locator import locate
from .producer_boundary import assert_clean


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def run_batch(producer_dir: Path, output: Path) -> dict:
    assert_clean([producer_dir])
    files = sorted(producer_dir.glob("P90-*.json"))
    if len(files) != 64:
        raise ValueError(f"expected exactly 64 producer inputs, got {len(files)}")
    predictions = []
    for path in files:
        value = json.loads(path.read_text(encoding="utf-8"))
        prediction = locate(value)
        if prediction["opaque_id"] != path.stem:
            raise ValueError("prediction opaque id does not match producer filename")
        predictions.append(prediction)
    predictions.sort(key=lambda row: row["opaque_id"])
    payload = canonical_bytes(predictions)
    output.write_bytes(payload)
    return {
        "unit": "ERC-3A",
        "status": "ERC3A_BATCH_PREDICTIONS_SEALED",
        "case_count": len(predictions),
        "prediction_seal_sha256": hashlib.sha256(payload).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_batch(args.producer_dir, args.output)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
