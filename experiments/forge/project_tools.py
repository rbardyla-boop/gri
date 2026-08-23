from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from experiments.forge.forge import Tool, canonical_json

Json = Any


def strict_json_object(text: Any) -> dict[str, Any]:
    if not isinstance(text, str):
        raise TypeError("strict_json_object requires text")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def canonical_compare(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"left", "right"}:
        raise ValueError("compare input must contain exactly left/right")
    return canonical_json(value["left"]) == canonical_json(value["right"])


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def retrieve_overlap(value: Any) -> dict[str, Any]:
    """Transparent lexical retrieval baseline.

    Input: {"query": str, "documents": [{"id":..., "text":...}, ...], "top_k": int?}
    Output includes scores so later tools can audit why a row was selected.
    """
    if not isinstance(value, dict):
        raise TypeError("retrieval request must be object")
    query = value.get("query")
    docs = value.get("documents")
    top_k = value.get("top_k", 3)
    if not isinstance(query, str) or not isinstance(docs, list):
        raise ValueError("retrieval request requires query/documents")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 0 <= top_k <= 100:
        raise ValueError("invalid top_k")
    q = _tokens(query)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for row in docs:
        if not isinstance(row, dict) or "id" not in row or "text" not in row:
            raise ValueError("invalid document")
        text = str(row["text"])
        score = len(q & _tokens(text))
        scored.append((score, str(row["id"]), row))
    scored.sort(key=lambda x: (-x[0], x[1]))
    selected = [
        {"score": score, "document": row}
        for score, _, row in scored[:top_k]
        if score > 0
    ]
    return {"query": query, "selected": selected}


def bounded_state_update(value: Any) -> dict[str, Any]:
    """Pure bounded state transition; state is data, not hidden mutable memory."""
    if not isinstance(value, dict) or set(value) - {"history", "append", "max_entries"}:
        raise ValueError("state update requires history/append/max_entries only")
    history = value.get("history", [])
    append = value.get("append")
    max_entries = value.get("max_entries", 8)
    if not isinstance(history, list):
        raise ValueError("history must be list")
    if isinstance(max_entries, bool) or not isinstance(max_entries, int) or not 0 <= max_entries <= 1024:
        raise ValueError("invalid max_entries")
    out = list(history)
    if append is not None:
        out.append(append)
    if max_entries == 0:
        out = []
    else:
        out = out[-max_entries:]
    return {"history": out, "count": len(out)}


def vote_confidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"votes"}:
        raise ValueError("confidence input requires votes only")
    votes = value.get("votes")
    if not isinstance(votes, list) or not votes:
        raise ValueError("votes must be non-empty list")
    encoded = [canonical_json(v) for v in votes]
    counts = collections.Counter(encoded)
    best_count = max(counts.values())
    winners = sorted(k for k, n in counts.items() if n == best_count)
    if len(winners) != 1:
        return {
            "status": "TIE",
            "prediction": None,
            "confidence": best_count / len(votes),
            "winner_count": best_count,
            "vote_count": len(votes),
        }
    return {
        "status": "UNIQUE_WINNER",
        "prediction": json.loads(winners[0]),
        "confidence": best_count / len(votes),
        "winner_count": best_count,
        "vote_count": len(votes),
    }


def inspect_failures(value: Any) -> dict[str, Any]:
    """Query already-supplied ledger/failure rows without filesystem authority."""
    if not isinstance(value, dict) or set(value) - {"rows", "failure_class", "tool", "limit"}:
        raise ValueError("failure query has unexpected keys")
    rows = value.get("rows")
    if not isinstance(rows, list):
        raise ValueError("rows must be list")
    failure_class = value.get("failure_class")
    tool = value.get("tool")
    limit = value.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 1000:
        raise ValueError("invalid limit")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if failure_class is not None and row.get("failure_class") != failure_class:
            continue
        tools = row.get("tools", [])
        if tool is not None and tool not in tools:
            continue
        out.append(row)
    return {"matches": out[:limit], "match_count": len(out)}


def fixed_project_tools() -> tuple[Tool, ...]:
    """Explicit non-generated starter tools aligned with the project end state."""
    return (
        Tool("strict_json", "text", "json", 1, strict_json_object),
        Tool("canonical_compare", "comparison", "bool", 1, canonical_compare),
        Tool("retrieve_overlap", "retrieval_request", "retrieval_packet", 1, retrieve_overlap),
        Tool("bounded_state", "state_update", "state", 1, bounded_state_update),
        Tool("vote_confidence", "votes", "confidence", 1, vote_confidence),
        Tool("inspect_failures", "failure_query", "failure_records", 1, inspect_failures),
    )
