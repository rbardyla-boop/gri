from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.forge.model_tools import broker_request

EXPECTED_STATUS = "TE0_E1_MODEL_PREFLIGHT_PASS"
SYSTEM_PROMPT = (
    "Follow the synthetic serialization instruction exactly. Return only the requested JSON object. "
    "Do not add markdown, prose, or commentary."
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def seed_for(case_id: str) -> int:
    return int.from_bytes(hashlib.sha256(case_id.encode("utf-8")).digest()[:4], "big") & 0x7FFFFFFF


def load_identity(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != EXPECTED_STATUS:
        raise ValueError("TE0_E1_MODEL_IDENTITY_NOT_QUALIFIED")
    observed = value.get("record_sha256")
    body = {k: v for k, v in value.items() if k != "record_sha256"}
    expected = hashlib.sha256(canonical(body)).hexdigest()
    if observed != expected:
        raise ValueError("TE0_E1_MODEL_IDENTITY_DIGEST_MISMATCH")
    return value


def load_pool(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("TE0_E1_EMPTY_POOL")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"case_id", "prompt", "target", "template_index"}:
            raise ValueError("TE0_E1_POOL_ROW_SHAPE_INVALID")
        cid = str(row["case_id"])
        if cid in seen:
            raise ValueError(f"TE0_E1_DUPLICATE_CASE:{cid}")
        seen.add(cid)
        if not isinstance(row["prompt"], str) or not isinstance(row["target"], dict):
            raise ValueError(f"TE0_E1_POOL_ROW_TYPES_INVALID:{cid}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect TE0-E1 raw producer outputs for BUILD or DEV only.")
    ap.add_argument("--pool", type=Path, required=True)
    ap.add_argument("--model-identity", type=Path, required=True)
    ap.add_argument("--broker-socket", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--phase", choices=["BUILD", "DEV"], required=True)
    args = ap.parse_args()

    if args.output.exists() or args.receipt.exists():
        raise FileExistsError("TE0_E1_REFUSE_OVERWRITE")
    identity = load_identity(args.model_identity)
    rows = load_pool(args.pool)
    socket_path = args.broker_socket.resolve()
    if not socket_path.exists():
        raise FileNotFoundError(socket_path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    request_count = 0
    raw_records: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows):
        cid = str(row["case_id"])
        body = {
            "model": identity["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": row["prompt"]},
            ],
            "options": {
                "temperature": 0,
                "seed": seed_for(cid),
                "num_predict": 256,
            },
        }
        request_count += 1
        outer = broker_request(socket_path, body)
        content = outer.get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"TE0_E1_MISSING_CONTENT:{cid}")
        raw_records.append({
            "case_id": cid,
            "input": content,
            "expected": row["target"],
        })
        trace_rows.append({
            "ordinal": ordinal,
            "case_id": cid,
            "prompt_sha256": hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest(),
            "target_sha256": hashlib.sha256(canonical(row["target"])).hexdigest(),
            "raw_content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "seed": seed_for(cid),
        })

    args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in raw_records), encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "unit": "TE0-E1",
        "status": "TE0_E1_COLLECTION_COMPLETE",
        "phase": args.phase,
        "scientific": False,
        "request_attempts": request_count,
        "one_request_per_case": request_count == len(rows),
        "pool_sha256": file_sha256(args.pool),
        "model_identity_sha256": file_sha256(args.model_identity),
        "model_identity_record_sha256": identity["record_sha256"],
        "output_sha256": file_sha256(args.output),
        "cases": trace_rows,
    }
    receipt["record_sha256"] = hashlib.sha256(canonical(receipt)).hexdigest()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
