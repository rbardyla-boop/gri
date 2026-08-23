from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

NAMESPACE = "erc1-mco04-cleanroom-v1"
EXPECTED_TOTAL = 90
EXPECTED_ENGINEERING = 27
EXPECTED_SCIENTIFIC = 63
LOSSLESS_REPACK_REVISION = "92c773ab7bb79f525ec7d5dc53d96a74dbebce4d"
HISTORICAL_HF_REVISION = "afeacb11bcc94dadfd1c8f483ee4377b2b8b614e"
HISTORICAL_SOURCE_MANIFEST_SHA256 = "88b7339c642838f8955c1d0f28ed14de6984772325617129422a6a64e73a56cb"
CASE_RE = re.compile(r"^re3(?P<system>ob|ss|tt)_(?P<service>.+)_(?P<fault>f[1-5])_(?P<rep>\d+)$", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_metrics(case_dir: Path) -> tuple[pd.DataFrame, Path]:
    parquet = case_dir / "metrics.parquet"
    original = case_dir / "metrics.json"
    if parquet.exists() and original.exists():
        raise ValueError(f"ambiguous metric representation in {case_dir}")
    if parquet.exists():
        return pd.read_parquet(parquet), parquet
    if original.exists():
        raw = json.loads(original.read_text(encoding="utf-8"))
        raw = {key: values for key, values in raw.items() if values}
        union = sorted({point[0] for values in raw.values() for point in values})
        pos = {timestamp: index for index, timestamp in enumerate(union)}
        columns = list(raw)
        arr = np.full((len(union), len(columns)), np.nan, dtype=np.float64)
        for j, column in enumerate(columns):
            for timestamp, value in raw[column]:
                if value is not None:
                    arr[pos[timestamp], j] = value
        frame = pd.DataFrame(arr, columns=columns)
        frame.insert(0, "time", np.asarray(union, dtype=np.int64))
        return frame, original
    raise FileNotFoundError(f"missing metrics.parquet/metrics.json in {case_dir}")


def discover_cases(root: Path) -> list[Path]:
    found: dict[Path, None] = {}
    for filename in ("metrics.parquet", "metrics.json"):
        for path in root.rglob(filename):
            case_dir = path.parent
            if (case_dir / "inject_time.txt").exists() and CASE_RE.match(case_dir.name):
                found[case_dir] = None
    return sorted(found)


def parse_case_name(name: str) -> dict:
    match = CASE_RE.match(name)
    if not match:
        raise ValueError(f"unexpected RE3 case name: {name}")
    value = match.groupdict()
    return {
        "source_case": name,
        "system": value["system"].lower(),
        "root_cause_service": value["service"],
        "fault": value["fault"].lower(),
        "repetition": int(value["rep"]),
    }


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if "time" not in frame.columns:
        raise ValueError("metrics frame missing time column")
    out = frame.copy()
    out["time"] = pd.to_numeric(out["time"], errors="raise").astype("int64")
    out = out.sort_values("time", kind="mergesort").reset_index(drop=True)
    for column in out.columns:
        if column != "time":
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
    return out


def stage(
    data_root: Path,
    output_root: Path,
    evidence_class: str,
    source_revision: str,
    historical_source_manifest: Path | None,
) -> dict:
    if evidence_class not in {"EXACT_SOURCE_REPRODUCTION", "LOSSLESS_REPACK_REPRODUCTION"}:
        raise ValueError("invalid evidence class")
    if evidence_class == "LOSSLESS_REPACK_REPRODUCTION" and source_revision != LOSSLESS_REPACK_REVISION:
        raise ValueError(f"lossless repack must use pinned revision {LOSSLESS_REPACK_REVISION}")
    if evidence_class == "EXACT_SOURCE_REPRODUCTION":
        if source_revision != HISTORICAL_HF_REVISION:
            raise ValueError(f"exact source mode must use historical revision {HISTORICAL_HF_REVISION}")
        if historical_source_manifest is None or not historical_source_manifest.exists():
            raise ValueError("exact source mode requires historical source_manifest.json")
        if sha256_file(historical_source_manifest) != HISTORICAL_SOURCE_MANIFEST_SHA256:
            raise ValueError("historical source manifest SHA-256 mismatch")

    cases = discover_cases(data_root)
    if len(cases) != EXPECTED_TOTAL:
        raise ValueError(f"expected {EXPECTED_TOTAL} RE3 cases, found {len(cases)}")

    candidate = output_root / "candidate"
    scorer = output_root / "scorer_only"
    if output_root.exists():
        shutil.rmtree(output_root)
    candidate.mkdir(parents=True)
    scorer.mkdir(parents=True)

    score_rows: list[dict] = []
    candidate_rows: list[dict] = []
    representation_seen: set[str] = set()

    for case_dir in cases:
        labels = parse_case_name(case_dir.name)
        opaque_id = "E1-" + sha256_text(NAMESPACE + "|" + case_dir.name)[:20]
        inject_time = int((case_dir / "inject_time.txt").read_text(encoding="utf-8").strip())
        frame, source_metrics = read_metrics(case_dir)
        frame = normalize_frame(frame)
        representation_seen.add(source_metrics.suffix)

        if evidence_class == "LOSSLESS_REPACK_REPRODUCTION" and source_metrics.suffix != ".parquet":
            raise ValueError("lossless repack mode requires metrics.parquet for every case")
        if evidence_class == "EXACT_SOURCE_REPRODUCTION" and source_metrics.suffix != ".json":
            raise ValueError("exact source mode requires historical metrics.json representation")

        staged_path = candidate / f"{opaque_id}.parquet"
        frame.to_parquet(staged_path, index=False)
        metadata = {
            "opaque_id": opaque_id,
            "inject_time": inject_time,
            "source_metrics_sha256": sha256_file(source_metrics),
            "staged_metrics_sha256": sha256_file(staged_path),
            "source_representation": source_metrics.name,
        }
        (candidate / f"{opaque_id}.json").write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        candidate_rows.append(metadata)
        score_rows.append({"opaque_id": opaque_id, **labels})

    engineering = [row for row in score_rows if row["repetition"] == 1]
    scientific = [row for row in score_rows if row["repetition"] != 1]
    if len(engineering) != EXPECTED_ENGINEERING or len(scientific) != EXPECTED_SCIENTIFIC:
        raise ValueError(f"split mismatch engineering={len(engineering)} scientific={len(scientific)}")

    score_rows.sort(key=lambda row: row["opaque_id"])
    candidate_rows.sort(key=lambda row: row["opaque_id"])
    (scorer / "labels.json").write_text(
        json.dumps(score_rows, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "unit": "ERC-1",
        "status": "ERC1_STAGED",
        "evidence_class": evidence_class,
        "source_revision": source_revision,
        "case_count": len(score_rows),
        "engineering_count": len(engineering),
        "scientific_count": len(scientific),
        "representations": sorted(representation_seen),
        "candidate_manifest_sha256": sha256_text(
            json.dumps(candidate_rows, sort_keys=True, separators=(",", ":"))
        ),
        "scorer_map_sha256": sha256_file(scorer / "labels.json"),
    }
    manifest["record_sha256"] = sha256_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    )
    (output_root / "STAGING_MANIFEST.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--evidence-class",
        required=True,
        choices=["EXACT_SOURCE_REPRODUCTION", "LOSSLESS_REPACK_REPRODUCTION"],
    )
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--historical-source-manifest", type=Path)
    args = parser.parse_args()
    result = stage(
        args.data_root,
        args.output_root,
        args.evidence_class,
        args.source_revision,
        args.historical_source_manifest,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
