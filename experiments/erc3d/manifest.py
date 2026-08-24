from __future__ import annotations

import argparse
import json
from pathlib import Path

from .protocol import EXPECTED_COLUMNS, sha256_json


def binding_sha256(row: dict) -> str:
    material = {key: row[key] for key in ("path", "compression", "crc32", "compressed_size", "uncompressed_size", "local_header_offset")}
    return sha256_json(material)


def build(index_path: Path, output_dir: Path) -> None:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index["status"] != "ERC3D_REMOTE_ZIP_INDEX_CAPTURED":
        raise ValueError("wrong ERC-3D index status")
    grouped = {"calibration": [], "science": []}
    for row in index["selected_members"]:
        grouped[row["role"]].append(
            {
                "opaque_id": row["opaque_id"],
                "t_evnt_start": row["t_evnt_start"],
                "waveform_binding": {
                    "payload_sha256": None,
                    "archive_member_binding_sha256": binding_sha256(row),
                    "channel_schema": list(EXPECTED_COLUMNS),
                    "sample_count": 6400,
                    "sample_rate_hz": 6400,
                    "time_representation": "integer-microsecond metadata; physical endpoint coordinate is (arange(6400)+1)/6400",
                },
            }
        )
    for role, rows in grouped.items():
        rows.sort(key=lambda row: row["opaque_id"])
        (output_dir / f"ERC3D_{role.upper()}_PRODUCER_MANIFEST.json").write_text(json.dumps(rows, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    build(args.index, args.output_dir)
    print("ERC3D_PRODUCER_MANIFEST_BUILD_PASS")


if __name__ == "__main__":
    main()
