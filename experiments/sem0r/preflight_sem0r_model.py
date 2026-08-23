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
HISTORICAL_OLLAMA_VERSION = "0.21.2"
DEFAULT_OLLAMA_ROOT = "http://127.0.0.1:11434"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse_ollama_version(text: str) -> str | None:
    matches = re.findall(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", text)
    return matches[-1] if matches else None


def parse_from_blob_sha256(modelfile: str) -> str | None:
    matches = re.findall(r"sha256[-:]([0-9a-fA-F]{64})", modelfile)
    if not matches:
        return None
    unique = {m.lower() for m in matches}
    if len(unique) != 1:
        raise ValueError(f"multiple distinct FROM blob hashes found: {sorted(unique)}")
    return next(iter(unique))


def fetch_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "gri-sem0r-preflight/1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_command(argv: list[str]) -> str:
    completed = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(argv)}\n{completed.stdout}")
    return completed.stdout


def find_tag(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    matches = []
    for row in models:
        if not isinstance(row, dict):
            continue
        if name in {str(row.get("name", "")), str(row.get("model", ""))}:
            matches.append(row)
    if len(matches) > 1:
        raise ValueError(f"multiple exact tag records for {name}")
    return matches[0] if matches else None


def preflight(ollama_root: str = DEFAULT_OLLAMA_ROOT, require_historical_runtime: bool = True) -> dict[str, Any]:
    version = parse_ollama_version(run_command(["ollama", "--version"]))
    if version is None:
        raise ValueError("could not parse Ollama version")
    tag = find_tag(fetch_json(ollama_root.rstrip("/") + "/api/tags"), EXPECTED_MODEL)
    if tag is None:
        raise ValueError(f"required pre-existing model is not installed: {EXPECTED_MODEL}")
    blob = parse_from_blob_sha256(run_command(["ollama", "show", "--modelfile", EXPECTED_MODEL]))
    if blob is None:
        raise ValueError("could not recover FROM blob SHA-256")
    tag_digest = str(tag.get("digest", "")).removeprefix("sha256:").lower()
    checks = {
        "model_name_exact": EXPECTED_MODEL in {str(tag.get("name", "")), str(tag.get("model", ""))},
        "historical_blob_exact": blob == EXPECTED_BLOB_SHA256,
        "historical_runtime_exact": version == HISTORICAL_OLLAMA_VERSION,
        "tag_digest_present": bool(re.fullmatch(r"[0-9a-fA-F]{64}", tag_digest)),
    }
    if not checks["model_name_exact"]:
        raise ValueError("model name mismatch")
    if not checks["historical_blob_exact"]:
        raise ValueError(f"SEM0R_MODEL_BLOB_MISMATCH: observed {blob}; expected {EXPECTED_BLOB_SHA256}")
    if require_historical_runtime and not checks["historical_runtime_exact"]:
        raise ValueError(f"SEM0R_RUNTIME_MISMATCH: observed {version}; expected {HISTORICAL_OLLAMA_VERSION}")

    body = {
        "model_id": EXPECTED_MODEL,
        "artifact_sha256": blob,
        "runtime": f"ollama-{version}-openai-compatible",
        "ollama_version": version,
        "base_url": ollama_root.rstrip("/") + "/v1",
        "tag_digest": tag_digest,
        "selection_basis": "pre-existing MCO-05 frozen reasoner selected before any SEM-0R real-model execution; no SEM-0R model shopping",
        "historical_source": {
            "path": "experiments/mco05/MCO05_CONFIG.json",
            "model": EXPECTED_MODEL,
            "blob_sha256": EXPECTED_BLOB_SHA256,
            "ollama_version": HISTORICAL_OLLAMA_VERSION,
        },
        "checks": checks,
    }
    record = dict(body)
    record["identity_record_sha256"] = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
    record["status"] = "SEM0R_MODEL_PREFLIGHT_PASS"
    record["scientific_run_authorized"] = False
    record["next_gate"] = "bind exact instrument hashes and create one-run authorization"
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama-root", default=DEFAULT_OLLAMA_ROOT)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--allow-runtime-change", action="store_true")
    args = ap.parse_args()
    try:
        result = preflight(args.ollama_root, require_historical_runtime=not args.allow_runtime_change)
    except Exception as exc:
        print(json.dumps({
            "status": "SEM0R_MODEL_PREFLIGHT_FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "scientific_run_authorized": False,
        }, indent=2, sort_keys=True))
        raise SystemExit(2)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
