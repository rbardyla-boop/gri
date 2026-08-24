from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.forge_e1.preflight_model import (
    EXPECTED_BLOB_SHA256,
    EXPECTED_MODEL,
    EXPECTED_OLLAMA_VERSION,
    model_blob,
    parse_version,
    run,
    fetch_json,
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def preflight(ollama_root: str) -> dict[str, Any]:
    version = parse_version(run(["ollama", "--version"]))
    if version != EXPECTED_OLLAMA_VERSION:
        raise ValueError(f"TE0_E2_RUNTIME_MISMATCH:{version}!={EXPECTED_OLLAMA_VERSION}")
    tags = fetch_json(ollama_root.rstrip("/") + "/api/tags")
    matches = [row for row in tags.get("models", []) if EXPECTED_MODEL in {str(row.get("name", "")), str(row.get("model", ""))}]
    if len(matches) != 1:
        raise ValueError(f"TE0_E2_MODEL_TAG_NOT_UNIQUE:{len(matches)}")
    blob = model_blob(run(["ollama", "show", "--modelfile", EXPECTED_MODEL]))
    if blob != EXPECTED_BLOB_SHA256:
        raise ValueError(f"TE0_E2_MODEL_BLOB_MISMATCH:{blob}")
    tag_digest = str(matches[0].get("digest", "")).removeprefix("sha256:").lower()
    if len(tag_digest) != 64:
        raise ValueError("TE0_E2_TAG_DIGEST_MISSING")
    body = {
        "schema_version": 1,
        "unit": "TE0-E2",
        "status": "TE0_E2_MODEL_PREFLIGHT_PASS",
        "model": EXPECTED_MODEL,
        "model_blob_sha256": blob,
        "ollama_version": version,
        "base_url": ollama_root.rstrip("/") + "/v1",
        "tag_digest": tag_digest,
        "scientific_authority": False,
        "engineering_collection_authorized": False,
    }
    body["record_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama-root", default="http://127.0.0.1:11434")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    try:
        result = preflight(args.ollama_root)
    except Exception as exc:
        print(json.dumps({"status": "TE0_E2_MODEL_PREFLIGHT_FAIL", "error": str(exc)}, indent=2, sort_keys=True))
        raise SystemExit(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
