from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import urllib.request
from pathlib import Path

MAX_REQUEST = 2 * 1024 * 1024


def validate_request(value: dict, allowed_models: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ValueError("request_not_object")
    allowed = {"model", "messages", "format", "options"}
    if set(value) - allowed:
        raise ValueError("unexpected_request_keys")
    model = value.get("model")
    if model not in allowed_models:
        raise ValueError("model_not_allowed")
    messages = value.get("messages")
    if not isinstance(messages, list) or not messages or len(messages) > 32:
        raise ValueError("invalid_messages")
    for row in messages:
        if not isinstance(row, dict) or set(row) != {"role", "content"}:
            raise ValueError("invalid_message_shape")
        if row["role"] not in {"system", "user", "assistant"} or not isinstance(row["content"], str):
            raise ValueError("invalid_message")
    options = value.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("invalid_options")
    allowed_options = {"temperature", "seed", "num_predict", "top_p", "top_k"}
    if set(options) - allowed_options:
        raise ValueError("unexpected_options")
    if int(options.get("num_predict", 512)) > 4096:
        raise ValueError("num_predict_too_large")
    out = {"model": model, "stream": False, "messages": messages, "options": options}
    if "format" in value:
        fmt = value["format"]
        if not (fmt == "json" or isinstance(fmt, dict)):
            raise ValueError("invalid_format")
        out["format"] = fmt
    return out


class BrokerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(MAX_REQUEST + 1)
        if len(line) > MAX_REQUEST:
            self.wfile.write(b'{"ok":false,"error":"request_too_large"}\n')
            return
        try:
            request = json.loads(line.decode("utf-8"))
            body = validate_request(request, self.server.allowed_models)
            req = urllib.request.Request(
                self.server.ollama_root.rstrip("/") + "/api/chat",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "te0-model-broker/1"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.server.timeout) as response:
                raw = response.read()
            outer = json.loads(raw.decode("utf-8"))
            payload = {"ok": True, "response": outer}
        except Exception as exc:
            payload = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
        self.wfile.write((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))


class UnixBroker(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, handler, *, allowed_models: set[str], ollama_root: str, timeout: float):
        self.allowed_models = allowed_models
        self.ollama_root = ollama_root
        self.timeout = timeout
        super().__init__(path, handler)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", type=Path, required=True)
    ap.add_argument("--model", action="append", default=["llama3.1:8b"])
    ap.add_argument("--ollama-root", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    path = args.socket.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    server = UnixBroker(str(path), BrokerHandler, allowed_models=set(args.model), ollama_root=args.ollama_root, timeout=args.timeout)
    os.chmod(path, 0o600)
    print(json.dumps({
        "status": "TE0_MODEL_BROKER_READY",
        "socket": str(path),
        "allowed_models": sorted(set(args.model)),
        "ollama_root": args.ollama_root,
    }, sort_keys=True), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
