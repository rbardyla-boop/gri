from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from experiments.forge.forge import Tool


def broker_request(socket_path: str | Path, body: dict[str, Any], timeout: float = 310.0) -> dict[str, Any]:
    path = str(socket_path)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall((json.dumps(body, sort_keys=True) + "\n").encode("utf-8"))
        chunks = bytearray()
        while True:
            block = sock.recv(65536)
            if not block:
                break
            chunks.extend(block)
            if b"\n" in block:
                break
    if not chunks:
        raise RuntimeError("FORGE_MODEL_BROKER_EMPTY_REPLY")
    reply = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    if not isinstance(reply, dict) or reply.get("ok") is not True:
        if isinstance(reply, dict):
            raise RuntimeError(f"FORGE_MODEL_BROKER_ERROR:{reply.get('error_type')}:{reply.get('error')}")
        raise RuntimeError("FORGE_MODEL_BROKER_INVALID_REPLY")
    outer = reply.get("response")
    if not isinstance(outer, dict):
        raise RuntimeError("FORGE_MODEL_BROKER_INVALID_RESPONSE")
    return outer


def make_broker_text_tool(
    *,
    name: str,
    socket_path: str | Path,
    model: str,
    system_prompt: str,
    seed: int = 20260823,
    num_predict: int = 512,
    json_mode: bool = False,
    cost: int = 4,
) -> Tool:
    """Create a fixed, pre-authorized local-model primitive.

    ToolSmith cannot synthesize this capability. It must be registered explicitly
    by the experiment protocol. The input must be a prompt string; no target/gold
    field is available through this contract.
    """
    if not model or not isinstance(model, str):
        raise ValueError("model required")
    if not system_prompt or not isinstance(system_prompt, str):
        raise ValueError("system_prompt required")
    if not 1 <= num_predict <= 4096:
        raise ValueError("num_predict out of range")

    def run(prompt: Any) -> str:
        if not isinstance(prompt, str):
            raise TypeError("broker model tool requires text input")
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0,
                "seed": seed,
                "num_predict": num_predict,
            },
        }
        if json_mode:
            body["format"] = "json"
        outer = broker_request(socket_path, body)
        content = outer.get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("FORGE_MODEL_RESPONSE_MISSING_CONTENT")
        return content

    return Tool(name=name, input_kind="text", output_kind="text", cost=cost, fn=run)
