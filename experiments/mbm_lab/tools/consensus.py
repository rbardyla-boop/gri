from __future__ import annotations

import collections
import json
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> None:
    env = json.load(sys.stdin)
    state = dict(env.get("state") or {})
    candidates = list(state.get("parsed_candidates") or [])
    if not candidates:
        raise ValueError("no parsed candidates")
    counts = collections.Counter(canonical(x) for x in candidates)
    best_count = max(counts.values())
    winners = sorted(k for k, v in counts.items() if v == best_count)
    if len(winners) != 1:
        raise ValueError("consensus tie")
    prediction = json.loads(winners[0])
    state["prediction"] = prediction
    state["consensus_count"] = best_count
    state["candidate_count"] = len(candidates)
    json.dump({"state": state}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
