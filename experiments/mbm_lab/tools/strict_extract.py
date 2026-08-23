from __future__ import annotations

import json
import sys


def expected_key(kind: str) -> str:
    return {
        "enum": "label",
        "copy": "value",
        "mapping": "mapping",
        "set": "selected",
        "binary_matrix": "matrix",
        "ordered_vector": "values",
    }[kind]


def main() -> None:
    env = json.load(sys.stdin)
    fixture = env["fixture"]
    state = dict(env.get("state") or {})
    raw = state.get("last_raw")
    if not isinstance(raw, str):
        raise ValueError("no last_raw candidate")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("model output must be JSON object")
    key = expected_key(fixture["kind"])
    if set(value) != {key}:
        raise ValueError(f"expected exactly key {key}")
    candidate = {key: value[key]}
    candidates = list(state.get("parsed_candidates") or [])
    candidates.append(candidate)
    state["parsed_candidates"] = candidates
    state["prediction"] = candidate
    json.dump({"state": state}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
