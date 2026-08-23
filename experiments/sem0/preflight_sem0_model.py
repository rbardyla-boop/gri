from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

EXPECTED_MODEL = "llama3.1:8b"
EXPECTED_BLOB_SHA256 = "667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29"
HISTORICAL_OLLAMA_VERSION = "0.21.2"
DEFAULT_OLLAMA_ROOT = "http://127.0.0.1:11434"


def parse_ollama_version(text: str) -> str | None:
    matches = re.findall(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", text)
    return matches[-1] if matches else None


def parse_from_blob_sha256(modelfile: str) -> str | None:
    # Handles common Ollama output such as:
    # FROM /home/user/.ollama/models/blobs/sha256-abc...
    # or FROM sha256:abc...
    matches = re.findall(r"sha256[-:]([0-9a-fA-F]{64})", modelfile)
    if not matches:
        return None
    unique = {m.lower() for m in matches}
    if len(unique) != 1:
        raise ValueError(f"multiple distinct FROM blob hashes found: {sorted(unique)}")
    return next(iter(unique))


def fetch_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "gri-sem0-preflight/1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def find_tag(tags_payload: dict[str, Any], model_name: str) -> dict[str, Any] | None:
    models = tags_payload.get("models")
    if not isinstance(models, list):
        return None
    exact = []
    for entry in models:
        if not isinstance(entry, dict):
            continue
        names = {str(entry.get("name", "")), str(entry.get("model", ""))}
        if model_name in names:
            exact.append(entry)
    if len(exact) > 1:
        raise ValueError(f"multiple exact tag records for {model_name}")
    return exact[0] if exact else None


def run_command(argv: list[str]) -> str:
    completed = subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(argv)}\n{completed.stdout}")
    return completed.stdout


def preflight(*, ollama_root: str = DEFAULT_OLLAMA_ROOT, require_historical_runtime: bool = True) -> dict[str, Any]:
    version_text = run_command(["ollama", "--version"])
    version = parse_ollama_version(version_text)
    if version is None:
        raise ValueError(f"could not parse Ollama version from: {version_text!r}")

    tags = fetch_json(ollama_root.rstrip("/") + "/api/tags")
    tag = find_tag(tags, EXPECTED_MODEL)
    if tag is None:
        raise ValueError(f"required pre-existing model is not installed: {EXPECTED_MODEL}")

    modelfile_text = run_command(["ollama", "show", "--modelfile", EXPECTED_MODEL])
    blob_sha = parse_from_blob_sha256(modelfile_text)
    if blob_sha is None:
        raise ValueError("could not recover a 64-hex FROM blob SHA-256 from `ollama show --modelfile`")

    tag_digest = str(tag.get("digest", "")).removeprefix("sha256:").lower()
    checks = {
        "model_name_exact": EXPECTED_MODEL in {str(tag.get("name", "")), str(tag.get("model", ""))},
        "historical_blob_exact": blob_sha == EXPECTED_BLOB_SHA256,
        "historical_runtime_exact": version == HISTORICAL_OLLAMA_VERSION,
        "tag_digest_present": bool(re.fullmatch(r"[0-9a-fA-F]{64}", tag_digest)),
    }
    if not checks["model_name_exact"]:
        raise ValueError("local model name does not exactly match the pre-existing frozen candidate")
    if not checks["historical_blob_exact"]:
        raise ValueError(
            "SEM0_MODEL_BLOB_MISMATCH: local llama3.1:8b FROM blob is "
            f"{blob_sha}, expected historical MCO-05 blob {EXPECTED_BLOB_SHA256}. "
            "Do not download/update/tune a replacement to rescue SEM-0."
        )
    if require_historical_runtime and not checks["historical_runtime_exact"]:
        raise ValueError(
            "SEM0_RUNTIME_MISMATCH: local Ollama version is "
            f"{version}, historical frozen runtime was {HISTORICAL_OLLAMA_VERSION}. "
            "Do not run SEM-0 under a changed runtime without a separately frozen successor authorization."
        )

    identity = {
        "model_id": EXPECTED_MODEL,
        "artifact_sha256": blob_sha,
        "runtime": f"ollama-{version}-openai-compatible",
        "ollama_version": version,
        "base_url": ollama_root.rstrip("/") + "/v1",
        "tag_digest": tag_digest,
        "selection_basis": (
            "pre-existing MCO-05 frozen reasoner selected before any SEM-0 real-model execution; "
            "no SEM-0 model shopping"
        ),
        "historical_source": {
            "path": "experiments/mco05/MCO05_CONFIG.json",
            "model": EXPECTED_MODEL,
            "blob_sha256": EXPECTED_BLOB_SHA256,
            "ollama_version": HISTORICAL_OLLAMA_VERSION,
        },
        "checks": checks,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity["identity_record_sha256"] = hashlib.sha256(canonical).hexdigest()
    return identity


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama-root", default=DEFAULT_OLLAMA_ROOT)
    ap.add_argument("--output", type=Path)
    ap.add_argument(
        "--allow-runtime-change",
        action="store_true",
        help="engineering diagnosis only; does not authorize SEM-0 science under a changed runtime",
    )
    args = ap.parse_args()
    try:
        result = preflight(
            ollama_root=args.ollama_root,
            require_historical_runtime=not args.allow_runtime_change,
        )
    except Exception as exc:
        error = {
            "status": "SEM0_MODEL_PREFLIGHT_FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "scientific_run_authorized": False,
        }
        print(json.dumps(error, indent=2, sort_keys=True))
        raise SystemExit(2)

    result["status"] = "SEM0_MODEL_PREFLIGHT_PASS"
    result["scientific_run_authorized"] = False
    result["next_gate"] = "commit and verify this exact identity, then create one-run authorization"
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
