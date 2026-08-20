from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


VALUES = ("RED", "BLUE", "GREEN", "YELLOW", "ORANGE", "PURPLE", "BLACK", "WHITE")
FIELD = "value"
CASES_PER_CONDITION = 16
TARGET_ENTITIES = tuple(f"entity-{i:02d}" for i in range(8))
SPLIT_SPECS = {
    "train": {
        "delays": (1, 4, 16),
        "distractors": (0, 8, 32),
        "capacities": (4, 16, 64),
    },
    "iid": {
        "delays": (1, 4, 16),
        "distractors": (0, 8, 32),
        "capacities": (4, 16, 64),
    },
    "extrapolation": {
        "delays": (64, 256, 1024),
        "distractors": (128, 512, 1024),
        "capacities": (256, 1024),
    },
}


@dataclass(frozen=True)
class LedgerEntry:
    memory_id: str
    entity: str
    field: str
    value: str
    creation_episode: int
    supersedes: str | None
    source_episode: int


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def content_hash(case: dict[str, Any]) -> str:
    payload = {key: case[key] for key in ("family", "condition", "episodes", "query")}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _value(split: str, family: str, condition: str, index: int) -> str:
    # Rotate a fixed class cycle by a deterministic condition-specific offset.
    # This gives exact balance for every 16-case condition while retaining
    # independent labels across splits and families.
    offset = stable_int("value-offset", split, family, condition) % len(VALUES)
    return VALUES[(index + offset) % len(VALUES)]


def _entity(index: int) -> str:
    return TARGET_ENTITIES[index % len(TARGET_ENTITIES)]


def _noise_event(split: str, family: str, condition: str, case_index: int, event_index: int) -> dict[str, Any]:
    # Noise contains no target entity, target field, answer, memory id, or case id.
    token = f"noise-{stable_int('noise', split, family, condition, case_index, event_index):016x}"
    return {"kind": "noise", "token": token}


def _write_event(memory_id: str, entity: str, value: str) -> dict[str, Any]:
    return {"kind": "write", "memory_id": memory_id, "entity": entity, "field": FIELD, "value": value}


def _query_event(entity: str, *, mode: str, as_of_episode: int | None = None) -> dict[str, Any]:
    return {"kind": "query", "entity": entity, "field": FIELD, "mode": mode, "as_of_episode": as_of_episode}


def _episodes(events: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [{"index": index, "events": episode_events} for index, episode_events in enumerate(events)]


def _case_id(split: str, family: str, condition: str, index: int) -> str:
    return f"dmc00-{split}-{family}-{condition}-{index:04d}"


def _make_delayed(split: str, delay: int, index: int) -> dict[str, Any]:
    family, condition = "delayed_recall", f"delay_{delay}"
    entity = _entity(index)
    value = _value(split, family, condition, index)
    events = [[_write_event(f"m-{split}-{family}-{condition}-{index}", entity, value)]]
    events.extend([[_noise_event(split, family, condition, index, j)] for j in range(delay)])
    events.append([_query_event(entity, mode="current")])
    return _finish(split, family, condition, index, events, entity, value, "current")


def _make_distractor(split: str, load: int, index: int) -> dict[str, Any]:
    family, condition = "distractor_resistance", f"load_{load}"
    entity = _entity(index)
    value = _value(split, family, condition, index)
    events = [[_write_event(f"m-{split}-{family}-{condition}-{index}", entity, value)]]
    events.extend([[_noise_event(split, family, condition, index, j)] for j in range(load)])
    events.append([_query_event(entity, mode="current")])
    return _finish(split, family, condition, index, events, entity, value, "current")


def _make_capacity(split: str, load: int, index: int) -> dict[str, Any]:
    family, condition = "capacity_pressure", f"load_{load}"
    target_slot = stable_int("capacity-target", split, load, index) % load
    target_entity = f"capacity-entity-{target_slot:04d}"
    value = _value(split, family, condition, index)
    events = []
    for slot in range(load):
        entity = f"capacity-entity-{slot:04d}"
        stored_value = value if slot == target_slot else VALUES[stable_int("capacity", split, load, index, slot) % len(VALUES)]
        events.append([_write_event(f"m-{split}-{family}-{condition}-{index}-{slot}", entity, stored_value)])
    events.append([_query_event(target_entity, mode="current")])
    return _finish(split, family, condition, index, events, target_entity, value, "current")


def _make_supersession(split: str, mode: str, index: int) -> dict[str, Any]:
    family, condition = "supersession", mode
    entity = _entity(index)
    original = _value(split, family, condition, index)
    current = VALUES[(VALUES.index(original) + 1) % len(VALUES)]
    events = [
        [_write_event(f"m-{split}-{family}-{index}-original", entity, original)],
        [_noise_event(split, family, condition, index, 0)],
        [_write_event(f"m-{split}-{family}-{index}-current", entity, current)],
    ]
    if mode == "current":
        events.append([_query_event(entity, mode="current")])
        answer = current
    elif mode == "history":
        events.append([_query_event(entity, mode="history", as_of_episode=0)])
        answer = original
    else:
        raise ValueError(mode)
    return _finish(split, family, condition, index, events, entity, answer, mode, extra={"original_value": original, "current_value": current})


def _finish(
    split: str,
    family: str,
    condition: str,
    index: int,
    events: list[list[dict[str, Any]]],
    entity: str,
    answer: str,
    mode: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = {
        "case_id": _case_id(split, family, condition, index),
        "split": split,
        "family": family,
        "condition": condition,
        "episodes": _episodes(events),
        "query": {"entity": entity, "field": FIELD, "mode": mode},
        "answer": answer,
        "metadata": extra or {},
    }
    case["content_hash"] = content_hash(case)
    return case


def build_split(split: str) -> list[dict[str, Any]]:
    if split not in SPLIT_SPECS:
        raise ValueError(f"unknown split: {split}")
    spec = SPLIT_SPECS[split]
    cases: list[dict[str, Any]] = []
    for delay in spec["delays"]:
        cases.extend(_make_delayed(split, delay, index) for index in range(CASES_PER_CONDITION))
    for load in spec["distractors"]:
        cases.extend(_make_distractor(split, load, index) for index in range(CASES_PER_CONDITION))
    for load in spec["capacities"]:
        cases.extend(_make_capacity(split, load, index) for index in range(CASES_PER_CONDITION))
    for mode in ("current", "history"):
        cases.extend(_make_supersession(split, mode, index) for index in range(CASES_PER_CONDITION))
    return cases


def build_dataset() -> dict[str, list[dict[str, Any]]]:
    return {split: build_split(split) for split in SPLIT_SPECS}


def _validate_event(event: dict[str, Any]) -> None:
    kind = event.get("kind")
    if kind == "write":
        required = {"kind", "memory_id", "entity", "field", "value"}
        if set(event) != required or not isinstance(event["value"], str) or event["field"] != FIELD:
            raise ValueError("malformed write event")
    elif kind == "noise":
        if set(event) != {"kind", "token"}:
            raise ValueError("malformed noise event")
    elif kind == "query":
        required = {"kind", "entity", "field", "mode", "as_of_episode"}
        if set(event) != required or event["field"] != FIELD or event["mode"] not in {"current", "history"}:
            raise ValueError("malformed query event")
        if event["mode"] == "current" and event["as_of_episode"] is not None:
            raise ValueError("current query cannot expose history index")
        if event["mode"] == "history" and not isinstance(event["as_of_episode"], int):
            raise ValueError("history query requires as_of_episode")
    else:
        raise ValueError("unknown event kind")


def validate_case(case: dict[str, Any]) -> None:
    required = {"case_id", "split", "family", "condition", "episodes", "query", "answer", "metadata", "content_hash"}
    if set(case) != required or case["answer"] not in VALUES:
        raise ValueError("malformed case")
    if case["content_hash"] != content_hash(case):
        raise ValueError("content hash mismatch")
    if not case["episodes"] or case["episodes"][-1]["events"][0]["kind"] != "query":
        raise ValueError("query must be the first event of the final episode")
    for expected_index, episode in enumerate(case["episodes"]):
        if set(episode) != {"index", "events"} or episode["index"] != expected_index or not episode["events"]:
            raise ValueError("malformed episode")
        for event in episode["events"]:
            _validate_event(event)
    query_event = case["episodes"][-1]["events"][0]
    if query_event["kind"] != "query" or query_event["entity"] != case["query"]["entity"] or query_event["mode"] != case["query"]["mode"]:
        raise ValueError("query metadata mismatch")
    if any(event["kind"] == "query" for episode in case["episodes"][:-1] for event in episode["events"]):
        raise ValueError("query appears before final episode")
    if any(event["kind"] == "write" and event["value"] == case["answer"] for event in case["episodes"][-1]["events"]):
        raise ValueError("answer appears in query episode")


def _ledger_for(case: dict[str, Any]) -> dict[tuple[str, str], list[LedgerEntry]]:
    ledger: dict[tuple[str, str], list[LedgerEntry]] = defaultdict(list)
    for episode in case["episodes"]:
        for event in episode["events"]:
            if event["kind"] != "write":
                continue
            key = (event["entity"], event["field"])
            prior = ledger[key][-1].memory_id if ledger[key] else None
            ledger[key].append(LedgerEntry(event["memory_id"], event["entity"], event["field"], event["value"], episode["index"], prior, episode["index"]))
    return ledger


def ledger_entries(case: dict[str, Any]) -> list[LedgerEntry]:
    return [entry for values in _ledger_for(case).values() for entry in values]


def oracle_answer(case: dict[str, Any]) -> str:
    validate_case(case)
    query = case["episodes"][-1]["events"][0]
    entries = _ledger_for(case).get((query["entity"], query["field"]), [])
    if query["mode"] == "current":
        eligible = entries
    else:
        eligible = [entry for entry in entries if entry.creation_episode <= query["as_of_episode"]]
    if not eligible:
        raise ValueError("query has no ledger answer")
    return eligible[-1].value


def current_episode_only(case: dict[str, Any]) -> str:
    """A control that can inspect only the final query episode, never prior state."""
    validate_case(case)
    final_events = case["episodes"][-1]["events"]
    if len(final_events) != 1 or final_events[0]["kind"] != "query":
        raise ValueError("current-episode control requires a query-only final episode")
    return VALUES[0]


def label_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(case["answer"] for case in cases).items()))
