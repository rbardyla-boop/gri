from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED = {
    "experiment",
    "model",
    "tools",
    "recipe",
    "task_set",
    "score",
    "runtime_seconds",
    "failures",
    "tool_hashes",
    "authority",
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def validate(record: dict[str, Any]) -> None:
    missing = REQUIRED - set(record)
    if missing:
        raise ValueError(f"missing fields: {sorted(missing)}")
    if not isinstance(record["tools"], list) or not isinstance(record["recipe"], list):
        raise ValueError("tools and recipe must be arrays")
    if type(record["authority"]) is not bool:
        raise ValueError("authority must be boolean")
    if record["authority"] and not record.get("judge_record_sha256"):
        raise ValueError("authority=true requires judge_record_sha256")


def append_record(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    validate(record)
    enriched = dict(record)
    enriched.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    enriched["record_sha256"] = record_hash(enriched)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (json.dumps(enriched, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return enriched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--record", type=Path, required=True)
    args = ap.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    saved = append_record(args.ledger, record)
    print(json.dumps(saved, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
