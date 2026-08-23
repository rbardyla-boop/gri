from __future__ import annotations

import argparse
import hashlib
import json
import random
import string
from pathlib import Path
from typing import Any

LABELS = ["ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN"]


def token(rng: random.Random, prefix: str, width: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return prefix + "_" + "".join(rng.choice(alphabet) for _ in range(width))


def fixture(index: int, kind: str, target: dict[str, Any], extra: str = "") -> dict[str, Any]:
    prompt = "Return exactly this JSON object, preserving every key and value: " + json.dumps(target, sort_keys=True)
    if extra:
        prompt += "\n" + extra
    return {"id": f"fx-{index:06d}", "kind": kind, "prompt": prompt, "target": target}


def make_fixture(rng: random.Random, index: int, kind: str) -> dict[str, Any]:
    if kind == "enum":
        return fixture(index, kind, {"label": rng.choice(LABELS)})

    if kind == "copy":
        return fixture(index, kind, {"value": token(rng, "Q")})

    if kind == "mapping":
        keys = [token(rng, "Q", 6) for _ in range(rng.randint(3, 8))]
        mapping = {k: rng.choice(LABELS) for k in keys}
        return fixture(index, kind, {"mapping": mapping})

    if kind == "set":
        universe = [token(rng, "S", 6) for _ in range(rng.randint(4, 10))]
        chosen = sorted(rng.sample(universe, rng.randint(0, len(universe))))
        return fixture(
            index,
            kind,
            {"selected": chosen},
            "Reference universe (do not add it to the returned object): " + json.dumps(universe),
        )

    if kind == "binary_matrix":
        rows = [token(rng, "Q", 5) for _ in range(rng.randint(2, 5))]
        cols = [token(rng, "S", 5) for _ in range(rng.randint(3, 7))]
        matrix = {r: {c: bool(rng.getrandbits(1)) for c in cols} for r in rows}
        return fixture(index, kind, {"matrix": matrix})

    if kind == "ordered_vector":
        values = [rng.choice(LABELS) for _ in range(rng.randint(4, 12))]
        return fixture(index, kind, {"values": values})

    raise ValueError(f"unknown fixture kind: {kind}")


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260823)
    ap.add_argument(
        "--kinds",
        default="enum,copy,mapping,set,binary_matrix,ordered_vector",
        help="comma-separated fixture kinds",
    )
    args = ap.parse_args()

    if args.output.exists():
        raise FileExistsError(args.output)
    kinds = [x.strip() for x in args.kinds.split(",") if x.strip()]
    rng = random.Random(args.seed)
    rows = [make_fixture(rng, i, kinds[i % len(kinds)]) for i in range(args.count)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    manifest = {
        "status": "MBM_SYNTHETIC_FIXTURES",
        "count": len(rows),
        "seed": args.seed,
        "kinds": kinds,
        "content_sha256": canonical_sha256(rows),
        "scientific_content": False,
        "task_type": "exact_json_serialization",
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
