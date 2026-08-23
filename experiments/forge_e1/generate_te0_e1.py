from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

LABELS = ("KAV", "MIR", "TOV")
TEMPLATES = (
    "Synthetic serialization task. Return exactly one JSON object with keys label and evidence. "
    "Set label to {label}. The evidence input is a multiset: {evidence}. Return evidence as the unique IDs in lexicographic order. "
    "Do not add keys, prose, markdown, or duplicate IDs.",
    "Interface-only task. Required JSON keys are label and evidence. label={label}. Evidence candidates={evidence}. "
    "Treat evidence as a set: deduplicate and sort ascending. Output JSON only.",
    "Produce one strict JSON object, nothing else. The required label is {label}. The evidence multiset is {evidence}. "
    "The evidence array must contain every distinct ID exactly once, sorted lexicographically.",
    "This is not a reasoning question. Copy the required label {label} into JSON key label. For JSON key evidence, canonicalize this multiset as a sorted unique list: {evidence}. JSON object only.",
    "Serialization check: label must be exactly {label}. Evidence values are {evidence}. Return only {{\"label\":...,\"evidence\":[...]}} with evidence deduplicated and sorted.",
    "Follow the data contract exactly. label -> {label}; evidence multiset -> {evidence}. Evidence has set semantics. Return only the two-key JSON object and no surrounding text.",
)


def seed_from_text(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def make_pool(*, seed_text: str, count: int, prefix: str) -> list[dict]:
    seed = seed_from_text(seed_text)
    rng = random.Random(seed)
    label_offset = seed % len(LABELS)
    template_offset = (seed // len(LABELS)) % len(TEMPLATES)
    rows: list[dict] = []
    for i in range(count):
        # Balance the tiny nonce vocabulary by construction. Random evidence and
        # pool-specific offsets retain variety without allowing an unlucky BUILD
        # draw to omit a valid label from ToolSmith's observed contract.
        label = LABELS[(i + label_offset) % len(LABELS)]
        unique_count = rng.randint(1, 4)
        unique_ids = sorted({f"E{rng.randrange(0, 10000):04d}" for _ in range(unique_count * 3)})[:unique_count]
        if not unique_ids:
            unique_ids = [f"E{rng.randrange(0, 10000):04d}"]
        multiset = list(unique_ids)
        # Add 0-3 duplicates and then shuffle. Correct target remains the set.
        for _ in range(rng.randint(0, 3)):
            multiset.append(rng.choice(unique_ids))
        rng.shuffle(multiset)
        template_index = (i + template_offset + rng.randrange(len(TEMPLATES))) % len(TEMPLATES)
        prompt = TEMPLATES[template_index].format(
            label=label,
            evidence=json.dumps(multiset, separators=(",", ":")),
        )
        target = {"label": label, "evidence": sorted(unique_ids)}
        rows.append(
            {
                "case_id": f"{prefix}-{i:04d}",
                "prompt": prompt,
                "target": target,
                "template_index": template_index,
            }
        )
    return rows


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--prefix", required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed-text")
    group.add_argument("--seed-file", type=Path)
    args = ap.parse_args()
    if args.count <= 0:
        raise SystemExit("count must be positive")
    if args.seed_file:
        seed_text = args.seed_file.read_text(encoding="utf-8").strip()
        if not seed_text:
            raise SystemExit("seed file is empty")
    else:
        seed_text = args.seed_text
    rows = make_pool(seed_text=seed_text, count=args.count, prefix=args.prefix)
    write_jsonl(args.output, rows)
    print(json.dumps({
        "status": "TE0_E1_POOL_GENERATED",
        "count": len(rows),
        "output": str(args.output),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "seed_sha256": hashlib.sha256(seed_text.encode("utf-8")).hexdigest(),
        "label_counts": {label: sum(row["target"]["label"] == label for row in rows) for label in LABELS},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
