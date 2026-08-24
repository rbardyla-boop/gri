from __future__ import annotations

import argparse
import json
import re
import struct
import urllib.request
from pathlib import Path

ARCHIVE_URL = "https://zenodo.org/records/21109169/files/hv_double_line_90kv_preprocessed_data.zip?download=1"
EXPECTED_ARCHIVE_MD5 = "7cf176f169299b825ba6a6be102edca8"
EXPECTED_DATA_MEMBERS = 9022
EOCD = b"PK\x05\x06"
ZIP64_LOCATOR = b"PK\x06\x07"
ZIP64_EOCD = b"PK\x06\x06"
CD_FILE = b"PK\x01\x02"


def head_size(url: str) -> tuple[int, str | None, str]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "gri-erc3a/1.0"})
    with urllib.request.urlopen(req, timeout=300) as response:
        length = response.headers.get("Content-Length")
        if not length:
            raise ValueError("archive HEAD missing Content-Length")
        return int(length), response.headers.get("Accept-Ranges"), response.geturl()


def fetch_range(url: str, start: int, end: int) -> bytes:
    if start < 0 or end < start:
        raise ValueError("invalid byte range")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "gri-erc3a/1.0",
            "Range": f"bytes={start}-{end}",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        if getattr(response, "status", None) != 206:
            raise ValueError(f"server did not honor Range: HTTP {getattr(response, 'status', None)}")
        data = response.read()
        expected = end - start + 1
        if len(data) != expected:
            raise ValueError(f"range length mismatch {len(data)} != {expected}")
        content_range = response.headers.get("Content-Range", "")
        if not content_range.startswith(f"bytes {start}-{end}/"):
            raise ValueError(f"unexpected Content-Range: {content_range}")
        return data


def parse_zip64_extra(extra: bytes, need_usize: bool, need_csize: bool, need_offset: bool, need_disk: bool) -> tuple[int | None, int | None, int | None, int | None]:
    pos = 0
    payload = None
    while pos + 4 <= len(extra):
        field_id, size = struct.unpack_from("<HH", extra, pos)
        pos += 4
        field = extra[pos:pos + size]
        pos += size
        if field_id == 0x0001:
            payload = field
            break
    if payload is None:
        raise ValueError("ZIP64 overflow field present but ZIP64 extra missing")
    p = 0
    usize = csize = offset = disk = None
    if need_usize:
        usize = struct.unpack_from("<Q", payload, p)[0]; p += 8
    if need_csize:
        csize = struct.unpack_from("<Q", payload, p)[0]; p += 8
    if need_offset:
        offset = struct.unpack_from("<Q", payload, p)[0]; p += 8
    if need_disk:
        disk = struct.unpack_from("<I", payload, p)[0]; p += 4
    return usize, csize, offset, disk


def central_directory_location(url: str, archive_size: int) -> tuple[int, int, int, int]:
    tail_len = min(4 * 1024 * 1024, archive_size)
    tail_start = archive_size - tail_len
    tail = fetch_range(url, tail_start, archive_size - 1)
    eocd_rel = tail.rfind(EOCD)
    if eocd_rel < 0 or eocd_rel + 22 > len(tail):
        raise ValueError("EOCD not found in archive tail")
    eocd_abs = tail_start + eocd_rel
    sig, disk_no, cd_disk, disk_entries, total_entries, cd_size32, cd_offset32, comment_len = struct.unpack_from("<4s4H2IH", tail, eocd_rel)
    if sig != EOCD:
        raise ValueError("bad EOCD signature")
    if eocd_rel + 22 + comment_len > len(tail):
        raise ValueError("EOCD comment truncated")

    needs_zip64 = total_entries == 0xFFFF or cd_size32 == 0xFFFFFFFF or cd_offset32 == 0xFFFFFFFF
    if not needs_zip64:
        return cd_offset32, cd_size32, total_entries, tail_len

    locator_rel = tail.rfind(ZIP64_LOCATOR, 0, eocd_rel)
    if locator_rel < 0 or locator_rel + 20 > len(tail):
        raise ValueError("ZIP64 locator missing")
    loc_sig, zip64_disk, zip64_offset, total_disks = struct.unpack_from("<4sIQI", tail, locator_rel)
    if loc_sig != ZIP64_LOCATOR or total_disks != 1 or zip64_disk != 0:
        raise ValueError("multi-disk or invalid ZIP64 archive")
    record = fetch_range(url, zip64_offset, zip64_offset + 55)
    values = struct.unpack_from("<4sQ2H2I4Q", record, 0)
    if values[0] != ZIP64_EOCD:
        raise ValueError("bad ZIP64 EOCD signature")
    _, record_size, made, needed, disk_no64, cd_disk64, disk_entries64, total_entries64, cd_size64, cd_offset64 = values
    if disk_no64 != 0 or cd_disk64 != 0 or disk_entries64 != total_entries64:
        raise ValueError("multi-disk ZIP64 archive unsupported")
    return int(cd_offset64), int(cd_size64), int(total_entries64), tail_len + len(record)


def parse_central_directory(blob: bytes, expected_entries: int) -> list[dict]:
    rows = []
    pos = 0
    while pos < len(blob):
        if pos + 46 > len(blob):
            raise ValueError("truncated central directory header")
        values = struct.unpack_from("<4s6H3I5H2I", blob, pos)
        if values[0] != CD_FILE:
            raise ValueError(f"unexpected central directory signature at {pos}: {values[0]!r}")
        (_, made, needed, flags, compression, mtime, mdate, crc32, csize32, usize32,
         fname_len, extra_len, comment_len, disk_start, internal_attr, external_attr, offset32) = values
        start = pos + 46
        fname_b = blob[start:start + fname_len]
        extra = blob[start + fname_len:start + fname_len + extra_len]
        end = start + fname_len + extra_len + comment_len
        if end > len(blob):
            raise ValueError("central directory entry truncated")
        name = fname_b.decode("utf-8" if flags & 0x800 else "cp437")
        need_usize = usize32 == 0xFFFFFFFF
        need_csize = csize32 == 0xFFFFFFFF
        need_offset = offset32 == 0xFFFFFFFF
        need_disk = disk_start == 0xFFFF
        usize, csize, offset, disk = (None, None, None, None)
        if need_usize or need_csize or need_offset or need_disk:
            usize, csize, offset, disk = parse_zip64_extra(extra, need_usize, need_csize, need_offset, need_disk)
        rows.append({
            "path": name,
            "compression": compression,
            "crc32": f"{crc32:08x}",
            "compressed_size": int(csize if need_csize else csize32),
            "uncompressed_size": int(usize if need_usize else usize32),
            "local_header_offset": int(offset if need_offset else offset32),
            "flags": flags,
        })
        pos = end
    if len(rows) != expected_entries:
        raise ValueError(f"central directory count mismatch {len(rows)} != {expected_entries}")
    return rows


def selected_index(rows: list[dict], selection: list[dict]) -> tuple[list[dict], int]:
    pkl_rows = [row for row in rows if row["path"].endswith("_sample_hv_double_line_90kv.pkl")]
    by_basename = {Path(row["path"]).name: row for row in pkl_rows}
    if len(pkl_rows) != EXPECTED_DATA_MEMBERS or len(by_basename) != EXPECTED_DATA_MEMBERS:
        raise ValueError(f"expected {EXPECTED_DATA_MEMBERS} unique pkl members, got {len(pkl_rows)} / {len(by_basename)}")
    selected = []
    for case in selection:
        basename = f"{case['sample_id']}_sample_hv_double_line_90kv.pkl"
        row = by_basename.get(basename)
        if row is None:
            raise ValueError(f"selected member missing: {basename}")
        selected.append({
            "opaque_id": case["opaque_id"],
            "sample_id": case["sample_id"],
            "t_evnt_start": case["t_evnt_start"],
            **row,
        })
    return selected, len(pkl_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if len(selection) != 64:
        raise ValueError("public selection must contain 64 cases")

    archive_size, accept_ranges, final_url = head_size(ARCHIVE_URL)
    cd_offset, cd_size, entry_count, structural_bytes = central_directory_location(ARCHIVE_URL, archive_size)
    cd_blob = fetch_range(ARCHIVE_URL, cd_offset, cd_offset + cd_size - 1)
    structural_bytes += len(cd_blob)
    rows = parse_central_directory(cd_blob, entry_count)
    selected, pkl_count = selected_index(rows, selection)

    record = {
        "unit": "ERC-3A",
        "status": "ERC3A_REMOTE_ZIP_INDEX_CAPTURED",
        "zenodo_record": "10.5281/zenodo.21109169",
        "archive_url": ARCHIVE_URL,
        "archive_published_md5": EXPECTED_ARCHIVE_MD5,
        "archive_size_bytes": archive_size,
        "accept_ranges_header": accept_ranges,
        "resolved_url_host": urllib.request.urlparse(final_url).netloc if hasattr(urllib.request, 'urlparse') else None,
        "zip_entry_count": entry_count,
        "pkl_member_count": pkl_count,
        "central_directory_offset": cd_offset,
        "central_directory_size": cd_size,
        "selected_member_count": len(selected),
        "selected_members": selected,
        "range_structure_bytes_read": structural_bytes,
        "selected_member_payload_bytes_read": 0,
        "waveform_members_opened": 0,
        "scientific_predictions": 0,
        "same_set_rescue_authorized": False,
    }
    args.output.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "selected_members"}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
