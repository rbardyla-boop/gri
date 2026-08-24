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
    EXPECTED_OLD_ERC3A_IDS_SHA256,
    EXPECTED_ROWS,
    EXPECTED_TARGETS,
    EXPECTED_TYPES,
    LABELS_MD5,
    LABELS_URL,
    OLD_ERC3A_MAP,
    PER_STRATUM,
    SCIENCE_COUNT,
    SCIENCE_SALT,
    canonical_json,
    opaque_id,
    sha256_bytes,
    sha256_json,
    sha256_text,
)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "gri-erc3b/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def parse_int_like(value: str) -> int:
    return int(float(value))


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
                "sample_id": parse_int_like(raw["sample_id"]),
                "fault_target": raw["fault_target"].strip(),
                "sc_type": parse_int_like(raw["sc_type"]),
                "t_evnt_start": float(raw["t_evnt_start"]),
            }
        )
    return rows


def _rank(row: dict, salt: str) -> tuple[str, int]:
    return sha256_text(f"{salt}|{row['sample_id']}"), int(row["sample_id"])


def load_old_exclusions(path: Path = OLD_ERC3A_MAP) -> tuple[set[int], str]:
    old = json.loads(path.read_text(encoding="utf-8"))
    ids = [int(row["sample_id"]) for row in old]
    if len(ids) != 64 or len(set(ids)) != 64:
        raise ValueError("inherited ERC-3A exclusion map is not exactly 64 unique IDs")
    digest = sha256_json(ids)
    if digest != EXPECTED_OLD_ERC3A_IDS_SHA256:
        raise ValueError(f"inherited ERC-3A exclusion hash changed: {digest}")
    return set(ids), digest


def select(rows: list[dict], old_exclusions: set[int]) -> tuple[list[dict], list[dict], list[dict]]:
    eligible = [row for row in rows if row["sample_id"] not in old_exclusions]
    if len({row["sample_id"] for row in eligible}) != len(eligible):
        raise ValueError("labels contain duplicate eligible sample IDs")

    calibration_rows = sorted(eligible, key=lambda row: _rank(row, CALIBRATION_SALT))[:CALIBRATION_COUNT]
    if len(calibration_rows) != CALIBRATION_COUNT:
        raise ValueError("calibration selection count mismatch")
    calibration_ids = {row["sample_id"] for row in calibration_rows}

    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in eligible:
        if row["sample_id"] in calibration_ids:
            continue
        key = (row["fault_target"], row["sc_type"])
        if key[0] in EXPECTED_TARGETS and key[1] in EXPECTED_TYPES:
            groups[key].append(row)
    expected_keys = {(target, sc_type) for target in EXPECTED_TARGETS for sc_type in EXPECTED_TYPES}
    if set(groups) != expected_keys:
        raise ValueError(f"science stratum set mismatch: {sorted(set(groups) ^ expected_keys)}")

    science_rows: list[dict] = []
    for key in sorted(expected_keys):
        candidates = sorted(groups[key], key=lambda row: _rank(row, SCIENCE_SALT))
        if len(candidates) < PER_STRATUM:
            raise ValueError(f"too few rows in science stratum {key}: {len(candidates)}")
        science_rows.extend(candidates[:PER_STRATUM])
    if len(science_rows) != SCIENCE_COUNT:
        raise ValueError("science selection count mismatch")
    if calibration_ids & {row["sample_id"] for row in science_rows}:
        raise ValueError("calibration/science selection overlap")

    calibration_acquisition: list[dict] = []
    calibration_public: list[dict] = []
    science_acquisition: list[dict] = []
    science_public: list[dict] = []
    scorer: list[dict] = []

    for row in sorted(calibration_rows, key=lambda item: item["sample_id"]):
        opaque = opaque_id("P90B-CAL", row["sample_id"])
        calibration_acquisition.append(
            {"opaque_id": opaque, "sample_id": row["sample_id"], "t_evnt_start": row["t_evnt_start"]}
        )
        calibration_public.append({"opaque_id": opaque, "t_evnt_start": row["t_evnt_start"]})

    for row in sorted(science_rows, key=lambda item: item["sample_id"]):
        opaque = opaque_id("P90B-SCI", row["sample_id"])
        science_acquisition.append(
            {"opaque_id": opaque, "sample_id": row["sample_id"], "t_evnt_start": row["t_evnt_start"]}
        )
        science_public.append({"opaque_id": opaque, "t_evnt_start": row["t_evnt_start"]})
        scorer.append(
            {
                "opaque_id": opaque,
                "truth": {"fault_target": row["fault_target"], "sc_type": row["sc_type"]},
            }
        )
    return (
        calibration_acquisition,
        calibration_public,
        science_acquisition,
        science_public,
        scorer,
    )


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--old-map", type=Path, default=OLD_ERC3A_MAP)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    labels_blob = download(LABELS_URL)
    labels_md5 = hashlib.md5(labels_blob).hexdigest()
    if labels_md5 != LABELS_MD5:
        raise ValueError(f"published labels MD5 mismatch: {labels_md5}")
    rows = parse_rows(labels_blob)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"expected {EXPECTED_ROWS} eligible label rows, got {len(rows)}")

    old_ids, old_hash = load_old_exclusions(args.old_map)
    calibration, calibration_public, science, science_public, scorer = select(rows, old_ids)
    counts = Counter(
        (item["truth"]["fault_target"], item["truth"]["sc_type"])
        for item in scorer
    )
    if len(counts) != 16 or set(counts.values()) != {PER_STRATUM}:
        raise ValueError(f"science balance mismatch: {counts}")

    _write(args.out_dir / "ERC3B_CALIBRATION_ACQUISITION_MAP.json", calibration)
    _write(args.out_dir / "ERC3B_CALIBRATION_PUBLIC_SELECTION.json", calibration_public)
    _write(args.out_dir / "ERC3B_SCIENCE_ACQUISITION_MAP.json", science)
    _write(args.out_dir / "ERC3B_PUBLIC_SELECTION.json", science_public)
    _write(args.out_dir / "ERC3B_SCORER_MAP.json", scorer)

    calibration_ids = [row["sample_id"] for row in calibration]
    science_ids = [row["sample_id"] for row in science]
    record = {
        "unit": "ERC-3B",
        "status": "ERC3B_METADATA_SELECTION_FROZEN",
        "labels_url": LABELS_URL,
        "labels_md5": labels_md5,
        "labels_sha256": sha256_bytes(labels_blob),
        "labels_row_count": len(rows),
        "inherited_erc3a_exclusion_count": len(old_ids),
        "inherited_erc3a_exclusion_sha256": old_hash,
        "calibration_selection_count": len(calibration),
        "calibration_ids_sha256": sha256_json(calibration_ids),
        "calibration_public_selection_sha256": sha256_json(calibration_public),
        "science_selection_count": len(science),
        "science_ids_sha256": sha256_json(science_ids),
        "science_public_selection_sha256": sha256_json(science_public),
        "stratum_count": len(counts),
        "per_stratum": PER_STRATUM,
        "calibration_science_overlap": 0,
        "waveform_archive_downloaded": False,
        "waveform_members_opened": 0,
        "scientific_waveforms_opened": 0,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
    }
    record["record_sha256"] = sha256_json(record)
    _write(args.out_dir / "ERC3B_METADATA_SELECTION_RECORD.json", record)
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
