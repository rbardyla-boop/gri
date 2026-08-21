from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


VALUES = ("RED", "BLUE", "GREEN", "YELLOW", "ORANGE", "PURPLE", "BLACK", "WHITE")
FIELD = "value"
CAPACITY = 16
CASES_PER_CONDITION = 16
RANDOM_CONTROL_SEED = 20260404
HIDDEN_DIM = 49
WORLD0_COMMIT = "1200050d1bbe99a7158e8482dacc534feb48d4c1"
DMC01_COMMIT = "48ae98f"
DMC02A_COMMIT = "f10394d"
DMC03_COMMIT = "489ec45"
DMC01_CHECKPOINT = "artifacts/dmc01/checkpoints/exact_seed1337_final.pt"
DMC01_CHECKPOINT_SHA256 = "4d7dd38a53216b6c010fbfbea27c5e382b572ba229db7fadaf9dd125c99b35a6"

FAMILIES = ("alias", "compositional", "hard_negative", "versioned", "cue_noise")
SPLIT_SPECS: dict[str, dict[str, Any]] = {
    "train": {
        "pair_parity": 0,
        "alias_candidate_counts": (4, 8),
        "versioned_candidate_count": 8,
        "noise_levels": (0, 2),
    },
    "iid": {
        "pair_parity": 0,
        "alias_candidate_counts": (4, 8),
        "versioned_candidate_count": 8,
        "noise_levels": (0, 2),
    },
    "extrapolation": {
        "pair_parity": 1,
        "alias_candidate_counts": (16,),
        "versioned_candidate_count": 16,
        "noise_levels": (8, 32),
    },
}

WRITE_TOKEN_RE = re.compile(r"^write_([AB])_token_([0-7])$")
QUERY_TOKEN_RE = re.compile(r"^query_([AB])_token_([0-7])$")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _opaque_id(*parts: object) -> str:
    return hashlib.sha256(canonical(list(parts)).encode("utf-8")).hexdigest()[:20]


def _pairs(parity: int) -> list[tuple[int, int]]:
    return [(a, b) for a in range(8) for b in range(8) if (a + b) % 2 == parity]


def composition_split() -> dict[str, Any]:
    train = [[a, b] for a, b in _pairs(0)]
    held_out = [[a, b] for a, b in _pairs(1)]
    return {
        "rule": "TRAIN iff (A+B) mod 2 == 0; EXTRAPOLATION iff (A+B) mod 2 == 1",
        "train": train,
        "held_out_composition": held_out,
        "train_atomic_A": list(range(8)),
        "train_atomic_B": list(range(8)),
        "all_train_atoms_seen": True,
    }


def _target_pair(split: str, index: int) -> tuple[int, int]:
    parity = int(SPLIT_SPECS[split]["pair_parity"])
    pairs = _pairs(parity)
    # This sequence covers every atomic value in the first eight cases and
    # remains deterministic for all families and splits.
    preferred = [(a, (a + parity) % 8) for a in range(8)]
    preferred += [(a, (a + 2 + parity) % 8) for a in range(8)]
    preferred = [pair for pair in preferred if (sum(pair) % 2) == parity]
    return preferred[index % len(preferred)] if preferred else pairs[index % len(pairs)]


def _answer(split: str, family: str, condition: str, index: int) -> str:
    # The answer is independent of the logical address.  Thus a query-only
    # observer can decode the address codebook but still has only the class
    # prior for the stored value.
    offset = stable_int("answer-offset", split, family, condition) % len(VALUES)
    return VALUES[(index + offset) % len(VALUES)]


def _write_descriptor(key: tuple[int, int]) -> dict[str, Any]:
    a, b = key
    return {
        "tokens": [f"write_A_token_{a}", f"write_B_token_{b}"],
        "attribute_order": ["A", "B"],
    }


def _query_descriptor(key: tuple[int, int], noise_level: int, *, case_parts: tuple[Any, ...]) -> dict[str, Any]:
    a, b = key
    noise = [f"noise_token_{stable_int('noise', *case_parts, j):016x}" for j in range(noise_level)]
    return {
        "tokens": [f"query_B_token_{b}", f"query_A_token_{a}", *noise],
        "attribute_order": ["B", "A"],
        "noise_token_count": noise_level,
    }


def _hidden_templates() -> dict[str, list[float]]:
    """Return hidden values produced by the frozen DMC-01 exact processor.

    This is intentionally lazy: DMC-04A has no trainable retrieval model, but
    its final-answer oracle uses the already frozen DMC-01 processor.  The
    checkpoint hash is checked before it is loaded.
    """

    root = Path(__file__).resolve().parents[2]
    checkpoint = root / DMC01_CHECKPOINT
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != DMC01_CHECKPOINT_SHA256:
        raise RuntimeError("DMC-04A frozen DMC-01 checkpoint identity mismatch")
    import torch
    from dmc01.memory import build_paired_controllers

    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model, _ = build_paired_controllers(int(payload["seed"]))
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    result: dict[str, list[float]] = {}
    with torch.no_grad():
        for value in VALUES:
            model.reset_case()
            record = model.process_write(
                {"kind": "write", "memory_id": "template", "entity": "template", "field": FIELD, "value": value},
                0,
            )
            result[value] = [float(item) for item in record.hidden_value.tolist()]
    return result


def _record(
    *,
    split: str,
    family: str,
    condition: str,
    case_index: int,
    ordinal: int,
    key: tuple[int, int],
    value: str,
    creation_episode: int,
    version: str,
    hidden_templates: dict[str, list[float]],
) -> dict[str, Any]:
    record_id = "r-" + _opaque_id("DMC04A", split, family, condition, case_index, ordinal, version, key)
    return {
        "record_id": record_id,
        "neural": {
            "write_descriptor": _write_descriptor(key),
            "hidden_value": list(hidden_templates[value]),
            "creation_episode": creation_episode,
        },
        "oracle": {
            "logical_key": [key[0], key[1]],
            "answer": value,
            "creation_episode": creation_episode,
            "version": version,
        },
    }


def _finish(
    *,
    split: str,
    family: str,
    condition: str,
    index: int,
    records: list[dict[str, Any]],
    target_key: tuple[int, int],
    target_record_id: str,
    answer: str,
    mode: str = "current",
    as_of_episode: int | None = None,
    noise_level: int = 0,
) -> dict[str, Any]:
    query = {
        "query_descriptor": _query_descriptor(target_key, noise_level, case_parts=(split, family, condition, index)),
        "mode": mode,
        "as_of_episode": as_of_episode,
    }
    neural_records = [record["neural"] for record in records]
    oracle_records = [
        {"record_id": record["record_id"], **record["oracle"]}
        for record in records
    ]
    case = {
        "case_id": f"dmc04a-{split}-{family}-{condition}-{index:04d}",
        "split": split,
        "family": family,
        "condition": condition,
        "neural_view": {"memory": neural_records, "query": query},
        "oracle_view": {
            "records": oracle_records,
            "target_logical_key": [target_key[0], target_key[1]],
            "target_record_id": target_record_id,
            "answer": answer,
            "mode": mode,
            "as_of_episode": as_of_episode,
        },
        "metadata": {
            "physical_memory_budget": CAPACITY,
            "candidate_count": len(records),
            "noise_level": noise_level,
            "retention_is_perfect": True,
            "logical_key_neural_visibility": False,
        },
    }
    case["content_hash"] = content_hash(case)
    return case


def content_hash(case: dict[str, Any]) -> str:
    payload = {
        key: case[key]
        for key in ("split", "family", "condition", "neural_view", "oracle_view", "metadata")
    }
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _generic_keys(target: tuple[int, int], count: int, parity: int, *, seed_parts: tuple[Any, ...]) -> list[tuple[int, int]]:
    pool = [pair for pair in _pairs(parity) if pair != target]
    pool.sort(key=lambda pair: stable_int("distractor-order", *seed_parts, pair))
    return [target, *pool[: count - 1]]


def _order_records(records: list[dict[str, Any]], target_record_id: str, target_slot: int) -> list[dict[str, Any]]:
    target = next(record for record in records if record["record_id"] == target_record_id)
    rest = [record for record in records if record["record_id"] != target_record_id]
    result: list[dict[str, Any]] = []
    rest_index = 0
    for index in range(len(records)):
        if index == target_slot:
            result.append(target)
        else:
            result.append(rest[rest_index])
            rest_index += 1
    return result


def _make_alias(split: str, count: int, index: int, templates: dict[str, list[float]]) -> dict[str, Any]:
    family, condition = "alias", f"candidate_{count}"
    target = _target_pair(split, index)
    answer = _answer(split, family, condition, index)
    keys = _generic_keys(target, count, int(SPLIT_SPECS[split]["pair_parity"]), seed_parts=(split, family, condition, index))
    records = [
        _record(split=split, family=family, condition=condition, case_index=index, ordinal=ordinal, key=key,
                value=answer if ordinal == 0 else VALUES[stable_int("alias-value", split, condition, index, ordinal) % 8],
                creation_episode=ordinal + 1, version="current", hidden_templates=templates)
        for ordinal, key in enumerate(keys)
    ]
    target_id = records[0]["record_id"]
    records = _order_records(records, target_id, index % count)
    return _finish(split=split, family=family, condition=condition, index=index, records=records,
                   target_key=target, target_record_id=target_id, answer=answer)


def _make_compositional(split: str, index: int, templates: dict[str, list[float]]) -> dict[str, Any]:
    family, condition = "compositional", "candidate_16"
    target = _target_pair(split, index)
    answer = _answer(split, family, condition, index)
    keys = _generic_keys(target, 16, int(SPLIT_SPECS[split]["pair_parity"]), seed_parts=(split, family, index))
    records = [
        _record(split=split, family=family, condition=condition, case_index=index, ordinal=ordinal, key=key,
                value=answer if ordinal == 0 else VALUES[stable_int("composition-value", split, index, ordinal) % 8],
                creation_episode=ordinal + 1, version="current", hidden_templates=templates)
        for ordinal, key in enumerate(keys)
    ]
    target_id = records[0]["record_id"]
    records = _order_records(records, target_id, index % 16)
    return _finish(split=split, family=family, condition=condition, index=index, records=records,
                   target_key=target, target_record_id=target_id, answer=answer)


def _hard_keys(target: tuple[int, int]) -> list[tuple[int, int]]:
    a, b = target
    same_a = [(a, other_b) for other_b in range(8) if other_b != b]
    same_b = [(other_a, b) for other_a in range(8) if other_a != a]
    neither = next((pair for pair in _pairs((a + b + 1) % 2) if pair[0] != a and pair[1] != b), None)
    if neither is None:
        neither = next(pair for pair in [(x, y) for x in range(8) for y in range(8)] if pair[0] != a and pair[1] != b)
    return [target, *same_a, *same_b, neither]


def _make_hard_negative(split: str, index: int, templates: dict[str, list[float]]) -> dict[str, Any]:
    family, condition = "hard_negative", "candidate_16"
    target = _target_pair(split, index)
    answer = _answer(split, family, condition, index)
    keys = _hard_keys(target)
    records = [
        _record(split=split, family=family, condition=condition, case_index=index, ordinal=ordinal, key=key,
                value=answer if ordinal == 0 else VALUES[stable_int("hard-value", split, index, ordinal) % 8],
                creation_episode=ordinal + 1, version="current", hidden_templates=templates)
        for ordinal, key in enumerate(keys)
    ]
    target_id = records[0]["record_id"]
    records = _order_records(records, target_id, index % 16)
    return _finish(split=split, family=family, condition=condition, index=index, records=records,
                   target_key=target, target_record_id=target_id, answer=answer)


def _make_versioned(split: str, mode: str, index: int, templates: dict[str, list[float]]) -> dict[str, Any]:
    family, condition = "versioned", f"{mode}_candidate_{SPLIT_SPECS[split]['versioned_candidate_count']}"
    count = int(SPLIT_SPECS[split]["versioned_candidate_count"])
    target = _target_pair(split, index)
    answer = _answer(split, family, condition, index)
    current_answer = VALUES[(VALUES.index(answer) + 1) % 8]
    target_history = _record(split=split, family=family, condition=condition, case_index=index, ordinal=0, key=target,
                             value=answer, creation_episode=1, version="history", hidden_templates=templates)
    target_current = _record(split=split, family=family, condition=condition, case_index=index, ordinal=1, key=target,
                             value=current_answer, creation_episode=2, version="current", hidden_templates=templates)
    keys = _generic_keys(target, count - 1, int(SPLIT_SPECS[split]["pair_parity"]), seed_parts=(split, family, mode, index))
    distractors = [
        _record(split=split, family=family, condition=condition, case_index=index, ordinal=ordinal + 2, key=key,
                value=VALUES[stable_int("version-value", split, mode, index, ordinal) % 8],
                creation_episode=10 + ordinal, version="current", hidden_templates=templates)
        for ordinal, key in enumerate(keys[1:])
    ]
    target_record = target_current if mode == "current" else target_history
    records = [target_history, target_current, *distractors]
    target_id = target_record["record_id"]
    records = _order_records(records, target_id, index % count)
    target_answer = current_answer if mode == "current" else answer
    return _finish(split=split, family=family, condition=condition, index=index, records=records,
                   target_key=target, target_record_id=target_id, answer=target_answer, mode=mode,
                   as_of_episode=1 if mode == "history" else None)


def _make_noise(split: str, noise_level: int, index: int, templates: dict[str, list[float]]) -> dict[str, Any]:
    family, condition = "cue_noise", f"noise_{noise_level}"
    target = _target_pair(split, index)
    answer = _answer(split, family, condition, index)
    keys = _generic_keys(target, 16, int(SPLIT_SPECS[split]["pair_parity"]), seed_parts=(split, family, noise_level, index))
    records = [
        _record(split=split, family=family, condition=condition, case_index=index, ordinal=ordinal, key=key,
                value=answer if ordinal == 0 else VALUES[stable_int("noise-value", split, noise_level, index, ordinal) % 8],
                creation_episode=ordinal + 1, version="current", hidden_templates=templates)
        for ordinal, key in enumerate(keys)
    ]
    target_id = records[0]["record_id"]
    records = _order_records(records, target_id, index % 16)
    return _finish(split=split, family=family, condition=condition, index=index, records=records,
                   target_key=target, target_record_id=target_id, answer=answer, noise_level=noise_level)


def build_split(split: str) -> list[dict[str, Any]]:
    if split not in SPLIT_SPECS:
        raise ValueError(f"unknown split: {split}")
    templates = _hidden_templates()
    spec = SPLIT_SPECS[split]
    cases: list[dict[str, Any]] = []
    for count in spec["alias_candidate_counts"]:
        cases.extend(_make_alias(split, int(count), index, templates) for index in range(CASES_PER_CONDITION))
    cases.extend(_make_compositional(split, index, templates) for index in range(CASES_PER_CONDITION))
    cases.extend(_make_hard_negative(split, index, templates) for index in range(CASES_PER_CONDITION))
    for mode in ("current", "history"):
        cases.extend(_make_versioned(split, mode, index, templates) for index in range(CASES_PER_CONDITION))
    for noise_level in spec["noise_levels"]:
        cases.extend(_make_noise(split, int(noise_level), index, templates) for index in range(CASES_PER_CONDITION))
    return cases


def build_dataset() -> dict[str, list[dict[str, Any]]]:
    templates = _hidden_templates()
    # Avoid loading the frozen processor three times during a generation.
    original = _hidden_templates
    try:
        globals()["_hidden_templates"] = lambda: templates
        return {split: build_split(split) for split in SPLIT_SPECS}
    finally:
        globals()["_hidden_templates"] = original


def _parse_query_key(case: dict[str, Any]) -> tuple[int, int]:
    tokens = case["neural_view"]["query"]["query_descriptor"]["tokens"]
    found: dict[str, int] = {}
    for token in tokens:
        match = QUERY_TOKEN_RE.match(token)
        if match:
            found[match.group(1)] = int(match.group(2))
    if set(found) != {"A", "B"}:
        raise ValueError("query does not contain exactly one A and B code")
    return found["A"], found["B"]


def _oracle_records(case: dict[str, Any]) -> list[dict[str, Any]]:
    return case["oracle_view"]["records"]


def oracle_retrieval(case: dict[str, Any]) -> str:
    target = tuple(case["oracle_view"]["target_logical_key"])
    mode = case["oracle_view"]["mode"]
    as_of = case["oracle_view"]["as_of_episode"]
    matches = [record for record in _oracle_records(case) if tuple(record["logical_key"]) == target]
    if mode == "history":
        matches = [record for record in matches if record["creation_episode"] <= as_of]
    if not matches:
        raise ValueError("oracle target is absent from candidate set")
    return max(matches, key=lambda record: record["creation_episode"])["record_id"]


def final_answer_from_record(case: dict[str, Any], record_id: str) -> str:
    record = next(record for record in _oracle_records(case) if record["record_id"] == record_id)
    return str(record["answer"])


def _record_index(case: dict[str, Any], record_id: str) -> int:
    for index, record in enumerate(_oracle_records(case)):
        if record["record_id"] == record_id:
            return index
    raise ValueError("record not in candidate set")


def random_retrieval(case: dict[str, Any], seed: int = RANDOM_CONTROL_SEED) -> str:
    records = _oracle_records(case)
    return records[stable_int("DMC04A-random", seed, case["case_id"]) % len(records)]["record_id"]


def exact_token_retrieval(case: dict[str, Any]) -> str:
    query_tokens = set(case["neural_view"]["query"]["query_descriptor"]["tokens"])
    memories = case["neural_view"]["memory"]
    scores = [len(set(memory["write_descriptor"]["tokens"]) & query_tokens) for memory in memories]
    # All codebooks are disjoint, so this is a deterministic tie-broken chance
    # control rather than a hidden address lookup.
    return _oracle_records(case)[max(range(len(scores)), key=lambda index: (scores[index], -index))]["record_id"]


def single_attribute_retrieval(case: dict[str, Any], attribute: str) -> str:
    if attribute not in {"A", "B"}:
        raise ValueError(attribute)
    target = _parse_query_key(case)
    target_value = target[0 if attribute == "A" else 1]
    candidates = []
    for index, record in enumerate(_oracle_records(case)):
        key = tuple(record["logical_key"])
        if key[0 if attribute == "A" else 1] == target_value:
            candidates.append(index)
    if not candidates:
        raise ValueError("single-attribute candidate set is empty")
    return _oracle_records(case)[candidates[0]]["record_id"]


def query_only_answer(case: dict[str, Any]) -> str:
    # RED is a frozen no-information classifier.  Every condition is balanced,
    # so its accuracy is exactly the eight-class prior.
    return VALUES[0]


def _validate_descriptor(descriptor: dict[str, Any], prefix: str) -> None:
    expected_keys = {"tokens", "attribute_order"} if prefix == "write" else {"tokens", "attribute_order", "noise_token_count"}
    if set(descriptor) != expected_keys:
        raise ValueError("malformed address descriptor")
    if descriptor["attribute_order"] != (["A", "B"] if prefix == "write" else ["B", "A"]):
        raise ValueError("wrong descriptor order")
    tokens = descriptor["tokens"]
    if not isinstance(tokens, list) or len(tokens) < 2:
        raise ValueError("address descriptor must contain two code tokens")
    if prefix == "write" and len(tokens) != 2:
        raise ValueError("write descriptor must contain two tokens")
    if prefix == "query":
        if not isinstance(descriptor["noise_token_count"], int) or descriptor["noise_token_count"] < 0 or len(tokens) != 2 + descriptor["noise_token_count"]:
            raise ValueError("query noise metadata mismatch")
        if any(not isinstance(token, str) or not token.startswith("noise_token_") for token in tokens[2:]):
            raise ValueError("malformed query noise token")
    pattern = WRITE_TOKEN_RE if prefix == "write" else QUERY_TOKEN_RE
    parsed = [pattern.match(token) for token in tokens[:2]]
    if any(match is None for match in parsed):
        raise ValueError("wrong codebook token")
    if {match.group(1) for match in parsed} != {"A", "B"}:
        raise ValueError("descriptor must contain A and B once")


def validate_case(case: dict[str, Any]) -> None:
    required = {"case_id", "split", "family", "condition", "neural_view", "oracle_view", "metadata", "content_hash"}
    if set(case) != required or case["split"] not in SPLIT_SPECS or case["family"] not in FAMILIES:
        raise ValueError("malformed DMC-04A case")
    if case["content_hash"] != content_hash(case):
        raise ValueError("content hash mismatch")
    neural = case["neural_view"]
    oracle = case["oracle_view"]
    if set(neural) != {"memory", "query"} or set(oracle) != {"records", "target_logical_key", "target_record_id", "answer", "mode", "as_of_episode"}:
        raise ValueError("malformed neural/oracle projections")
    memories = neural["memory"]
    records = oracle["records"]
    if not 1 <= len(memories) <= CAPACITY or len(memories) != len(records):
        raise ValueError("candidate capacity violation")
    query = neural["query"]
    if set(query) != {"query_descriptor", "mode", "as_of_episode"}:
        raise ValueError("malformed neural query")
    _validate_descriptor(query["query_descriptor"], "query")
    if query["mode"] not in {"current", "history"} or query["mode"] != oracle["mode"]:
        raise ValueError("invalid query mode")
    if query["mode"] == "current" and query["as_of_episode"] is not None:
        raise ValueError("current query exposes history position")
    if query["mode"] == "history" and not isinstance(query["as_of_episode"], int):
        raise ValueError("history query needs as_of_episode")
    if query["as_of_episode"] != oracle["as_of_episode"]:
        raise ValueError("query/oracle version metadata mismatch")
    if tuple(_parse_query_key(case)) != tuple(oracle["target_logical_key"]):
        raise ValueError("query code does not decode to oracle target")
    if oracle["answer"] not in VALUES or oracle["mode"] not in {"current", "history"}:
        raise ValueError("malformed oracle target")
    ids = [record["record_id"] for record in records]
    if len(ids) != len(set(ids)) or oracle["target_record_id"] not in ids:
        raise ValueError("invalid candidate record IDs")
    write_tokens: set[str] = set()
    query_tokens = set(query["query_descriptor"]["tokens"])
    for memory, record in zip(memories, records):
        if set(memory) != {"write_descriptor", "hidden_value", "creation_episode"}:
            raise ValueError("neural memory exposes forbidden metadata")
        _validate_descriptor(memory["write_descriptor"], "write")
        write_tokens.update(memory["write_descriptor"]["tokens"])
        hidden = memory["hidden_value"]
        if not isinstance(hidden, list) or len(hidden) != HIDDEN_DIM or any(not math.isfinite(float(item)) for item in hidden):
            raise ValueError("malformed frozen hidden representation")
        if not isinstance(memory["creation_episode"], int) or memory["creation_episode"] < 0:
            raise ValueError("malformed creation episode")
        if set(record) != {"record_id", "logical_key", "answer", "creation_episode", "version"}:
            raise ValueError("malformed oracle record")
        if not isinstance(record["logical_key"], list) or len(record["logical_key"]) != 2 or any(int(value) not in range(8) for value in record["logical_key"]):
            raise ValueError("malformed logical key")
        if record["answer"] not in VALUES or record["creation_episode"] != memory["creation_episode"]:
            raise ValueError("oracle/neural record mismatch")
        if record["version"] not in {"history", "current"}:
            raise ValueError("malformed version")
        if any(forbidden in memory for forbidden in ("logical_key", "answer", "value", "record_id", "case_id")):
            raise ValueError("oracle information leaked into neural memory")
    if write_tokens & query_tokens:
        raise ValueError("write/query codebooks are not disjoint")
    neural_serialized = canonical(neural)
    if any(forbidden in neural_serialized for forbidden in ("logical_key", '"answer"', '"record_id"', case["case_id"])):
        raise ValueError("neural projection leakage")
    if oracle_retrieval(case) != oracle["target_record_id"]:
        raise ValueError("oracle version semantics invalid")
    if case["metadata"].get("physical_memory_budget") != CAPACITY or case["metadata"].get("candidate_count") != len(records):
        raise ValueError("invalid capacity metadata")
    if case["metadata"].get("noise_level") != query["query_descriptor"]["noise_token_count"]:
        raise ValueError("noise metadata mismatch")


def validate_balance(dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = []
    for (split, family, condition), cases in _groups(dataset).items():
        counts = Counter(case["oracle_view"]["answer"] for case in cases)
        rows.append({"split": split, "family": family, "condition": condition, "case_count": len(cases), "counts": dict(sorted(counts.items())), "balanced": counts == Counter({value: 2 for value in VALUES})})
    return {"pass": all(row["balanced"] for row in rows), "rows": sorted(rows, key=lambda row: (row["split"], row["family"], row["condition"]))}


def _groups(dataset: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for split, cases in dataset.items():
        for case in cases:
            groups[(split, case["family"], case["condition"])].append(case)
    return groups


def score(cases: list[dict[str, Any]], selector: Callable[[dict[str, Any]], str]) -> float:
    return sum(selector(case) == oracle_retrieval(case) for case in cases) / len(cases)


def answer_score(cases: list[dict[str, Any]], selector: Callable[[dict[str, Any]], str]) -> float:
    return sum(final_answer_from_record(case, selector(case)) == case["oracle_view"]["answer"] for case in cases) / len(cases)


def primary_retrieval(cases: list[dict[str, Any]], selector: Callable[[dict[str, Any]], str]) -> dict[str, float]:
    groups = _groups({"extrapolation": cases})
    components = {
        "ALIAS16_H1": score(groups[("extrapolation", "alias", "candidate_16")], selector),
        "COMP16_H1": score(groups[("extrapolation", "compositional", "candidate_16")], selector),
        "HARD16_H1": score(groups[("extrapolation", "hard_negative", "candidate_16")], selector),
        "CURRENT16_H1": score(groups[("extrapolation", "versioned", "current_candidate_16")], selector),
        "HISTORY16_H1": score(groups[("extrapolation", "versioned", "history_candidate_16")], selector),
        "NOISE8_H1": score(groups[("extrapolation", "cue_noise", "noise_8")], selector),
        "NOISE32_H1": score(groups[("extrapolation", "cue_noise", "noise_32")], selector),
    }
    components["P_retrieval"] = sum(components.values()) / len(components)
    return components


def primary_answer(cases: list[dict[str, Any]], selector: Callable[[dict[str, Any]], str]) -> dict[str, float]:
    groups = _groups({"extrapolation": cases})
    components = {
        "ALIAS16_A": answer_score(groups[("extrapolation", "alias", "candidate_16")], selector),
        "COMP16_A": answer_score(groups[("extrapolation", "compositional", "candidate_16")], selector),
        "HARD16_A": answer_score(groups[("extrapolation", "hard_negative", "candidate_16")], selector),
        "CURRENT16_A": answer_score(groups[("extrapolation", "versioned", "current_candidate_16")], selector),
        "HISTORY16_A": answer_score(groups[("extrapolation", "versioned", "history_candidate_16")], selector),
        "NOISE8_A": answer_score(groups[("extrapolation", "cue_noise", "noise_8")], selector),
        "NOISE32_A": answer_score(groups[("extrapolation", "cue_noise", "noise_32")], selector),
    }
    components["P_answer"] = sum(components.values()) / len(components)
    return components
