from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable


VALUES = ("RED", "BLUE", "GREEN", "YELLOW", "ORANGE", "PURPLE", "BLACK", "WHITE")
FIELD = "value"
CAPACITY = 16
CASES_PER_CONDITION = 16
RANDOM_CONTROL_SEED = 20260202

FAMILIES = ("mission_set", "salience", "supersession", "utility_change", "distractor_flood")

# The split allocation is part of the DMC-02A contract.  The 25% and 75%
# utility shifts are held out from training and appear only in extrapolation.
SPLIT_SPECS = {
    "train": {
        "mission_set_loads": (32, 64),
        "salience_loads": (32, 64),
        "supersession_loads": (32, 64),
        "utility_loads": (32, 64),
        "utility_overlaps": (0, 50, 100),
        "flood_distractors": (0, 32),
    },
    "iid": {
        "mission_set_loads": (32, 64),
        "salience_loads": (32, 64),
        "supersession_loads": (32, 64),
        "utility_loads": (32, 64),
        "utility_overlaps": (0, 50, 100),
        "flood_distractors": (0, 32),
    },
    "extrapolation": {
        "mission_set_loads": (128, 256, 1024),
        "salience_loads": (128, 256, 1024),
        "supersession_loads": (128, 256, 1024),
        "utility_loads": (128, 256, 1024),
        "utility_overlaps": (0, 25, 50, 75, 100),
        "flood_distractors": (128, 512, 1024),
    },
}


@dataclass(frozen=True)
class StoredRecord:
    memory_id: str
    entity: str
    field: str
    value: str
    creation_episode: int
    supersedes: str | None
    salience: str | None


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _opaque_id(*parts: object) -> str:
    return hashlib.sha256(canonical(list(parts)).encode("utf-8")).hexdigest()[:20]


def content_hash(case: dict[str, Any]) -> str:
    # The answer is deliberately excluded.  A dataset hash authenticates the
    # generated exam, not a hidden oracle label appended after generation.
    payload = {key: case[key] for key in ("family", "condition", "episodes", "query", "metadata")}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _target_value(split: str, family: str, condition: str, case_index: int, variant: str = "") -> str:
    offset = stable_int("answer-offset", split, family, condition, variant) % len(VALUES)
    return VALUES[(case_index + offset) % len(VALUES)]


def _filler_value(split: str, family: str, condition: str, case_index: int, slot: int, variant: str = "") -> str:
    return VALUES[stable_int("filler", split, family, condition, case_index, slot, variant) % len(VALUES)]


def _memory_id(split: str, family: str, condition: str, case_index: int, ordinal: int) -> str:
    return "m-" + _opaque_id("DMC02A", split, family, condition, case_index, ordinal)


def _write_event(
    memory_id: str,
    entity: str,
    value: str,
    *,
    salience: str | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "write",
        "memory_id": memory_id,
        "entity": entity,
        "field": FIELD,
        "value": value,
        "salience": salience,
        "supersedes": supersedes,
    }


def _mission_set_event(entities: list[str]) -> dict[str, Any]:
    return {"kind": "mission_set", "entities": list(entities)}


def _mission_update_event(entities: list[str]) -> dict[str, Any]:
    return {"kind": "mission_update", "entities": list(entities)}


def _query_event(entity: str, *, mode: str = "current", as_of_episode: int | None = None) -> dict[str, Any]:
    return {"kind": "query", "entity": entity, "field": FIELD, "mode": mode, "as_of_episode": as_of_episode}


def _episodes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"index": index, "events": [event]} for index, event in enumerate(events)]


def _case_id(split: str, family: str, condition: str, index: int) -> str:
    return f"dmc02a-{split}-{family}-{condition}-{index:04d}"


def _finish(
    split: str,
    family: str,
    condition: str,
    index: int,
    events: list[dict[str, Any]],
    query: dict[str, Any],
    answer: str,
    *,
    load: int,
    query_eligible_records: int,
    minimum_required_records: int,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = {
        "physical_memory_budget": CAPACITY,
        "total_writes": sum(event["kind"] == "write" for event in events),
        "query_eligible_records": query_eligible_records,
        "minimum_required_records": minimum_required_records,
        "load": load,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    case = {
        "case_id": _case_id(split, family, condition, index),
        "split": split,
        "family": family,
        "condition": condition,
        "episodes": _episodes([*events, query]),
        "query": dict(query),
        "answer": answer,
        "metadata": metadata,
    }
    case["content_hash"] = content_hash(case)
    return case


def _make_mission_set(split: str, load: int, index: int) -> dict[str, Any]:
    family, condition = "mission_set", f"load_{load}"
    entities = [f"mission-entity-{slot:02d}" for slot in range(16)]
    target_slot = index % 16
    answer = _target_value(split, family, condition, index)
    events: list[dict[str, Any]] = [_mission_set_event(entities)]
    for slot, entity in enumerate(entities):
        value = answer if slot == target_slot else _filler_value(split, family, condition, index, slot)
        events.append(_write_event(_memory_id(split, family, condition, index, slot), entity, value))
    for slot in range(16, load):
        entity = f"mission-distractor-{slot:04d}"
        events.append(_write_event(_memory_id(split, family, condition, index, slot), entity, _filler_value(split, family, condition, index, slot)))
    query = _query_event(entities[target_slot])
    return _finish(split, family, condition, index, events, query, answer, load=load, query_eligible_records=16, minimum_required_records=16)


def _make_salience(split: str, load: int, index: int) -> dict[str, Any]:
    family, condition = "salience", f"load_{load}"
    target_slot = index % 16
    answer = _target_value(split, family, condition, index)
    events: list[dict[str, Any]] = []
    for slot in range(load):
        high = slot < 16
        entity = f"salience-entity-{slot:04d}"
        value = answer if high and slot == target_slot else _filler_value(split, family, condition, index, slot)
        events.append(_write_event(_memory_id(split, family, condition, index, slot), entity, value, salience="HIGH" if high else "LOW"))
    query = _query_event(f"salience-entity-{target_slot:04d}")
    return _finish(split, family, condition, index, events, query, answer, load=load, query_eligible_records=16, minimum_required_records=16)


def _make_supersession(split: str, load: int, mode: str, index: int) -> dict[str, Any]:
    family, condition = "supersession", f"load_{load}_{mode}"
    entities = [f"supersession-entity-{slot:02d}" for slot in range(8)]
    target_slot = index % 8
    original_answer = _target_value(split, family, condition, index, "original")
    current_answer = VALUES[(VALUES.index(original_answer) + 1) % len(VALUES)]
    answer = current_answer if mode == "current" else original_answer
    events: list[dict[str, Any]] = [_mission_set_event(entities)]
    ordinal = 0
    target_original_episode = None
    for slot, entity in enumerate(entities):
        original_id = _memory_id(split, family, condition, index, ordinal)
        original_value = original_answer if slot == target_slot else _filler_value(split, family, condition, index, slot, "original")
        events.append(_write_event(original_id, entity, original_value))
        if slot == target_slot:
            target_original_episode = len(events) - 1
        ordinal += 1
        current_id = _memory_id(split, family, condition, index, ordinal)
        current_value = current_answer if slot == target_slot else VALUES[(_value_index(_filler_value(split, family, condition, index, slot, "current")) + 1) % len(VALUES)]
        events.append(_write_event(current_id, entity, current_value, supersedes=original_id))
        ordinal += 1
    for slot in range(16, load):
        entity = f"supersession-distractor-{slot:04d}"
        events.append(_write_event(_memory_id(split, family, condition, index, ordinal), entity, _filler_value(split, family, condition, index, slot)))
        ordinal += 1
    if target_original_episode is None:
        raise AssertionError("target original episode missing")
    query = _query_event(entities[target_slot], mode=mode, as_of_episode=target_original_episode if mode == "history" else None)
    return _finish(
        split,
        family,
        condition,
        index,
        events,
        query,
        answer,
        load=load,
        query_eligible_records=16,
        minimum_required_records=16,
        extra_metadata={"mission_entity_count": 8, "query_mode": mode},
    )


def _value_index(value: str) -> int:
    return VALUES.index(value)


def _make_utility_change(split: str, load: int, overlap: int, index: int) -> dict[str, Any]:
    family, condition = "utility_change", f"load_{load}_overlap_{overlap}"
    a_entities = [f"utility-a-entity-{slot:02d}" for slot in range(16)]
    b_entities = a_entities[: overlap * 16 // 100] + [f"utility-b-entity-{slot:02d}" for slot in range(16 - overlap * 16 // 100)]
    target_slot = index % 16
    answer = _target_value(split, family, condition, index)
    events: list[dict[str, Any]] = [_mission_set_event(a_entities)]
    ordinal = 0
    for slot, entity in enumerate(a_entities):
        events.append(_write_event(_memory_id(split, family, condition, index, ordinal), entity, _filler_value(split, family, condition, index, slot, "phase_a")))
        ordinal += 1
    extra = load - 32
    before_update = extra // 2
    after_update = extra - before_update
    for slot in range(before_update):
        entity = f"utility-pre-distractor-{slot:04d}"
        events.append(_write_event(_memory_id(split, family, condition, index, ordinal), entity, _filler_value(split, family, condition, index, ordinal, "pre")))
        ordinal += 1
    events.append(_mission_update_event(b_entities))
    for slot, entity in enumerate(b_entities):
        value = answer if slot == target_slot else _filler_value(split, family, condition, index, slot, "phase_b")
        events.append(_write_event(_memory_id(split, family, condition, index, ordinal), entity, value))
        ordinal += 1
    for slot in range(after_update):
        entity = f"utility-post-distractor-{slot:04d}"
        events.append(_write_event(_memory_id(split, family, condition, index, ordinal), entity, _filler_value(split, family, condition, index, ordinal, "post")))
        ordinal += 1
    query = _query_event(b_entities[target_slot])
    return _finish(
        split,
        family,
        condition,
        index,
        events,
        query,
        answer,
        load=load,
        query_eligible_records=16,
        minimum_required_records=16,
        extra_metadata={"phase_a_mission_count": 16, "phase_b_mission_count": 16, "overlap_percent": overlap},
    )


def _make_distractor_flood(split: str, distractors: int, index: int) -> dict[str, Any]:
    family, condition = "distractor_flood", f"distractors_{distractors}"
    target_slot = index % 16
    answer = _target_value(split, family, condition, index)
    events: list[dict[str, Any]] = []
    for slot in range(16):
        entity = f"flood-entity-{slot:02d}"
        value = answer if slot == target_slot else _filler_value(split, family, condition, index, slot, "relevant")
        events.append(_write_event(_memory_id(split, family, condition, index, slot), entity, value, salience="HIGH"))
    for slot in range(distractors):
        entity = f"flood-distractor-{slot:04d}"
        ordinal = 16 + slot
        events.append(_write_event(_memory_id(split, family, condition, index, ordinal), entity, _filler_value(split, family, condition, index, ordinal, "distractor"), salience="LOW"))
    query = _query_event(f"flood-entity-{target_slot:02d}")
    return _finish(split, family, condition, index, events, query, answer, load=distractors, query_eligible_records=16, minimum_required_records=16, extra_metadata={"relevant_records": 16, "irrelevant_writes": distractors})


def build_split(split: str) -> list[dict[str, Any]]:
    if split not in SPLIT_SPECS:
        raise ValueError(f"unknown split: {split}")
    spec = SPLIT_SPECS[split]
    cases: list[dict[str, Any]] = []
    for load in spec["mission_set_loads"]:
        cases.extend(_make_mission_set(split, load, index) for index in range(CASES_PER_CONDITION))
    for load in spec["salience_loads"]:
        cases.extend(_make_salience(split, load, index) for index in range(CASES_PER_CONDITION))
    for load in spec["supersession_loads"]:
        for mode in ("current", "history"):
            cases.extend(_make_supersession(split, load, mode, index) for index in range(CASES_PER_CONDITION))
    for load in spec["utility_loads"]:
        for overlap in spec["utility_overlaps"]:
            cases.extend(_make_utility_change(split, load, overlap, index) for index in range(CASES_PER_CONDITION))
    for distractors in spec["flood_distractors"]:
        cases.extend(_make_distractor_flood(split, distractors, index) for index in range(CASES_PER_CONDITION))
    return cases


def build_dataset() -> dict[str, list[dict[str, Any]]]:
    return {split: build_split(split) for split in SPLIT_SPECS}


def _validate_event(event: dict[str, Any]) -> None:
    kind = event.get("kind")
    if kind == "write":
        required = {"kind", "memory_id", "entity", "field", "value", "salience", "supersedes"}
        if set(event) != required or event["field"] != FIELD or event["value"] not in VALUES or not isinstance(event["memory_id"], str):
            raise ValueError("malformed write event")
        if event["salience"] not in {None, "HIGH", "LOW"} or (event["supersedes"] is not None and not isinstance(event["supersedes"], str)):
            raise ValueError("malformed write metadata")
    elif kind in {"mission_set", "mission_update"}:
        if set(event) != {"kind", "entities"} or not isinstance(event["entities"], list) or not event["entities"] or len(set(event["entities"])) != len(event["entities"]):
            raise ValueError("malformed mission scope event")
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


def _writes(case: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [(episode["index"], event) for episode in case["episodes"] for event in episode["events"] if event["kind"] == "write"]


def _scope_events(case: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [event for episode in case["episodes"] for event in episode["events"] if event["kind"] == kind]


def validate_case(case: dict[str, Any]) -> None:
    required = {"case_id", "split", "family", "condition", "episodes", "query", "answer", "metadata", "content_hash"}
    if set(case) != required or case["split"] not in SPLIT_SPECS or case["family"] not in FAMILIES or case["answer"] not in VALUES:
        raise ValueError("malformed case")
    if case["content_hash"] != content_hash(case):
        raise ValueError("content hash mismatch")
    if not isinstance(case["metadata"], dict) or case["metadata"].get("physical_memory_budget") != CAPACITY:
        raise ValueError("invalid capacity metadata")
    episodes = case["episodes"]
    if not episodes or episodes[-1]["events"] != [episodes[-1]["events"][0]] or episodes[-1]["events"][0].get("kind") != "query":
        raise ValueError("final episode must contain exactly one query")
    for expected_index, episode in enumerate(episodes):
        if set(episode) != {"index", "events"} or episode["index"] != expected_index or len(episode["events"]) != 1:
            raise ValueError("malformed episode")
        _validate_event(episode["events"][0])
    query_event = episodes[-1]["events"][0]
    if case["query"] != query_event:
        raise ValueError("query metadata mismatch")
    if any(episode["events"][0]["kind"] == "query" for episode in episodes[:-1]):
        raise ValueError("query appears before final episode")
    if "value" in query_event or "answer" in query_event or "memory_id" in query_event or case["case_id"] in canonical(episodes[-1]):
        raise ValueError("answer or case identity leaked into final query")
    writes = _writes(case)
    if len(writes) != case["metadata"].get("total_writes") or len(writes) < 16:
        raise ValueError("invalid write count")
    if case["metadata"].get("minimum_required_records", CAPACITY + 1) > CAPACITY:
        raise ValueError("case requires more than physical capacity")
    memory_ids = [event["memory_id"] for _, event in writes]
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError("duplicate memory id")
    by_family = {
        "mission_set": _validate_mission_family,
        "salience": _validate_salience_family,
        "supersession": _validate_supersession_family,
        "utility_change": _validate_utility_family,
        "distractor_flood": _validate_flood_family,
    }
    by_family[case["family"]](case, writes)


def _validate_mission_family(case: dict[str, Any], writes: list[tuple[int, dict[str, Any]]]) -> None:
    scopes = _scope_events(case, "mission_set")
    if len(scopes) != 1 or len(scopes[0]["entities"]) != 16:
        raise ValueError("mission family requires exactly 16 mission entities")
    mission = set(scopes[0]["entities"])
    mission_writes = [event for _, event in writes if event["entity"] in mission]
    if len(mission_writes) != 16 or case["query"]["entity"] not in mission:
        raise ValueError("invalid mission family writes")


def _validate_salience_family(case: dict[str, Any], writes: list[tuple[int, dict[str, Any]]]) -> None:
    high = [event for _, event in writes if event["salience"] == "HIGH"]
    if len(high) != 16 or case["query"]["entity"] not in {event["entity"] for event in high} or any(event["salience"] != "LOW" for _, event in writes if event not in high):
        raise ValueError("invalid salience family")


def _validate_supersession_family(case: dict[str, Any], writes: list[tuple[int, dict[str, Any]]]) -> None:
    scopes = _scope_events(case, "mission_set")
    if len(scopes) != 1 or len(scopes[0]["entities"]) != 8:
        raise ValueError("supersession requires eight mission entities")
    mission = set(scopes[0]["entities"])
    relevant = [event for _, event in writes if event["entity"] in mission]
    originals = [event for event in relevant if event["supersedes"] is None]
    currents = [event for event in relevant if event["supersedes"] is not None]
    if len(relevant) != 16 or len(originals) != 8 or len(currents) != 8:
        raise ValueError("supersession records are incomplete")
    original_ids = {event["memory_id"] for event in originals}
    if {event["supersedes"] for event in currents} != original_ids:
        raise ValueError("supersession provenance mismatch")
    if case["query"]["entity"] not in mission:
        raise ValueError("supersession query outside mission")


def _validate_utility_family(case: dict[str, Any], writes: list[tuple[int, dict[str, Any]]]) -> None:
    initial = _scope_events(case, "mission_set")
    updates = _scope_events(case, "mission_update")
    if len(initial) != 1 or len(updates) != 1 or len(initial[0]["entities"]) != 16 or len(updates[0]["entities"]) != 16:
        raise ValueError("utility change requires two 16-key scopes")
    if case["metadata"].get("overlap_percent") != round(100 * len(set(initial[0]["entities"]) & set(updates[0]["entities"])) / 16):
        raise ValueError("utility overlap mismatch")
    update_episode = next(index for index, episode in enumerate(case["episodes"]) if episode["events"][0]["kind"] == "mission_update")
    first_b_write = next(index for index, event in writes if index > update_episode and event["entity"] in set(updates[0]["entities"]))
    if first_b_write <= update_episode or case["query"]["entity"] not in set(updates[0]["entities"]):
        raise ValueError("utility update ordering invalid")


def _validate_flood_family(case: dict[str, Any], writes: list[tuple[int, dict[str, Any]]]) -> None:
    high = [event for _, event in writes if event["salience"] == "HIGH"]
    low = [event for _, event in writes if event["salience"] == "LOW"]
    if len(high) != 16 or len(low) != case["metadata"].get("irrelevant_writes") or case["query"]["entity"] not in {event["entity"] for event in high}:
        raise ValueError("invalid distractor flood")


def _records_from_events(case: dict[str, Any]) -> list[StoredRecord]:
    records: list[StoredRecord] = []
    for episode_index, event in _writes(case):
        records.append(StoredRecord(event["memory_id"], event["entity"], event["field"], event["value"], episode_index, event["supersedes"], event["salience"]))
    return records


def _answer_from_records(records: Iterable[StoredRecord], query: dict[str, Any]) -> str | None:
    eligible = [record for record in records if record.entity == query["entity"] and record.field == query["field"]]
    if query["mode"] == "history":
        eligible = [record for record in eligible if record.creation_episode <= query["as_of_episode"]]
    if not eligible:
        return None
    return max(eligible, key=lambda record: record.creation_episode).value


def unbounded_oracle(case: dict[str, Any]) -> str:
    validate_case(case)
    answer = _answer_from_records(_records_from_events(case), case["query"])
    if answer is None:
        raise ValueError("unbounded oracle found no answer")
    return answer


def current_episode_only(case: dict[str, Any]) -> str:
    validate_case(case)
    if case["episodes"][-1]["events"] != [case["episodes"][-1]["events"][0]]:
        raise ValueError("query episode is not query-only")
    return VALUES[0]


def _bounded_admission(case: dict[str, Any], event: dict[str, Any], active_scope: set[str] | None) -> bool:
    family = case["family"]
    if family in {"mission_set", "supersession", "utility_change"}:
        return active_scope is not None and event["entity"] in active_scope
    if family in {"salience", "distractor_flood"}:
        return event["salience"] == "HIGH"
    raise ValueError(f"unknown family: {family}")


def _bounded_run(case: dict[str, Any]) -> tuple[str | None, int]:
    validate_case(case)
    store: list[StoredRecord] = []
    peak = 0
    active_scope: set[str] | None = None
    for episode_index, event in _writes_and_controls(case):
        if event["kind"] == "mission_set":
            active_scope = set(event["entities"])
        elif event["kind"] == "mission_update":
            active_scope = set(event["entities"])
            store = [record for record in store if record.entity in active_scope]
        elif event["kind"] == "write":
            record = StoredRecord(event["memory_id"], event["entity"], event["field"], event["value"], episode_index, event["supersedes"], event["salience"])
            if _bounded_admission(case, event, active_scope):
                if case["family"] == "utility_change":
                    store = [old for old in store if old.entity != record.entity]
                store.append(record)
                if len(store) > CAPACITY:
                    raise AssertionError("bounded oracle exceeded physical capacity")
                peak = max(peak, len(store))
    answer = _answer_from_records(store, case["query"])
    return answer, peak


def bounded_oracle(case: dict[str, Any]) -> str:
    answer, _ = _bounded_run(case)
    if answer is None:
        raise ValueError("bounded oracle could not solve a valid case")
    return answer


def bounded_peak_records(case: dict[str, Any]) -> int:
    _, peak = _bounded_run(case)
    return peak


def _writes_and_controls(case: dict[str, Any]) -> Iterable[tuple[int, dict[str, Any]]]:
    for episode in case["episodes"][:-1]:
        event = episode["events"][0]
        yield episode["index"], event


def fifo_control(case: dict[str, Any]) -> str | None:
    validate_case(case)
    store: list[StoredRecord] = []
    for episode_index, event in _writes_and_controls(case):
        if event["kind"] != "write":
            continue
        store.append(StoredRecord(event["memory_id"], event["entity"], event["field"], event["value"], episode_index, event["supersedes"], event["salience"]))
        if len(store) > CAPACITY:
            store.pop(0)
    return _answer_from_records(store, case["query"])


def random_retention_control(case: dict[str, Any], seed: int = RANDOM_CONTROL_SEED) -> str | None:
    validate_case(case)
    store: list[StoredRecord] = []
    seen = 0
    for episode_index, event in _writes_and_controls(case):
        if event["kind"] != "write":
            continue
        seen += 1
        record = StoredRecord(event["memory_id"], event["entity"], event["field"], event["value"], episode_index, event["supersedes"], event["salience"])
        if len(store) < CAPACITY:
            store.append(record)
            continue
        slot_draw = stable_int("DMC02A-random-reservoir", seed, case["case_id"], seen, event["memory_id"])
        if slot_draw % seen < CAPACITY:
            slot = stable_int("DMC02A-random-slot", seed, case["case_id"], seen, event["memory_id"]) % CAPACITY
            store[slot] = record
    return _answer_from_records(store, case["query"])


def evaluate_cases(cases: list[dict[str, Any]], answerer: Callable[[dict[str, Any]], str | None | str]) -> dict[str, Any]:
    rows = []
    correct = 0
    for case in cases:
        answer = answerer(case)
        hit = answer == case["answer"]
        correct += hit
        rows.append({"case_id": case["case_id"], "predicted": answer, "answer": case["answer"], "correct": hit})
    return {"cases": len(cases), "correct": correct, "accuracy": correct / len(cases), "rows": rows}


def label_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(case["answer"] for case in cases).items()))
