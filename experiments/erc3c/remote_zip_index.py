from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from experiments.erc3b.remote_zip_index import (
    central_directory_location,
    fetch_range,
    head_size,
    parse_central_directory,
)

from .protocol import ARCHIVE_PUBLISHED_MD5, ARCHIVE_URL, EXPECTED_PKL_MEMBERS, sha256_json


def _load_map(path: Path, role: str, count: int) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) != count:
        raise ValueError(f"{path} must contain {count} rows")
    output = []
    for row in rows:
        if set(row) != {"opaque_id", "sample_id", "t_evnt_start"}:
            raise ValueError(f"unexpected acquisition fields in {path}")
        output.append({**row, "role": role})
    return output


def build_index(calibration_map: Path, science_map: Path, output: Path) -> dict:
    calibration = _load_map(calibration_map, "calibration", 8)
    science = _load_map(science_map, "science", 64)
    selected_maps = calibration + science
    if len({row["opaque_id"] for row in selected_maps}) != 72:
        raise ValueError("ERC-3C opaque IDs are not unique")
    if len({int(row["sample_id"]) for row in selected_maps}) != 72:
        raise ValueError("ERC-3C selected sample IDs are not unique")

    archive_size, accept_ranges, final_url, identity_headers = head_size(ARCHIVE_URL)
    cd_offset, cd_size, entry_count, structural_bytes = central_directory_location(ARCHIVE_URL, archive_size)
    central_blob = fetch_range(ARCHIVE_URL, cd_offset, cd_offset + cd_size - 1)
    structural_bytes += len(central_blob)
    central_rows = parse_central_directory(central_blob, entry_count)
    pkl_rows = [row for row in central_rows if row["path"].endswith("_sample_hv_double_line_90kv.pkl")]
    by_basename = {Path(row["path"]).name: row for row in pkl_rows}
    if len(pkl_rows) != EXPECTED_PKL_MEMBERS or len(by_basename) != EXPECTED_PKL_MEMBERS:
        raise ValueError(f"expected {EXPECTED_PKL_MEMBERS} unique pkl members")

    selected: list[dict] = []
    for case in selected_maps:
        basename = f"{int(case['sample_id'])}_sample_hv_double_line_90kv.pkl"
        member = by_basename.get(basename)
        if member is None:
            raise ValueError(f"selected member missing: {basename}")
        selected.append({"role": case["role"], "opaque_id": case["opaque_id"], "sample_id": int(case["sample_id"]), "t_evnt_start": float(case["t_evnt_start"]), **member})

    record = {
        "unit": "ERC-3C",
        "status": "ERC3C_REMOTE_ZIP_INDEX_CAPTURED",
        "zenodo_record": "10.5281/zenodo.21109169",
        "archive_url": ARCHIVE_URL,
        "archive_published_md5": ARCHIVE_PUBLISHED_MD5,
        "archive_size_bytes": archive_size,
        "accept_ranges_header": accept_ranges,
        "resolved_url": final_url,
        "resolved_url_host": urlparse(final_url).netloc,
        "archive_identity_headers": identity_headers,
        "zip_entry_count": entry_count,
        "pkl_member_count": len(pkl_rows),
        "central_directory_offset": cd_offset,
        "central_directory_size": cd_size,
        "calibration_member_count": 8,
        "science_member_count": 64,
        "selected_member_count": 72,
        "selected_members_sha256": sha256_json([{key: value for key, value in row.items() if key != "sample_id"} for row in selected]),
        "selected_members": selected,
        "range_structure_bytes_read": structural_bytes,
        "selected_member_payload_bytes_read": 0,
        "selected_member_payload_ranges_requested": 0,
        "waveform_members_opened": 0,
        "calibration_waveforms_opened": 0,
        "science_waveforms_opened": 0,
        "science_signal_columns_read": 0,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "same_set_rescue_authorized": False,
    }
    output.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Index ERC-3C ZIP central directory without payload access")
    parser.add_argument("--calibration-map", type=Path, required=True)
    parser.add_argument("--science-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = build_index(args.calibration_map, args.science_map, args.output)
    print(json.dumps({key: value for key, value in record.items() if key != "selected_members"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
