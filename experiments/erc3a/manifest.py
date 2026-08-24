from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from .channel_schema import CHANNEL_SCHEMA_RECORD


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _map_by_opaque(rows: list[dict], label: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        opaque_id = row.get("opaque_id")
        if not isinstance(opaque_id, str) or opaque_id in result:
            raise ValueError(f"invalid or duplicate opaque_id in {label}")
        result[opaque_id] = row
    return result


def build_manifest(index_record: dict, acquisition_map: list[dict]) -> list[dict]:
    acquisition = _map_by_opaque(acquisition_map, "acquisition map")
    selected = index_record.get("selected_members")
    if not isinstance(selected, list) or len(selected) != len(acquisition):
        raise ValueError("index/acquisition map count mismatch")

    archive_identity = {
        "archive_url": index_record["archive_url"],
        "archive_host": urlparse(index_record["archive_url"]).netloc,
        "archive_published_md5": index_record["archive_published_md5"],
        "archive_size_bytes": index_record["archive_size_bytes"],
        "central_directory_offset": index_record["central_directory_offset"],
        "central_directory_size": index_record["central_directory_size"],
    }
    manifest = []
    for row in sorted(selected, key=lambda item: item["opaque_id"]):
        opaque_id = row["opaque_id"]
        acq = acquisition.get(opaque_id)
        if acq is None:
            raise ValueError(f"indexed member missing from acquisition map: {opaque_id}")
        if row["sample_id"] != acq["sample_id"] or row["t_evnt_start"] != acq["t_evnt_start"]:
            raise ValueError(f"acquisition/index binding mismatch: {opaque_id}")

        binding = {
            **archive_identity,
            "member_crc32": row["crc32"],
            "compressed_size": row["compressed_size"],
            "uncompressed_size": row["uncompressed_size"],
            "local_header_offset": row["local_header_offset"],
            "compression": row["compression"],
            "flags": row["flags"],
        }
        manifest.append(
            {
                "opaque_id": opaque_id,
                "t_evnt_start": acq["t_evnt_start"],
                "waveform_binding": {
                    "kind": "ZIP_CENTRAL_DIRECTORY_MEMBER",
                    "sha256": sha256_text(canonical_json(binding)),
                    "archive_md5": archive_identity["archive_published_md5"],
                    "member_crc32": row["crc32"],
                    "compressed_size": row["compressed_size"],
                    "uncompressed_size": row["uncompressed_size"],
                    "payload_sha256": None,
                },
                "channel_schema": CHANNEL_SCHEMA_RECORD,
            }
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-map", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    acquisition = json.loads(args.acquisition_map.read_text(encoding="utf-8"))
    index_record = json.loads(args.index.read_text(encoding="utf-8"))
    manifest = build_manifest(index_record, acquisition)
    args.output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ERC3A_PRODUCER_MANIFEST_BUILT", "case_count": len(manifest)}, indent=2))


if __name__ == "__main__":
    main()

