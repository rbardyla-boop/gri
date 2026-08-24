from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from .protocol import (
    CALIBRATION_COUNT,
    CALIBRATION_SALT,
    ERC3B_CALIBRATION_MAP,
    ERC3B_SCIENCE_MAP,
    ERC3C_CALIBRATION_MAP,
    ERC3C_SCIENCE_MAP,
    EXPECTED_ERC3A_IDS_SHA256,
    EXPECTED_ERC3B_CALIBRATION_IDS_SHA256,
    EXPECTED_ERC3B_SCIENCE_IDS_SHA256,
    EXPECTED_ERC3C_CALIBRATION_IDS_SHA256,
    EXPECTED_ERC3C_SCIENCE_IDS_SHA256,
    EXPECTED_ROWS,
    EXPECTED_TARGETS,
    EXPECTED_TYPES,
    LABELS_MD5,
    LABELS_URL,
    OLD_ERC3A_MAP,
    PER_STRATUM,
    SCIENCE_COUNT,
    SCIENCE_SALT,
    sha256_bytes,
    sha256_json,
    sha256_text,
    opaque_id,
)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "gri-erc3d/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def parse_rows(blob: bytes) -> list[dict]:
    reader = csv.DictReader(blob.decode("utf-8-sig").splitlines())
    required = {"sample_id", "fault_target", "sc_type", "t_evnt_start"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError(f"missing required label columns: {required - set(reader.fieldnames or [])}")
    rows: list[dict] = []
    for raw in reader:
        if any(raw.get(key, "").strip() == "" for key in required):
            continue
        rows.append(
            {
                "sample_id": int(float(raw["sample_id"])),
                "fault_target": raw["fault_target"].strip(),
                "sc_type": int(float(raw["sc_type"])),
                "t_evnt_start": float(raw["t_evnt_start"]),
            }
        )
    return rows


def _rank(row: dict, salt: str) -> tuple[str, int]:
    return sha256_text(f"{salt}|{row['sample_id']}"), int(row["sample_id"])


def _map_ids(path: Path, expected_count: int, expected_hash: str) -> set[int]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) != expected_count:
        raise ValueError(f"{path} must contain {expected_count} rows")
    ids = [int(row["sample_id"]) for row in rows]
    if len(set(ids)) != expected_count:
        raise ValueError(f"duplicate IDs in {path}")
    digest = sha256_json(ids)
    if digest != expected_hash:
        raise ValueError(f"frozen predecessor hash changed for {path}: {digest}")
    return set(ids)


def load_exclusion_union() -> tuple[set[int], dict[str, str]]:
    groups = {
        "erc3a_ids": _map_ids(OLD_ERC3A_MAP, 64, EXPECTED_ERC3A_IDS_SHA256),
        "erc3b_calibration_ids": _map_ids(ERC3B_CALIBRATION_MAP, 8, EXPECTED_ERC3B_CALIBRATION_IDS_SHA256),
        "erc3b_science_ids": _map_ids(ERC3B_SCIENCE_MAP, 64, EXPECTED_ERC3B_SCIENCE_IDS_SHA256),
        "erc3c_calibration_ids": _map_ids(ERC3C_CALIBRATION_MAP, 8, EXPECTED_ERC3C_CALIBRATION_IDS_SHA256),
        "erc3c_science_ids": _map_ids(ERC3C_SCIENCE_MAP, 64, EXPECTED_ERC3C_SCIENCE_IDS_SHA256),
    }
    names = list(groups)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1 :]:
            if groups[left_name] & groups[right_name]:
                raise ValueError(f"predecessor exclusion overlap: {left_name} / {right_name}")
    union = set().union(*groups.values())
    if len(union) != 208:
        raise ValueError(f"permanent exclusion union must contain 208 IDs, got {len(union)}")
    hashes = {f"{name}_sha256": sha256_json(sorted(ids)) for name, ids in groups.items()}
    hashes["exclusion_union_sha256"] = sha256_json(sorted(union))
    return union, hashes


def select(rows: list[dict], exclusions: set[int]) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    eligible = [row for row in rows if row["sample_id"] not in exclusions]
    if len({row["sample_id"] for row in eligible}) != len(eligible):
        raise ValueError("labels contain duplicate eligible sample IDs")
    calibration_rows = sorted(eligible, key=lambda row: _rank(row, CALIBRATION_SALT))[:CALIBRATION_COUNT]
    if len(calibration_rows) != CALIBRATION_COUNT:
        raise ValueError("calibration selection count mismatch")
    calibration_ids = {row["sample_id"] for row in calibration_rows}

    expected_keys = {(target, sc_type) for target in EXPECTED_TARGETS for sc_type in EXPECTED_TYPES}
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in eligible:
        if row["sample_id"] in calibration_ids:
            continue
        key = (row["fault_target"], row["sc_type"])
        if key in expected_keys:
            groups[key].append(row)
    if set(groups) != expected_keys:
        raise ValueError(f"science stratum mismatch: {sorted(set(groups) ^ expected_keys)}")
    science_rows: list[dict] = []
    for key in sorted(expected_keys):
        candidates = sorted(groups[key], key=lambda row: _rank(row, SCIENCE_SALT))
        if len(candidates) < PER_STRATUM:
            raise ValueError(f"too few candidates in stratum {key}")
        science_rows.extend(candidates[:PER_STRATUM])
    if len(science_rows) != SCIENCE_COUNT:
        raise ValueError("science selection count mismatch")
    science_ids = {row["sample_id"] for row in science_rows}
    if calibration_ids & science_ids or science_ids & exclusions:
        raise ValueError("ERC-3D selection overlaps exclusion union or calibration")

    calibration_acquisition: list[dict] = []
    calibration_public: list[dict] = []
    science_acquisition: list[dict] = []
    science_public: list[dict] = []
    scorer: list[dict] = []
    for row in sorted(calibration_rows, key=lambda item: item["sample_id"]):
        opaque = opaque_id("P90D-CAL", row["sample_id"])
        calibration_acquisition.append({"opaque_id": opaque, "sample_id": row["sample_id"], "t_evnt_start": row["t_evnt_start"]})
        calibration_public.append({"opaque_id": opaque, "t_evnt_start": row["t_evnt_start"]})
    for row in sorted(science_rows, key=lambda item: item["sample_id"]):
        opaque = opaque_id("P90D-SCI", row["sample_id"])
        science_acquisition.append({"opaque_id": opaque, "sample_id": row["sample_id"], "t_evnt_start": row["t_evnt_start"]})
        science_public.append({"opaque_id": opaque, "t_evnt_start": row["t_evnt_start"]})
        scorer.append({"opaque_id": opaque, "truth": {"fault_target": row["fault_target"], "sc_type": row["sc_type"]}})
    return calibration_acquisition, calibration_public, science_acquisition, science_public, scorer


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    blob = download(LABELS_URL)
    if hashlib.md5(blob).hexdigest() != LABELS_MD5:
        raise ValueError("published labels MD5 mismatch")
    rows = parse_rows(blob)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"expected {EXPECTED_ROWS} label rows, got {len(rows)}")
    exclusions, predecessor_hashes = load_exclusion_union()
    calibration, calibration_public, science, science_public, scorer = select(rows, exclusions)
    counts = Counter((row["truth"]["fault_target"], row["truth"]["sc_type"]) for row in scorer)
    if len(counts) != 16 or set(counts.values()) != {PER_STRATUM}:
        raise ValueError(f"science balance mismatch: {counts}")
    _write(args.out_dir / "ERC3D_CALIBRATION_ACQUISITION_MAP.json", calibration)
    _write(args.out_dir / "ERC3D_CALIBRATION_PUBLIC_SELECTION.json", calibration_public)
    _write(args.out_dir / "ERC3D_SCIENCE_ACQUISITION_MAP.json", science)
    _write(args.out_dir / "ERC3D_PUBLIC_SELECTION.json", science_public)
    _write(args.out_dir / "ERC3D_SCORER_MAP.json", scorer)
    calibration_ids = [row["sample_id"] for row in calibration]
    science_ids = [row["sample_id"] for row in science]
    record = {
        "unit": "ERC-3D",
        "status": "ERC3D_METADATA_SELECTION_FROZEN",
        "labels_url": LABELS_URL,
        "labels_md5": LABELS_MD5,
        "labels_sha256": sha256_bytes(blob),
        "labels_row_count": len(rows),
        "permanent_exclusion_count": len(exclusions),
        **predecessor_hashes,
        "calibration_selection_count": len(calibration),
        "calibration_ids_sha256": sha256_json(calibration_ids),
        "science_selection_count": len(science),
        "science_ids_sha256": sha256_json(science_ids),
        "science_public_selection_sha256": sha256_json(science_public),
        "stratum_count": len(counts),
        "per_stratum": PER_STRATUM,
        "calibration_science_overlap": 0,
        "selection_exclusion_overlap": 0,
        "waveform_archive_downloaded": False,
        "calibration_waveforms_opened": 0,
        "science_waveforms_opened": 0,
        "science_signal_columns_read": 0,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
    }
    record["record_sha256"] = sha256_json(record)
    _write(args.out_dir / "ERC3D_METADATA_SELECTION_RECORD.json", record)
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
