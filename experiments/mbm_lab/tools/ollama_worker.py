from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def system(style: str) -> str:
    if style == "minimal":
        return "Complete the synthetic task. Return only the requested JSON, with no explanation."
    if style == "explicit":
        return (
            "This is a synthetic instruction-following and serialization task. The user prompt contains all authoritative task information. "
            "Optional upstream tool context may be supplied separately. Do not invent facts. Return only JSON representing the requested answer, with no markdown or commentary."
        )
    raise ValueError(style)


def upstream_context(state: dict) -> dict:
    allowed = {}
    for key in ("retrieved", "memory_history", "parsed_candidates", "prediction", "consensus_count", "candidate_count"):
        if key in state:
            allowed[key] = state[key]
    return allowed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--root", default="http://127.0.0.1:11434")
    ap.add_argument("--style", choices=["minimal", "explicit"], default="explicit")
    ap.add_argument("--json-mode", action="store_true")
    ap.add_argument("--seed-offset", type=int, default=0)
    args = ap.parse_args()

    env = json.load(sys.stdin)
    fixture = env["fixture"]
    state = dict(env.get("state") or {})
    context = upstream_context(state)
    user = fixture["prompt"]
    if context:
        user += "\n\nOPTIONAL UPSTREAM TOOL CONTEXT:\n" + json.dumps(context, sort_keys=True)
    body = {
        "model": args.model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system(args.style)},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0, "seed": 20260823 + args.seed_offset, "num_predict": 512},
    }
    if args.json_mode:
        body["format"] = "json"
    req = urllib.request.Request(
        args.root.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "te0-ollama-worker/1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300.0) as resp:
        outer = json.loads(resp.read().decode())
    content = outer.get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("missing message.content")
    history = list(state.get("raw_candidates") or [])
    history.append(content)
    state["raw_candidates"] = history
    state["last_raw"] = content
    json.dump({"state": state}, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
