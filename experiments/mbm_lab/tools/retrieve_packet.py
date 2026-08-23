from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def toks(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args()
    env = json.load(sys.stdin)
    fixture = env["fixture"]
    state = dict(env.get("state") or {})
    query = toks(fixture.get("prompt", ""))
    rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    scored = []
    for row in rows:
        text = str(row.get("text", ""))
        overlap = len(query & toks(text))
        scored.append((overlap, str(row.get("id", "")), row))
    scored.sort(key=lambda x: (-x[0], x[1]))
    state["retrieved"] = [row for score, _, row in scored[: max(args.top_k, 0)] if score > 0]
    json.dump({"state": state}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
