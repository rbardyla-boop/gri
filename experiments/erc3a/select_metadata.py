from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

LABELS_URL = "https://zenodo.org/records/21109169/files/hv_double_line_90kv_labels.csv?download=1"
LABELS_MD5 = "5f015330f77ed53b76bd5db26e83c48d"
EXPECTED_ROWS = 9022
EXPECTED_TARGETS = ("Line_1_2_a", "Line_1_2_b", "Line_2_3_a", "Line_2_3_b")
EXPECTED_TYPES = (0, 1, 2, 3)
PER_STRATUM = 4
SALT = "ERC3A-PROTECT90-v1"


def digest_bytes(data: bytes, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    h.update(data)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gri-erc3a/1.0"})
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read()


def parse_int_like(value: str) -> int:
    return int(float(value))


def parse_rows(blob: bytes) -> list[dict]:
    text = blob.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    required = {"sample_id", "fault_target", "sc_type", "t_evnt_start"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ValueError(f"missing required columns: {required - set(reader.fieldnames or [])}")
    rows = []
    for raw in reader:
        if any(raw.get(key, "").strip() == "" for key in required):
            continue
        rows.append({
            "sample_id": parse_int_like(raw["sample_id"]),
            "fault_target": raw["fault_target"].strip(),
            "sc_type": parse_int_like(raw["sc_type"]),
            "t_evnt_start": float(raw["t_evnt_start"]),
        })
    return rows


def select(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        key = (row["fault_target"], row["sc_type"])
        if row["fault_target"] in EXPECTED_TARGETS and row["sc_type"] in EXPECTED_TYPES:
            groups[key].append(row)

    expected_keys = {(target, sc_type) for target in EXPECTED_TARGETS for sc_type in EXPECTED_TYPES}
    if set(groups) != expected_keys:
        raise ValueError(f"stratum set mismatch: {sorted(set(groups) ^ expected_keys)}")

    chosen = []
    for key in sorted(expected_keys):
        candidates = groups[key]
        if len(candidates) < PER_STRATUM:
            raise ValueError(f"too few rows in stratum {key}: {len(candidates)}")
        candidates = sorted(
            candidates,
            key=lambda row: (
                sha256_text(f"{SALT}|{row['sample_id']}"),
                row["sample_id"],
            ),
        )
        chosen.extend(candidates[:PER_STRATUM])

    public = []
    scorer = []
    for row in sorted(chosen, key=lambda r: r["sample_id"]):
        opaque_id = "P90-" + sha256_text(f"ERC3A-CASE|{row['sample_id']}")[:16]
        public.append({
            "opaque_id": opaque_id,
            "sample_id": row["sample_id"],
            "t_evnt_start": row["t_evnt_start"],
        })
        scorer.append({
            "opaque_id": opaque_id,
            "sample_id": row["sample_id"],
            "fault_target": row["fault_target"],
            "sc_type": row["sc_type"],
        })
    return public, scorer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    blob = download(LABELS_URL)
    if digest_bytes(blob, "md5") != LABELS_MD5:
        raise ValueError("published labels MD5 mismatch")
    labels_sha256 = digest_bytes(blob, "sha256")
    rows = parse_rows(blob)
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"expected {EXPECTED_ROWS} eligible rows, got {len(rows)}")

    public, scorer = select(rows)
    if len(public) != 64 or len(scorer) != 64:
        raise ValueError("selected case count mismatch")
    if len({row["sample_id"] for row in public}) != 64:
        raise ValueError("duplicate sample id")
    counts = Counter((row["fault_target"], row["sc_type"]) for row in scorer)
    if set(counts.values()) != {PER_STRATUM} or len(counts) != 16:
        raise ValueError(f"selection balance mismatch: {counts}")

    public_path = out / "ERC3A_PUBLIC_SELECTION.json"
    scorer_path = out / "ERC3A_SCORER_MAP.json"
    public_path.write_text(json.dumps(public, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    scorer_path.write_text(json.dumps(scorer, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    record = {
        "unit": "ERC-3A",
        "status": "ERC3A_METADATA_SELECTION_FROZEN",
        "zenodo_record": "10.5281/zenodo.21109169",
        "labels_url": LABELS_URL,
        "labels_md5": LABELS_MD5,
        "labels_sha256": labels_sha256,
        "labels_row_count": len(rows),
        "scientific_case_count": len(public),
        "stratum_count": len(counts),
        "per_stratum": PER_STRATUM,
        "public_selection_sha256": sha256_text(canonical_json(public)),
        "scorer_map_sha256": sha256_text(canonical_json(scorer)),
        "waveform_archive_downloaded": False,
        "waveform_members_opened": 0,
        "scientific_predictions": 0,
        "same_set_rescue_authorized": False,
    }
    record["record_sha256"] = sha256_text(canonical_json(record))
    (out / "ERC3A_METADATA_SELECTION_RECORD.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
