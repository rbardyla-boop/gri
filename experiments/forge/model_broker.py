from __future__ import annotations

import argparse
import json
import os
import re
import socketserver
import urllib.request
from pathlib import Path
from typing import Any

MAX_REQUEST_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 300.0


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}_not_number")
    number = float(value)
    if not (-1e12 < number < 1e12):
        raise ValueError(f"{name}_out_of_range")
    return number


def validate_request(value: Any, allowed_models: set[str]) -> dict[str, Any]:
    """Validate the only capability exposed from the sandbox to local Ollama.

    The broker accepts a deliberately small subset of /api/chat. It does not
    proxy arbitrary URLs, tools, files, shell commands, or model management.
    """
    if not isinstance(value, dict):
        raise ValueError("request_not_object")
    allowed_keys = {"model", "messages", "format", "options"}
    extra = set(value) - allowed_keys
    if extra:
        raise ValueError(f"unexpected_request_keys:{sorted(extra)}")

    model = value.get("model")
    if not isinstance(model, str) or model not in allowed_models:
        raise ValueError("model_not_allowed")

    messages = value.get("messages")
    if not isinstance(messages, list) or not (1 <= len(messages) <= 32):
        raise ValueError("invalid_messages")
    normalized_messages: list[dict[str, str]] = []
    total_chars = 0
    for row in messages:
        if not isinstance(row, dict) or set(row) != {"role", "content"}:
            raise ValueError("invalid_message_shape")
        role = row.get("role")
        content = row.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str):
            raise ValueError("invalid_message")
        total_chars += len(content)
        if total_chars > 500_000:
            raise ValueError("messages_too_large")
        normalized_messages.append({"role": role, "content": content})

    raw_options = value.get("options", {})
    if not isinstance(raw_options, dict):
        raise ValueError("invalid_options")
    allowed_options = {"temperature", "seed", "num_predict", "top_p", "top_k"}
    extra_options = set(raw_options) - allowed_options
    if extra_options:
        raise ValueError(f"unexpected_options:{sorted(extra_options)}")

    options: dict[str, Any] = {}
    if "temperature" in raw_options:
        t = _finite_number(raw_options["temperature"], "temperature")
        if not 0.0 <= t <= 2.0:
            raise ValueError("temperature_out_of_range")
        options["temperature"] = t
    if "seed" in raw_options:
        seed = raw_options["seed"]
        if isinstance(seed, bool) or not isinstance(seed, int) or not -(2**31) <= seed < 2**31:
            raise ValueError("seed_out_of_range")
        options["seed"] = seed
    if "num_predict" in raw_options:
        n = raw_options["num_predict"]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 4096:
            raise ValueError("num_predict_out_of_range")
        options["num_predict"] = n
    if "top_p" in raw_options:
        top_p = _finite_number(raw_options["top_p"], "top_p")
        if not 0.0 < top_p <= 1.0:
            raise ValueError("top_p_out_of_range")
        options["top_p"] = top_p
    if "top_k" in raw_options:
        top_k = raw_options["top_k"]
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 0 <= top_k <= 10000:
            raise ValueError("top_k_out_of_range")
        options["top_k"] = top_k

    request: dict[str, Any] = {
        "model": model,
        "stream": False,
        "messages": normalized_messages,
        "options": options,
    }
    if "format" in value:
        fmt = value["format"]
        if fmt == "json":
            request["format"] = "json"
        elif isinstance(fmt, dict):
            # JSON schema is allowed, but cap its serialized size and forbid
            # remote refs. The object is forwarded only to local Ollama.
            encoded = json.dumps(fmt, sort_keys=True)
            if len(encoded) > 200_000:
                raise ValueError("format_too_large")
            if re.search(r'"\$ref"\s*:\s*"(?:https?|file):', encoded, flags=re.I):
                raise ValueError("remote_schema_ref_forbidden")
            request["format"] = fmt
        else:
            raise ValueError("invalid_format")
    return request


class BrokerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(line) > MAX_REQUEST_BYTES:
            self.wfile.write(b'{"ok":false,"error":"request_too_large"}\n')
            return
        try:
            request = json.loads(line.decode("utf-8"))
            body = validate_request(request, self.server.allowed_models)  # type: ignore[attr-defined]
            upstream = urllib.request.Request(
                self.server.ollama_root.rstrip("/") + "/api/chat",  # type: ignore[attr-defined]
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "gri-forge-model-broker/1"},
                method="POST",
            )
            with urllib.request.urlopen(upstream, timeout=self.server.timeout) as response:  # type: ignore[attr-defined]
                raw = response.read()
            outer = json.loads(raw.decode("utf-8"))
            payload = {"ok": True, "response": outer}
        except Exception as exc:
            payload = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
        self.wfile.write((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))


class UnixBroker(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, *, allowed_models: set[str], ollama_root: str, timeout: float):
        self.allowed_models = allowed_models
        self.ollama_root = ollama_root
        self.timeout = timeout
        super().__init__(path, BrokerHandler)


def main() -> None:
    ap = argparse.ArgumentParser(description="Narrow Unix-socket bridge from Forge sandbox to approved local Ollama model(s).")
    ap.add_argument("--socket", type=Path, required=True)
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--ollama-root", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = ap.parse_args()

    models = set(args.model)
    if not models:
        raise SystemExit("at least one --model is required")
    path = args.socket.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()

    server = UnixBroker(str(path), allowed_models=models, ollama_root=args.ollama_root, timeout=args.timeout)
    os.chmod(path, 0o600)
    print(json.dumps({
        "status": "FORGE_MODEL_BROKER_READY",
        "socket": str(path),
        "allowed_models": sorted(models),
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
