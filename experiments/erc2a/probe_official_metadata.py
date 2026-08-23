from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

UNIT = "ERC-2A"
DEFINITION_URL = (
    "https://iair.mchtr.pw.edu.pl/content/download/173/857/file/"
    "damadics-benchmark-definition.zip"
)
DESCRIPTION_URL = (
    "https://iair.mchtr.pw.edu.pl/content/download/161/809/file/"
    "damadics-lublin-data-description.zip"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "gri-erc2a-metadata-qualification/1.0",
            "Accept": "application/octet-stream,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        if not body:
            raise ValueError(f"empty response from {url}")
        return body


def inspect_zip(name: str, url: str, body: bytes) -> dict:
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
        "size": len(body),
        "sha256": sha256_bytes(body),
        "entry_count": len(entries),
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    definition = fetch(DEFINITION_URL)
    description = fetch(DESCRIPTION_URL)
    result = {
        "unit": UNIT,
        "status": "ERC2A_METADATA_INVENTORY_CAPTURED",
        "telemetry_downloaded": False,
        "scientific_predictions": 0,
        "scorer_opened": False,
        "archives": [
            inspect_zip("benchmark_definition", DEFINITION_URL, definition),
            inspect_zip("data_file_description", DESCRIPTION_URL, description),
        ],
    }
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["record_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
