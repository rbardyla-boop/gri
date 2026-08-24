from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

EXPECTED_MODEL = "llama3.1:8b"
EXPECTED_BLOB_SHA256 = "667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29"
EXPECTED_OLLAMA_VERSION = "0.21.2"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_version(text: str) -> str:
    matches = re.findall(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", text)
    if not matches:
        raise ValueError("TE0_E1_OLLAMA_VERSION_UNPARSEABLE")
    return matches[-1]


def run(argv: list[str]) -> str:
    proc = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(argv)}\n{proc.stdout}")
    return proc.stdout


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "te0-e1-preflight/1"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def model_blob(modelfile: str) -> str:
    hits = re.findall(r"sha256[-:]([0-9a-fA-F]{64})", modelfile)
    unique = {x.lower() for x in hits}
    if len(unique) != 1:
        raise ValueError(f"TE0_E1_MODEL_BLOB_UNRESOLVED:{sorted(unique)}")
    return next(iter(unique))


def preflight(ollama_root: str) -> dict[str, Any]:
    version = parse_version(run(["ollama", "--version"]))
    if version != EXPECTED_OLLAMA_VERSION:
        raise ValueError(f"TE0_E1_RUNTIME_MISMATCH:{version}!={EXPECTED_OLLAMA_VERSION}")
    tags = fetch_json(ollama_root.rstrip("/") + "/api/tags")
    matches = [
        row for row in tags.get("models", [])
        if EXPECTED_MODEL in {str(row.get("name", "")), str(row.get("model", ""))}
    ]
    if len(matches) != 1:
        raise ValueError(f"TE0_E1_MODEL_TAG_NOT_UNIQUE:{len(matches)}")
    tag = matches[0]
    blob = model_blob(run(["ollama", "show", "--modelfile", EXPECTED_MODEL]))
    if blob != EXPECTED_BLOB_SHA256:
        raise ValueError(f"TE0_E1_MODEL_BLOB_MISMATCH:{blob}")
    tag_digest = str(tag.get("digest", "")).removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", tag_digest):
        raise ValueError("TE0_E1_TAG_DIGEST_MISSING")
    body = {
        "schema_version": 1,
        "unit": "TE0-E1",
        "status": "TE0_E1_MODEL_PREFLIGHT_PASS",
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
        print(json.dumps({"status": "TE0_E1_MODEL_PREFLIGHT_FAIL", "error": str(exc)}, indent=2, sort_keys=True))
        raise SystemExit(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
