from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LABELS = ["ASSERTED", "ENTAILED", "PRESUPPOSED", "IMPLICATED", "CONTRADICTED", "UNKNOWN"]

SYSTEM_PROMPT = """You are participating in a frozen semantic-comprehension evaluation.

Classify each proposition relative to the supplied context using exactly one label:

ASSERTED: the proposition is directly stated in the context.
ENTAILED: the proposition must be true if the context is true, but is not directly stated.
PRESUPPOSED: the proposition is backgrounded by a conventional trigger and remains supported under ordinary negation of that trigger.
IMPLICATED: the proposition is suggested by ordinary cooperative language use but can be cancelled without contradiction.
CONTRADICTED: the context supports the proposition's negation or an incompatible state.
UNKNOWN: the proposition is neither supported nor contradicted.

Tie-breaking:
1. Use ASSERTED for direct statement.
2. Use PRESUPPOSED when the support comes from a presupposition trigger.
3. Use ENTAILED for other necessary consequences.
4. Use IMPLICATED only for cancellable pragmatic inference.
5. Use CONTRADICTED when the proposition is incompatible with the context.
6. Otherwise use UNKNOWN.

For each proposition also return the IDs of the minimum context statements needed for your classification. For UNKNOWN use an empty evidence list.

Return JSON only in this schema:
{"id":"CASE_ID","answers":[{"id":"PROPOSITION_ID","label":"LABEL","evidence":["STATEMENT_ID"]}, ...]}

Do not explain your answers outside the JSON.
"""

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def load_identity(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = ["model_id", "artifact_sha256", "runtime", "base_url"]
    missing = [k for k in required if not value.get(k)]
    if missing:
        raise ValueError(f"model identity missing fields: {missing}")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(value["artifact_sha256"])):
        raise ValueError("artifact_sha256 must be a 64-hex SHA-256")
    if str(value["model_id"]).startswith("TO_BE_") or str(value["artifact_sha256"]).startswith("TO_BE_"):
        raise ValueError("model identity is still a placeholder")
    return value

def case_prompt(case: dict[str, Any]) -> str:
    lines = [f"CASE {case['id']}", "", "CONTEXT:"]
    for stmt in case["context"]:
        lines.append(f"{stmt['id']}: {stmt['text']}")
    lines.extend(["", "PROPOSITIONS:"])
    for prop in case["propositions"]:
        lines.append(f"{prop['id']}: {prop['text']}")
    lines.append("")
    lines.append("Return the required JSON object only.")
    return "\n".join(lines)

def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("response JSON is not an object")
        return value
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("response does not contain a JSON object")
        value = json.loads(text[start:end+1])
        if not isinstance(value, dict):
            raise ValueError("response JSON is not an object")
        return value

def post_chat(base_url: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "gri-sem0/1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def run_case(case: dict[str, Any], identity: dict[str, Any], *, timeout: float, transport_retries: int) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "model": identity["model_id"],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case_prompt(case)},
        ],
    }
    api_key = os.environ.get("SEM0_API_KEY", "local")
    errors = []
    started = time.time()
    response = None
    for attempt in range(transport_retries + 1):
        try:
            response = post_chat(identity["base_url"], api_key, payload, timeout)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            errors.append({"attempt": attempt + 1, "error": type(exc).__name__, "message": str(exc)})
            if attempt >= transport_retries:
                raise
            time.sleep(1.0)
    assert response is not None
    choices = response.get("choices") or []
    if not choices:
        raise ValueError(f"{case['id']}: model response has no choices")
    raw = choices[0].get("message", {}).get("content", "")
    parsed = extract_json_object(raw)
    if parsed.get("id") != case["id"]:
        raise ValueError(f"{case['id']}: response id mismatch")
    expected = {p["id"] for p in case["propositions"]}
    answers = parsed.get("answers")
    if not isinstance(answers, list):
        raise ValueError(f"{case['id']}: answers must be a list")
    seen = {a.get("id") for a in answers if isinstance(a, dict)}
    if seen != expected:
        raise ValueError(f"{case['id']}: proposition id set mismatch")
    for answer in answers:
        if answer.get("label") not in LABELS:
            raise ValueError(f"{case['id']}/{answer.get('id')}: invalid label")
        ev = answer.get("evidence", [])
        if not isinstance(ev, list):
            raise ValueError(f"{case['id']}/{answer.get('id')}: evidence must be a list")
    call_record = {
        "case_id": case["id"],
        "model_id": identity["model_id"],
        "model_artifact_sha256": identity["artifact_sha256"],
        "request": {
            "temperature": 0,
            "top_p": 1,
            "max_tokens": 700,
            "system_prompt": SYSTEM_PROMPT,
            "user_prompt": case_prompt(case),
        },
        "response": response,
        "transport_errors": errors,
        "wall_seconds": time.time() - started,
    }
    return parsed, call_record

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--model-identity", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--calls", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--transport-retries", type=int, default=2)
    args = ap.parse_args()

    cases = load_jsonl(args.cases)
    identity = load_identity(args.model_identity)
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    args.calls.parent.mkdir(parents=True, exist_ok=True)
    predictions = []
    calls = []
    for case in cases:
        pred, call = run_case(case, identity, timeout=args.timeout, transport_retries=args.transport_retries)
        predictions.append(pred)
        calls.append(call)
    args.predictions.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in predictions), encoding="utf-8")
    args.calls.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in calls), encoding="utf-8")
    print(json.dumps({
        "case_count": len(cases),
        "prediction_path": str(args.predictions),
        "calls_path": str(args.calls),
        "model_id": identity["model_id"],
        "model_artifact_sha256": identity["artifact_sha256"],
    }, sort_keys=True))

if __name__ == "__main__":
    main()
