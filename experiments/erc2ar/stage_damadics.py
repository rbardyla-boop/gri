from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ARCHIVES = {
    "part2": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/164/821/file/Lublin_all_data_part2.zip",
        "sha256": "5e23c3b0e5adcb50541704024846d54f33bc374e1fd36f50b1043a663dfba803",
    },
    "part3": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/165/825/file/Lublin_all_data_part3.zip",
        "sha256": "2e961f290e3a7fdd3ebf3e2688af207cd1affef065aae13e3fb68755f7ee9628",
    },
    "part4": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/166/829/file/Lublin_all_data_part4.zip",
        "sha256": "d8a61f82c3b66df5f566bc8c78060db678cc886ab94f4059bab5de3b68784cf2",
    },
}

DAYS = {
    "2001-10-30": {
        "part": "part4",
        "member": "Lublin_all_data/30102001.txt",
        "raw_sha256": "75706a15cff60b132ae7fd291ce08a06bb0ef0df6ed65a15cb05fe18889363d1",
    },
    "2001-11-09": {
        "part": "part2",
        "member": "Lublin_all_data/09112001.txt",
        "raw_sha256": "b3af2f899fe23c2826a0821fd9024a9dcc6c1a7f99e2191b752bb6b4a218d488",
    },
    "2001-11-17": {
        "part": "part3",
        "member": "Lublin_all_data/17112001.txt",
        "raw_sha256": "2744046eedf781c157f0bc02db96be2b3651063112d04d2e80f56260594b1538",
    },
    "2001-11-20": {
        "part": "part3",
        "member": "Lublin_all_data/20112001.txt",
        "raw_sha256": "8ce1310dcfb8f4907aecc2414dc8dbd013b382cf9fc08e45b2e740b74f9fec79",
    },
}

# Frozen clean set mechanically derived by ERC-2A before telemetry.
EVENTS = [
    {"opaque_id":"E1-X01","item":1,"actuator":"A1","date":"2001-10-30","fault":"f18","start":58800},
    {"opaque_id":"E1-X02","item":2,"actuator":"A1","date":"2001-11-09","fault":"f16","start":57275},
    {"opaque_id":"E1-X03","item":4,"actuator":"A1","date":"2001-11-09","fault":"f18","start":58520},
    {"opaque_id":"E1-X04","item":5,"actuator":"A1","date":"2001-11-17","fault":"f18","start":54600},
    {"opaque_id":"E1-X05","item":6,"actuator":"A1","date":"2001-11-17","fault":"f16","start":56670},
    {"opaque_id":"E1-X06","item":7,"actuator":"A1","date":"2001-11-20","fault":"f17","start":37780},
    {"opaque_id":"E1-X07","item":8,"actuator":"A2","date":"2001-11-17","fault":"f17","start":53780},
    {"opaque_id":"E1-X08","item":9,"actuator":"A2","date":"2001-11-17","fault":"f17","start":54193},
    {"opaque_id":"E1-X09","item":10,"actuator":"A2","date":"2001-11-17","fault":"f19","start":55482},
    {"opaque_id":"E1-X10","item":11,"actuator":"A2","date":"2001-11-17","fault":"f19","start":55977},
    {"opaque_id":"E1-X11","item":13,"actuator":"A2","date":"2001-11-20","fault":"f17","start":44400},
    {"opaque_id":"E1-X12","item":14,"actuator":"A3","date":"2001-10-30","fault":"f18","start":57340},
    {"opaque_id":"E1-X13","item":19,"actuator":"A3","date":"2001-11-17","fault":"f19","start":58150},
]

# Official DAMADICS daily-file positions (1-based): time=1; A1=2..7; A2=18..23; A3=24..29.
# Converted here to zero-based dataframe positions. All become generic symptom signals.
SOURCE_POSITIONS = {
    "A1": [1, 2, 3, 4, 5, 6],
    "A2": [17, 18, 19, 20, 21, 22],
    "A3": [23, 24, 25, 26, 27, 28],
}

WINDOW = 300
EXPECTED_COMPILER_SHA256 = "2d7135512894736281d1d0381a07bd76e1eb0052cf61c61ae5359f02f2d1288d"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "erc2ar/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def load_days() -> dict[str, pd.DataFrame]:
    archive_bytes: dict[str, bytes] = {}
    for part, spec in ARCHIVES.items():
        data = download(spec["url"])
        observed = sha256_bytes(data)
        if observed != spec["sha256"]:
            raise ValueError(f"archive hash mismatch {part}: {observed}")
        archive_bytes[part] = data

    days: dict[str, pd.DataFrame] = {}
    for date, spec in DAYS.items():
        with zipfile.ZipFile(io.BytesIO(archive_bytes[spec["part"]])) as zf:
            raw = zf.read(spec["member"])
        if sha256_bytes(raw) != spec["raw_sha256"]:
            raise ValueError(f"raw day hash mismatch {date}")
        frame = pd.read_csv(io.BytesIO(raw), sep=r"\s+", header=None, na_values=["NaN"], engine="python")
        if frame.shape != (86400, 33):
            raise ValueError(f"unexpected day shape {date}: {frame.shape}")
        times = pd.to_numeric(frame.iloc[:, 0], errors="raise")
        if int(times.iloc[0]) != 0 or int(times.iloc[-1]) != 86399 or not (times.to_numpy() == range(86400)).all():
            raise ValueError(f"timestamp contract failed {date}")
        days[date] = frame
    return days


def adapted_window(frame: pd.DataFrame, start: int) -> pd.DataFrame:
    window = frame.iloc[start - WINDOW:start + WINDOW, :]
    if len(window) != 600:
        raise ValueError("window length mismatch")
    out = pd.DataFrame({"time": pd.to_numeric(window.iloc[:, 0], errors="raise").astype("int64")})
    for actuator in ("A1", "A2", "A3"):
        for ordinal, source_pos in enumerate(SOURCE_POSITIONS[actuator], start=1):
            out[f"{actuator}_sig{ordinal:02d}"] = pd.to_numeric(window.iloc[:, source_pos], errors="coerce").to_numpy()
    if list(out.columns) != ["time"] + [f"{a}_sig{i:02d}" for a in ("A1","A2","A3") for i in range(1,7)]:
        raise ValueError("adapter column contract mismatch")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--scorer-map", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--compiler", type=Path, default=Path("experiments/erc1/compiler.py"))
    args = p.parse_args()

    if sha256_file(args.compiler) != EXPECTED_COMPILER_SHA256:
        raise ValueError("frozen compiler hash mismatch")
    args.candidate_dir.mkdir(parents=True, exist_ok=True)
    args.scorer_map.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    days = load_days()
    scorer_rows = []
    manifest_rows = []
    for event in EVENTS:
        adapted = adapted_window(days[event["date"]], event["start"])
        parquet_path = args.candidate_dir / f"{event['opaque_id']}.parquet"
        adapted.to_parquet(parquet_path, index=False)
        staged_sha = sha256_file(parquet_path)
        meta = {
            "opaque_id": event["opaque_id"],
            "inject_time": event["start"],
            "source_metrics_sha256": DAYS[event["date"]]["raw_sha256"],
            "staged_metrics_sha256": staged_sha,
        }
        meta_path = args.candidate_dir / f"{event['opaque_id']}.json"
        meta_path.write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        scorer_rows.append({
            "opaque_id": event["opaque_id"],
            "item": event["item"],
            "date": event["date"],
            "fault": event["fault"],
            "true_actuator": event["actuator"],
        })
        manifest_rows.append({
            "opaque_id": event["opaque_id"],
            "candidate_meta_sha256": sha256_file(meta_path),
            "staged_metrics_sha256": staged_sha,
            "source_metrics_sha256": DAYS[event["date"]]["raw_sha256"],
            "row_count": len(adapted),
            "column_count": len(adapted.columns),
        })

    forbidden = ("true_actuator", "fault", "date", "item", "P51_05", "P57_03", "P74_00")
    for path in args.candidate_dir.iterdir():
        if path.suffix == ".json":
            text = path.read_text(encoding="utf-8")
            if any(term in text for term in forbidden):
                raise ValueError(f"candidate metadata leakage: {path.name}")

    args.scorer_map.write_text(json.dumps({"unit":"ERC-2AR","events":scorer_rows}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "unit": "ERC-2AR",
        "status": "ERC2AR_STAGING_PASS",
        "case_count": len(manifest_rows),
        "compiler_sha256": EXPECTED_COMPILER_SHA256,
        "events": manifest_rows,
        "scientific_predictions": 0,
        "feature_scores_computed": False,
        "candidate_contains_labels": False,
    }
    args.manifest.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status":manifest["status"],"case_count":manifest["case_count"],"scientific_predictions":0}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
