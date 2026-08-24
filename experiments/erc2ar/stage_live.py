from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from experiments.erc2ar.contract import ARCHIVES, DAYS, EVENTS_PUBLIC, SIGNAL_COLUMNS, WINDOW_SECONDS, opaque_id


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gri-erc2ar/1.0"})
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read()


def project_fields(fields: list[bytes]) -> dict[str, float]:
    if len(fields) != 33:
        raise ValueError(f"expected 33 fields, got {len(fields)}")
    return {name: float(fields[column_1_based - 1]) for column_1_based, name in SIGNAL_COLUMNS}


def load_bound_days() -> dict[str, bytes]:
    needed_parts = sorted({DAYS[date]["archive"] for date in DAYS})
    archives: dict[str, bytes] = {}
    for part in needed_parts:
        blob = download(ARCHIVES[part]["url"])
        if sha256_bytes(blob) != ARCHIVES[part]["sha256"]:
            raise ValueError(f"archive digest mismatch: {part}")
        archives[part] = blob

    days: dict[str, bytes] = {}
    for date, spec in DAYS.items():
        with zipfile.ZipFile(io.BytesIO(archives[spec["archive"]])) as zf:
            raw = zf.read(spec["member"])
        if sha256_bytes(raw) != spec["raw_sha256"]:
            raise ValueError(f"raw day digest mismatch: {date}")
        days[date] = raw
    return days


def window_frame(raw: bytes, start: int) -> pd.DataFrame:
    lines = raw.splitlines()
    if len(lines) != 86400:
        raise ValueError(f"expected 86400 rows, got {len(lines)}")
    left, right = start - WINDOW_SECONDS, start + WINDOW_SECONDS
    if left < 0 or right > 86400:
        raise ValueError("event window outside day")
    rows: list[dict[str, float | int]] = []
    for expected_time, line in enumerate(lines[left:right], start=left):
        fields = line.split()
        if len(fields) != 33:
            raise ValueError(f"row {expected_time}: expected 33 fields, got {len(fields)}")
        actual_time = int(fields[0])
        if actual_time != expected_time:
            raise ValueError(f"timestamp mismatch {actual_time} != {expected_time}")
        row: dict[str, float | int] = {"time": actual_time}
        row.update(project_fields(fields))
        rows.append(row)
    frame = pd.DataFrame(rows, columns=["time"] + [name for _, name in SIGNAL_COLUMNS])
    if len(frame) != 600 or list(frame.columns) != ["time"] + [name for _, name in SIGNAL_COLUMNS]:
        raise ValueError("adapter shape mismatch")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir
    candidate = out / "candidate"
    candidate.mkdir(parents=True, exist_ok=True)
    if any(candidate.iterdir()):
        raise ValueError("candidate output directory must start empty")

    days = load_bound_days()
    manifest = []
    for event in EVENTS_PUBLIC:
        oid = opaque_id(event)
        raw = days[event["date"]]
        frame = window_frame(raw, event["start"])
        parquet_path = candidate / f"{oid}.parquet"
        frame.to_parquet(parquet_path, index=False, engine="pyarrow", compression=None)
        metadata = {
            "opaque_id": oid,
            "inject_time": int(event["start"]),
            "source_metrics_sha256": DAYS[event["date"]]["raw_sha256"],
            "staged_metrics_sha256": sha256_file(parquet_path),
        }
        (candidate / f"{oid}.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        manifest.append({
            "opaque_id": oid,
            "item": event["item"],
            "date": event["date"],
            "start": event["start"],
            "source_metrics_sha256": metadata["source_metrics_sha256"],
            "staged_metrics_sha256": metadata["staged_metrics_sha256"],
            "row_count": len(frame),
            "signal_count": 18,
        })

    report = {
        "unit": "ERC-2AR",
        "status": "ERC2AR_LIVE_CASES_STAGED",
        "case_count": len(manifest),
        "truth_labels_in_candidate_metadata": False,
        "target_actuator_in_candidate_metadata": False,
        "window_seconds_each_side": WINDOW_SECONDS,
        "signal_count_per_case": 18,
        "manifest": manifest,
    }
    (out / "PUBLIC_STAGE_MANIFEST.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
