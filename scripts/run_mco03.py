#!/usr/bin/env python3
from __future__ import annotations

"""MCO-03 relation-boundary repair and state-compiler verification harness."""

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_mco02 as mco02  # noqa: E402


EXPERIMENT_ROOT = ROOT / "experiments/mco03"
OUT = ROOT / "artifacts/mco03"
ENGINEERING_ROOT = OUT / "engineering"
CONFIG_PATH = EXPERIMENT_ROOT / "MCO03_CONFIG.json"
CONTRACT_PATH = EXPERIMENT_ROOT / "MCO03_CONTRACT.md"
FREEZE_PATH = EXPERIMENT_ROOT / "MCO03_FREEZE.json"
SCIENTIFIC_ROOT = OUT / "scientific"
LEARNED_ROOT = SCIENTIFIC_ROOT / "learned"
TRANSPARENT_ROOT = SCIENTIFIC_ROOT / "transparent"
REPLAY_ROOT = SCIENTIFIC_ROOT / "replay"
MODEL_CALL_ROOT = SCIENTIFIC_ROOT / "model_calls"
EMBEDDING_ROOT = SCIENTIFIC_ROOT / "embeddings"

MODEL_SEED = 20260822
PRIMARY_MODEL = "llama3.1:8b"
PRIMARY_MODEL_BLOB_SHA256 = mco02.MODEL_BLOB_SHA256
FALLBACK_MODEL = "stateforge-gemma12b"
FALLBACK_MODEL_BLOB_SHA256 = (
    "e8ad13eff07a78d89926e9e8b882317d082ef5bf9768ad7b50fcdbbcd63748de"
)
ENGINEERING_SEED = 2701
ENGINEERING_RECORDS = 120
BATCH_SIZE = 12
CONTEXT_LIMIT = 8192
ALLOWED_RELATIONS = mco02.ALLOWED_RELATIONS
EMBEDDING_MODEL = "embeddinggemma:300m"
EMBEDDING_MODEL_BLOB_SHA256 = (
    "0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515"
)
EMBEDDING_BATCH_SIZE = 256
RAG_CAPACITY = 16

KEYED_SYSTEM_PROMPT = (
    "Classify the semantic relationship expressed by every input sentence. Choose "
    "depends_on when one entity relies on, draws on, cannot proceed without, or has "
    "another entity as an upstream or supporting requirement. Choose renamed_to when an "
    "old entity label is replaced by a new entity name or designation. Choose "
    "failure_threshold when the sentence gives a failure, safety-floor, minimum-safe-"
    "temperature, or not-rated-below temperature for one entity. Every sentence is "
    "identified by an opaque record ID. Return exactly one relation under each supplied "
    "record-ID key. Match by record ID, never by output-array position."
)

SINGLE_SYSTEM_PROMPT = (
    "Classify the one supplied sentence as exactly one of depends_on, renamed_to, or "
    "failure_threshold. depends_on means reliance or an upstream/supporting requirement; "
    "renamed_to means replacement by a new name or designation; failure_threshold means "
    "a failure temperature, safety floor, minimum safe temperature, or not-rated-below "
    "temperature. Return only the required JSON object."
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def chunks(values: Sequence[Any], size: int) -> Iterable[tuple[int, Sequence[Any]]]:
    for start in range(0, len(values), size):
        yield start, values[start : start + size]


class FrozenModelClient:
    """Content-addressed Ollama client with replayable raw request/response receipts."""

    def __init__(
        self,
        *,
        model_name: str,
        cache_root: Path,
        mode: str = "live",
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        if mode not in {"live", "replay"}:
            raise ValueError(f"invalid mode: {mode}")
        self.model_name = model_name
        self.cache_root = cache_root
        self.mode = mode
        self.base_url = base_url.rstrip("/")
        self.used_call_ids: list[str] = []

    def cache_path(self, purpose: str, call_id: str) -> Path:
        return self.cache_root / purpose / f"{call_id}.json"

    def call(
        self,
        *,
        purpose: str,
        key: str,
        messages: Sequence[dict[str, str]],
        num_ctx: int,
        num_predict: int,
        format_spec: str | dict[str, Any] | None = None,
        stop: Sequence[str] | None = None,
        force_live_repeat: bool = False,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": 0,
            "seed": MODEL_SEED,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        }
        if stop:
            options["stop"] = list(stop)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": list(messages),
            "stream": False,
            "keep_alive": "30m",
            "options": options,
        }
        if format_spec is not None:
            payload["format"] = format_spec
        request_sha256 = digest(payload)
        safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "-", key)[:100]
        call_id = f"{safe_key}__{request_sha256[:16]}"
        path = self.cache_path(purpose, call_id)
        qualified = f"{purpose}/{call_id}"
        self.used_call_ids.append(qualified)
        if path.exists() and not force_live_repeat:
            cached = read_json(path)
            if cached.get("request_sha256") != request_sha256:
                raise RuntimeError(f"cache request mismatch: {path}")
            return {**cached, "cache_hit": True}
        if self.mode == "replay" and not force_live_repeat:
            raise FileNotFoundError(path)

        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                raw = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Ollama call failed for {qualified}: {exc}") from exc
        wall = time.perf_counter() - started
        content = str(raw.get("message", {}).get("content", ""))
        record = {
            "schema_version": 1,
            "model": self.model_name,
            "purpose": purpose,
            "key": key,
            "call_id": call_id,
            "request_sha256": request_sha256,
            "request": payload,
            "response": raw,
            "response_content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "accounting": {
                "prompt_eval_count": int(raw.get("prompt_eval_count", 0)),
                "eval_count": int(raw.get("eval_count", 0)),
                "prompt_eval_duration_ns": int(raw.get("prompt_eval_duration", 0)),
                "eval_duration_ns": int(raw.get("eval_duration", 0)),
                "load_duration_ns": int(raw.get("load_duration", 0)),
                "total_duration_ns": int(raw.get("total_duration", 0)),
                "wall_time_seconds": wall,
            },
            "cache_hit": False,
        }
        write_json(path, record)
        return record

    def resolve(self, qualified_call_id: str) -> dict[str, Any]:
        purpose, call_id = qualified_call_id.split("/", 1)
        return read_json(self.cache_path(purpose, call_id))


def usage_for_calls(client: FrozenModelClient, call_ids: Sequence[str]) -> dict[str, Any]:
    unique = list(dict.fromkeys(call_ids))
    records = [client.resolve(call_id) for call_id in unique]
    return {
        "model_calls": len(records),
        "input_tokens": sum(int(row["accounting"]["prompt_eval_count"]) for row in records),
        "output_tokens": sum(int(row["accounting"]["eval_count"]) for row in records),
        "wall_time_seconds": sum(float(row["accounting"]["wall_time_seconds"]) for row in records),
        "expensive_token_units": sum(
            int(row["accounting"]["prompt_eval_count"])
            + 4 * int(row["accounting"]["eval_count"])
            for row in records
        ),
        "call_ids": unique,
    }


def model_identity(model_name: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/show",
        data=json.dumps({"model": model_name}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        show = json.load(response)
    modelfile = str(show.get("modelfile", ""))
    match = re.search(r"sha256-([0-9a-f]{64})", modelfile)
    return {
        "model": model_name,
        "blob_sha256": match.group(1) if match else None,
        "details": show.get("details", {}),
        "capabilities": show.get("capabilities", []),
        "parameters": show.get("parameters", ""),
    }


def keyed_schema(record_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            record_id: {"type": "string", "enum": list(ALLOWED_RELATIONS)}
            for record_id in record_ids
        },
        "required": list(record_ids),
        "additionalProperties": False,
    }


def single_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "relation": {"type": "string", "enum": list(ALLOWED_RELATIONS)}
        },
        "required": ["relation"],
        "additionalProperties": False,
    }


def parse_keyed(content: str, record_ids: Sequence[str]) -> dict[str, str] | None:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    expected = set(record_ids)
    if (
        not isinstance(parsed, dict)
        or set(parsed) != expected
        or any(value not in ALLOWED_RELATIONS for value in parsed.values())
    ):
        return None
    return {record_id: str(parsed[record_id]) for record_id in record_ids}


def parse_single(content: str) -> str | None:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if (
        not isinstance(parsed, dict)
        or set(parsed) != {"relation"}
        or parsed["relation"] not in ALLOWED_RELATIONS
    ):
        return None
    return str(parsed["relation"])


def keyed_prompt(rows: Sequence[dict[str, Any]]) -> str:
    return "\n".join(
        f"{row['record_id']}: {mco02.semantic_clause(str(row['text']))}" for row in rows
    )


def single_prompt(row: dict[str, Any]) -> str:
    return (
        f"Record ID: {row['record_id']}\n"
        f"Sentence: {mco02.semantic_clause(str(row['text']))}"
    )


def _template_pattern(template: str, *, object_is_integer: bool) -> re.Pattern[str]:
    escaped = re.escape(template)
    escaped = escaped.replace(re.escape("{subject}"), r"[ed]_[0-9a-f]{16}")
    object_pattern = r"-?[0-9]+" if object_is_integer else r"[ed]_[0-9a-f]{16}"
    escaped = escaped.replace(re.escape("{object}"), object_pattern)
    return re.compile(f"^{escaped}$")


TRANSPARENT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "depends_on": tuple(
        _template_pattern(template, object_is_integer=False)
        for template in mco02.DEPENDENCY_TEMPLATES
    ),
    "renamed_to": tuple(
        _template_pattern(template, object_is_integer=False)
        for template in mco02.RENAME_TEMPLATES
    ),
    "failure_threshold": tuple(
        _template_pattern(template, object_is_integer=True)
        for template in mco02.THRESHOLD_TEMPLATES
    ),
}


def transparent_relation(text: str) -> str | None:
    clause = mco02.semantic_clause(text)
    matches = [
        relation
        for relation, patterns in TRANSPARENT_PATTERNS.items()
        if any(pattern.fullmatch(clause) for pattern in patterns)
    ]
    return matches[0] if len(matches) == 1 else None


def classify_model_records(
    client: FrozenModelClient,
    records: Sequence[dict[str, Any]],
    *,
    interface: str,
    key_prefix: str,
    purpose: str,
    batch_size: int = BATCH_SIZE,
    progress_every: int | None = None,
) -> dict[str, Any]:
    if interface not in {"positional", "keyed", "single"}:
        raise ValueError(f"unsupported interface: {interface}")
    predictions: dict[str, str | None] = {}
    record_call_ids: dict[str, str] = {}
    call_ids: list[str] = []
    malformed_call_ids: list[str] = []

    if interface == "single":
        for index, row in enumerate(records):
            record_id = str(row["record_id"])
            response = client.call(
                purpose=purpose,
                key=f"{key_prefix}-single-{index}-{record_id}",
                messages=[
                    {"role": "system", "content": SINGLE_SYSTEM_PROMPT},
                    {"role": "user", "content": single_prompt(row)},
                ],
                num_ctx=CONTEXT_LIMIT,
                num_predict=32,
                format_spec=single_schema(),
            )
            qualified = f"{purpose}/{response['call_id']}"
            call_ids.append(qualified)
            record_call_ids[record_id] = qualified
            content = str(response["response"].get("message", {}).get("content", ""))
            relation = parse_single(content)
            predictions[record_id] = relation
            if relation is None:
                malformed_call_ids.append(qualified)
            if progress_every and (index + 1) % progress_every == 0:
                print(
                    f"{key_prefix}: classified {index + 1}/{len(records)} records",
                    file=sys.stderr,
                    flush=True,
                )
    else:
        for start, batch in chunks(records, batch_size):
            record_ids = [str(row["record_id"]) for row in batch]
            if interface == "keyed":
                system_prompt = KEYED_SYSTEM_PROMPT
                user_prompt = keyed_prompt(batch)
                schema = keyed_schema(record_ids)
            else:
                system_prompt = mco02.EXTRACTION_SYSTEM_PROMPT
                user_prompt = mco02.extraction_user_prompt(batch)
                schema = mco02.relation_format_schema(len(batch))
            response = client.call(
                purpose=purpose,
                key=f"{key_prefix}-{interface}-{start}-{start + len(batch) - 1}",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                num_ctx=CONTEXT_LIMIT,
                num_predict=(
                    max(512, len(batch) * 40)
                    if interface == "keyed"
                    else max(96, len(batch) * 18)
                ),
                format_spec=schema,
            )
            qualified = f"{purpose}/{response['call_id']}"
            call_ids.append(qualified)
            for record_id in record_ids:
                record_call_ids[record_id] = qualified
            content = str(response["response"].get("message", {}).get("content", ""))
            if interface == "keyed":
                parsed = parse_keyed(content, record_ids)
            else:
                ordered = mco02.parse_relation_json(content, len(batch))
                parsed = (
                    dict(zip(record_ids, ordered, strict=True)) if ordered is not None else None
                )
            if parsed is None:
                malformed_call_ids.append(qualified)
                for record_id in record_ids:
                    predictions[record_id] = None
            else:
                predictions.update(parsed)

    return {
        "interface": interface,
        "model": client.model_name,
        "predictions": predictions,
        "record_call_ids": record_call_ids,
        "malformed_call_ids": malformed_call_ids,
        "usage": usage_for_calls(client, call_ids),
    }


def score_predictions(
    public: dict[str, Any], oracle: dict[str, Any], predictions: dict[str, str | None]
) -> dict[str, Any]:
    expected_by_id = {str(row["record_id"]): str(row["relation"]) for row in oracle["records"]}
    critical_ids = {
        str(record_id)
        for query in oracle["queries"]
        for record_id in query["expected"]["path_record_ids"]
    }
    correct_by_id = {
        record_id: predictions.get(record_id) == expected
        for record_id, expected in expected_by_id.items()
    }
    by_relation: dict[str, list[bool]] = defaultdict(list)
    by_template: dict[str, list[bool]] = defaultdict(list)
    confusion: Counter[str] = Counter()
    unresolved = 0
    for record_id, expected in expected_by_id.items():
        observed = predictions.get(record_id)
        correct = correct_by_id[record_id]
        by_relation[expected].append(correct)
        metadata = oracle["rendering_metadata"][record_id]
        by_template[f"{expected}:{metadata['template_index']}"].append(correct)
        confusion[f"{expected}->{observed or 'UNRESOLVED'}"] += 1
        unresolved += observed is None
    critical = [correct_by_id[record_id] for record_id in sorted(critical_ids)]
    return {
        "history_id": public["history_id"],
        "record_count": len(expected_by_id),
        "exact_records": sum(correct_by_id.values()),
        "relation_accuracy": statistics.fmean(correct_by_id.values()),
        "critical_record_count": len(critical),
        "critical_relation_accuracy": statistics.fmean(critical) if critical else None,
        "unresolved_records": unresolved,
        "by_relation": {
            relation: {
                "n": len(values),
                "accuracy": statistics.fmean(values),
            }
            for relation, values in sorted(by_relation.items())
        },
        "by_template": {
            key: {"n": len(values), "accuracy": statistics.fmean(values)}
            for key, values in sorted(by_template.items())
        },
        "confusion": dict(sorted(confusion.items())),
        "incorrect_record_ids": sorted(
            record_id for record_id, correct in correct_by_id.items() if not correct
        ),
    }


def transparent_variant(public: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    predictions = {
        str(row["record_id"]): transparent_relation(str(row["text"]))
        for row in public["records"]
    }
    wall = time.perf_counter() - started
    return {
        "interface": "transparent_template_compiler",
        "model": None,
        "predictions": predictions,
        "malformed_call_ids": [],
        "usage": {
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "wall_time_seconds": wall,
            "expensive_token_units": 0,
            "call_ids": [],
        },
        "metrics": score_predictions(public, oracle, predictions),
    }


def engineering_smoke() -> dict[str, Any]:
    public, oracle = mco02.build_language_history(ENGINEERING_SEED, ENGINEERING_RECORDS)
    root = ENGINEERING_ROOT / "model_calls"
    primary = FrozenModelClient(model_name=PRIMARY_MODEL, cache_root=root / "primary")
    variants: dict[str, Any] = {
        "transparent": transparent_variant(public, oracle),
    }
    for interface in ("positional", "keyed", "single"):
        result = classify_model_records(
            primary,
            public["records"],
            interface=interface,
            key_prefix=f"engineering-{ENGINEERING_SEED}",
            purpose=interface,
        )
        result["metrics"] = score_predictions(public, oracle, result["predictions"])
        variants[f"primary_{interface}"] = result

    keyed_repeat = classify_model_records(
        primary,
        public["records"],
        interface="keyed",
        key_prefix=f"engineering-{ENGINEERING_SEED}-repeat",
        purpose="keyed_repeat",
    )
    keyed_repeat["metrics"] = score_predictions(public, oracle, keyed_repeat["predictions"])
    original_predictions = variants["primary_keyed"]["predictions"]
    keyed_repeat["semantic_prediction_stability"] = statistics.fmean(
        keyed_repeat["predictions"].get(record_id) == relation
        for record_id, relation in original_predictions.items()
    )
    variants["primary_keyed_repeat"] = keyed_repeat

    primary_keyed_pass = bool(
        variants["primary_keyed"]["metrics"]["relation_accuracy"] >= 0.99
        and variants["primary_keyed"]["metrics"]["critical_relation_accuracy"] >= 0.99
        and not variants["primary_keyed"]["malformed_call_ids"]
        and keyed_repeat["semantic_prediction_stability"] >= 0.99
    )
    primary_single_pass = bool(
        variants["primary_single"]["metrics"]["relation_accuracy"] >= 0.99
        and variants["primary_single"]["metrics"]["critical_relation_accuracy"] >= 0.99
        and not variants["primary_single"]["malformed_call_ids"]
    )

    fallback_run = not (primary_keyed_pass or primary_single_pass)
    if fallback_run:
        fallback = FrozenModelClient(model_name=FALLBACK_MODEL, cache_root=root / "fallback")
        result = classify_model_records(
            fallback,
            public["records"],
            interface="keyed",
            key_prefix=f"engineering-{ENGINEERING_SEED}",
            purpose="keyed",
        )
        result["metrics"] = score_predictions(public, oracle, result["predictions"])
        variants["fallback_keyed"] = result

    if primary_keyed_pass:
        selected = {"model": PRIMARY_MODEL, "interface": "keyed", "batch_size": BATCH_SIZE}
        selection_reason = "primary keyed interface cleared quality and stability gates"
    elif primary_single_pass:
        selected = {"model": PRIMARY_MODEL, "interface": "single", "batch_size": 1}
        selection_reason = "primary keyed failed; primary single-record ceiling cleared gates"
    elif (
        variants.get("fallback_keyed", {}).get("metrics", {}).get("relation_accuracy", 0.0)
        >= 0.99
        and variants.get("fallback_keyed", {}).get("metrics", {}).get(
            "critical_relation_accuracy", 0.0
        )
        >= 0.99
        and not variants.get("fallback_keyed", {}).get("malformed_call_ids", ["missing"])
    ):
        selected = {"model": FALLBACK_MODEL, "interface": "keyed", "batch_size": BATCH_SIZE}
        selection_reason = "bounded larger-model fallback cleared gates"
    else:
        selected = None
        selection_reason = "no learned extraction candidate cleared the frozen engineering gate"

    report = {
        "experiment_id": "MCO-03",
        "phase": "PRE_SCIENTIFIC_ENGINEERING",
        "scientific_corpus_calls": 0,
        "engineering_fixture": {
            "seed": ENGINEERING_SEED,
            "records": ENGINEERING_RECORDS,
            "history_id": public["history_id"],
            "public_sha256": digest(public),
            "oracle_sha256": digest(oracle),
        },
        "search_budget": {
            "always_run": [
                "transparent_template_compiler",
                "primary_positional_batch12",
                "primary_keyed_batch12",
                "primary_single_record",
                "primary_keyed_batch12_repeat",
            ],
            "conditional_fallback": "fallback_keyed_batch12 only if both primary learned interfaces fail",
            "fallback_run": fallback_run,
            "engineering_amendments": [
                {
                    "id": "MCO03-ENG-01",
                    "reason": (
                        "The first keyed probe allocated 216 output tokens; nine of ten "
                        "otherwise schema-following responses ended with done_reason=length "
                        "while emitting opaque record-ID keys."
                    ),
                    "change": "keyed num_predict raised to max(512, batch_size * 40)",
                    "unchanged": [
                        "fixture",
                        "model",
                        "prompt",
                        "schema",
                        "batch size",
                        "thresholds",
                        "selection rule",
                    ],
                    "scientific_corpus_calls_before_change": 0,
                    "truncated_raw_receipts_preserved": True,
                }
            ],
        },
        "model_identities": {
            "primary": model_identity(PRIMARY_MODEL),
            "fallback": model_identity(FALLBACK_MODEL),
        },
        "variants": variants,
        "selected_scientific_extractor": selected,
        "selection_reason": selection_reason,
        "pass": selected is not None,
    }
    write_json(ENGINEERING_ROOT / "engineering_smoke.json", report)
    return report


def verify_engineering() -> dict[str, Any]:
    path = ENGINEERING_ROOT / "engineering_smoke.json"
    if not path.exists():
        return {"pass": False, "errors": ["missing-engineering-smoke"]}
    report = read_json(path)
    errors: list[str] = []
    fixture_public, fixture_oracle = mco02.build_language_history(
        ENGINEERING_SEED, ENGINEERING_RECORDS
    )
    fixture = report.get("engineering_fixture", {})
    if fixture.get("public_sha256") != digest(fixture_public):
        errors.append("public-fixture-hash")
    if fixture.get("oracle_sha256") != digest(fixture_oracle):
        errors.append("oracle-fixture-hash")
    if report.get("scientific_corpus_calls") != 0:
        errors.append("scientific-call-leakage")
    primary_identity = report.get("model_identities", {}).get("primary", {})
    if primary_identity.get("blob_sha256") != PRIMARY_MODEL_BLOB_SHA256:
        errors.append("primary-model-identity")
    fallback_identity = report.get("model_identities", {}).get("fallback", {})
    if fallback_identity.get("blob_sha256") != FALLBACK_MODEL_BLOB_SHA256:
        errors.append("fallback-model-identity")
    return {
        "pass": not errors and bool(report.get("pass")),
        "selected_scientific_extractor": report.get("selected_scientific_extractor"),
        "engineering_report_sha256": file_sha256(path),
        "errors": errors,
    }


def freeze_sources() -> list[Path]:
    return [
        ROOT / "scripts/run_mco03.py",
        ROOT / "tests/test_mco03.py",
        CONFIG_PATH,
        CONTRACT_PATH,
        ENGINEERING_ROOT / "engineering_smoke.json",
        mco02.CORPUS_MANIFEST_PATH,
        mco02.FREEZE_PATH,
        mco02.OUT / "MCO02_VERDICT.json",
    ]


def create_freeze() -> dict[str, Any]:
    if not CONFIG_PATH.exists() or not CONTRACT_PATH.exists():
        raise FileNotFoundError("MCO-03 config and contract must exist before freeze")
    config = read_json(CONFIG_PATH)
    if config.get("status") != "PREREGISTERED_BEFORE_SCIENTIFIC_INFERENCE":
        raise RuntimeError("MCO-03 config is not preregistered")
    engineering = verify_engineering()
    if not engineering["pass"]:
        raise RuntimeError(f"engineering verification failed: {engineering}")
    existing_scientific_calls = list(MODEL_CALL_ROOT.rglob("*.json")) if MODEL_CALL_ROOT.exists() else []
    existing_embeddings = list(EMBEDDING_ROOT.rglob("*.npz")) if EMBEDDING_ROOT.exists() else []
    if existing_scientific_calls or existing_embeddings:
        raise RuntimeError("scientific artifacts already exist; refusing first freeze")
    missing = [str(path) for path in freeze_sources() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing freeze sources: {missing}")
    freeze = {
        "experiment_id": "MCO-03",
        "status": "FROZEN_BEFORE_SCIENTIFIC_INFERENCE",
        "scientific_model_calls_before_freeze": 0,
        "scientific_embedding_calls_before_freeze": 0,
        "selected_extractor": config["learned_extractor"],
        "model_identities": {
            "reasoning_and_extraction": model_identity(PRIMARY_MODEL),
            "embedding": model_identity(EMBEDDING_MODEL),
        },
        "files": {
            str(path.relative_to(ROOT)): {
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in freeze_sources()
        },
    }
    write_json(FREEZE_PATH, freeze)
    return freeze


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.exists():
        return {"pass": False, "errors": ["missing-mco03-freeze"]}
    freeze = read_json(FREEZE_PATH)
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    for relative, expected in freeze.get("files", {}).items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        passed = observed == expected.get("sha256")
        checks.append(
            {
                "path": relative,
                "expected_sha256": expected.get("sha256"),
                "observed_sha256": observed,
                "pass": passed,
            }
        )
        if not passed:
            errors.append(f"hash:{relative}")
    extraction_identity = model_identity(PRIMARY_MODEL)
    embedding_identity = model_identity(EMBEDDING_MODEL)
    if extraction_identity.get("blob_sha256") != PRIMARY_MODEL_BLOB_SHA256:
        errors.append("primary-model-identity")
    if embedding_identity.get("blob_sha256") != EMBEDDING_MODEL_BLOB_SHA256:
        errors.append("embedding-model-identity")
    if freeze.get("selected_extractor") != read_json(CONFIG_PATH).get("learned_extractor"):
        errors.append("selected-extractor")
    return {
        "pass": not errors and bool(checks),
        "checks": checks,
        "reasoning_and_extraction_model": extraction_identity,
        "embedding_model": embedding_identity,
        "errors": errors,
    }


def preflight() -> dict[str, Any]:
    checks = {
        "engineering": verify_engineering(),
        "mco02_corpus": mco02.verify_corpus(deep=True),
        "mco02_freeze": mco02.verify_freeze(),
        "mco03_freeze": verify_freeze(),
    }
    mco02_verdict = read_json(mco02.OUT / "MCO02_VERDICT.json")
    prior_state = {
        "pass": bool(
            mco02_verdict.get("verdict") == "MCO_02_ACCOUNTING_INVALID"
            and not mco02_verdict.get("gate_pass")
            and mco02_verdict.get("training_accounting", {}).get(
                "dmc_historical_optimizer_steps_preserved"
            )
            == 10880
            and mco02_verdict.get("training_accounting", {}).get(
                "dmc_historical_training_label"
            )
            == "TRAINING_COST_UNKNOWN"
        ),
        "verdict": mco02_verdict.get("verdict"),
    }
    checks["prior_state"] = prior_state
    return {
        "pass": all(bool(check.get("pass")) for check in checks.values()),
        "checks": checks,
    }


def materialize_records(
    public: dict[str, Any], predictions: dict[str, str | None]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for public_row in public["records"]:
        row = mco02.parse_scaffold(str(public_row["text"]))
        row["relation"] = predictions.get(str(public_row["record_id"])) or "unknown"
        records.append(row)
    return records


def indexing_check(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    record_ids = [str(row["record_id"]) for row in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("duplicate-record-id")
    unresolved = [
        str(row["record_id"])
        for row in records
        if row.get("relation") not in ALLOWED_RELATIONS
    ]
    if unresolved:
        errors.append("unresolved-relation")
    if not errors:
        indexed = mco02.mco01.index_records(records)
        indexed_ids = {
            str(row["record_id"])
            for rows in indexed.values()
            for row in rows
        }
        if indexed_ids != set(record_ids):
            errors.append("index-record-loss")
    return {
        "pass": not errors,
        "record_count": len(records),
        "unresolved_record_ids": unresolved,
        "errors": errors,
    }


def prepared_extraction(
    public: dict[str, Any],
    oracle: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, Any]:
    records = materialize_records(public, variant["predictions"])
    return {
        "experiment_id": "MCO-03",
        "history_id": public["history_id"],
        "history_size": public["history_size"],
        "extractor": variant["interface"],
        "model": variant["model"],
        "source_public_sha256": digest(public),
        "source_oracle_sha256": digest(oracle),
        "records": records,
        "predictions": variant["predictions"],
        "record_call_ids": variant.get("record_call_ids", {}),
        "metrics": score_predictions(public, oracle, variant["predictions"]),
        "indexing": indexing_check(records),
        "malformed_call_ids": variant["malformed_call_ids"],
        "usage": variant["usage"],
        "artifact_sha256": digest(records),
    }


def _extraction_output_root(run_id: str) -> Path:
    return SCIENTIFIC_ROOT / run_id


def run_scientific_extraction(*, mode: str, run_id: str) -> dict[str, Any]:
    if mode not in {"live", "replay"}:
        raise ValueError(mode)
    readiness = preflight()
    if not readiness["pass"]:
        raise RuntimeError(f"preflight failed: {readiness}")
    config = read_json(CONFIG_PATH)
    selected = config["learned_extractor"]
    if selected != {"model": PRIMARY_MODEL, "interface": "single", "batch_size": 1}:
        raise RuntimeError(f"unexpected learned extractor: {selected}")
    output_root = _extraction_output_root(run_id)
    learned_client = FrozenModelClient(
        model_name=PRIMARY_MODEL,
        cache_root=MODEL_CALL_ROOT / "learned_extraction",
        mode=mode,
    )
    summaries: list[dict[str, Any]] = []
    for public, oracle in mco02.load_corpus():
        history_id = str(public["history_id"])
        print(f"{run_id}: starting {history_id}", file=sys.stderr, flush=True)
        learned_variant = classify_model_records(
            learned_client,
            public["records"],
            interface="single",
            key_prefix=history_id,
            purpose="single_extraction",
            batch_size=1,
            progress_every=250,
        )
        learned = prepared_extraction(public, oracle, learned_variant)
        transparent = prepared_extraction(public, oracle, transparent_variant(public, oracle))
        write_json(output_root / "learned" / f"{history_id}.json", learned)
        write_json(output_root / "transparent" / f"{history_id}.json", transparent)
        summaries.append(
            {
                "history_id": history_id,
                "history_size": public["history_size"],
                "learned_metrics": learned["metrics"],
                "transparent_metrics": transparent["metrics"],
                "learned_usage": learned["usage"],
                "learned_artifact_sha256": learned["artifact_sha256"],
                "transparent_artifact_sha256": transparent["artifact_sha256"],
                "artifacts_identical": (
                    learned["artifact_sha256"] == transparent["artifact_sha256"]
                ),
            }
        )
        print(f"{run_id}: completed {history_id}", file=sys.stderr, flush=True)
    result = {
        "experiment_id": "MCO-03",
        "mode": mode,
        "run_id": run_id,
        "histories": summaries,
        "history_count": len(summaries),
        "record_count": sum(int(row["history_size"]) for row in summaries),
        "pass": bool(
            len(summaries) == mco02.EXPECTED_HISTORIES
            and all(row["learned_metrics"]["unresolved_records"] == 0 for row in summaries)
            and all(row["transparent_metrics"]["relation_accuracy"] == 1.0 for row in summaries)
        ),
    }
    write_json(output_root / "extraction_summary.json", result)
    return result


def compiler_prediction(
    traversal: dict[str, Any], query: dict[str, Any]
) -> dict[str, Any]:
    path = list(traversal["path"])
    complete = bool(traversal["complete"] and path and len(path) <= RAG_CAPACITY)
    if not complete:
        return {
            "complete": False,
            "terminal_entity": None,
            "failure_threshold": None,
            "requires_inspection": None,
            "path_record_ids": [str(row["record_id"]) for row in path[:RAG_CAPACITY]],
        }
    terminal = path[-1]
    threshold = int(terminal["object"])
    return {
        "complete": True,
        "terminal_entity": str(terminal["subject"]),
        "failure_threshold": threshold,
        "requires_inspection": int(query["deployment_temperature"]) < threshold,
        "path_record_ids": [str(row["record_id"]) for row in path],
    }


def answer_exact(prediction: dict[str, Any], expected: dict[str, Any]) -> bool:
    return bool(
        prediction.get("complete")
        and prediction.get("terminal_entity") == expected["terminal_entity"]
        and prediction.get("failure_threshold") == expected["failure_threshold"]
        and prediction.get("requires_inspection") == expected["requires_inspection"]
    )


def planner_row(
    *,
    variant_name: str,
    public: dict[str, Any],
    oracle: dict[str, Any],
    public_query: dict[str, Any],
    oracle_query: dict[str, Any],
    prepared: dict[str, Any],
    reasoner: FrozenModelClient,
) -> dict[str, Any]:
    expected = oracle_query["expected"]
    expected_path = [str(value) for value in expected["path_record_ids"]]
    traversal = mco02.traverse_extracted(prepared["records"], public_query)
    packet = list(traversal["path"][:RAG_CAPACITY])
    packet_ids = [str(row["record_id"]) for row in packet]
    compiler = compiler_prediction(traversal, public_query)
    evidence = [mco02.structured_evidence_line(row) for row in packet]
    outcome = mco02.call_final_reasoner(
        reasoner,
        system="mco03_frozen_exact_planner",
        history_id=str(public["history_id"]),
        query=public_query,
        evidence_lines=evidence,
        num_ctx=CONTEXT_LIMIT,
    )
    model_prediction = outcome["prediction"]
    model_path = [str(value) for value in model_prediction.get("path_record_ids", [])]
    expected_set = set(expected_path)
    packet_set = set(packet_ids)
    critical_recall = sum(record_id in packet_set for record_id in expected_path) / len(
        expected_path
    )
    packet_precision = (
        sum(record_id in expected_set for record_id in packet_ids) / len(packet_ids)
        if packet_ids
        else 0.0
    )
    oracle_by_id = {str(row["record_id"]): row for row in oracle["records"]}
    prepared_by_id = {str(row["record_id"]): row for row in prepared["records"]}
    extraction_critical_failure = any(
        prepared_by_id.get(record_id, {}).get("relation")
        != oracle_by_id[record_id]["relation"]
        for record_id in expected_path
    )
    compiler_answer = answer_exact(compiler, expected)
    packet_exact = packet_ids == expected_path
    model_answer = answer_exact(model_prediction, expected)
    model_provenance = model_path == expected_path
    if extraction_critical_failure:
        failure_class = "LANGUAGE_EXTRACTION_FAILURE"
    elif not packet_exact:
        failure_class = "PACKET_SELECTION_FAILURE"
    elif not model_answer:
        failure_class = "REASONING_FAILURE"
    elif not model_provenance:
        failure_class = "PROVENANCE_COPY_FAILURE"
    else:
        failure_class = None
    usage = outcome["usage"]
    return {
        "history_id": public["history_id"],
        "history_size": public["history_size"],
        "seed": public["seed"],
        "query_id": public_query["query_id"],
        "dependency_hops": oracle_query["dependency_hops"],
        "families": oracle_query["families"],
        "variant": variant_name,
        "extractor": prepared["extractor"],
        "model": prepared["model"],
        "extraction_critical_failure": extraction_critical_failure,
        "packet_complete": compiler["complete"],
        "packet_answer_accuracy": float(compiler_answer),
        "packet_provenance_accuracy": float(packet_exact),
        "packet_critical_recall": critical_recall,
        "packet_precision": packet_precision,
        "packet_record_count": len(packet_ids),
        "packet_record_ids": packet_ids,
        "expected_path_sha256": digest(expected_path),
        "compiler_owned_provenance": packet_ids,
        "model_answer_accuracy": float(model_answer),
        "model_generated_provenance_accuracy": float(model_provenance),
        "model_generated_path_record_ids": model_path,
        "model_visible_records": len(packet),
        "model_visible_tokens": outcome["maximum_model_visible_tokens"],
        "query_model_calls": usage["model_calls"],
        "query_input_tokens": usage["input_tokens"],
        "query_output_tokens": usage["output_tokens"],
        "query_expensive_token_units": (
            int(usage["input_tokens"]) + 4 * int(usage["output_tokens"])
        ),
        "query_wall_time_seconds": usage["wall_time_seconds"],
        "raw_model_output_sha256": outcome["raw_output_sha256"],
        "model_call_ids": outcome["call_ids"],
        "failure_class": failure_class,
    }


def summarize_metric(rows: Sequence[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def summarize_planner(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["variant"])].append(row)
    result: dict[str, Any] = {}
    for variant, variant_rows in sorted(by_variant.items()):
        by_load: dict[str, Any] = {}
        for size in mco02.HISTORY_SIZES:
            selected = [row for row in variant_rows if int(row["history_size"]) == size]
            by_load[str(size)] = {
                "n": len(selected),
                "packet_answer_accuracy": summarize_metric(
                    selected, "packet_answer_accuracy"
                ),
                "packet_provenance_accuracy": summarize_metric(
                    selected, "packet_provenance_accuracy"
                ),
                "model_answer_accuracy": summarize_metric(
                    selected, "model_answer_accuracy"
                ),
                "model_generated_provenance_accuracy": summarize_metric(
                    selected, "model_generated_provenance_accuracy"
                ),
            }
        result[variant] = {
            "n": len(variant_rows),
            "packet_answer_accuracy": summarize_metric(
                variant_rows, "packet_answer_accuracy"
            ),
            "packet_provenance_accuracy": summarize_metric(
                variant_rows, "packet_provenance_accuracy"
            ),
            "packet_critical_recall": summarize_metric(
                variant_rows, "packet_critical_recall"
            ),
            "packet_precision": summarize_metric(variant_rows, "packet_precision"),
            "model_answer_accuracy": summarize_metric(
                variant_rows, "model_answer_accuracy"
            ),
            "model_generated_provenance_accuracy": summarize_metric(
                variant_rows, "model_generated_provenance_accuracy"
            ),
            "maximum_model_visible_records": max(
                int(row["model_visible_records"]) for row in variant_rows
            ),
            "maximum_model_visible_tokens": max(
                int(row["model_visible_tokens"]) for row in variant_rows
            ),
            "mean_query_model_calls": summarize_metric(variant_rows, "query_model_calls"),
            "mean_query_expensive_token_units": summarize_metric(
                variant_rows, "query_expensive_token_units"
            ),
            "failure_counts": dict(
                sorted(
                    Counter(
                        str(row["failure_class"])
                        for row in variant_rows
                        if row["failure_class"] is not None
                    ).items()
                )
            ),
            "by_history_size": by_load,
        }
    return result


def run_planner(*, mode: str, extraction_run_id: str, run_id: str) -> dict[str, Any]:
    readiness = preflight()
    if not readiness["pass"]:
        raise RuntimeError(f"preflight failed: {readiness}")
    extraction_root = _extraction_output_root(extraction_run_id)
    if not (extraction_root / "extraction_summary.json").exists():
        raise FileNotFoundError("missing extraction run")
    reasoner = FrozenModelClient(
        model_name=PRIMARY_MODEL,
        cache_root=MODEL_CALL_ROOT / "frozen_reasoner",
        mode=mode,
    )
    rows: list[dict[str, Any]] = []
    for public, oracle in mco02.load_corpus():
        history_id = str(public["history_id"])
        oracle_queries = {str(row["query_id"]): row for row in oracle["queries"]}
        prepared_by_variant = {
            "learned_single": read_json(
                extraction_root / "learned" / f"{history_id}.json"
            ),
            "transparent_compiler": read_json(
                extraction_root / "transparent" / f"{history_id}.json"
            ),
        }
        for public_query in public["queries"]:
            oracle_query = oracle_queries[str(public_query["query_id"])]
            for variant_name, prepared in prepared_by_variant.items():
                rows.append(
                    planner_row(
                        variant_name=variant_name,
                        public=public,
                        oracle=oracle,
                        public_query=public_query,
                        oracle_query=oracle_query,
                        prepared=prepared,
                        reasoner=reasoner,
                    )
                )
        print(f"{run_id}: planner completed {history_id}", file=sys.stderr, flush=True)
    output_root = SCIENTIFIC_ROOT / run_id
    write_jsonl(output_root / "planner_results.jsonl", rows)
    summary = {
        "experiment_id": "MCO-03",
        "mode": mode,
        "run_id": run_id,
        "extraction_run_id": extraction_run_id,
        "population": {
            "rows": len(rows),
            "queries": mco02.EXPECTED_QUERIES,
            "variants": sorted({str(row["variant"]) for row in rows}),
        },
        "variants": summarize_planner(rows),
        "pass": bool(
            len(rows) == mco02.EXPECTED_QUERIES * 2
            and max(int(row["model_visible_records"]) for row in rows) <= RAG_CAPACITY
            and max(int(row["model_visible_tokens"]) for row in rows) <= CONTEXT_LIMIT
        ),
    }
    write_json(output_root / "planner_summary.json", summary)
    return summary


def select_stability_records(
    public: dict[str, Any], oracle: dict[str, Any], fraction: float = 0.1
) -> list[dict[str, Any]]:
    critical_ids = {
        str(record_id)
        for query in oracle["queries"]
        for record_id in query["expected"]["path_record_ids"]
    }
    oracle_by_id = {str(row["record_id"]): row for row in oracle["records"]}
    strata: dict[tuple[str, int, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in public["records"]:
        record_id = str(row["record_id"])
        relation = str(oracle_by_id[record_id]["relation"])
        template = int(oracle["rendering_metadata"][record_id]["template_index"])
        strata[(relation, template, record_id in critical_ids)].append(row)
    selected: list[dict[str, Any]] = []
    for stratum, rows in sorted(strata.items()):
        ordered = sorted(
            rows,
            key=lambda row: (
                mco02.mco01.stable_int(
                    public["history_id"], row["record_id"], stratum, "mco03-stability"
                ),
                str(row["record_id"]),
            ),
        )
        count = max(1, math.ceil(len(ordered) * fraction))
        selected.extend(ordered[:count])
    return sorted(selected, key=lambda row: int(row["position"]))


def run_stability_recheck(*, extraction_run_id: str, fraction: float = 0.1) -> dict[str, Any]:
    readiness = preflight()
    if not readiness["pass"]:
        raise RuntimeError(f"preflight failed: {readiness}")
    extraction_root = _extraction_output_root(extraction_run_id)
    original_client = FrozenModelClient(
        model_name=PRIMARY_MODEL,
        cache_root=MODEL_CALL_ROOT / "learned_extraction",
        mode="replay",
    )
    repeat_client = FrozenModelClient(
        model_name=PRIMARY_MODEL,
        cache_root=MODEL_CALL_ROOT / "stability_repeat",
        mode="live",
    )
    comparisons: list[dict[str, Any]] = []
    for public, oracle in mco02.load_corpus():
        history_id = str(public["history_id"])
        prepared = read_json(extraction_root / "learned" / f"{history_id}.json")
        selected = select_stability_records(public, oracle, fraction)
        repeat = classify_model_records(
            repeat_client,
            selected,
            interface="single",
            key_prefix=f"repeat-{history_id}",
            purpose="single_repeat",
            batch_size=1,
            progress_every=250,
        )
        for row in selected:
            record_id = str(row["record_id"])
            original_call_id = str(prepared["record_call_ids"][record_id])
            repeat_call_id = str(repeat["record_call_ids"][record_id])
            original_call = original_client.resolve(original_call_id)
            repeat_call = repeat_client.resolve(repeat_call_id)
            original_content = str(
                original_call["response"].get("message", {}).get("content", "")
            )
            repeat_content = str(
                repeat_call["response"].get("message", {}).get("content", "")
            )
            comparisons.append(
                {
                    "history_id": history_id,
                    "record_id": record_id,
                    "raw_content_identical": original_content == repeat_content,
                    "semantic_relation_identical": (
                        prepared["predictions"][record_id]
                        == repeat["predictions"][record_id]
                    ),
                    "original_relation": prepared["predictions"][record_id],
                    "repeat_relation": repeat["predictions"][record_id],
                    "prompt_tokens_identical": (
                        original_call["accounting"]["prompt_eval_count"]
                        == repeat_call["accounting"]["prompt_eval_count"]
                    ),
                    "output_tokens_identical": (
                        original_call["accounting"]["eval_count"]
                        == repeat_call["accounting"]["eval_count"]
                    ),
                    "original_call_id": original_call_id,
                    "repeat_call_id": repeat_call_id,
                }
            )
        print(
            f"stability: completed {history_id} ({len(selected)} records)",
            file=sys.stderr,
            flush=True,
        )
    raw_stability = statistics.fmean(
        bool(row["raw_content_identical"]) for row in comparisons
    )
    semantic_stability = statistics.fmean(
        bool(row["semantic_relation_identical"]) for row in comparisons
    )
    result = {
        "experiment_id": "MCO-03",
        "fraction": fraction,
        "selected_records": len(comparisons),
        "population_records": mco02.EXPECTED_RECORDS,
        "raw_content_stability": raw_stability,
        "semantic_relation_stability": semantic_stability,
        "minimum_raw_required": 0.95,
        "minimum_semantic_required": 0.99,
        "comparisons": comparisons,
        "pass": raw_stability >= 0.95 and semantic_stability >= 0.99,
    }
    write_json(SCIENTIFIC_ROOT / "stability_recheck.json", result)
    return result


def normalized_extraction_artifact(value: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(value))
    if "usage" in normalized:
        normalized["usage"].pop("wall_time_seconds", None)
    return normalized


def extraction_replay_check(*, live_run_id: str, replay_run_id: str) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for public, _ in mco02.load_corpus():
        history_id = str(public["history_id"])
        for variant in ("learned", "transparent"):
            live_path = SCIENTIFIC_ROOT / live_run_id / variant / f"{history_id}.json"
            replay_path = SCIENTIFIC_ROOT / replay_run_id / variant / f"{history_id}.json"
            live = normalized_extraction_artifact(read_json(live_path))
            replay = normalized_extraction_artifact(read_json(replay_path))
            comparisons.append(
                {
                    "history_id": history_id,
                    "variant": variant,
                    "live_sha256": digest(live),
                    "replay_sha256": digest(replay),
                    "identical": live == replay,
                }
            )
    result = {
        "experiment_id": "MCO-03",
        "live_run_id": live_run_id,
        "replay_run_id": replay_run_id,
        "comparisons": comparisons,
        "pass": all(bool(row["identical"]) for row in comparisons),
    }
    write_json(SCIENTIFIC_ROOT / "extraction_replay_check.json", result)
    return result


class FrozenEmbeddingClient:
    """Replayable Ollama embedding client storing float32 matrices plus receipts."""

    def __init__(
        self,
        *,
        model_name: str = EMBEDDING_MODEL,
        cache_root: Path = EMBEDDING_ROOT,
        mode: str = "live",
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        if mode not in {"live", "replay"}:
            raise ValueError(mode)
        self.model_name = model_name
        self.cache_root = cache_root
        self.mode = mode
        self.base_url = base_url.rstrip("/")

    def _paths(self, key: str, request_sha256: str) -> tuple[Path, Path, str]:
        safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "-", key)[:100]
        call_id = f"{safe_key}__{request_sha256[:16]}"
        return (
            self.cache_root / f"{call_id}.json",
            self.cache_root / f"{call_id}.npz",
            call_id,
        )

    def _batch(self, *, key: str, inputs: Sequence[str]) -> dict[str, Any]:
        payload = {
            "model": self.model_name,
            "input": list(inputs),
            "truncate": False,
            "options": {"num_ctx": 2048},
        }
        request_sha256 = digest(payload)
        metadata_path, matrix_path, call_id = self._paths(key, request_sha256)
        if metadata_path.exists() and matrix_path.exists():
            metadata = read_json(metadata_path)
            if metadata.get("request_sha256") != request_sha256:
                raise RuntimeError(f"embedding cache mismatch: {metadata_path}")
            with np.load(matrix_path) as archive:
                matrix = np.asarray(archive["embeddings"], dtype=np.float32)
            if hashlib.sha256(matrix.tobytes()).hexdigest() != metadata["matrix_sha256"]:
                raise RuntimeError(f"embedding matrix hash mismatch: {matrix_path}")
            return {"matrix": matrix, "metadata": metadata, "cache_hit": True}
        if self.mode == "replay":
            raise FileNotFoundError(metadata_path)
        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                raw = json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"embedding call failed: {call_id}: {exc}") from exc
        wall = time.perf_counter() - started
        matrix = np.asarray(raw.get("embeddings", []), dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(inputs):
            raise RuntimeError(
                f"embedding shape mismatch for {call_id}: {matrix.shape} vs {len(inputs)}"
            )
        norms = np.linalg.norm(matrix, axis=1)
        metadata = {
            "schema_version": 1,
            "model": self.model_name,
            "call_id": call_id,
            "request_sha256": request_sha256,
            "input_count": len(inputs),
            "input_sha256": digest(list(inputs)),
            "shape": list(matrix.shape),
            "matrix_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
            "norm_min": float(norms.min()) if len(norms) else None,
            "norm_max": float(norms.max()) if len(norms) else None,
            "accounting": {
                "prompt_eval_count": int(raw.get("prompt_eval_count", 0)),
                "load_duration_ns": int(raw.get("load_duration", 0)),
                "total_duration_ns": int(raw.get("total_duration", 0)),
                "wall_time_seconds": wall,
            },
        }
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(matrix_path, embeddings=matrix)
        write_json(metadata_path, metadata)
        return {"matrix": matrix, "metadata": metadata, "cache_hit": False}

    def embed(self, *, key: str, inputs: Sequence[str]) -> dict[str, Any]:
        matrices: list[np.ndarray] = []
        receipts: list[dict[str, Any]] = []
        for start, batch in chunks(inputs, EMBEDDING_BATCH_SIZE):
            result = self._batch(
                key=f"{key}-{start}-{start + len(batch) - 1}", inputs=batch
            )
            matrices.append(result["matrix"])
            receipts.append(result["metadata"])
        matrix = (
            np.concatenate(matrices, axis=0)
            if matrices
            else np.empty((0, 0), dtype=np.float32)
        )
        return {
            "matrix": matrix,
            "usage": {
                "model_calls": len(receipts),
                "input_tokens": sum(
                    int(row["accounting"]["prompt_eval_count"]) for row in receipts
                ),
                "wall_time_seconds": sum(
                    float(row["accounting"]["wall_time_seconds"]) for row in receipts
                ),
                "call_ids": [str(row["call_id"]) for row in receipts],
            },
            "matrix_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
        }


class HybridRagIndex:
    def __init__(
        self, records: Sequence[dict[str, Any]], embeddings: np.ndarray
    ) -> None:
        self.records = list(records)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        if self.embeddings.shape[0] != len(self.records):
            raise ValueError("record/embedding count mismatch")
        self.sparse = mco02.ConventionalRagIndex(self.records)
        self.scaffolds = [mco02.parse_scaffold(str(row["text"])) for row in self.records]
        self.by_subject: dict[str, list[int]] = defaultdict(list)
        for index, scaffold in enumerate(self.scaffolds):
            self.by_subject[str(scaffold["subject"])].append(index)

    def rankings(self, question: str, query_embedding: np.ndarray) -> dict[str, Any]:
        sparse_query = self.sparse.vectorizer.transform([question])
        sparse_scores = (self.sparse.matrix @ sparse_query.T).toarray().ravel()
        dense_scores = self.embeddings @ np.asarray(query_embedding, dtype=np.float32)
        sparse_order = sorted(
            range(len(self.records)),
            key=lambda index: (
                -float(sparse_scores[index]),
                mco02.mco01.stable_int(question, self.records[index]["record_id"], "sparse"),
                str(self.records[index]["record_id"]),
            ),
        )
        dense_order = sorted(
            range(len(self.records)),
            key=lambda index: (
                -float(dense_scores[index]),
                mco02.mco01.stable_int(question, self.records[index]["record_id"], "dense"),
                str(self.records[index]["record_id"]),
            ),
        )
        sparse_rank = np.empty(len(self.records), dtype=np.int64)
        dense_rank = np.empty(len(self.records), dtype=np.int64)
        sparse_rank[np.asarray(sparse_order)] = np.arange(len(self.records))
        dense_rank[np.asarray(dense_order)] = np.arange(len(self.records))
        rrf_scores = 1.0 / (60.0 + sparse_rank) + 1.0 / (60.0 + dense_rank)
        hybrid_order = sorted(
            range(len(self.records)),
            key=lambda index: (
                -float(rrf_scores[index]),
                int(sparse_rank[index] + dense_rank[index]),
                str(self.records[index]["record_id"]),
            ),
        )
        return {
            "dense_order": dense_order,
            "sparse_order": sparse_order,
            "hybrid_order": hybrid_order,
            "hybrid_rank": {index: rank for rank, index in enumerate(hybrid_order)},
        }

    def retrieve(
        self,
        *,
        variant: str,
        question: str,
        root_entity: str,
        query_embedding: np.ndarray,
        top_k: int = RAG_CAPACITY,
    ) -> list[dict[str, Any]]:
        ranks = self.rankings(question, query_embedding)
        if variant == "dense_rag":
            selected = ranks["dense_order"][:top_k]
        elif variant == "hybrid_rag":
            selected = ranks["hybrid_order"][:top_k]
        elif variant == "entity_hybrid_rag":
            selected = []
            selected_set: set[int] = set()
            frontier = [root_entity]
            seen_entities: set[str] = set()
            while frontier and len(selected) < top_k:
                next_frontier: list[str] = []
                for entity in frontier:
                    if entity in seen_entities:
                        continue
                    seen_entities.add(entity)
                    candidates = sorted(
                        self.by_subject.get(entity, []),
                        key=lambda index: (
                            ranks["hybrid_rank"][index],
                            str(self.records[index]["record_id"]),
                        ),
                    )
                    for index in candidates:
                        if index in selected_set:
                            continue
                        selected.append(index)
                        selected_set.add(index)
                        obj = self.scaffolds[index]["object"]
                        if isinstance(obj, str) and re.fullmatch(
                            r"[ed]_[0-9a-f]{16}", obj
                        ):
                            next_frontier.append(obj)
                        if len(selected) >= top_k:
                            break
                    if len(selected) >= top_k:
                        break
                frontier = list(dict.fromkeys(next_frontier))
        else:
            raise ValueError(variant)
        return [self.records[index] for index in selected]


def rag_row(
    *,
    variant: str,
    public: dict[str, Any],
    public_query: dict[str, Any],
    oracle_query: dict[str, Any],
    selected: Sequence[dict[str, Any]],
    reasoner: FrozenModelClient,
    ingestion_embedding_usage: dict[str, Any],
    query_embedding_usage: dict[str, Any],
) -> dict[str, Any]:
    expected = oracle_query["expected"]
    expected_path = [str(value) for value in expected["path_record_ids"]]
    selected_ids = [str(row["record_id"]) for row in selected]
    selected_set = set(selected_ids)
    recall = sum(record_id in selected_set for record_id in expected_path) / len(expected_path)
    precision = (
        sum(record_id in set(expected_path) for record_id in selected_ids) / len(selected_ids)
        if selected_ids
        else 0.0
    )
    outcome = mco02.call_final_reasoner(
        reasoner,
        system=f"mco03_{variant}",
        history_id=str(public["history_id"]),
        query=public_query,
        evidence_lines=[str(row["text"]) for row in selected],
        num_ctx=CONTEXT_LIMIT,
    )
    prediction = outcome["prediction"]
    predicted_path = [str(value) for value in prediction.get("path_record_ids", [])]
    model_answer = answer_exact(prediction, expected)
    provenance = predicted_path == expected_path
    if recall < 1.0:
        failure_class = "RETRIEVAL_FAILURE"
    elif not model_answer:
        failure_class = "REASONING_FAILURE"
    elif not provenance:
        failure_class = "PROVENANCE_FAILURE"
    else:
        failure_class = None
    usage = outcome["usage"]
    return {
        "history_id": public["history_id"],
        "history_size": public["history_size"],
        "seed": public["seed"],
        "query_id": public_query["query_id"],
        "dependency_hops": oracle_query["dependency_hops"],
        "families": oracle_query["families"],
        "variant": variant,
        "retrieval_recall": recall,
        "retrieval_precision": precision,
        "retrieved_records": len(selected_ids),
        "retrieved_record_ids": selected_ids,
        "model_answer_accuracy": float(model_answer),
        "model_generated_provenance_accuracy": float(provenance),
        "model_generated_path_record_ids": predicted_path,
        "model_visible_records": len(selected_ids),
        "model_visible_tokens": outcome["maximum_model_visible_tokens"],
        "ingestion_embedding_calls": ingestion_embedding_usage["model_calls"],
        "ingestion_embedding_tokens": ingestion_embedding_usage["input_tokens"],
        "query_embedding_calls": query_embedding_usage["model_calls"],
        "query_embedding_tokens": query_embedding_usage["input_tokens"],
        "query_reasoning_calls": usage["model_calls"],
        "query_reasoning_input_tokens": usage["input_tokens"],
        "query_reasoning_output_tokens": usage["output_tokens"],
        "query_reasoning_expensive_token_units": (
            int(usage["input_tokens"]) + 4 * int(usage["output_tokens"])
        ),
        "failure_class": failure_class,
        "model_call_ids": outcome["call_ids"],
        "raw_model_output_sha256": outcome["raw_output_sha256"],
    }


def summarize_rag(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["variant"])].append(row)
    return {
        variant: {
            "n": len(selected),
            "retrieval_recall": summarize_metric(selected, "retrieval_recall"),
            "retrieval_precision": summarize_metric(selected, "retrieval_precision"),
            "model_answer_accuracy": summarize_metric(selected, "model_answer_accuracy"),
            "model_generated_provenance_accuracy": summarize_metric(
                selected, "model_generated_provenance_accuracy"
            ),
            "maximum_model_visible_records": max(
                int(row["model_visible_records"]) for row in selected
            ),
            "maximum_model_visible_tokens": max(
                int(row["model_visible_tokens"]) for row in selected
            ),
            "mean_query_reasoning_expensive_token_units": summarize_metric(
                selected, "query_reasoning_expensive_token_units"
            ),
            "failure_counts": dict(
                sorted(
                    Counter(
                        str(row["failure_class"])
                        for row in selected
                        if row["failure_class"] is not None
                    ).items()
                )
            ),
            "by_history_size": {
                str(size): {
                    "n": len(load_rows),
                    "retrieval_recall": summarize_metric(load_rows, "retrieval_recall"),
                    "model_answer_accuracy": summarize_metric(
                        load_rows, "model_answer_accuracy"
                    ),
                    "model_generated_provenance_accuracy": summarize_metric(
                        load_rows, "model_generated_provenance_accuracy"
                    ),
                }
                for size in mco02.HISTORY_SIZES
                for load_rows in [
                    [row for row in selected if int(row["history_size"]) == size]
                ]
            },
        }
        for variant, selected in sorted(by_variant.items())
    }


def run_rag(*, mode: str, run_id: str) -> dict[str, Any]:
    readiness = preflight()
    if not readiness["pass"]:
        raise RuntimeError(f"preflight failed: {readiness}")
    embedder = FrozenEmbeddingClient(mode=mode)
    reasoner = FrozenModelClient(
        model_name=PRIMARY_MODEL,
        cache_root=MODEL_CALL_ROOT / "rag_reasoner",
        mode=mode,
    )
    rows: list[dict[str, Any]] = []
    embedding_histories: list[dict[str, Any]] = []
    for public, oracle in mco02.load_corpus():
        history_id = str(public["history_id"])
        document_result = embedder.embed(
            key=f"{history_id}-documents",
            inputs=[str(row["text"]) for row in public["records"]],
        )
        query_result = embedder.embed(
            key=f"{history_id}-queries",
            inputs=[str(row["question"]) for row in public["queries"]],
        )
        index = HybridRagIndex(public["records"], document_result["matrix"])
        oracle_queries = {str(row["query_id"]): row for row in oracle["queries"]}
        for query_index, public_query in enumerate(public["queries"]):
            oracle_query = oracle_queries[str(public_query["query_id"])]
            for variant in ("dense_rag", "hybrid_rag", "entity_hybrid_rag"):
                selected = index.retrieve(
                    variant=variant,
                    question=str(public_query["question"]),
                    root_entity=str(public_query["root_entity"]),
                    query_embedding=query_result["matrix"][query_index],
                )
                rows.append(
                    rag_row(
                        variant=variant,
                        public=public,
                        public_query=public_query,
                        oracle_query=oracle_query,
                        selected=selected,
                        reasoner=reasoner,
                        ingestion_embedding_usage=document_result["usage"],
                        query_embedding_usage={
                            "model_calls": query_result["usage"]["model_calls"]
                            / len(public["queries"]),
                            "input_tokens": query_result["usage"]["input_tokens"]
                            / len(public["queries"]),
                        },
                    )
                )
        embedding_histories.append(
            {
                "history_id": history_id,
                "document_matrix_sha256": document_result["matrix_sha256"],
                "query_matrix_sha256": query_result["matrix_sha256"],
                "document_usage": document_result["usage"],
                "query_usage": query_result["usage"],
                "sparse_persistent_bytes": index.sparse.persistent_bytes,
                "dense_persistent_bytes": int(document_result["matrix"].nbytes),
            }
        )
        print(f"{run_id}: RAG completed {history_id}", file=sys.stderr, flush=True)
    output_root = SCIENTIFIC_ROOT / run_id
    write_jsonl(output_root / "rag_results.jsonl", rows)
    summary = {
        "experiment_id": "MCO-03",
        "mode": mode,
        "run_id": run_id,
        "population": {
            "rows": len(rows),
            "queries": mco02.EXPECTED_QUERIES,
            "variants": sorted({str(row["variant"]) for row in rows}),
        },
        "embedding_model": model_identity(EMBEDDING_MODEL),
        "embedding_histories": embedding_histories,
        "variants": summarize_rag(rows),
        "pass": bool(
            len(rows) == mco02.EXPECTED_QUERIES * 3
            and max(int(row["model_visible_records"]) for row in rows) <= RAG_CAPACITY
            and max(int(row["model_visible_tokens"]) for row in rows) <= CONTEXT_LIMIT
        ),
    }
    write_json(output_root / "rag_summary.json", summary)
    return summary


def aggregate_extraction(summary: dict[str, Any]) -> dict[str, Any]:
    histories = summary["histories"]
    learned_metrics = [row["learned_metrics"] for row in histories]
    transparent_metrics = [row["transparent_metrics"] for row in histories]
    learned_usage = [row["learned_usage"] for row in histories]
    record_count = sum(int(row["record_count"]) for row in learned_metrics)
    learned_exact = sum(int(row["exact_records"]) for row in learned_metrics)
    learned_critical_count = sum(
        int(row["critical_record_count"]) for row in learned_metrics
    )
    learned_critical_exact = sum(
        round(
            float(row["critical_relation_accuracy"])
            * int(row["critical_record_count"])
        )
        for row in learned_metrics
    )
    transparent_exact = sum(int(row["exact_records"]) for row in transparent_metrics)
    relation_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"n": 0, "exact": 0}
    )
    for metrics in learned_metrics:
        for relation, values in metrics["by_relation"].items():
            n = int(values["n"])
            relation_totals[relation]["n"] += n
            relation_totals[relation]["exact"] += round(float(values["accuracy"]) * n)
    return {
        "record_count": record_count,
        "history_count": len(histories),
        "learned": {
            "exact_records": learned_exact,
            "relation_accuracy": learned_exact / record_count,
            "critical_exact_records": learned_critical_exact,
            "critical_record_count": learned_critical_count,
            "critical_relation_accuracy": (
                learned_critical_exact / learned_critical_count
            ),
            "unresolved_records": sum(
                int(row["unresolved_records"]) for row in learned_metrics
            ),
            "minimum_history_relation_accuracy": min(
                float(row["relation_accuracy"]) for row in learned_metrics
            ),
            "by_history": {
                str(history["history_id"]): {
                    "history_size": history["history_size"],
                    "relation_accuracy": history["learned_metrics"]["relation_accuracy"],
                    "critical_relation_accuracy": history["learned_metrics"][
                        "critical_relation_accuracy"
                    ],
                }
                for history in histories
            },
            "by_relation": {
                relation: {
                    "n": values["n"],
                    "exact": values["exact"],
                    "accuracy": values["exact"] / values["n"],
                }
                for relation, values in sorted(relation_totals.items())
            },
            "usage": {
                "model_calls": sum(int(row["model_calls"]) for row in learned_usage),
                "input_tokens": sum(int(row["input_tokens"]) for row in learned_usage),
                "output_tokens": sum(int(row["output_tokens"]) for row in learned_usage),
                "expensive_token_units": sum(
                    int(row["expensive_token_units"]) for row in learned_usage
                ),
                "wall_time_seconds": sum(
                    float(row["wall_time_seconds"]) for row in learned_usage
                ),
            },
        },
        "transparent": {
            "exact_records": transparent_exact,
            "relation_accuracy": transparent_exact / record_count,
            "model_calls": 0,
            "expensive_token_units": 0,
        },
        "artifacts_identical_histories": sum(
            bool(row["artifacts_identical"]) for row in histories
        ),
    }


def replay_file_check() -> dict[str, Any]:
    pairs = {
        "planner": (
            SCIENTIFIC_ROOT / "live_planner/planner_results.jsonl",
            SCIENTIFIC_ROOT / "replay_planner/planner_results.jsonl",
        ),
        "rag": (
            SCIENTIFIC_ROOT / "live_rag/rag_results.jsonl",
            SCIENTIFIC_ROOT / "replay_rag/rag_results.jsonl",
        ),
    }
    comparisons: dict[str, Any] = {}
    for name, (live_path, replay_path) in pairs.items():
        live_hash = file_sha256(live_path) if live_path.exists() else None
        replay_hash = file_sha256(replay_path) if replay_path.exists() else None
        comparisons[name] = {
            "live_sha256": live_hash,
            "replay_sha256": replay_hash,
            "byte_identical": live_hash is not None and live_hash == replay_hash,
        }
    extraction_path = SCIENTIFIC_ROOT / "extraction_replay_check.json"
    extraction = read_json(extraction_path) if extraction_path.exists() else {"pass": False}
    return {
        "pass": bool(
            extraction.get("pass")
            and all(row["byte_identical"] for row in comparisons.values())
        ),
        "extraction": extraction,
        "result_files": comparisons,
    }


def evaluate_mco03_verdict(
    *,
    extraction: dict[str, Any],
    planner: dict[str, Any],
    rag: dict[str, Any],
    stability: dict[str, Any],
    integrity_pass: bool,
) -> tuple[str, dict[str, Any]]:
    criteria = read_json(CONFIG_PATH)["acceptance_criteria"]
    learned = extraction["learned"]
    transparent = extraction["transparent"]
    learned_planner = planner["variants"]["learned_single"]
    transparent_planner = planner["variants"]["transparent_compiler"]
    learned_extraction_quality = bool(
        learned["relation_accuracy"] >= criteria["minimum_relation_accuracy_overall"]
        and learned["critical_relation_accuracy"]
        >= criteria["minimum_critical_relation_accuracy"]
        and learned["minimum_history_relation_accuracy"]
        >= criteria["minimum_relation_accuracy_each_history"]
        and learned["unresolved_records"] == 0
    )
    learned_packet_quality = bool(
        learned_planner["packet_answer_accuracy"]
        >= criteria["minimum_packet_answer_accuracy"]
        and learned_planner["packet_provenance_accuracy"]
        >= criteria["minimum_packet_provenance_accuracy"]
        and learned_planner["packet_critical_recall"]
        >= criteria["minimum_packet_critical_recall"]
        and all(
            row["packet_answer_accuracy"]
            >= criteria["minimum_packet_answer_accuracy_each_load"]
            and row["packet_provenance_accuracy"]
            >= criteria["minimum_packet_provenance_accuracy_each_load"]
            for row in learned_planner["by_history_size"].values()
        )
    )
    frozen_downstream_quality = bool(
        learned_planner["model_answer_accuracy"]
        >= criteria["minimum_model_answer_accuracy"]
        and learned_planner["model_generated_provenance_accuracy"]
        >= criteria["minimum_model_generated_provenance_accuracy"]
    )
    stability_pass = bool(
        stability["raw_content_stability"]
        >= criteria["minimum_raw_response_stability"]
        and stability["semantic_relation_stability"]
        >= criteria["minimum_semantic_relation_stability"]
    )
    transparent_dominates = bool(
        transparent["relation_accuracy"] >= learned["relation_accuracy"]
        and transparent_planner["packet_answer_accuracy"]
        >= learned_planner["packet_answer_accuracy"]
        and transparent_planner["packet_provenance_accuracy"]
        >= learned_planner["packet_provenance_accuracy"]
        and transparent["model_calls"] < learned["usage"]["model_calls"]
        and transparent["expensive_token_units"]
        < learned["usage"]["expensive_token_units"]
    )
    best_rag_name, best_rag = max(
        rag["variants"].items(),
        key=lambda item: (
            float(item[1]["model_answer_accuracy"]),
            float(item[1]["model_generated_provenance_accuracy"]),
            float(item[1]["retrieval_recall"]),
        ),
    )
    hybrid_dominates = bool(
        best_rag["model_answer_accuracy"]
        >= learned_planner["model_answer_accuracy"]
        - criteria["rag_quality_equivalence_delta"]
        and best_rag["model_generated_provenance_accuracy"]
        >= learned_planner["model_generated_provenance_accuracy"]
        - criteria["rag_quality_equivalence_delta"]
        and best_rag["retrieval_recall"]
        >= criteria["minimum_rag_critical_recall_for_dominance"]
    )
    state_compiler_quality = bool(
        learned_extraction_quality
        and learned_packet_quality
        and frozen_downstream_quality
        and stability_pass
    )
    gates = {
        "integrity_pass": integrity_pass,
        "learned_extraction_quality": learned_extraction_quality,
        "learned_packet_quality": learned_packet_quality,
        "frozen_downstream_quality": frozen_downstream_quality,
        "stability_pass": stability_pass,
        "state_compiler_quality": state_compiler_quality,
        "transparent_compiler_dominates": transparent_dominates,
        "best_rag_variant": best_rag_name,
        "best_rag": best_rag,
        "hybrid_rag_dominates": hybrid_dominates,
        "learned_relation_accuracy": learned["relation_accuracy"],
        "learned_critical_relation_accuracy": learned[
            "critical_relation_accuracy"
        ],
        "learned_packet_answer_accuracy": learned_planner["packet_answer_accuracy"],
        "learned_packet_provenance_accuracy": learned_planner[
            "packet_provenance_accuracy"
        ],
        "learned_model_answer_accuracy": learned_planner["model_answer_accuracy"],
        "learned_model_generated_provenance_accuracy": learned_planner[
            "model_generated_provenance_accuracy"
        ],
    }
    if not integrity_pass:
        outcome = "MCO_03_ACCOUNTING_INVALID"
    elif not learned_extraction_quality:
        outcome = "MCO_03_RELATION_EXTRACTION_FAILS"
    elif transparent_dominates:
        outcome = "MCO_03_TRANSPARENT_COMPILER_DOMINATES"
    elif hybrid_dominates:
        outcome = "MCO_03_HYBRID_RAG_DOMINATES"
    elif state_compiler_quality:
        outcome = "MCO_03_STATE_COMPILER_ADVANCES"
    else:
        outcome = "MCO_03_LANGUAGE_BOUNDARY_INCOMPLETE"
    return outcome, gates


def render_report(
    verdict: dict[str, Any],
    extraction: dict[str, Any],
    planner: dict[str, Any],
    rag: dict[str, Any],
    verification: dict[str, Any],
) -> str:
    learned = extraction["learned"]
    transparent = extraction["transparent"]
    planner_variants = planner["variants"]
    lines = [
        "# MCO-03 — RELATION BOUNDARY / STATE COMPILER",
        "",
        "## Claim under test",
        "",
        (
            "A frozen, single-record constrained language normalizer can repair MCO-02's "
            "relation boundary and produce exact bounded state packets that retain quality "
            "against equally informed transparent compilation and strong dense/hybrid RAG controls."
        ),
        "",
        "## Check",
        "",
        (
            "Self-verified preregistered experiment on the unchanged MCO-02 population: "
            f"{extraction['history_count']} histories, {extraction['record_count']:,} records, "
            "64 queries, frozen Llama 3.1 8B extraction/reasoning, frozen EmbeddingGemma "
            "dense retrieval, deterministic transparent compilation, live stability repeats, "
            "and frozen-response replay."
        ),
        "",
        "| Component | Relation/answer | Critical/provenance | Model calls | Expensive units |",
        "|---|---:|---:|---:|---:|",
        (
            f"| learned single-record extraction | {learned['relation_accuracy']:.2%} | "
            f"{learned['critical_relation_accuracy']:.2%} | "
            f"{learned['usage']['model_calls']:,} | "
            f"{learned['usage']['expensive_token_units']:,} |"
        ),
        (
            f"| transparent compiler | {transparent['relation_accuracy']:.2%} | n/a | "
            f"0 | 0 |"
        ),
        (
            f"| learned exact packet | {planner_variants['learned_single']['packet_answer_accuracy']:.2%} | "
            f"{planner_variants['learned_single']['packet_provenance_accuracy']:.2%} | "
            "0 packet-selection calls | 0 packet-selection units |"
        ),
        (
            f"| frozen model over learned packet | {planner_variants['learned_single']['model_answer_accuracy']:.2%} | "
            f"{planner_variants['learned_single']['model_generated_provenance_accuracy']:.2%} | "
            f"{planner_variants['learned_single']['mean_query_model_calls']:.2f}/query | "
            f"{planner_variants['learned_single']['mean_query_expensive_token_units']:.1f}/query |"
        ),
    ]
    for name, values in rag["variants"].items():
        lines.append(
            f"| {name} | {values['model_answer_accuracy']:.2%} | "
            f"{values['model_generated_provenance_accuracy']:.2%} | 1 reasoning/query | "
            f"{values['mean_query_reasoning_expensive_token_units']:.1f}/query |"
        )
    lines.extend(
        [
            "",
            f"## Verdict — {verdict['overall_verification']}",
            "",
            f"`{verdict['verdict']}`",
            "",
            "## Criteria",
            "",
        ]
    )
    for key, value in verdict["gates"].items():
        if isinstance(value, bool):
            lines.append(f"- {key}: **{'PASS' if value else 'FAIL'}**")
    lines.extend(
        [
            "",
            "## Assumption register",
            "",
            "- Verified here: relation normalization, exact packet selection, bounded contexts, local token/call accounting, semantic/raw stability, and deterministic replay on the frozen synthetic renderer.",
            "- Checkable but unchecked here: arbitrary real documents, OCR, entity ambiguity, mutable schemas, access control, production concurrency, user demand, and deployment economics.",
            "- The transparent compiler knows the renderer's finite language templates but receives no oracle labels, queries, or answers. Its result cannot be generalized to open language.",
            "- Embedding retrieval uses the same complete raw record store and 16-record model-visible budget; entity-aware RAG additionally uses deterministic subject/entity parsing available in the public text.",
            "- Societal impact remains externally contingent and unfalsifiable in this experiment.",
            "",
            "## Credit assignment",
            "",
            "Learned normalization receives credit only if its frozen quality gates pass. Exact packet selection receives separate credit from the model's ability to copy provenance. If transparent compilation matches quality with zero model calls, it receives architecture credit for this synthetic family; learned retention and DMC receive none.",
            "",
            "## Verification gap",
            "",
            "No independent verifier was available, so the result is self-verified. Frozen replay checks the harness, not independent replication. The next authorized test, if any, must use real incident evidence and externally checkable outcomes.",
            "",
            "## Stop/continue",
            "",
            verdict["stop_decision"],
            "",
            "## Is this going to change the world?",
            "",
            f"**{verdict['world_impact_disposition']}.** {verdict['world_impact_reason']}",
            "",
            "## Maturity status",
            "",
            f"`{verdict['maturity_status']}`",
            "",
            "## Verification status",
            "",
            f"`{verification['verification_mode']}`; integrity: `{'PASS' if verification['all_integrity_checks_pass'] else 'FAIL'}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_artifact_manifest() -> dict[str, Any]:
    path = OUT / "SHA256SUMS.json"
    entries = {
        str(candidate.relative_to(ROOT)): {
            "sha256": file_sha256(candidate),
            "bytes": candidate.stat().st_size,
        }
        for candidate in sorted(OUT.rglob("*"))
        if candidate.is_file() and candidate != path
    }
    manifest = {
        "experiment_id": "MCO-03",
        "entry_count": len(entries),
        "entries": entries,
    }
    write_json(path, manifest)
    return manifest


def finalize() -> dict[str, Any]:
    readiness = preflight()
    live_extraction = read_json(
        SCIENTIFIC_ROOT / "live_extraction/extraction_summary.json"
    )
    live_planner = read_json(SCIENTIFIC_ROOT / "live_planner/planner_summary.json")
    live_rag = read_json(SCIENTIFIC_ROOT / "live_rag/rag_summary.json")
    stability = read_json(SCIENTIFIC_ROOT / "stability_recheck.json")
    replay = replay_file_check()
    extraction = aggregate_extraction(live_extraction)
    population_pass = bool(
        extraction["history_count"] == mco02.EXPECTED_HISTORIES
        and extraction["record_count"] == mco02.EXPECTED_RECORDS
        and live_planner["population"]["rows"] == mco02.EXPECTED_QUERIES * 2
        and live_rag["population"]["rows"] == mco02.EXPECTED_QUERIES * 3
    )
    integrity_pass = bool(
        readiness["pass"]
        and live_extraction["pass"]
        and live_planner["pass"]
        and live_rag["pass"]
        and stability["pass"]
        and replay["pass"]
        and population_pass
    )
    outcome, gates = evaluate_mco03_verdict(
        extraction=extraction,
        planner=live_planner,
        rag=live_rag,
        stability=stability,
        integrity_pass=integrity_pass,
    )
    if outcome == "MCO_03_STATE_COMPILER_ADVANCES":
        overall = "PASS"
    elif outcome in {
        "MCO_03_TRANSPARENT_COMPILER_DOMINATES",
        "MCO_03_HYBRID_RAG_DOMINATES",
        "MCO_03_RELATION_EXTRACTION_FAILS",
        "MCO_03_ACCOUNTING_INVALID",
    }:
        overall = "FAIL"
    else:
        overall = "INCONCLUSIVE"
    structured_product_path = bool(
        live_planner["variants"]["transparent_compiler"]["packet_answer_accuracy"]
        >= 0.95
        and live_planner["variants"]["transparent_compiler"][
            "packet_provenance_accuracy"
        ]
        >= 0.95
    )
    if outcome == "MCO_03_TRANSPARENT_COMPILER_DOMINATES" and structured_product_path:
        stop_decision = (
            "STOP learned extraction work on this synthetic family. CONTINUE only with "
            "MCO-04, a real software-incident state-compiler product proof using deterministic "
            "or constrained normalization, exact provenance, and a strong retrieval control."
        )
    elif outcome == "MCO_03_STATE_COMPILER_ADVANCES":
        stop_decision = (
            "STOP synthetic optimization. CONTINUE only with a preregistered real software-"
            "incident product proof; no learned retention or agent redesign is authorized."
        )
    else:
        stop_decision = (
            "STOP this branch at its terminal result. Do not proceed to a product claim "
            "unless the transparent structured path independently cleared exact packet gates."
        )
    verification = {
        "experiment_id": "MCO-03",
        "verification_mode": "SELF_VERIFIED",
        "preflight": readiness,
        "population_pass": population_pass,
        "stability": stability,
        "replay": replay,
        "all_integrity_checks_pass": integrity_pass,
    }
    verdict = {
        "experiment_id": "MCO-03",
        "status": "TERMINAL_VALID" if integrity_pass else "TERMINAL_INVALID",
        "verdict": outcome,
        "overall_verification": overall,
        "gate_pass": overall == "PASS",
        "gates": gates,
        "secondary_findings": {
            "learned_language_normalization": (
                "PASS" if gates["learned_extraction_quality"] else "FAIL"
            ),
            "structured_state_compiler_mechanics": (
                "PASS" if structured_product_path else "FAIL"
            ),
            "architecture_advantage": (
                "FAIL"
                if gates["transparent_compiler_dominates"]
                or gates["hybrid_rag_dominates"]
                else "PASS" if gates["state_compiler_quality"] else "INCONCLUSIVE"
            ),
        },
        "authorized_successor": (
            "MCO-04 — SOFTWARE INCIDENT STATE-COMPILER PRODUCT PROOF"
            if structured_product_path
            else None
        ),
        "stop_decision": stop_decision,
        "world_impact_disposition": "NOT_ESTABLISHED",
        "world_impact_reason": (
            "A controlled synthetic mechanism—even if valid—does not establish novelty, "
            "customer demand, independent replication, production reliability, adoption, "
            "or long-horizon societal impact."
        ),
        "maturity_status": (
            "MATURE_CONTROLLED_SYNTHETIC_BOUNDARY_TEST; "
            "EARLY_UNVALIDATED_REAL_WORLD_PRODUCT; WORLD_IMPACT_CLAIM_NOT_MATURE"
        ),
        "training_accounting": {
            "online_optimizer_steps": 0,
            "online_backward_calls": 0,
            "dmc_historical_optimizer_steps_preserved": 10880,
            "dmc_historical_training_label": "TRAINING_COST_UNKNOWN",
            "pretrained_model_training_cost": "UNKNOWN_NOT_ZERO",
        },
    }
    write_json(OUT / "aggregate.json", {
        "extraction": extraction,
        "planner": live_planner,
        "rag": live_rag,
    })
    write_json(OUT / "verification.json", verification)
    write_json(OUT / "MCO03_VERDICT.json", verdict)
    report = render_report(
        verdict, extraction, live_planner, live_rag, verification
    )
    (OUT / "MCO03_REPORT.md").write_text(report, encoding="utf-8")
    build_artifact_manifest()
    return verdict


def verify_final_artifacts() -> dict[str, Any]:
    manifest_path = OUT / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["missing-artifact-manifest"]}
    manifest = read_json(manifest_path)
    errors: list[str] = []
    for relative, expected in manifest.get("entries", {}).items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        if observed != expected.get("sha256"):
            errors.append(f"hash:{relative}")
    verification = read_json(OUT / "verification.json")
    verdict = read_json(OUT / "MCO03_VERDICT.json")
    if not verification.get("all_integrity_checks_pass"):
        errors.append("verification")
    if verdict.get("status") != "TERMINAL_VALID":
        errors.append("verdict-status")
    return {
        "pass": not errors,
        "entry_count": manifest.get("entry_count"),
        "verdict": verdict.get("verdict"),
        "world_impact_disposition": verdict.get("world_impact_disposition"),
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("engineering-smoke")
    subparsers.add_parser("verify-engineering")
    subparsers.add_parser("freeze")
    subparsers.add_parser("preflight")
    extraction_parser = subparsers.add_parser("run-extraction")
    extraction_parser.add_argument("--mode", choices=("live", "replay"), required=True)
    extraction_parser.add_argument("--run-id", required=True)
    planner_parser = subparsers.add_parser("run-planner")
    planner_parser.add_argument("--mode", choices=("live", "replay"), required=True)
    planner_parser.add_argument("--extraction-run-id", required=True)
    planner_parser.add_argument("--run-id", required=True)
    stability_parser = subparsers.add_parser("stability-recheck")
    stability_parser.add_argument("--extraction-run-id", required=True)
    stability_parser.add_argument("--fraction", type=float, default=0.1)
    replay_parser = subparsers.add_parser("extraction-replay-check")
    replay_parser.add_argument("--live-run-id", required=True)
    replay_parser.add_argument("--replay-run-id", required=True)
    rag_parser = subparsers.add_parser("run-rag")
    rag_parser.add_argument("--mode", choices=("live", "replay"), required=True)
    rag_parser.add_argument("--run-id", required=True)
    subparsers.add_parser("finalize")
    subparsers.add_parser("verify")
    args = parser.parse_args(argv)
    if args.command == "engineering-smoke":
        result = engineering_smoke()
    elif args.command == "verify-engineering":
        result = verify_engineering()
    elif args.command == "freeze":
        result = create_freeze()
    elif args.command == "preflight":
        result = preflight()
    elif args.command == "run-extraction":
        result = run_scientific_extraction(mode=args.mode, run_id=args.run_id)
    elif args.command == "run-planner":
        result = run_planner(
            mode=args.mode,
            extraction_run_id=args.extraction_run_id,
            run_id=args.run_id,
        )
    elif args.command == "stability-recheck":
        result = run_stability_recheck(
            extraction_run_id=args.extraction_run_id,
            fraction=args.fraction,
        )
    elif args.command == "extraction-replay-check":
        result = extraction_replay_check(
            live_run_id=args.live_run_id,
            replay_run_id=args.replay_run_id,
        )
    elif args.command == "run-rag":
        result = run_rag(mode=args.mode, run_id=args.run_id)
    elif args.command == "finalize":
        result = finalize()
    elif args.command == "verify":
        result = verify_final_artifacts()
    else:
        parser.error(f"unknown command: {args.command}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
