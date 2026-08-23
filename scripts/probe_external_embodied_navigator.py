#!/usr/bin/env python3
"""Pin and extract a controlled positive ablation from Embodied-Navigator.

The probe reads only the authors' pinned public README. It verifies the stated
matched-control conditions and parses the Memory block of the controlled
component-attribution table. It does not rerun training/evaluation and therefore
supports only retrospective, conditional mechanism credit.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path


REPO = "ZJU-OmniAI/Embodied-Navigator"
COMMIT = "2f82cbd5ae4cd3abe0c15da0d70dc8f1adb6f04d"
README_URL = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/README.md"
OUTPUT = Path(".gauntlet/external-embodied-navigator-evidence.json")

CONTROL_STATEMENT = (
    "All variants below use the same Qwen2.5-VL-7B policy, sensing inputs, "
    "validation-unseen splits, fixed non-learned SLAM controller, and evaluation protocol. "
    "Each block changes only its named component."
)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "gri-gauntlet-external-probe/1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"unexpected HTTP status for {url}: {response.status}")
        return response.read()


def normalize(text: str) -> str:
    return " ".join(text.replace("**", "").split())


def parse_metrics(cell: str, expected: int) -> list[float]:
    clean = cell.replace("**", "").strip()
    values = [float(part.strip()) for part in clean.split("/")]
    if len(values) != expected:
        raise RuntimeError(f"unexpected metric vector {clean!r}: expected {expected}, got {len(values)}")
    return values


def find_memory_row(section: str, variant: str) -> tuple[list[float], list[float]]:
    # Markdown rows have: block | variant | R2R metrics | RxR metrics.
    for raw in section.splitlines():
        if not raw.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        cleaned_variant = cells[1].replace("**", "").strip()
        if cleaned_variant == variant:
            return parse_metrics(cells[2], 4), parse_metrics(cells[3], 4)
    raise RuntimeError(f"controlled Memory row not found for {variant!r}")


def main() -> int:
    payload = fetch(README_URL)
    text = payload.decode("utf-8")
    flat = normalize(text)
    if normalize(CONTROL_STATEMENT) not in flat:
        raise RuntimeError("pinned README no longer contains the matched-control attribution statement")

    start = text.find("### Controlled component attribution")
    end = text.find("### MultiNav-CoT supervision study", start + 1)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("could not isolate controlled component-attribution section")
    section = text[start:end]

    full_history_r2r, full_history_rxr = find_memory_row(section, "Full history")
    no_sti_r2r, no_sti_rxr = find_memory_row(section, "AT-Mem without STI")
    full_atmem_r2r, full_atmem_rxr = find_memory_row(section, "Full AT-Mem")

    # R2R vector = NE / OS / SR / SPL; RxR vector = NE / SR / SPL / nDTW.
    full_history = {"r2r_sr": full_history_r2r[2], "rxr_sr": full_history_rxr[1]}
    no_sti = {"r2r_sr": no_sti_r2r[2], "rxr_sr": no_sti_rxr[1]}
    full_atmem = {"r2r_sr": full_atmem_r2r[2], "rxr_sr": full_atmem_rxr[1]}

    expected = {
        "full_history": {"r2r_sr": 61.9, "rxr_sr": 61.1},
        "no_sti": {"r2r_sr": 63.6, "rxr_sr": 62.4},
        "full_atmem": {"r2r_sr": 66.2, "rxr_sr": 65.7},
    }
    observed = {"full_history": full_history, "no_sti": no_sti, "full_atmem": full_atmem}
    if observed != expected:
        raise RuntimeError(f"pinned controlled Memory metrics changed: {observed!r}")

    evidence = {
        "schema_version": 1,
        "probe_type": "PINNED_PUBLIC_SOURCE_RETROSPECTIVE",
        "source": {
            "repository": REPO,
            "commit": COMMIT,
            "readme_url": README_URL,
            "readme_sha256": hashlib.sha256(payload).hexdigest(),
        },
        "controls": {
            "same_policy": True,
            "policy": "Qwen2.5-VL-7B",
            "same_sensing_inputs": True,
            "same_validation_splits": True,
            "same_fixed_slam_controller": True,
            "same_evaluation_protocol": True,
            "authors_state_each_block_changes_only_named_component": True,
        },
        "memory_block": {
            "full_history": full_history,
            "atmem_without_sti": no_sti,
            "full_atmem": full_atmem,
            "full_atmem_minus_full_history": {
                "r2r_sr_points": round(full_atmem["r2r_sr"] - full_history["r2r_sr"], 10),
                "rxr_sr_points": round(full_atmem["rxr_sr"] - full_history["rxr_sr"], 10),
            },
            "full_atmem_minus_no_sti": {
                "r2r_sr_points": round(full_atmem["r2r_sr"] - no_sti["r2r_sr"], 10),
                "rxr_sr_points": round(full_atmem["rxr_sr"] - no_sti["rxr_sr"], 10),
            },
        },
        "boundary": {
            "fresh_rerun": False,
            "independent_replication": False,
            "causal_claim_beyond_reported_controlled_ablation": False,
            "general_memory_superiority_established": False,
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
