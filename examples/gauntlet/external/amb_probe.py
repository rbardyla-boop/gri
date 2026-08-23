from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path


REPO = "AlekseiMarchenko/agent-memory-benchmark"
COMMIT = "9146ffa044109166b5d61146ebbf1c89fa544608"
BASE = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}"
URLS = {
    "readme": f"{BASE}/README.md",
    "baseline_source": f"{BASE}/src/adapters/in-memory.ts",
    "candidate_results": f"{BASE}/amb-results/results.json",
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "gauntlet-external-probe/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def category_score(result: dict, category: str) -> float:
    for row in result.get("categories", []):
        if row.get("category") == category:
            return float(row["score"])
    raise RuntimeError(f"category missing: {category}")


def main() -> None:
    raw = {name: fetch(url) for name, url in URLS.items()}
    readme = raw["readme"].decode("utf-8")
    baseline_source = raw["baseline_source"].decode("utf-8")
    candidate_results = json.loads(raw["candidate_results"].decode("utf-8"))

    baseline_row = re.search(
        r"\|\s*In-Memory Baseline\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|",
        readme,
    )
    candidate_row = re.search(
        r"\|\s*Central Intelligence\s*\|\s*\*\*(\d+(?:\.\d+)?)\*\*\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|",
        readme,
    )
    require(baseline_row is not None, "published in-memory score row missing")
    require(candidate_row is not None, "published candidate score row missing")

    baseline_overall = float(baseline_row.group(1))
    baseline_factual = float(baseline_row.group(2))
    baseline_semantic = float(baseline_row.group(3))
    published_candidate_overall = float(candidate_row.group(1))
    published_candidate_factual = float(candidate_row.group(2))
    published_candidate_semantic = float(candidate_row.group(3))

    result_candidate_overall = float(candidate_results["overallScore"])
    result_candidate_semantic = category_score(candidate_results, "semantic-search")
    require(candidate_results.get("provider") == "Central Intelligence", "unexpected candidate provider")
    require(result_candidate_overall == published_candidate_overall, "README/result overall score mismatch")
    require(result_candidate_semantic == published_candidate_semantic, "README/result semantic score mismatch")

    floor_phrase = "It's a floor, not a meaningful comparison for semantic capabilities."
    baseline_self_described_floor = floor_phrase in readme
    lexical_overlap = "queryWords" in baseline_source and "contentLower.includes(word)" in baseline_source
    require(baseline_self_described_floor, "benchmark no longer describes the baseline as a semantic floor")
    require(lexical_overlap, "baseline implementation no longer matches expected lexical-overlap structure")

    evidence = {
        "schema_version": 1,
        "external_repository": REPO,
        "external_commit": COMMIT,
        "candidate": {
            "name": str(candidate_results["provider"]),
            "overall_score": result_candidate_overall,
            "factual_score": published_candidate_factual,
            "semantic_score": result_candidate_semantic,
        },
        "baseline": {
            "name": "In-Memory Baseline",
            "overall_score": baseline_overall,
            "factual_score": baseline_factual,
            "semantic_score": baseline_semantic,
            "self_described_floor": baseline_self_described_floor,
            "lexical_overlap_search": lexical_overlap,
            "meaningful_semantic_comparator": False,
        },
        "comparison": {
            "overall_advantage_points": result_candidate_overall - baseline_overall,
            "semantic_advantage_points": result_candidate_semantic - baseline_semantic,
        },
        "source_receipts": {
            name: {"url": URLS[name], "sha256": sha256(value), "bytes": len(value)}
            for name, value in raw.items()
        },
        "boundary": {
            "note": "The upstream benchmark itself discloses that its in-memory baseline is a floor rather than a meaningful semantic comparator. This probe records that limitation; it does not allege benchmark misconduct.",
            "independent_rerun_of_candidate": False,
        },
    }

    output = Path(".gauntlet/external-amb-evidence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
