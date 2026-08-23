#!/usr/bin/env python3
"""Pin and conservatively extract the public AMB comparison used by Gauntlet.

This probe verifies only the published Layer-1 headline comparison and the
benchmark author's own description/implementation of the in-memory baseline.
It does not re-run AMB and does not establish product superiority.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path


REPO = "AlekseiMarchenko/agent-memory-benchmark"
COMMIT = "9146ffa044109166b5d61146ebbf1c89fa544608"
RAW_ROOT = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}"
README_URL = f"{RAW_ROOT}/README.md"
ADAPTER_URL = f"{RAW_ROOT}/src/adapters/in-memory.ts"
OUTPUT = Path(".gauntlet/external-amb-evidence.json")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "gri-gauntlet-external-probe/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"unexpected HTTP status for {url}: {response.status}")
        return response.read()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalized(text: str) -> str:
    return " ".join(text.split())


def layer1_section(readme: str) -> str:
    start_marker = "**Layer 1 (3s store delay)**"
    end_marker = "**Layer 2 (multi-step)**"
    start = readme.find(start_marker)
    end = readme.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("could not isolate the pinned README Layer 1 score section")
    return readme[start:end]


def layer1_scores(readme: str, provider: str) -> dict[str, float]:
    section = layer1_section(readme)
    row_pattern = re.compile(rf"^\|\s*{re.escape(provider)}\s*\|(?P<cells>.+)$", flags=re.MULTILINE)
    matches = list(row_pattern.finditer(section))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one Layer 1 published row for {provider!r}, got {len(matches)}"
        )

    cells = [cell.strip().replace("**", "") for cell in matches[0].group("cells").split("|")]
    cells = [cell for cell in cells if cell]
    if len(cells) < 8:
        raise RuntimeError(f"unexpected Layer 1 score row shape for {provider!r}: {cells}")

    try:
        values = [float(cell) for cell in cells[:8]]
    except ValueError as exc:
        raise RuntimeError(f"non-numeric Layer 1 score cell for {provider!r}: {cells[:8]}") from exc

    names = ("overall", "factual", "semantic", "temporal", "conflict", "forgetting", "cross_session", "cost")
    return dict(zip(names, values, strict=True))


def main() -> int:
    readme_bytes = fetch(README_URL)
    adapter_bytes = fetch(ADAPTER_URL)
    readme = readme_bytes.decode("utf-8")
    adapter = adapter_bytes.decode("utf-8")
    flat_readme = normalized(readme)

    candidate = layer1_scores(readme, "Central Intelligence")
    baseline_scores = layer1_scores(readme, "In-Memory Baseline")

    baseline_disclosure = (
        "The in-memory baseline uses exact keyword matching, not embeddings. "
        "It's a floor, not a meaningful comparison for semantic capabilities."
    )
    if normalized(baseline_disclosure) not in flat_readme:
        raise RuntimeError("pinned README no longer contains the expected baseline limitation disclosure")

    same_author_disclosure = (
        "Central Intelligence is maintained by the same author as this benchmark. "
        "Run it yourself and verify."
    )
    if normalized(same_author_disclosure) not in flat_readme:
        raise RuntimeError("pinned README no longer contains the expected same-author disclosure")

    lexical_markers = (
        "const queryWords = queryLower.split(/\\s+/).filter(w => w.length > 2);",
        "if (contentLower.includes(word))",
        "matchScore += 1;",
    )
    missing_markers = [marker for marker in lexical_markers if marker not in adapter]
    if missing_markers:
        raise RuntimeError(f"pinned in-memory adapter is missing expected lexical markers: {missing_markers}")

    if candidate["overall"] != 90.0 or baseline_scores["overall"] != 55.0:
        raise RuntimeError(
            "published pinned overall scores changed: "
            f"Central Intelligence={candidate['overall']}, In-Memory Baseline={baseline_scores['overall']}"
        )
    if candidate["semantic"] != 100.0 or baseline_scores["semantic"] != 0.0:
        raise RuntimeError(
            "published pinned semantic scores changed: "
            f"Central Intelligence={candidate['semantic']}, In-Memory Baseline={baseline_scores['semantic']}"
        )

    result = {
        "schema_version": 1,
        "probe_type": "PINNED_PUBLIC_SOURCE_RETROSPECTIVE",
        "source": {
            "repository": REPO,
            "commit": COMMIT,
            "readme_url": README_URL,
            "adapter_url": ADAPTER_URL,
            "readme_sha256": sha256(readme_bytes),
            "adapter_sha256": sha256(adapter_bytes),
        },
        "published": {
            "candidate": {"name": "Central Intelligence", **candidate},
            "baseline": {"name": "In-Memory Baseline", **baseline_scores},
        },
        "comparison": {
            "overall_advantage_points": candidate["overall"] - baseline_scores["overall"],
            "semantic_advantage_points": candidate["semantic"] - baseline_scores["semantic"],
        },
        "baseline": {
            "self_described_floor": True,
            "meaningful_semantic_comparator": False,
            "lexical_overlap_search": True,
            "semantic_score": baseline_scores["semantic"],
        },
        "disclosures": {
            "same_author": True,
            "independent_verification_encouraged": True,
        },
        "boundary": {
            "benchmark_rerun": False,
            "strong_semantic_baseline_tested": False,
            "architecture_superiority_established": False,
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
