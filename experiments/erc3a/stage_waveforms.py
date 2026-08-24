from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .acquire_member import acquire_member, producer_input
from .channel_schema import CHANNEL_SCHEMA, SAMPLE_COUNT, SAMPLE_RATE_HZ, TIME_COLUMN
from .producer_boundary import assert_clean


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _by_opaque(rows: list[dict], label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        opaque_id = row.get("opaque_id")
        if not isinstance(opaque_id, str) or opaque_id in result:
            raise ValueError(f"invalid/duplicate opaque_id in {label}")
        result[opaque_id] = row
    return result


def waveform_from_published_pickle(payload: bytes) -> dict[str, list[float]]:
    """Decode one trusted official PROTECT-90 pandas pickle and enforce the frozen schema."""

    frame = pd.read_pickle(io.BytesIO(payload))
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("published waveform payload is not a pandas DataFrame")
    expected_columns = (TIME_COLUMN, *CHANNEL_SCHEMA)
    if frame.shape != (SAMPLE_COUNT, len(expected_columns)):
        raise ValueError(f"waveform shape mismatch: {frame.shape} != {(SAMPLE_COUNT, len(expected_columns))}")
    if tuple(str(column) for column in frame.columns) != expected_columns:
        raise ValueError("waveform column order/schema mismatch")

    times = pd.to_numeric(frame[TIME_COLUMN], errors="raise").to_numpy(dtype=np.float64)
    expected_times = np.arange(SAMPLE_COUNT, dtype=np.float64) / float(SAMPLE_RATE_HZ)
    if not np.all(np.isfinite(times)):
        raise ValueError("time axis contains non-finite values")
    if not np.allclose(times, expected_times, rtol=0.0, atol=1e-12):
        raise ValueError("time axis is not the frozen 6.4 kHz 0..6399/6400 grid")

    waveform: dict[str, list[float]] = {}
    for channel in CHANNEL_SCHEMA:
        values = pd.to_numeric(frame[channel], errors="raise").to_numpy(dtype=np.float64)
        if values.shape != (SAMPLE_COUNT,) or not np.all(np.isfinite(values)):
            raise ValueError(f"invalid/non-finite waveform values in {channel}")
        waveform[channel] = values.tolist()
    return waveform


def stage_selected(
    *,
    acquisition_map_path: Path,
    index_path: Path,
    producer_dir: Path,
    acquisition_receipt_path: Path,
    stage_receipt_path: Path,
) -> dict:
    acquisition_rows = json.loads(acquisition_map_path.read_text(encoding="utf-8"))
    index_record = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(acquisition_rows, list) or len(acquisition_rows) != 64:
        raise ValueError("acquisition map must contain exactly 64 rows")
    selected = index_record.get("selected_members")
    if not isinstance(selected, list) or len(selected) != 64:
        raise ValueError("acquisition index must contain exactly 64 selected members")
    if index_record.get("pkl_member_count") != 9022:
        raise ValueError("remote archive member-count binding mismatch")

    acquisition = _by_opaque(acquisition_rows, "acquisition map")
    indexed = _by_opaque(selected, "acquisition index")
    if set(acquisition) != set(indexed):
        raise ValueError("acquisition/index opaque-id set mismatch")

    archive_url = str(index_record["archive_url"])
    producer_dir.mkdir(parents=True, exist_ok=True)
    provenance_rows: list[dict] = []
    producer_receipts: list[dict] = []
    total_uncompressed_payload_bytes = 0
    total_compressed_payload_bytes = 0

    for opaque_id in sorted(acquisition):
        acq = acquisition[opaque_id]
        idx = indexed[opaque_id]
        acquired = acquire_member(
            archive_url=archive_url,
            acquisition_row=acq,
            index_row=idx,
        )
        waveform = waveform_from_published_pickle(acquired.payload)
        producer = producer_input(
            opaque_id=opaque_id,
            t_evnt_start=float(acq["t_evnt_start"]),
            waveform=waveform,
            payload_sha256=acquired.payload_sha256,
        )
        producer_bytes = (json.dumps(producer, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        producer_path = producer_dir / f"{opaque_id}.json"
        producer_path.write_bytes(producer_bytes)

        provenance_rows.append(
            {
                "opaque_id": opaque_id,
                "sample_id": int(acquired.sample_id),
                "member_path": acquired.member_path,
                "member_crc32": idx["crc32"],
                "compressed_size": int(idx["compressed_size"]),
                "uncompressed_size": int(idx["uncompressed_size"]),
                "payload_sha256": acquired.payload_sha256,
            }
        )
        producer_receipts.append(
            {
                "opaque_id": opaque_id,
                "producer_json_sha256": sha256_bytes(producer_bytes),
                "waveform_sha256": acquired.payload_sha256,
            }
        )
        total_uncompressed_payload_bytes += len(acquired.payload)
        total_compressed_payload_bytes += int(idx["compressed_size"])

    assert_clean([producer_dir])
    acquisition_receipt_path.write_text(json.dumps(provenance_rows, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    result = {
        "unit": "ERC-3A",
        "status": "ERC3A_WAVEFORMS_STAGED_PRODUCER_CLEAN",
        "case_count": len(producer_receipts),
        "waveform_members_opened": len(producer_receipts),
        "selected_member_payload_ranges_requested": len(producer_receipts),
        "compressed_payload_bytes_read": total_compressed_payload_bytes,
        "uncompressed_payload_bytes_decoded": total_uncompressed_payload_bytes,
        "producer_identity_boundary_pass": True,
        "scientific_predictions": 0,
        "same_set_rescue_authorized": False,
        "producer_receipts": producer_receipts,
    }
    result["producer_receipts_sha256"] = sha256_bytes(canonical_json(producer_receipts).encode("utf-8"))
    stage_receipt_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-map", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--producer-dir", type=Path, required=True)
    parser.add_argument("--acquisition-receipt", type=Path, required=True)
    parser.add_argument("--stage-receipt", type=Path, required=True)
    args = parser.parse_args()
    result = stage_selected(
        acquisition_map_path=args.acquisition_map,
        index_path=args.index,
        producer_dir=args.producer_dir,
        acquisition_receipt_path=args.acquisition_receipt,
        stage_receipt_path=args.stage_receipt,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "producer_receipts"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
