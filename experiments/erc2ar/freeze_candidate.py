from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from experiments.erc2ar.contract import COMPILER_SHA256, DATA_BINDING_RECORD_SHA256, EXPECTED_CASES
from experiments.erc2ar.freeze_common import CRITICAL_FILES, RUNTIME


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    hashes = {path: sha256_file(Path(path)) for path in CRITICAL_FILES}
    if hashes["experiments/erc1/compiler.py"] != COMPILER_SHA256:
        raise ValueError("frozen compiler hash mismatch")
    body = {
        "unit": "ERC-2AR",
        "status": "ERC2AR_FREEZE_CANDIDATE",
        "qualified_head": head,
        "scientific_case_count": EXPECTED_CASES,
        "compiler_sha256": COMPILER_SHA256,
        "data_binding_record_sha256": DATA_BINDING_RECORD_SHA256,
        "runtime": RUNTIME,
        "source_hashes": hashes,
        "same_set_rescue_authorized": False,
        "llm_calls": 0,
    }
    args.output.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(body, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
