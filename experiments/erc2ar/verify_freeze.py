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
    parser.add_argument("--freeze", type=Path, default=Path("experiments/erc2ar/ERC2AR_FREEZE.json"))
    args = parser.parse_args()
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    if freeze["status"] != "ERC2AR_LIVE_AUTHORIZED":
        raise ValueError("live freeze is not authorized")
    if freeze["scientific_case_count"] != EXPECTED_CASES:
        raise ValueError("case count changed")
    if freeze["compiler_sha256"] != COMPILER_SHA256:
        raise ValueError("compiler binding changed")
    if freeze["data_binding_record_sha256"] != DATA_BINDING_RECORD_SHA256:
        raise ValueError("data binding changed")
    if freeze["runtime"] != RUNTIME:
        raise ValueError("runtime binding changed")
    if set(freeze["source_hashes"]) != set(CRITICAL_FILES):
        raise ValueError("critical file set changed")
    for path in CRITICAL_FILES:
        actual = sha256_file(Path(path))
        if actual != freeze["source_hashes"][path]:
            raise ValueError(f"source hash mismatch: {path}")
    if sha256_file(Path("experiments/erc1/compiler.py")) != COMPILER_SHA256:
        raise ValueError("frozen compiler bytes changed")
    parent = subprocess.check_output(["git", "rev-parse", "HEAD^"], text=True).strip()
    if parent != freeze["qualified_head"]:
        raise ValueError(f"freeze parent {parent} != qualified head {freeze['qualified_head']}")
    if freeze.get("same_set_rescue_authorized") is not False or freeze.get("llm_calls") != 0:
        raise ValueError("scientific boundary changed")
    print("ERC2AR_LIVE_FREEZE_VERIFIED")


if __name__ == "__main__":
    main()
