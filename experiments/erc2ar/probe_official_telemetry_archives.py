from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

UNIT = "ERC-2AR"
ARCHIVES = (
    (
        "part1",
        "https://iair.mchtr.pw.edu.pl/content/download/163/817/file/Lublin_all_data_part1.zip",
    ),
    (
        "part2",
        "https://iair.mchtr.pw.edu.pl/content/download/164/821/file/Lublin_all_data_part2.zip",
    ),
    (
        "part3",
        "https://iair.mchtr.pw.edu.pl/content/download/165/825/file/Lublin_all_data_part3.zip",
    ),
    (
        "part4",
        "https://iair.mchtr.pw.edu.pl/content/download/166/829/file/Lublin_all_data_part4.zip",
    ),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "gri-erc2ar-source-inventory/1.0",
            "Accept": "application/zip,application/octet-stream,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read()
    if not body:
        raise ValueError(f"empty response from {url}")
    return body


def inspect_archive(name: str, url: str, body: bytes) -> dict:
    try:
        archive = zipfile.ZipFile(BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{name} is not a valid ZIP archive") from exc

    entries = []
    for info in sorted(archive.infolist(), key=lambda row: row.filename.lower()):
        if info.is_dir():
            continue
        entries.append(
            {
                "path": info.filename,
                "size": info.file_size,
                "compressed_size": info.compress_size,
                "crc32": f"{info.CRC:08x}",
            }
        )
    if not entries:
        raise ValueError(f"{name} ZIP contains no files")
    return {
        "name": name,
        "url": url,
        "archive_size": len(body),
        "archive_sha256": sha256_bytes(body),
        "entry_count": len(entries),
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for name, url in ARCHIVES:
        rows.append(inspect_archive(name, url, fetch(url)))

    result = {
        "unit": UNIT,
        "status": "ERC2AR_OFFICIAL_TELEMETRY_ARCHIVE_INVENTORY_CAPTURED",
        "telemetry_archives_downloaded": True,
        "telemetry_member_values_read": False,
        "event_windows_constructed": False,
        "feature_scores_computed": False,
        "scientific_predictions": 0,
        "scorer_opened_after_prediction": False,
        "archive_count": len(rows),
        "archives": rows,
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    result["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "unit": result["unit"],
        "status": result["status"],
        "archive_count": result["archive_count"],
        "archives": [
            {
                "name": row["name"],
                "archive_sha256": row["archive_sha256"],
                "archive_size": row["archive_size"],
                "entry_count": row["entry_count"],
                "entries": row["entries"],
            }
            for row in rows
        ],
        "record_sha256": result["record_sha256"],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
