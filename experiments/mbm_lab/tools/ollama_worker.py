from __future__ import annotations

import argparse
import json
import os
import socket
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


def via_broker(path: str, body: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(310.0)
        sock.connect(path)
        sock.sendall((json.dumps(body) + "\n").encode("utf-8"))
        chunks = bytearray()
        while True:
            block = sock.recv(65536)
            if not block:
                break
            chunks.extend(block)
            if b"\n" in block:
                break
    reply = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    if reply.get("ok") is not True:
        raise RuntimeError(f"broker error: {reply.get('error_type')}: {reply.get('error')}")
    outer = reply.get("response")
    if not isinstance(outer, dict):
        raise ValueError("broker returned invalid response")
    return outer


def direct(root: str, body: dict) -> dict:
    request_body = {**body, "stream": False}
    req = urllib.request.Request(
        root.rstrip("/") + "/api/chat",
        data=json.dumps(request_body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "te0-ollama-worker/1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300.0) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--root", default="http://127.0.0.1:11434")
    ap.add_argument("--broker-socket", default=os.environ.get("TE0_MODEL_BROKER", ""))
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
        "messages": [
            {"role": "system", "content": system(args.style)},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": 0, "seed": 20260823 + args.seed_offset, "num_predict": 512},
    }
    if args.json_mode:
        body["format"] = "json"
    outer = via_broker(args.broker_socket, body) if args.broker_socket else direct(args.root, body)
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
