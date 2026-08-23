from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

UNIT = "ERC-2AR"
EXPECTED_ROWS = 86400
EXPECTED_COLUMNS = 33

ARCHIVES = {
    "part1": {
        "url": "https://iair.mchtr.pw.edu.pl/content/download/163/817/file/Lublin_all_data_part1.zip",
        "sha256": "4fea6d279b1077bc51a15a21170144125e9e973214de57b1f8b622e16ba774a3",
    },
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

SELECTED_DAYS = {
    "2001-10-30": ("part4", "Lublin_all_data/30102001.txt"),
    "2001-11-09": ("part2", "Lublin_all_data/09112001.txt"),
    "2001-11-17": ("part3", "Lublin_all_data/17112001.txt"),
    "2001-11-20": ("part3", "Lublin_all_data/20112001.txt"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "gri-erc2ar-data-binding/1.0",
            "Accept": "application/zip,application/octet-stream,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        body = response.read()
    if not body:
        raise ValueError(f"empty response from {url}")
    return body


def validate_daily_file(date: str, member_path: str, body: bytes) -> dict:
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{date} daily file is not strict ASCII") from exc

    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != EXPECTED_ROWS:
        raise ValueError(f"{date} expected {EXPECTED_ROWS} non-empty rows, found {len(lines)}")

    bad_width = []
    timestamps = []
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) != EXPECTED_COLUMNS:
            bad_width.append({"row": index, "columns": len(fields)})
            if len(bad_width) >= 10:
                break
        try:
            timestamp = float(fields[0])
        except (ValueError, IndexError) as exc:
            raise ValueError(f"{date} row {index} has invalid timestamp") from exc
        if not timestamp.is_integer():
            raise ValueError(f"{date} row {index} timestamp is not integral: {timestamp}")
        timestamps.append(int(timestamp))

    if bad_width:
        raise ValueError(f"{date} row-width failures: {bad_width}")
    if timestamps != list(range(EXPECTED_ROWS)):
        mismatch = next(
            (i for i, (actual, expected) in enumerate(zip(timestamps, range(EXPECTED_ROWS))) if actual != expected),
            None,
        )
        raise ValueError(f"{date} timestamp sequence mismatch at row {mismatch}")

    return {
        "date": date,
        "member_path": member_path,
        "raw_sha256": sha256_bytes(body),
        "raw_size": len(body),
        "row_count": len(lines),
        "column_count": EXPECTED_COLUMNS,
        "first_timestamp": timestamps[0],
        "last_timestamp": timestamps[-1],
        "timestamps_strict_0_86399": True,
        "signal_values_numeric_parsed": False,
        "signal_values_scored": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    needed_parts = sorted({part for part, _ in SELECTED_DAYS.values()})
    archive_bodies: dict[str, bytes] = {}
    archive_rows = []
    for part in needed_parts:
        spec = ARCHIVES[part]
        body = fetch(spec["url"])
        actual_sha = sha256_bytes(body)
        if actual_sha != spec["sha256"]:
            raise ValueError(f"{part} archive SHA mismatch: {actual_sha} != {spec['sha256']}")
        archive_bodies[part] = body
        archive_rows.append(
            {
                "part": part,
                "url": spec["url"],
                "sha256": actual_sha,
                "size": len(body),
            }
        )

    selected = []
    for date, (part, member_path) in sorted(SELECTED_DAYS.items()):
        with zipfile.ZipFile(BytesIO(archive_bodies[part])) as archive:
            names = set(archive.namelist())
            if member_path not in names:
                raise ValueError(f"{date} selected member missing from {part}: {member_path}")
            selected.append(validate_daily_file(date, member_path, archive.read(member_path)))

    result = {
        "unit": UNIT,
        "status": "ERC2AR_DATA_BINDING_PASS",
        "telemetry_archives_downloaded": True,
        "telemetry_member_values_read_as_text": True,
        "telemetry_signal_values_numeric_parsed": False,
        "event_windows_constructed": False,
        "feature_scores_computed": False,
        "scientific_predictions": 0,
        "scorer_opened_after_prediction": False,
        "bound_archive_count": len(archive_rows),
        "selected_day_count": len(selected),
        "archives": archive_rows,
        "selected_days": selected,
        "unneeded_but_inventory_bound_part1_sha256": ARCHIVES["part1"]["sha256"],
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    result["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
