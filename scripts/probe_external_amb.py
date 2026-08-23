#!/usr/bin/env python3
"""Pin and conservatively extract the public AMB comparison used by Gauntlet.

This probe is deliberately narrow. It verifies only the published Layer-1
headline scores and the benchmark author's own description of the in-memory
baseline. It does not re-run AMB and does not establish product superiority.
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
OUTPUT = Path("artifacts/gauntlet/external/amb_9146ffa_probe.json")


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


def published_layer1_score(readme: str, provider: str) -> int:
    # Match only a markdown table row beginning with the requested provider.
    row_pattern = re.compile(
        rf"^\|\s*{re.escape(provider)}\s*\|\s*\**(?P<score>\d+(?:\.\d+)?)\**\s*\|",
        flags=re.MULTILINE,
    )
    matches = list(row_pattern.finditer(readme))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one published row for {provider!r}, got {len(matches)}")
    score = float(matches[0].group("score"))
    if not score.is_integer():
        raise RuntimeError(f"expected integer headline score for {provider!r}, got {score}")
    return int(score)


def main() -> int:
    readme_bytes = fetch(README_URL)
    adapter_bytes = fetch(ADAPTER_URL)
    readme = readme_bytes.decode("utf-8")
    adapter = adapter_bytes.decode("utf-8")
    flat_readme = normalized(readme)

    central_score = published_layer1_score(readme, "Central Intelligence")
    baseline_score = published_layer1_score(readme, "In-Memory Baseline")

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

    # Source-level evidence for the lexical baseline. These checks are kept
    # explicit so a materially different adapter implementation fails closed.
    lexical_markers = (
        "const queryWords = queryLower.split(/\\s+/).filter(w => w.length > 2);",
        "if (contentLower.includes(word))",
        "matchScore += 1;",
    )
    missing_markers = [marker for marker in lexical_markers if marker not in adapter]
    if missing_markers:
        raise RuntimeError(f"pinned in-memory adapter is missing expected lexical markers: {missing_markers}")

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
            "central_intelligence_overall": central_score,
            "in_memory_overall": baseline_score,
        },
        "baseline": {
            "keyword_overlap_only": True,
            "author_calls_floor": True,
            "author_says_not_meaningful_semantic_comparison": True,
        },
        "disclosures": {
            "same_author": True,
            "independent_verification_encouraged": True,
        },
        "boundary": {
            "benchmark_rerun": False,
            "semantic_baseline_tested": False,
            "architecture_superiority_established": False,
        },
    }

    if central_score != 90 or baseline_score != 55:
        raise RuntimeError(
            f"published pinned headline scores changed: Central Intelligence={central_score}, "
            f"In-Memory Baseline={baseline_score}"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
