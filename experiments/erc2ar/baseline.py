from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from experiments.erc1.compiler import canonical_json, score_feature, sha256_file


def baseline_case(metrics_path: Path, meta_path: Path) -> dict:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if sha256_file(metrics_path) != meta["staged_metrics_sha256"]:
        raise ValueError(f"staged digest mismatch: {meta['opaque_id']}")
    frame = pd.read_parquet(metrics_path)
    times = pd.to_numeric(frame["time"], errors="raise").to_numpy(dtype="int64")
    best: dict[str, tuple[float, str]] = {}
    for column in frame.columns:
        if column == "time":
            continue
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")
        record = score_feature(
            meta["opaque_id"], column, times, values, int(meta["inject_time"]),
            meta["source_metrics_sha256"], meta["staged_metrics_sha256"],
        )
        if record is None:
            continue
        current = best.get(record.service)
        candidate = (float(record.score), record.column)
        if current is None or candidate[0] > current[0] or (candidate[0] == current[0] and candidate[1] < current[1]):
            best[record.service] = candidate
    ranking = sorted(best, key=lambda service: (-best[service][0], service))
    return {
        "opaque_id": meta["opaque_id"],
        "actuator_ranking": ranking,
        "strongest_signal_score": {service: best[service][0] for service in ranking},
        "strongest_signal_column": {service: best[service][1] for service in ranking},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for meta_path in sorted(args.candidate_dir.glob("E1-*.json")):
        rows.append(baseline_case(args.candidate_dir / f"{meta_path.stem}.parquet", meta_path))
    if not rows:
        raise ValueError("no baseline cases")
    rows.sort(key=lambda row: row["opaque_id"])
    body = {"unit": "ERC-2AR", "case_count": len(rows), "predictions": rows}
    body["prediction_seal_sha256"] = hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
    args.output.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in body.items() if k != "predictions"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
