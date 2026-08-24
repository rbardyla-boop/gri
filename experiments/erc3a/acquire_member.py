from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .channel_schema import CHANNEL_SCHEMA

FetchRange = Callable[[str, int, int], bytes]
LOCAL_FILE = b"PK\x03\x04"


@dataclass(frozen=True)
class AcquiredMember:
    """Acquisition-layer result; this object must not cross the producer boundary."""

    opaque_id: str
    sample_id: int
    t_evnt_start: float
    member_path: str
    payload: bytes
    payload_sha256: str


def fetch_range(url: str, start: int, end: int) -> bytes:
    request = Request(url, headers={"User-Agent": "gri-erc3a/1.0", "Range": f"bytes={start}-{end}"})
    with urlopen(request, timeout=300) as response:
        if getattr(response, "status", None) != 206:
            raise ValueError(f"member acquisition requires HTTP 206, got {getattr(response, 'status', None)}")
        body = response.read()
        if len(body) != end - start + 1:
            raise ValueError("member range length mismatch")
        return body


def acquire_member(
    *,
    archive_url: str,
    acquisition_row: dict,
    index_row: dict,
    range_fetcher: FetchRange = fetch_range,
) -> AcquiredMember:
    """Fetch and validate one ZIP member. This function is not called by the index gate."""

    if acquisition_row["opaque_id"] != index_row["opaque_id"]:
        raise ValueError("opaque id mismatch")
    sample_id = int(acquisition_row["sample_id"])
    expected_name = f"{sample_id}_sample_hv_double_line_90kv.pkl"
    if Path(index_row["path"]).name != expected_name:
        raise ValueError("acquisition/index member binding mismatch")

    offset = int(index_row["local_header_offset"])
    fixed = range_fetcher(archive_url, offset, offset + 29)
    if fixed[:4] != LOCAL_FILE:
        raise ValueError("bad ZIP local-file signature")
    _, version, flags, compression, mtime, mdate, crc32, csize32, usize32, fname_len, extra_len = struct.unpack(
        "<4s5H3I2H", fixed
    )
    if flags & 0x08:
        raise ValueError("data-descriptor ZIP members are not supported by the acquisition binding")
    header_end = offset + 30 + fname_len + extra_len
    header = range_fetcher(archive_url, offset, header_end - 1)
    name_start = 30
    name_end = name_start + fname_len
    name = header[name_start:name_end].decode("utf-8" if flags & 0x800 else "cp437")
    if name != index_row["path"]:
        raise ValueError("central/local member name mismatch")
    if csize32 == 0xFFFFFFFF or usize32 == 0xFFFFFFFF:
        raise ValueError("ZIP64 local size fields require ZIP64 local-extra parsing")
    payload_start = header_end
    compressed = range_fetcher(archive_url, payload_start, payload_start + csize32 - 1)
    if compression == 0:
        payload = compressed
    elif compression == 8:
        payload = zlib.decompress(compressed, -15)
    else:
        raise ValueError(f"unsupported ZIP compression method: {compression}")
    if len(payload) != usize32:
        raise ValueError("uncompressed member size mismatch")
    if zlib.crc32(payload) & 0xFFFFFFFF != crc32:
        raise ValueError("member CRC32 mismatch")
    return AcquiredMember(
        opaque_id=acquisition_row["opaque_id"],
        sample_id=sample_id,
        t_evnt_start=float(acquisition_row["t_evnt_start"]),
        member_path=name,
        payload=payload,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )


def producer_input(
    *,
    opaque_id: str,
    t_evnt_start: float,
    waveform: dict[str, list[float]],
    payload_sha256: str,
) -> dict:
    """Create the only shape accepted by the locator; raw acquisition identity is omitted."""

    if set(waveform) != set(CHANNEL_SCHEMA):
        raise ValueError("waveform channel set does not match the frozen producer schema")
    return {
        "opaque_id": opaque_id,
        "t_evnt_start": float(t_evnt_start),
        "waveform_sha256": payload_sha256,
        "channel_schema": list(CHANNEL_SCHEMA),
        "waveform": waveform,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire one selected member; never used by pre-waveform index gates")
    parser.add_argument("--archive-url", required=True)
    parser.add_argument("--acquisition-row", type=Path, required=True)
    parser.add_argument("--index-row", type=Path, required=True)
    args = parser.parse_args()
    acquisition_row = json.loads(args.acquisition_row.read_text(encoding="utf-8"))
    index_row = json.loads(args.index_row.read_text(encoding="utf-8"))
    result = acquire_member(archive_url=args.archive_url, acquisition_row=acquisition_row, index_row=index_row)
    print(json.dumps({"opaque_id": result.opaque_id, "payload_sha256": result.payload_sha256}))


if __name__ == "__main__":
    main()

