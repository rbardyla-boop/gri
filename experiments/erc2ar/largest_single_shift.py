from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.erc1.compiler import score_feature, sha256_file, sha256_text, canonical_json


def score_case(metrics_path: Path, meta_path: Path) -> dict:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if sha256_file(metrics_path) != meta["staged_metrics_sha256"]:
        raise ValueError("staged digest mismatch")
    frame = pd.read_parquet(metrics_path)
    times = pd.to_numeric(frame["time"], errors="raise").to_numpy(dtype="int64")
    maxima = {"A1": float("-inf"), "A2": float("-inf"), "A3": float("-inf")}
    witnesses = {}
    for column in frame.columns:
        if column == "time":
            continue
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")
        rec = score_feature(
            meta["opaque_id"], column, times, values, int(meta["inject_time"]),
            meta["source_metrics_sha256"], meta["staged_metrics_sha256"],
        )
        if rec is None:
            continue
        if rec.score > maxima[rec.service] or (rec.score == maxima[rec.service] and rec.column < witnesses.get(rec.service, "~")):
            maxima[rec.service] = float(rec.score)
            witnesses[rec.service] = rec.column
    ranking = sorted(maxima, key=lambda s: (-maxima[s], s))
    return {
        "opaque_id": meta["opaque_id"],
        "ranking": ranking,
        "scores": maxima,
        "witness_columns": witnesses,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    rows = []
    for meta_path in sorted(args.candidate_dir.glob("E1-*.json")):
        rows.append(score_case(args.candidate_dir / f"{meta_path.stem}.parquet", meta_path))
    if len(rows) != 13:
        raise ValueError(f"expected 13 cases, found {len(rows)}")
    body = {"unit":"ERC-2AR","baseline":"LARGEST_SINGLE_SHIFT","case_count":13,"predictions":rows}
    body["prediction_seal_sha256"] = sha256_text(canonical_json(rows))
    args.output.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in body.items() if k != "predictions"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
