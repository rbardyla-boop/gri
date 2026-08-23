from __future__ import annotations

import argparse
import copy
import json
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-entries", type=int, default=8)
    args = ap.parse_args()
    env = json.load(sys.stdin)
    state = dict(env.get("state") or {})
    history = list(state.get("memory_history") or [])
    snapshot = {}
    for key in ("prediction", "last_raw", "retrieved", "consensus_count", "candidate_count"):
        if key in state:
            snapshot[key] = copy.deepcopy(state[key])
    if snapshot:
        history.append(snapshot)
    if args.max_entries > 0:
        history = history[-args.max_entries:]
    state["memory_history"] = history
    json.dump({"state": state}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
