from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .protocol import CHANNEL_SCHEMA, sha256_json


def _binding(row: dict) -> str:
    material = {
        "path": row["path"],
        "compression": row["compression"],
        "crc32": row["crc32"],
        "compressed_size": row["compressed_size"],
        "uncompressed_size": row["uncompressed_size"],
        "local_header_offset": row["local_header_offset"],
    }
    return sha256_json(material)


def build(index_path: Path, output_dir: Path) -> tuple[list[dict], list[dict]]:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index["status"] != "ERC3B_REMOTE_ZIP_INDEX_CAPTURED":
        raise ValueError("remote index is not a captured ERC-3B index")
    manifests = {"calibration": [], "science": []}
    for row in index["selected_members"]:
        item = {
            "opaque_id": row["opaque_id"],
            "t_evnt_start": row["t_evnt_start"],
            "waveform_binding": {
                "payload_sha256": None,
                "archive_member_binding_sha256": _binding(row),
                "channel_schema": list(CHANNEL_SCHEMA),
            },
        }
        manifests[row["role"]].append(item)
    for role, rows in manifests.items():
        rows.sort(key=lambda item: item["opaque_id"])
        (output_dir / f"ERC3B_{role.upper()}_PRODUCER_MANIFEST.json").write_text(
            json.dumps(rows, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    return manifests["calibration"], manifests["science"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    calibration, science = build(args.index, args.output_dir)
    print(json.dumps({"calibration_manifest_count": len(calibration), "science_manifest_count": len(science)}))


if __name__ == "__main__":
    main()
