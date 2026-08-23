#!/usr/bin/env python3
from __future__ import annotations

"""MCO-02 language/inference-boundary benchmark and frozen-response replay harness."""

import argparse
import hashlib
import json
import math
import platform
import re
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_mco01 as mco01  # noqa: E402


EXPERIMENT_ROOT = ROOT / "experiments/mco02"
CONFIG_PATH = EXPERIMENT_ROOT / "MCO02_CONFIG.json"
CONTRACT_PATH = EXPERIMENT_ROOT / "MCO02_CONTRACT.md"
FREEZE_PATH = EXPERIMENT_ROOT / "MCO02_FREEZE.json"
MCO01_RECEIPT_PATH = ROOT / "experiments/mco01/MCO01_TERMINAL_RECEIPT.json"
OUT = ROOT / "artifacts/mco02"
CORPUS_ROOT = OUT / "corpus"
CORPUS_MANIFEST_PATH = CORPUS_ROOT / "corpus_manifest.json"
CALL_CACHE_ROOT = OUT / "model_calls"
LIVE_ROOT = OUT / "live"
REPLAY_ROOT = OUT / "replays"

HISTORY_SIZES = (100, 1_000, 5_000, 10_000)
SEEDS = (2601, 2602)
QUERIES_PER_HISTORY = 8
EXPECTED_HISTORIES = len(HISTORY_SIZES) * len(SEEDS)
EXPECTED_QUERIES = EXPECTED_HISTORIES * QUERIES_PER_HISTORY
EXPECTED_RECORDS = sum(HISTORY_SIZES) * len(SEEDS)
CAPACITY = 16
EXTRACTION_BATCH_SIZE = 12
ROLLING_CHUNK_SIZE = 256
SUMMARY_RECORDS = 8
RECENT_SUMMARY_RECORDS = 8
RAG_TOP_K = 16
MODEL_NAME = "llama3.1:8b"
MODEL_BLOB_SHA256 = (
    "667b0c1932bc6ffc593ed1d03f895bf2dc8dc6df21db3042284a6f4416b06a29"
)
MODEL_SEED = 20260822
EXTRACTION_CONTEXT = 8192
BOUNDED_CONTEXT = 8192
SUMMARY_CONTEXT = 16384
FULL_CONTEXT_LIMIT = 32768
OUTPUT_TOKEN_WEIGHT = 4
QUERY_COUNTS = (1, 2, 8, 32, 128)

SYSTEMS = (
    "full_context",
    "recent_window",
    "rolling_summary",
    "conventional_rag",
    "structured_exact_planner",
    "iterative_need_retrieval",
)
BOUNDED_SYSTEMS = SYSTEMS[1:]
QUALITY_METRICS = (
    "answer_accuracy",
    "critical_recall",
    "dependency_chain_accuracy",
    "temporal_update_accuracy",
    "provenance_accuracy",
)
FAILURE_CLASSES = (
    "LANGUAGE_EXTRACTION_FAILURE",
    "INDEXING_FAILURE",
    "RETRIEVAL_FAILURE",
    "ACQUISITION_PLANNING_FAILURE",
    "REASONING_FAILURE",
    "PROVENANCE_FAILURE",
)
RUNTIME_FIELDS = frozenset(
    {
        "wall_time_seconds",
        "ingestion_wall_time_seconds",
        "query_wall_time_seconds",
        "index_wall_time_seconds",
    }
)

ALLOWED_RELATIONS = ("depends_on", "renamed_to", "failure_threshold")
ENTITY_PATTERN = re.compile(r"\bentity\s+([ed]_[0-9a-f]{16})\b", re.IGNORECASE)
HEADER_PATTERN = re.compile(
    r"^\[Record (r_[0-9a-f]{16}); source (AUTHORITY|CURATED|UNVERIFIED); event (\d+)\]\s+"
)
SUPERSEDES_PATTERN = re.compile(
    r"(?:replacing|superseding) record (r_[0-9a-f]{16})", re.IGNORECASE
)
TEMPERATURE_PATTERN = re.compile(r"(?<![0-9])(-?\d+)\s+C\b", re.IGNORECASE)
RECORD_ID_PATTERN = re.compile(r"\br_[0-9a-f]{16}\b")
STRUCTURED_THRESHOLD_PATTERN = re.compile(
    r"subject=([ed]_[0-9a-f]{16});\s+relation=failure_threshold;\s+object=(-?\d+)"
)
FORBIDDEN_LANGUAGE_MARKERS = (
    "depends_on",
    "renamed_to",
    "failure_threshold",
    "utility_label",
    "answer_label",
    "critical_record",
    "query_id",
)

DEPENDENCY_TEMPLATES = (
    "Entity {subject} relies on entity {object}.",
    "Regarding entity {subject}, its upstream requirement is entity {object}.",
    "The operations of entity {subject} draw on entity {object}.",
    "When entity {subject} runs, it depends upon entity {object}.",
    "Entity {subject} cannot proceed without entity {object}.",
    "For entity {subject}, the supporting requirement is entity {object}.",
)
RENAME_TEMPLATES = (
    "Entity {subject} is now known as entity {object}.",
    "Regarding entity {subject}, the registry changed its designation to entity {object}.",
    "Entity {subject} received the replacement name entity {object}.",
    "The old label entity {subject} gave way to entity {object}.",
    "Entity {subject} was redesignated as entity {object}.",
    "For entity {subject}, staff now use the name entity {object}.",
)
THRESHOLD_TEMPLATES = (
    "Entity {subject} has a failure threshold of {object} C.",
    "Regarding entity {subject}, it ceases safe operation below {object} C.",
    "The minimum safe temperature recorded for entity {subject} is {object} C.",
    "At {object} C, entity {subject} reaches its documented safety floor.",
    "Entity {subject} is not rated for operation below {object} C.",
    "The archived temperature floor for entity {subject} is {object} C.",
)
NARRATIVE_PREFIXES = (
    "",
    "During a routine archive review, ",
    "After an unrelated maintenance discussion, ",
    "In the ordinary course of plant reporting, ",
)
NARRATIVE_SUFFIXES = (
    "",
    " The filing also mentioned routine paperwork with no operational consequence.",
    " This was recorded alongside unrelated scheduling notes.",
    " No other part of the archival narrative changed this statement.",
)

EXTRACTION_SYSTEM_PROMPT = (
    "Classify the semantic relationship expressed by every input sentence. Choose "
    "depends_on when one entity relies on, draws on, cannot proceed without, or has "
    "another entity as an upstream or supporting requirement. Choose renamed_to when an "
    "old entity label is replaced by a new entity name or designation. Choose "
    "failure_threshold when the sentence gives a failure, safety-floor, minimum-safe-"
    "temperature, or not-rated-below temperature for one entity. Return one relation for "
    "every sentence in the original order using the required JSON schema."
)

FINAL_REASONING_SYSTEM_PROMPT = (
    "Answer only from the supplied evidence. Current truth rules: an explicitly "
    "replaced or superseded record is inactive; among remaining contradictions, source "
    "priority is AUTHORITY over CURATED over UNVERIFIED, then later event time. Follow "
    "renames before upstream requirements until reaching a temperature threshold. "
    "The terminal_entity is the subject of the winning failure-threshold record, and the "
    "failure_threshold is that record's integer value, never the deployment temperature. "
    "path_record_ids contains the winning record IDs in traversal order. Return only the "
    "required evidence-grounded JSON. Inspection is derived for every system by the same "
    "transparent integer comparison after this response."
)

NEED_SYSTEM_PROMPT = (
    "Select the winning continuation for demand-driven retrieval from only the supplied "
    "candidate records. An explicitly superseded record is inactive. Among remaining "
    "contradictions, source priority is AUTHORITY over CURATED over UNVERIFIED, then later "
    "event time. Return the winning record ID and its object entity through the required "
    "JSON schema. The two fields must describe the same visible record. Do not invent IDs."
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value) + "\n" if compact else json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def chunks(values: Sequence[Any], size: int) -> Iterable[tuple[int, Sequence[Any]]]:
    for start in range(0, len(values), size):
        yield start, values[start : start + size]


def stable_choice(values: Sequence[str], *parts: Any) -> tuple[int, str]:
    index = mco01.stable_int(*parts) % len(values)
    return index, values[index]


def renderer_metadata(history_id: str, row: dict[str, Any]) -> dict[str, Any]:
    relation = str(row["relation"])
    templates = {
        "depends_on": DEPENDENCY_TEMPLATES,
        "renamed_to": RENAME_TEMPLATES,
        "failure_threshold": THRESHOLD_TEMPLATES,
    }[relation]
    template_index, _ = stable_choice(
        templates, history_id, row["record_id"], "relation-template"
    )
    prefix_index, _ = stable_choice(
        NARRATIVE_PREFIXES, history_id, row["record_id"], "narrative-prefix"
    )
    suffix_index, _ = stable_choice(
        NARRATIVE_SUFFIXES, history_id, row["record_id"], "narrative-suffix"
    )
    return {
        "relation": relation,
        "template_index": template_index,
        "prefix_index": prefix_index,
        "suffix_index": suffix_index,
        "uses_local_pronoun": "its " in templates[template_index]
        or " it " in templates[template_index],
        "uses_irrelevant_narrative": prefix_index > 0 or suffix_index > 0,
    }


def render_record(history_id: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    metadata = renderer_metadata(history_id, row)
    templates = {
        "depends_on": DEPENDENCY_TEMPLATES,
        "renamed_to": RENAME_TEMPLATES,
        "failure_threshold": THRESHOLD_TEMPLATES,
    }[str(row["relation"])]
    sentence = templates[metadata["template_index"]].format(
        subject=row["subject"], object=row["object"]
    )
    operation = str(row["operation"])
    if operation == "correct":
        administrative = f"a correction replacing record {row['supersedes']} states: "
    elif operation == "supersede":
        administrative = f"an update superseding record {row['supersedes']} states: "
    elif operation == "observe":
        administrative = "an observation states: "
    else:
        administrative = "the ledger states: "
    text = (
        f"[Record {row['record_id']}; source {row['source']}; event {row['event_time']}] "
        f"At event time {row['event_time']}, "
        f"{NARRATIVE_PREFIXES[metadata['prefix_index']]}{administrative}{sentence}"
        f"{NARRATIVE_SUFFIXES[metadata['suffix_index']]}"
    )
    return text, metadata


def parse_scaffold(text: str) -> dict[str, Any]:
    header = HEADER_PATTERN.match(text)
    if header is None:
        raise ValueError("language record has an invalid provenance header")
    record_id, source, event_text = header.groups()
    entities = ENTITY_PATTERN.findall(text)
    lowered = text.lower()
    supersedes_match = SUPERSEDES_PATTERN.search(text)
    supersedes = supersedes_match.group(1) if supersedes_match else None
    if "a correction replacing record" in lowered:
        operation = "correct"
    elif "an update superseding record" in lowered:
        operation = "supersede"
    elif "an observation states" in lowered:
        operation = "observe"
    else:
        operation = "assert"
    if len(entities) >= 2:
        subject = entities[0]
        object_value: str | int = entities[1]
    elif len(entities) == 1:
        subject = entities[0]
        temperature = TEMPERATURE_PATTERN.findall(text)
        if not temperature:
            raise ValueError(f"one-entity record has no temperature: {record_id}")
        object_value = int(temperature[-1])
    else:
        raise ValueError(f"record has no entity IDs: {record_id}")
    return {
        "record_id": record_id,
        "position": int(event_text),
        "event_time": int(event_text),
        "subject": subject,
        "relation": None,
        "object": object_value,
        "source": source,
        "operation": operation,
        "supersedes": supersedes,
    }


def render_question(query: dict[str, Any]) -> str:
    return (
        f"Entity {query['root_entity']} is deployed at "
        f"{query['deployment_temperature']} C. Starting from that entity, follow its "
        "current name changes and upstream requirements until a temperature threshold "
        "is reached. Identify the terminal entity, threshold, whether inspection is "
        "required, and the ordered provenance record IDs."
    )


def corpus_names(history_size: int, seed: int) -> tuple[str, str]:
    stem = f"history_n{history_size}_s{seed}.json"
    return f"public/{stem}", f"oracle/{stem}"


def build_language_history(seed: int, history_size: int) -> tuple[dict[str, Any], dict[str, Any]]:
    semantic = mco01.build_history(seed, history_size)
    public_records: list[dict[str, Any]] = []
    rendering: dict[str, dict[str, Any]] = {}
    for row in semantic["records"]:
        text, metadata = render_record(str(semantic["history_id"]), row)
        public_records.append(
            {
                "record_id": row["record_id"],
                "position": row["position"],
                "text": text,
            }
        )
        rendering[str(row["record_id"])] = metadata
    public_queries = [
        {
            "query_id": query["query_id"],
            "root_entity": query["root_entity"],
            "deployment_temperature": query["deployment_temperature"],
            "question": render_question(query),
        }
        for query in semantic["queries"]
    ]
    public = {
        "schema_version": 1,
        "experiment_id": "MCO-02",
        "history_id": semantic["history_id"].replace("mco01_", "mco02_"),
        "semantic_history_id": semantic["history_id"],
        "seed": seed,
        "history_size": history_size,
        "records": public_records,
        "queries": public_queries,
    }
    oracle = {
        "schema_version": 1,
        "experiment_id": "MCO-02",
        "history_id": public["history_id"],
        "semantic_history_sha256": digest(semantic),
        "source_priority": mco01.SOURCE_PRIORITY,
        "records": semantic["records"],
        "queries": semantic["queries"],
        "rendering_metadata": rendering,
    }
    return public, oracle


def verify_language_history(public: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    public_records = list(public.get("records", []))
    semantic_records = list(oracle.get("records", []))
    if len(public_records) != int(public.get("history_size", -1)):
        errors.append("public-record-count")
    if len(public_records) != len(semantic_records):
        errors.append("public-oracle-record-count")
    if len(public.get("queries", [])) != QUERIES_PER_HISTORY:
        errors.append("public-query-count")
    if len(oracle.get("queries", [])) != QUERIES_PER_HISTORY:
        errors.append("oracle-query-count")
    semantic_by_id = {str(row["record_id"]): row for row in semantic_records}
    template_counts: Counter[tuple[str, int]] = Counter()
    pronoun_count = 0
    narrative_count = 0
    for position, row in enumerate(public_records):
        record_id = str(row.get("record_id"))
        semantic = semantic_by_id.get(record_id)
        if semantic is None:
            errors.append(f"unknown-record:{record_id}")
            continue
        if int(row.get("position", -1)) != position:
            errors.append(f"position:{record_id}")
        text = str(row.get("text", ""))
        for marker in FORBIDDEN_LANGUAGE_MARKERS:
            if marker.lower() in text.lower():
                errors.append(f"forbidden-language:{record_id}:{marker}")
        try:
            scaffold = parse_scaffold(text)
        except ValueError as exc:
            errors.append(f"scaffold:{record_id}:{exc}")
            continue
        expected_without_relation = {
            key: value for key, value in semantic.items() if key != "relation"
        }
        observed_without_relation = {
            key: value for key, value in scaffold.items() if key != "relation"
        }
        if observed_without_relation != expected_without_relation:
            errors.append(f"scaffold-semantics:{record_id}")
        metadata = oracle["rendering_metadata"][record_id]
        if metadata["relation"] != semantic["relation"]:
            errors.append(f"render-relation:{record_id}")
        template_counts[(metadata["relation"], int(metadata["template_index"]))] += 1
        pronoun_count += int(metadata["uses_local_pronoun"])
        narrative_count += int(metadata["uses_irrelevant_narrative"])
    public_query_ids = [str(row["query_id"]) for row in public.get("queries", [])]
    oracle_query_ids = [str(row["query_id"]) for row in oracle.get("queries", [])]
    if public_query_ids != oracle_query_ids:
        errors.append("query-identity")
    semantic_check = mco01.verify_history(
        {
            "history_id": oracle["history_id"],
            "history_size": len(semantic_records),
            "records": semantic_records,
            "queries": oracle["queries"],
        }
    )
    if not semantic_check["pass"]:
        errors.append("semantic-reconstruction")
    return {
        "pass": not errors,
        "history_id": public.get("history_id"),
        "record_count": len(public_records),
        "query_count": len(public.get("queries", [])),
        "template_counts": {
            f"{relation}:{index}": value
            for (relation, index), value in sorted(template_counts.items())
        },
        "local_pronoun_records": pronoun_count,
        "irrelevant_narrative_records": narrative_count,
        "semantic_check": semantic_check,
        "errors": errors,
    }


def generate_corpus(output_root: Path = CORPUS_ROOT) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"corpus output is not empty: {output_root}")
    files: list[dict[str, Any]] = []
    integrity_rows: list[dict[str, Any]] = []
    aggregate_templates: Counter[str] = Counter()
    aggregate_pronouns = 0
    aggregate_narrative = 0
    for history_size in HISTORY_SIZES:
        for seed in SEEDS:
            public, oracle = build_language_history(seed, history_size)
            check = verify_language_history(public, oracle)
            if not check["pass"]:
                raise RuntimeError(canonical(check))
            public_name, oracle_name = corpus_names(history_size, seed)
            public_path = output_root / public_name
            oracle_path = output_root / oracle_name
            write_json(public_path, public, compact=True)
            write_json(oracle_path, oracle, compact=True)
            files.append(
                {
                    "history_id": public["history_id"],
                    "history_size": history_size,
                    "seed": seed,
                    "public_path": public_name,
                    "public_sha256": file_sha256(public_path),
                    "public_bytes": public_path.stat().st_size,
                    "oracle_path": oracle_name,
                    "oracle_sha256": file_sha256(oracle_path),
                    "oracle_bytes": oracle_path.stat().st_size,
                    "semantic_history_sha256": oracle["semantic_history_sha256"],
                    "query_count": len(public["queries"]),
                }
            )
            integrity_rows.append(check)
            aggregate_templates.update(check["template_counts"])
            aggregate_pronouns += int(check["local_pronoun_records"])
            aggregate_narrative += int(check["irrelevant_narrative_records"])
    relation_template_coverage = {
        relation: sum(
            1
            for key, count in aggregate_templates.items()
            if key.startswith(f"{relation}:") and count > 0
        )
        for relation in ("depends_on", "renamed_to", "failure_threshold")
    }
    counts = {
        "histories": len(files),
        "queries": sum(int(row["query_count"]) for row in files),
        "semantic_records": sum(int(row["history_size"]) for row in files),
    }
    integrity_pass = bool(
        all(row["pass"] for row in integrity_rows)
        and counts
        == {
            "histories": EXPECTED_HISTORIES,
            "queries": EXPECTED_QUERIES,
            "semantic_records": EXPECTED_RECORDS,
        }
        and all(value >= 4 for value in relation_template_coverage.values())
        and aggregate_pronouns > 0
        and aggregate_narrative > 0
    )
    manifest = {
        "experiment_id": "MCO-02",
        "schema_version": 1,
        "status": "FROZEN_CORPUS_CANDIDATE",
        "config_sha256": file_sha256(CONFIG_PATH),
        "contract_sha256": file_sha256(CONTRACT_PATH),
        "mco01_runner_sha256": file_sha256(ROOT / "scripts/run_mco01.py"),
        "mco02_generator_sha256": file_sha256(Path(__file__)),
        "counts": counts,
        "history_sizes": list(HISTORY_SIZES),
        "seeds": list(SEEDS),
        "files": files,
        "integrity": {
            "pass": integrity_pass,
            "history_checks_passed": sum(row["pass"] for row in integrity_rows),
            "history_checks_expected": EXPECTED_HISTORIES,
            "relation_template_coverage": relation_template_coverage,
            "template_counts": dict(sorted(aggregate_templates.items())),
            "local_pronoun_records": aggregate_pronouns,
            "irrelevant_narrative_records": aggregate_narrative,
            "forbidden_language_markers": list(FORBIDDEN_LANGUAGE_MARKERS),
        },
    }
    manifest["corpus_digest"] = digest(
        {
            "files": [
                {
                    "public_path": row["public_path"],
                    "public_sha256": row["public_sha256"],
                    "oracle_path": row["oracle_path"],
                    "oracle_sha256": row["oracle_sha256"],
                }
                for row in files
            ],
            "counts": counts,
        }
    )
    if not integrity_pass:
        raise RuntimeError("corpus integrity failed")
    write_json(output_root / "corpus_manifest.json", manifest)
    return manifest


def verify_corpus(corpus_root: Path = CORPUS_ROOT, *, deep: bool = True) -> dict[str, Any]:
    manifest_path = corpus_root / "corpus_manifest.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["missing-corpus-manifest"]}
    manifest = read_json(manifest_path)
    errors: list[str] = []
    if manifest.get("counts") != {
        "histories": EXPECTED_HISTORIES,
        "queries": EXPECTED_QUERIES,
        "semantic_records": EXPECTED_RECORDS,
    }:
        errors.append("population-counts")
    if manifest.get("config_sha256") != file_sha256(CONFIG_PATH):
        errors.append("config-hash")
    if manifest.get("contract_sha256") != file_sha256(CONTRACT_PATH):
        errors.append("contract-hash")
    if manifest.get("mco02_generator_sha256") != file_sha256(Path(__file__)):
        errors.append("generator-hash")
    file_checks: list[dict[str, Any]] = []
    deep_checks: list[dict[str, Any]] = []
    for row in manifest.get("files", []):
        public_path = corpus_root / row["public_path"]
        oracle_path = corpus_root / row["oracle_path"]
        public_hash = file_sha256(public_path) if public_path.exists() else None
        oracle_hash = file_sha256(oracle_path) if oracle_path.exists() else None
        passed = public_hash == row["public_sha256"] and oracle_hash == row["oracle_sha256"]
        if not passed:
            errors.append(f"file-hash:{row.get('history_id')}")
        file_checks.append(
            {
                "history_id": row.get("history_id"),
                "public_pass": public_hash == row.get("public_sha256"),
                "oracle_pass": oracle_hash == row.get("oracle_sha256"),
                "pass": passed,
            }
        )
        if deep and passed:
            check = verify_language_history(read_json(public_path), read_json(oracle_path))
            deep_checks.append(check)
            if not check["pass"]:
                errors.append(f"deep-integrity:{row.get('history_id')}")
    observed_digest = digest(
        {
            "files": [
                {
                    "public_path": row["public_path"],
                    "public_sha256": row["public_sha256"],
                    "oracle_path": row["oracle_path"],
                    "oracle_sha256": row["oracle_sha256"],
                }
                for row in manifest.get("files", [])
            ],
            "counts": manifest.get("counts"),
        }
    )
    if observed_digest != manifest.get("corpus_digest"):
        errors.append("corpus-digest")
    return {
        "pass": not errors,
        "manifest_sha256": file_sha256(manifest_path),
        "corpus_digest": observed_digest,
        "file_checks": file_checks,
        "deep_checks": deep_checks,
        "errors": errors,
    }


def load_corpus() -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
    manifest = read_json(CORPUS_MANIFEST_PATH)
    for row in manifest["files"]:
        yield (
            read_json(CORPUS_ROOT / row["public_path"]),
            read_json(CORPUS_ROOT / row["oracle_path"]),
        )


class FrozenOllamaClient:
    def __init__(
        self,
        cache_root: Path = CALL_CACHE_ROOT,
        *,
        mode: str = "live",
        base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        if mode not in {"live", "replay"}:
            raise ValueError(f"invalid client mode: {mode}")
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
            "model": MODEL_NAME,
            "messages": list(messages),
            "stream": False,
            "keep_alive": "30m",
            "options": options,
        }
        if format_spec is not None:
            payload["format"] = format_spec
        request_digest = digest(payload)
        call_id = f"{re.sub(r'[^a-zA-Z0-9_.-]+', '-', key)[:80]}__{request_digest[:16]}"
        path = self.cache_path(purpose, call_id)
        self.used_call_ids.append(f"{purpose}/{call_id}")
        if path.exists() and not force_live_repeat:
            cached = read_json(path)
            if cached.get("request_sha256") != request_digest:
                raise RuntimeError(f"call-cache request mismatch: {path}")
            cached = dict(cached)
            cached["cache_hit"] = True
            return cached
        if self.mode == "replay" and not force_live_repeat:
            raise FileNotFoundError(f"missing frozen model response: {path}")

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
            raise RuntimeError(f"Ollama call failed for {purpose}/{key}: {exc}") from exc
        wall = time.perf_counter() - started
        record = {
            "schema_version": 1,
            "purpose": purpose,
            "key": key,
            "call_id": call_id,
            "request_sha256": request_digest,
            "request": payload,
            "response": raw,
            "response_content_sha256": hashlib.sha256(
                str(raw.get("message", {}).get("content", "")).encode("utf-8")
            ).hexdigest(),
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
        path = self.cache_path(purpose, call_id)
        if not path.exists():
            raise FileNotFoundError(path)
        return read_json(path)


def model_identity() -> dict[str, Any]:
    def post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://127.0.0.1:11434{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    show = post("/api/show", {"model": MODEL_NAME})
    with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=30) as response:
        version = json.load(response)
    info = show.get("model_info", {})
    modelfile = str(show.get("modelfile", ""))
    blob_match = re.search(r"sha256-([0-9a-f]{64})", modelfile)
    observed_blob = blob_match.group(1) if blob_match else None
    result = {
        "pass": bool(
            observed_blob == MODEL_BLOB_SHA256
            and show.get("details", {}).get("parameter_size") == "8.0B"
            and show.get("details", {}).get("quantization_level") == "Q4_K_M"
            and int(info.get("llama.context_length", 0)) == 131072
            and str(version.get("version")) == "0.21.2"
        ),
        "model": MODEL_NAME,
        "blob_sha256": observed_blob,
        "parameter_size": show.get("details", {}).get("parameter_size"),
        "quantization": show.get("details", {}).get("quantization_level"),
        "native_context_length": info.get("llama.context_length"),
        "tokenizer_model": info.get("tokenizer.ggml.model"),
        "tokenizer_pretokenizer": info.get("tokenizer.ggml.pre"),
        "ollama_version": version.get("version"),
    }
    return result


def usage_for_calls(
    client: FrozenOllamaClient, qualified_ids: Sequence[str]
) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(qualified_ids))
    records = [client.resolve(call_id) for call_id in unique_ids]
    return {
        "model_calls": len(records),
        "input_tokens": sum(
            int(row["accounting"]["prompt_eval_count"]) for row in records
        ),
        "output_tokens": sum(int(row["accounting"]["eval_count"]) for row in records),
        "wall_time_seconds": sum(
            float(row["accounting"]["wall_time_seconds"]) for row in records
        ),
        "prompt_eval_duration_ns": sum(
            int(row["accounting"]["prompt_eval_duration_ns"]) for row in records
        ),
        "eval_duration_ns": sum(
            int(row["accounting"]["eval_duration_ns"]) for row in records
        ),
        "call_ids": unique_ids,
    }


def relation_format_schema(expected_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "relations": {
                "type": "array",
                "items": {"type": "string", "enum": list(ALLOWED_RELATIONS)},
                "minItems": expected_count,
                "maxItems": expected_count,
            }
        },
        "required": ["relations"],
        "additionalProperties": False,
    }


def parse_relation_json(content: str, expected_count: int) -> list[str] | None:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict) or set(parsed) != {"relations"}:
        return None
    relations = parsed["relations"]
    if (
        not isinstance(relations, list)
        or len(relations) != expected_count
        or any(value not in ALLOWED_RELATIONS for value in relations)
    ):
        return None
    return [str(value) for value in relations]


def semantic_clause(text: str) -> str:
    """Remove deterministic renderer scaffolding before model relation classification."""
    marker = "states: "
    if marker not in text:
        raise ValueError("language record has no semantic-clause marker")
    clause = text.split(marker, 1)[1]
    for suffix in NARRATIVE_SUFFIXES[1:]:
        if clause.endswith(suffix):
            clause = clause[: -len(suffix)]
            break
    clause = clause.strip()
    if not clause:
        raise ValueError("language record has an empty semantic clause")
    return clause


def extraction_user_prompt(rows: Sequence[dict[str, Any]]) -> str:
    return "\n".join(
        f"{index + 1}. {semantic_clause(str(row['text']))}"
        for index, row in enumerate(rows)
    )


def extract_history(
    client: FrozenOllamaClient,
    public: dict[str, Any],
    oracle: dict[str, Any],
) -> dict[str, Any]:
    records = list(public["records"])
    predicted_relations: list[str | None] = [None] * len(records)
    call_ids: list[str] = []
    malformed_calls: list[str] = []

    def classify(start: int, batch: Sequence[dict[str, Any]], depth: int = 0) -> None:
        key = f"{public['history_id']}-records-{start}-{start + len(batch) - 1}-d{depth}"
        response = client.call(
            purpose="extraction",
            key=key,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": extraction_user_prompt(batch)},
            ],
            num_ctx=EXTRACTION_CONTEXT,
            num_predict=max(96, len(batch) * 12),
            format_spec=relation_format_schema(len(batch)),
        )
        qualified = f"extraction/{response['call_id']}"
        call_ids.append(qualified)
        content = str(response["response"].get("message", {}).get("content", ""))
        relations = parse_relation_json(content, len(batch))
        if relations is not None:
            for offset, relation in enumerate(relations):
                predicted_relations[start + offset] = relation
            return
        malformed_calls.append(qualified)
        if len(batch) == 1:
            predicted_relations[start] = None
            return
        midpoint = len(batch) // 2
        classify(start, batch[:midpoint], depth + 1)
        classify(start + midpoint, batch[midpoint:], depth + 1)

    for start, batch in chunks(records, EXTRACTION_BATCH_SIZE):
        classify(start, batch)

    predicted_records: list[dict[str, Any]] = []
    for row, relation in zip(records, predicted_relations, strict=True):
        extracted = parse_scaffold(str(row["text"]))
        extracted["relation"] = relation or "unknown"
        predicted_records.append(extracted)

    expected_records = list(oracle["records"])
    exact = [predicted == expected for predicted, expected in zip(predicted_records, expected_records, strict=True)]
    relation_exact = [
        predicted["relation"] == expected["relation"]
        for predicted, expected in zip(predicted_records, expected_records, strict=True)
    ]
    nonrelation_exact = [
        {key: value for key, value in predicted.items() if key != "relation"}
        == {key: value for key, value in expected.items() if key != "relation"}
        for predicted, expected in zip(predicted_records, expected_records, strict=True)
    ]
    template_counts: Counter[str] = Counter()
    template_correct: Counter[str] = Counter()
    for predicted, expected in zip(predicted_records, expected_records, strict=True):
        metadata = oracle["rendering_metadata"][str(expected["record_id"])]
        key = f"{metadata['relation']}:{metadata['template_index']}"
        template_counts[key] += 1
        template_correct[key] += int(predicted == expected)
    usage = usage_for_calls(client, call_ids)
    index = mco01.index_records(predicted_records)
    indexing_errors: list[str] = []
    for row in predicted_records:
        key = (str(row["subject"]), str(row["relation"]))
        if row not in index.get(key, []):
            indexing_errors.append(str(row["record_id"]))
    artifact = {
        "experiment_id": "MCO-02",
        "history_id": public["history_id"],
        "records": predicted_records,
        "shared_extraction_sha256": digest(predicted_records),
        "metrics": {
            "record_count": len(predicted_records),
            "exact_records": sum(exact),
            "extraction_precision": statistics.fmean(exact),
            "extraction_recall": statistics.fmean(exact),
            "relation_accuracy": statistics.fmean(relation_exact),
            "nonrelation_scaffold_accuracy": statistics.fmean(nonrelation_exact),
            "malformed_model_calls": len(malformed_calls),
            "unresolved_records": sum(
                relation is None for relation in predicted_relations
            ),
            "template_accuracy": {
                key: template_correct[key] / template_counts[key]
                for key in sorted(template_counts)
            },
        },
        "indexing": {
            "pass": not indexing_errors,
            "indexed_records": sum(len(values) for values in index.values()),
            "errors": indexing_errors,
        },
        "usage": usage,
        "malformed_call_ids": malformed_calls,
    }
    return artifact


SUMMARY_SYSTEM_PROMPT = (
    "Maintain a bounded query-independent memory for future questions that follow entity "
    "renames, upstream requirements, corrections, source authority, and temperature "
    "thresholds. From the candidate event records, select at most eight record IDs worth "
    "retaining. Prefer current authoritative records and dependency coverage, but no "
    "future query is available. Return only one selected record ID per line, no explanation."
)


def parse_selected_record_ids(content: str, allowed: set[str]) -> tuple[list[str], list[str]]:
    observed = re.findall(r"r_[0-9a-f]{16}", content)
    selected: list[str] = []
    invalid: list[str] = []
    for record_id in observed:
        if record_id not in allowed:
            invalid.append(record_id)
        elif record_id not in selected:
            selected.append(record_id)
    return selected[:SUMMARY_RECORDS], invalid


def build_rolling_summary(
    client: FrozenOllamaClient, public: dict[str, Any]
) -> dict[str, Any]:
    records = list(public["records"])
    by_id = {str(row["record_id"]): row for row in records}
    selected_ids: list[str] = []
    call_ids: list[str] = []
    invalid_selections: list[dict[str, Any]] = []
    for start, batch in chunks(records, ROLLING_CHUNK_SIZE):
        candidate_ids = list(dict.fromkeys([*selected_ids, *[str(row["record_id"]) for row in batch]]))
        candidates = [by_id[record_id] for record_id in candidate_ids]
        prompt = "\n".join(row["text"] for row in candidates)
        response = client.call(
            purpose="summary",
            key=f"{public['history_id']}-chunk-{start}-{start + len(batch) - 1}",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            num_ctx=SUMMARY_CONTEXT,
            num_predict=160,
        )
        qualified = f"summary/{response['call_id']}"
        call_ids.append(qualified)
        content = str(response["response"].get("message", {}).get("content", ""))
        selected, invalid = parse_selected_record_ids(content, set(candidate_ids))
        fallback_used = False
        if len(selected) < SUMMARY_RECORDS:
            fallback_used = True
            for record_id in [*selected_ids, *reversed(candidate_ids)]:
                if record_id not in selected:
                    selected.append(record_id)
                if len(selected) == SUMMARY_RECORDS:
                    break
        selected_ids = selected[:SUMMARY_RECORDS]
        if invalid or fallback_used:
            invalid_selections.append(
                {
                    "call_id": qualified,
                    "invalid_ids": invalid,
                    "fallback_used": fallback_used,
                    "valid_model_selections": len(selected) - int(fallback_used),
                }
            )
    usage = usage_for_calls(client, call_ids)
    selected_records = [by_id[record_id] for record_id in selected_ids]
    return {
        "experiment_id": "MCO-02",
        "history_id": public["history_id"],
        "selected_record_ids": selected_ids,
        "selected_records": selected_records,
        "usage": usage,
        "invalid_selection_events": invalid_selections,
        "persistent_bytes": sum(
            len(row["text"].encode("utf-8")) + 1 for row in selected_records
        ),
    }


class ConventionalRagIndex:
    def __init__(self, records: Sequence[dict[str, Any]]) -> None:
        self.records = list(records)
        self.vectorizer = FeatureUnion(
            [
                (
                    "word",
                    TfidfVectorizer(
                        lowercase=True,
                        analyzer="word",
                        ngram_range=(1, 2),
                        token_pattern=r"(?u)\b[\w_-]+\b",
                        max_features=50_000,
                        sublinear_tf=True,
                    ),
                ),
                (
                    "char",
                    TfidfVectorizer(
                        lowercase=True,
                        analyzer="char_wb",
                        ngram_range=(3, 5),
                        max_features=50_000,
                        sublinear_tf=True,
                    ),
                ),
            ]
        )
        started = time.perf_counter()
        self.matrix = self.vectorizer.fit_transform([str(row["text"]) for row in self.records])
        self.build_wall_time_seconds = time.perf_counter() - started
        sparse_bytes = int(
            self.matrix.data.nbytes + self.matrix.indices.nbytes + self.matrix.indptr.nbytes
        )
        vocabulary_bytes = len(canonical(self.vectorizer.get_feature_names_out().tolist()).encode("utf-8"))
        self.persistent_bytes = sparse_bytes + vocabulary_bytes

    def retrieve(self, question: str, top_k: int = RAG_TOP_K) -> tuple[list[dict[str, Any]], int]:
        query = self.vectorizer.transform([question])
        scores = (self.matrix @ query.T).toarray().ravel()
        order = sorted(
            range(len(self.records)),
            key=lambda index: (
                -float(scores[index]),
                mco01.stable_int(question, self.records[index]["record_id"], "rag-tie"),
                str(self.records[index]["record_id"]),
            ),
        )[:top_k]
        return [self.records[index] for index in order], int(self.matrix.shape[0])


def raw_persistent_bytes(records: Sequence[dict[str, Any]]) -> int:
    return sum(len(str(row["text"]).encode("utf-8")) + 1 for row in records)


def structured_persistent_bytes(records: Sequence[dict[str, Any]]) -> int:
    return sum(len(canonical(row).encode("utf-8")) + 1 for row in records)


def structured_evidence_line(row: dict[str, Any]) -> str:
    return (
        f"[Record {row['record_id']}; source {row['source']}; event {row['event_time']}] "
        f"subject={row['subject']}; relation={row['relation']}; object={row['object']}; "
        f"operation={row['operation']}; supersedes={row['supersedes']}"
    )


def parse_answer(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    required = {"status", "terminal_entity", "failure_threshold", "path_record_ids"}
    if isinstance(parsed, dict) and set(parsed) == required:
        status = parsed["status"]
        path = parsed["path_record_ids"]
        if status == "UNKNOWN" and isinstance(path, list):
            return {
                "complete": False,
                "terminal_entity": None,
                "failure_threshold": None,
                "requires_inspection": None,
                "path_record_ids": [],
                "parse_valid": True,
            }
        if (
            status == "ANSWER"
            and isinstance(parsed["terminal_entity"], str)
            and re.fullmatch(r"[ed]_[0-9a-f]{16}", parsed["terminal_entity"])
            and isinstance(parsed["failure_threshold"], int)
            and isinstance(path, list)
            and all(
                isinstance(record_id, str)
                and re.fullmatch(r"r_[0-9a-f]{16}", record_id)
                for record_id in path
            )
        ):
            return {
                "complete": True,
                "terminal_entity": parsed["terminal_entity"],
                "failure_threshold": parsed["failure_threshold"],
                "requires_inspection": None,
                "path_record_ids": list(path),
                "parse_valid": True,
            }
    return {
        "complete": False,
        "terminal_entity": None,
        "failure_threshold": None,
        "requires_inspection": None,
        "path_record_ids": [],
        "parse_valid": False,
    }


def answer_candidates_from_evidence(
    evidence_lines: Sequence[str],
) -> tuple[list[tuple[str, int]], list[str]]:
    threshold_candidates: set[tuple[str, int]] = set()
    record_ids: set[str] = set()
    for line in evidence_lines:
        record_ids.update(RECORD_ID_PATTERN.findall(line))
        structured = STRUCTURED_THRESHOLD_PATTERN.search(line)
        if structured is not None:
            threshold_candidates.add((structured.group(1), int(structured.group(2))))
            continue
        temperatures = TEMPERATURE_PATTERN.findall(line)
        entities = ENTITY_PATTERN.findall(line)
        if temperatures and len(entities) == 1:
            threshold_candidates.add((entities[0], int(temperatures[-1])))
    return sorted(threshold_candidates), sorted(record_ids)


def final_format_schema(evidence_lines: Sequence[str]) -> dict[str, Any]:
    candidates, record_ids = answer_candidates_from_evidence(evidence_lines)
    if candidates:
        status = ["ANSWER"]
        terminals = sorted({terminal for terminal, _ in candidates})
        thresholds = sorted({threshold for _, threshold in candidates})
    else:
        status = ["UNKNOWN"]
        terminals = ["UNKNOWN"]
        thresholds = [0]
    record_items: dict[str, Any] = {"type": "string"}
    if record_ids:
        record_items["enum"] = record_ids
    else:
        record_items["pattern"] = "^r_[0-9a-f]{16}$"
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": status},
            "terminal_entity": {"type": "string", "enum": terminals},
            "failure_threshold": {"type": "integer", "enum": thresholds},
            "path_record_ids": {
                "type": "array",
                "items": record_items,
                "minItems": 0,
                "maxItems": CAPACITY,
            },
        },
        "required": [
            "status",
            "terminal_entity",
            "failure_threshold",
            "path_record_ids",
        ],
        "additionalProperties": False,
    }


def derive_inspection(
    prediction: dict[str, Any], query: dict[str, Any]
) -> dict[str, Any]:
    result = dict(prediction)
    if result.get("complete") and isinstance(result.get("failure_threshold"), int):
        result["requires_inspection"] = int(query["deployment_temperature"]) < int(
            result["failure_threshold"]
        )
    return result


def reasoning_user_prompt(question: str, evidence_lines: Sequence[str]) -> str:
    evidence = "\n".join(evidence_lines) if evidence_lines else "(no evidence currently visible)"
    return f"QUESTION\n{question}\n\nEVIDENCE\n{evidence}"


def call_final_reasoner(
    client: FrozenOllamaClient,
    *,
    system: str,
    history_id: str,
    query: dict[str, Any],
    evidence_lines: Sequence[str],
    num_ctx: int = BOUNDED_CONTEXT,
) -> dict[str, Any]:
    response = client.call(
        purpose="reasoning",
        key=f"{system}-{history_id}-{query['query_id']}",
        messages=[
            {"role": "system", "content": FINAL_REASONING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": reasoning_user_prompt(str(query["question"]), evidence_lines),
            },
        ],
        num_ctx=num_ctx,
        num_predict=192,
        format_spec=final_format_schema(evidence_lines),
    )
    qualified = f"reasoning/{response['call_id']}"
    content = str(response["response"].get("message", {}).get("content", ""))
    usage = usage_for_calls(client, [qualified])
    return {
        "prediction": derive_inspection(parse_answer(content), query),
        "raw_output": content,
        "raw_output_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "usage": usage,
        "maximum_model_visible_tokens": int(response["accounting"]["prompt_eval_count"]),
        "call_ids": [qualified],
    }


def traverse_extracted(
    records: Sequence[dict[str, Any]], query: dict[str, Any]
) -> dict[str, Any]:
    index = mco01.index_records(records)
    current = str(query["root_entity"])
    path: list[dict[str, Any]] = []
    external_reads = 0
    index_probes = 0
    visited: set[str] = set()
    for _ in range(32):
        if current in visited:
            break
        visited.add(current)
        selected: dict[str, Any] | None = None
        for relation in mco01.RELATION_PRECEDENCE:
            index_probes += 1
            candidates = index.get((current, relation), [])
            external_reads += len(candidates)
            winner = mco01.winning_record(candidates)
            if winner is not None:
                selected = winner
                break
        if selected is None:
            break
        path.append(selected)
        if selected["relation"] == "failure_threshold":
            return {
                "complete": True,
                "path": path,
                "external_reads": external_reads,
                "index_probes": index_probes,
            }
        current = str(selected["object"])
    return {
        "complete": False,
        "path": path,
        "external_reads": external_reads,
        "index_probes": index_probes,
    }


def run_iterative_need(
    client: FrozenOllamaClient,
    *,
    history_id: str,
    query: dict[str, Any],
    extracted_records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    index = mco01.index_records(extracted_records)
    active: list[dict[str, Any]] = []
    active_ids: set[str] = set()
    retained: list[dict[str, Any]] = []
    retrieved_ids: set[str] = set()
    requested_entities: list[str] = []
    call_ids: list[str] = []
    maximum_active = 0
    maximum_tokens = 0
    external_reads = 0
    index_probes = 0
    prediction = parse_answer("UNKNOWN")
    acquisition_failure: str | None = None
    raw_outputs: list[str] = []

    current = str(query["root_entity"])
    for step in range(8):
        if current in requested_entities:
            acquisition_failure = "repeated-need"
            break
        requested_entities.append(current)
        selected_relation: str | None = None
        selected_candidates: list[dict[str, Any]] = []
        bundle: list[dict[str, Any]] = []
        for relation in mco01.RELATION_PRECEDENCE:
            index_probes += 1
            candidates = list(index.get((current, relation), []))
            external_reads += len(candidates)
            bundle.extend(candidates)
            if (
                selected_relation is None
                and mco01.winning_record(candidates) is not None
            ):
                selected_relation = relation
                selected_candidates = candidates
        if not bundle or selected_relation is None:
            acquisition_failure = "empty-need-result"
            break
        retrieved_ids.update(str(row["record_id"]) for row in bundle)
        active = deduplicated_records([*retained, *bundle])
        active_ids = {str(row["record_id"]) for row in active}
        maximum_active = max(maximum_active, len(active))
        if maximum_active > CAPACITY:
            acquisition_failure = "active-cap-exceeded"
            break
        if selected_relation == "failure_threshold":
            reasoned = call_final_reasoner(
                client,
                system="iterative_need_retrieval",
                history_id=history_id,
                query=query,
                evidence_lines=[structured_evidence_line(row) for row in active],
            )
            prediction = reasoned["prediction"]
            call_ids.extend(reasoned["call_ids"])
            maximum_tokens = max(
                maximum_tokens, int(reasoned["maximum_model_visible_tokens"])
            )
            raw_outputs.append(str(reasoned["raw_output"]))
            break

        candidate_ids = sorted(
            {str(row["record_id"]) for row in selected_candidates}
        )
        candidate_entities = sorted(
            {str(row["object"]) for row in selected_candidates}
        )
        acquisition_schema = {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "enum": candidate_ids},
                "needed_entity": {"type": "string", "enum": candidate_entities},
            },
            "required": ["record_id", "needed_entity"],
            "additionalProperties": False,
        }
        response = client.call(
            purpose="acquisition",
            key=f"iterative-{history_id}-{query['query_id']}-step-{step}",
            messages=[
                {"role": "system", "content": NEED_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"CURRENT ENTITY\n{current}\n\nCANDIDATE RECORDS\n"
                        + "\n".join(
                            structured_evidence_line(row)
                            for row in selected_candidates
                        )
                    ),
                },
            ],
            num_ctx=BOUNDED_CONTEXT,
            num_predict=96,
            format_spec=acquisition_schema,
        )
        qualified = f"acquisition/{response['call_id']}"
        call_ids.append(qualified)
        maximum_tokens = max(
            maximum_tokens, int(response["accounting"]["prompt_eval_count"])
        )
        content = str(response["response"].get("message", {}).get("content", ""))
        raw_outputs.append(content)
        try:
            selection = json.loads(content)
            selected_record_id = str(selection["record_id"])
            needed = str(selection["needed_entity"])
        except (json.JSONDecodeError, KeyError, TypeError):
            acquisition_failure = "malformed-need"
            break
        selected = next(
            (
                row
                for row in selected_candidates
                if str(row["record_id"]) == selected_record_id
                and str(row["object"]) == needed
            ),
            None,
        )
        if selected is None:
            acquisition_failure = "inconsistent-need-selection"
            break
        winner = mco01.winning_record(selected_candidates)
        if winner is None or selected != winner:
            acquisition_failure = "wrong-need-selection"
        retained.append(selected)
        current = needed
    else:
        acquisition_failure = "round-limit"

    usage = usage_for_calls(client, call_ids)
    return {
        "prediction": prediction,
        "raw_output": "\n---\n".join(raw_outputs),
        "raw_output_sha256": digest(raw_outputs),
        "usage": usage,
        "call_ids": call_ids,
        "visible_record_ids": sorted(active_ids),
        "retrieved_record_ids": sorted(retrieved_ids),
        "maximum_model_visible_records": maximum_active,
        "maximum_model_visible_tokens": maximum_tokens,
        "retrieval_rounds": len(requested_entities),
        "requested_entities": requested_entities,
        "external_reads": external_reads,
        "index_probes": index_probes,
        "acquisition_failure": acquisition_failure,
    }


def empty_usage() -> dict[str, Any]:
    return {
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "wall_time_seconds": 0.0,
        "prompt_eval_duration_ns": 0,
        "eval_duration_ns": 0,
        "call_ids": [],
    }


def expensive_token_units(input_tokens: float, output_tokens: float, weight: int = OUTPUT_TOKEN_WEIGHT) -> float:
    return float(input_tokens) + float(weight) * float(output_tokens)


def make_noniterative_outcome(
    reasoned: dict[str, Any],
    *,
    visible_records: Sequence[dict[str, Any]],
    retrieved_record_ids: Sequence[str] | None = None,
    retrieval_rounds: int,
    external_reads: int,
    index_probes: int,
) -> dict[str, Any]:
    visible_ids = [str(row["record_id"]) for row in visible_records]
    return {
        **reasoned,
        "visible_record_ids": visible_ids,
        "retrieved_record_ids": list(retrieved_record_ids or visible_ids),
        "maximum_model_visible_records": len(set(visible_ids)),
        "retrieval_rounds": retrieval_rounds,
        "external_reads": external_reads,
        "index_probes": index_probes,
        "acquisition_failure": None,
    }


def infeasible_full_context_outcome(estimated_tokens: int) -> dict[str, Any]:
    return {
        "prediction": {
            "complete": False,
            "terminal_entity": None,
            "failure_threshold": None,
            "requires_inspection": None,
            "path_record_ids": [],
            "parse_valid": True,
        },
        "raw_output": "FULL_CONTEXT_INFEASIBLE",
        "raw_output_sha256": hashlib.sha256(b"FULL_CONTEXT_INFEASIBLE").hexdigest(),
        "usage": empty_usage(),
        "call_ids": [],
        "visible_record_ids": [],
        "retrieved_record_ids": [],
        "maximum_model_visible_records": 0,
        "maximum_model_visible_tokens": estimated_tokens,
        "retrieval_rounds": 0,
        "external_reads": 0,
        "index_probes": 0,
        "acquisition_failure": None,
        "full_context_estimated_tokens": estimated_tokens,
    }


def score_query_result(
    *,
    system: str,
    public: dict[str, Any],
    public_query: dict[str, Any],
    oracle_query: dict[str, Any],
    oracle_records: Sequence[dict[str, Any]],
    outcome: dict[str, Any],
    ingestion: dict[str, Any],
    extraction: dict[str, Any] | None,
    persistent_records: int,
    persistent_bytes: int,
    feasible: bool = True,
) -> dict[str, Any]:
    expected = oracle_query["expected"]
    expected_path = [str(value) for value in expected["path_record_ids"]]
    predicted = outcome["prediction"]
    predicted_path = [str(value) for value in predicted.get("path_record_ids", [])]
    visible_ids = {str(value) for value in outcome.get("visible_record_ids", [])}
    retrieved_ids = {str(value) for value in outcome.get("retrieved_record_ids", [])}
    oracle_by_id = {str(row["record_id"]): row for row in oracle_records}
    if feasible:
        answer_correct = bool(
            predicted.get("complete")
            and predicted.get("terminal_entity") == expected["terminal_entity"]
            and predicted.get("failure_threshold") == expected["failure_threshold"]
            and predicted.get("requires_inspection") == expected["requires_inspection"]
        )
        dependency_correct = bool(
            predicted.get("complete")
            and predicted.get("terminal_entity") == expected["terminal_entity"]
            and len(predicted_path) == int(oracle_query["dependency_hops"])
        )
        provenance_correct = predicted_path == expected_path
        critical_recall = sum(record_id in retrieved_ids for record_id in expected_path) / len(expected_path)
        retrieval_precision = (
            sum(record_id in set(expected_path) for record_id in retrieved_ids) / len(retrieved_ids)
            if retrieved_ids
            else 0.0
        )
        updated_ids = [str(value) for value in expected["updated_record_ids"]]
        temporal_accuracy = (
            sum(record_id in predicted_path for record_id in updated_ids) / len(updated_ids)
            if updated_ids
            else float(provenance_correct)
        )
    else:
        answer_correct = dependency_correct = provenance_correct = None
        critical_recall = retrieval_precision = temporal_accuracy = None

    extraction_critical_failure = False
    extraction_metrics: dict[str, Any] | None = None
    indexing_pass = True
    shared_extraction_sha256: str | None = None
    if extraction is not None:
        extracted_by_id = {
            str(row["record_id"]): row for row in extraction["records"]
        }
        extraction_critical_failure = any(
            extracted_by_id.get(record_id) != oracle_by_id.get(record_id)
            for record_id in expected_path
        )
        extraction_metrics = extraction["metrics"]
        indexing_pass = bool(extraction["indexing"]["pass"])
        shared_extraction_sha256 = str(extraction["shared_extraction_sha256"])

    failure_class: str | None = None
    wrong = bool(feasible and (not answer_correct or not provenance_correct))
    if wrong:
        if extraction_critical_failure:
            failure_class = "LANGUAGE_EXTRACTION_FAILURE"
        elif not indexing_pass:
            failure_class = "INDEXING_FAILURE"
        elif system == "iterative_need_retrieval" and outcome.get("acquisition_failure"):
            failure_class = "ACQUISITION_PLANNING_FAILURE"
        elif critical_recall is not None and critical_recall < 1.0:
            failure_class = "RETRIEVAL_FAILURE"
        elif not answer_correct:
            failure_class = "REASONING_FAILURE"
        else:
            failure_class = "PROVENANCE_FAILURE"
    if failure_class is not None and failure_class not in FAILURE_CLASSES:
        raise RuntimeError(f"unknown failure class: {failure_class}")

    query_usage = outcome["usage"]
    row = {
        "history_id": public["history_id"],
        "history_size": int(public["history_size"]),
        "seed": int(public["seed"]),
        "query_id": public_query["query_id"],
        "dependency_hops": int(oracle_query["dependency_hops"]),
        "families": list(oracle_query["families"]),
        "system": system,
        "status": "SCORED" if feasible else "FULL_CONTEXT_INFEASIBLE",
        "answer_accuracy": float(answer_correct) if answer_correct is not None else None,
        "critical_recall": critical_recall,
        "dependency_chain_accuracy": (
            float(dependency_correct) if dependency_correct is not None else None
        ),
        "temporal_update_accuracy": temporal_accuracy,
        "provenance_accuracy": (
            float(provenance_correct) if provenance_correct is not None else None
        ),
        "retrieval_precision": retrieval_precision,
        "retrieval_recall": critical_recall,
        "failure_class": failure_class,
        "extraction_critical_failure": extraction_critical_failure,
        "extraction_precision": (
            extraction_metrics["extraction_precision"] if extraction_metrics else None
        ),
        "extraction_recall": (
            extraction_metrics["extraction_recall"] if extraction_metrics else None
        ),
        "shared_extraction_sha256": shared_extraction_sha256,
        "indexing_pass": indexing_pass,
        "maximum_model_visible_records": int(
            outcome["maximum_model_visible_records"]
        ),
        "maximum_model_visible_tokens": int(
            outcome["maximum_model_visible_tokens"]
        ),
        "persistent_records": persistent_records,
        "persistent_bytes": persistent_bytes,
        "retrieved_records": len(retrieved_ids),
        "retrieval_rounds": int(outcome["retrieval_rounds"]),
        "external_reads": int(outcome["external_reads"]),
        "index_probes": int(outcome["index_probes"]),
        "ingestion_model_calls": int(ingestion["model_calls"]),
        "ingestion_input_tokens": int(ingestion["input_tokens"]),
        "ingestion_output_tokens": int(ingestion["output_tokens"]),
        "ingestion_wall_time_seconds": float(ingestion["wall_time_seconds"]),
        "query_model_calls": int(query_usage["model_calls"]),
        "query_input_tokens": int(query_usage["input_tokens"]),
        "query_output_tokens": int(query_usage["output_tokens"]),
        "query_wall_time_seconds": float(query_usage["wall_time_seconds"]),
        "ingestion_expensive_token_units": expensive_token_units(
            ingestion["input_tokens"], ingestion["output_tokens"]
        ),
        "query_expensive_token_units": expensive_token_units(
            query_usage["input_tokens"], query_usage["output_tokens"]
        ),
        "embedding_or_extraction_calls": (
            int(ingestion["model_calls"])
            if system in {"structured_exact_planner", "iterative_need_retrieval"}
            else int(system == "conventional_rag")
        ),
        "billed_cost_usd": 0.0,
        "estimated_cost_usd": None,
        "prediction_complete": bool(predicted.get("complete")),
        "predicted_terminal_entity": predicted.get("terminal_entity"),
        "predicted_failure_threshold": predicted.get("failure_threshold"),
        "predicted_requires_inspection": predicted.get("requires_inspection"),
        "predicted_path_record_ids": predicted_path,
        "expected_path_sha256": digest(expected_path),
        "retrieved_record_ids_sha256": digest(sorted(retrieved_ids)),
        "visible_record_ids_sha256": digest(sorted(visible_ids)),
        "raw_model_output_sha256": outcome["raw_output_sha256"],
        "acquisition_failure": outcome.get("acquisition_failure"),
        "model_call_ids": list(outcome.get("call_ids", [])),
    }
    return row


def deduplicated_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in records:
        record_id = str(row["record_id"])
        if record_id not in seen:
            result.append(row)
            seen.add(record_id)
    return result


def estimated_full_context_tokens(question: str, records: Sequence[dict[str, Any]]) -> int:
    prompt = reasoning_user_prompt(question, [str(row["text"]) for row in records])
    total_bytes = len(FINAL_REASONING_SYSTEM_PROMPT.encode("utf-8")) + len(
        prompt.encode("utf-8")
    )
    return math.ceil(total_bytes / 3.0)


def evaluate_history(
    client: FrozenOllamaClient,
    public: dict[str, Any],
    oracle: dict[str, Any],
    *,
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    extraction = extract_history(client, public, oracle)
    summary = build_rolling_summary(client, public)
    artifact_root.mkdir(parents=True, exist_ok=True)
    write_json(artifact_root / f"{public['history_id']}_extraction.json", extraction)
    write_json(artifact_root / f"{public['history_id']}_summary.json", summary)
    rag = ConventionalRagIndex(public["records"])
    raw_bytes = raw_persistent_bytes(public["records"])
    extracted_bytes = structured_persistent_bytes(extraction["records"])
    recent_summary = list(public["records"][-RECENT_SUMMARY_RECORDS:])
    public_by_id = {str(row["record_id"]): row for row in public["records"]}
    summary_query_records = deduplicated_records(
        [
            *[public_by_id[record_id] for record_id in summary["selected_record_ids"]],
            *recent_summary,
        ]
    )[:CAPACITY]
    summary_persistent_bytes = raw_persistent_bytes(summary_query_records)
    oracle_queries = {str(row["query_id"]): row for row in oracle["queries"]}

    ingestion_by_system = {
        "full_context": empty_usage(),
        "recent_window": empty_usage(),
        "rolling_summary": summary["usage"],
        "conventional_rag": {
            **empty_usage(),
            "wall_time_seconds": rag.build_wall_time_seconds,
        },
        "structured_exact_planner": extraction["usage"],
        "iterative_need_retrieval": extraction["usage"],
    }
    persistence = {
        "full_context": (len(public["records"]), raw_bytes),
        "recent_window": (
            min(CAPACITY, len(public["records"])),
            raw_persistent_bytes(public["records"][-CAPACITY:]),
        ),
        "rolling_summary": (len(summary_query_records), summary_persistent_bytes),
        "conventional_rag": (
            len(public["records"]),
            raw_bytes + rag.persistent_bytes,
        ),
        "structured_exact_planner": (len(extraction["records"]), extracted_bytes),
        "iterative_need_retrieval": (len(extraction["records"]), extracted_bytes),
    }

    rows: list[dict[str, Any]] = []
    for public_query in public["queries"]:
        oracle_query = oracle_queries[str(public_query["query_id"])]

        full_estimate = estimated_full_context_tokens(
            str(public_query["question"]), public["records"]
        )
        if full_estimate > FULL_CONTEXT_LIMIT:
            full_outcome = infeasible_full_context_outcome(full_estimate)
            full_feasible = False
        else:
            reasoned = call_final_reasoner(
                client,
                system="full_context",
                history_id=str(public["history_id"]),
                query=public_query,
                evidence_lines=[str(row["text"]) for row in public["records"]],
                num_ctx=FULL_CONTEXT_LIMIT,
            )
            full_outcome = make_noniterative_outcome(
                reasoned,
                visible_records=public["records"],
                retrieval_rounds=0,
                external_reads=len(public["records"]),
                index_probes=0,
            )
            full_outcome["full_context_estimated_tokens"] = full_estimate
            full_feasible = True
        rows.append(
            score_query_result(
                system="full_context",
                public=public,
                public_query=public_query,
                oracle_query=oracle_query,
                oracle_records=oracle["records"],
                outcome=full_outcome,
                ingestion=ingestion_by_system["full_context"],
                extraction=None,
                persistent_records=persistence["full_context"][0],
                persistent_bytes=persistence["full_context"][1],
                feasible=full_feasible,
            )
        )

        recent = list(public["records"][-CAPACITY:])
        reasoned = call_final_reasoner(
            client,
            system="recent_window",
            history_id=str(public["history_id"]),
            query=public_query,
            evidence_lines=[str(row["text"]) for row in recent],
        )
        recent_outcome = make_noniterative_outcome(
            reasoned,
            visible_records=recent,
            retrieval_rounds=0,
            external_reads=len(recent),
            index_probes=0,
        )
        rows.append(
            score_query_result(
                system="recent_window",
                public=public,
                public_query=public_query,
                oracle_query=oracle_query,
                oracle_records=oracle["records"],
                outcome=recent_outcome,
                ingestion=ingestion_by_system["recent_window"],
                extraction=None,
                persistent_records=persistence["recent_window"][0],
                persistent_bytes=persistence["recent_window"][1],
            )
        )

        reasoned = call_final_reasoner(
            client,
            system="rolling_summary",
            history_id=str(public["history_id"]),
            query=public_query,
            evidence_lines=[str(row["text"]) for row in summary_query_records],
        )
        summary_outcome = make_noniterative_outcome(
            reasoned,
            visible_records=summary_query_records,
            retrieval_rounds=0,
            external_reads=len(summary_query_records),
            index_probes=0,
        )
        rows.append(
            score_query_result(
                system="rolling_summary",
                public=public,
                public_query=public_query,
                oracle_query=oracle_query,
                oracle_records=oracle["records"],
                outcome=summary_outcome,
                ingestion=ingestion_by_system["rolling_summary"],
                extraction=None,
                persistent_records=persistence["rolling_summary"][0],
                persistent_bytes=persistence["rolling_summary"][1],
            )
        )

        rag_records, rag_reads = rag.retrieve(str(public_query["question"]))
        reasoned = call_final_reasoner(
            client,
            system="conventional_rag",
            history_id=str(public["history_id"]),
            query=public_query,
            evidence_lines=[str(row["text"]) for row in rag_records],
        )
        rag_outcome = make_noniterative_outcome(
            reasoned,
            visible_records=rag_records,
            retrieval_rounds=1,
            external_reads=rag_reads,
            index_probes=1,
        )
        rows.append(
            score_query_result(
                system="conventional_rag",
                public=public,
                public_query=public_query,
                oracle_query=oracle_query,
                oracle_records=oracle["records"],
                outcome=rag_outcome,
                ingestion=ingestion_by_system["conventional_rag"],
                extraction=None,
                persistent_records=persistence["conventional_rag"][0],
                persistent_bytes=persistence["conventional_rag"][1],
            )
        )

        traversal = traverse_extracted(extraction["records"], public_query)
        planner_records = traversal["path"]
        reasoned = call_final_reasoner(
            client,
            system="structured_exact_planner",
            history_id=str(public["history_id"]),
            query=public_query,
            evidence_lines=[structured_evidence_line(row) for row in planner_records],
        )
        planner_outcome = make_noniterative_outcome(
            reasoned,
            visible_records=planner_records,
            retrieval_rounds=1,
            external_reads=int(traversal["external_reads"]),
            index_probes=int(traversal["index_probes"]),
        )
        rows.append(
            score_query_result(
                system="structured_exact_planner",
                public=public,
                public_query=public_query,
                oracle_query=oracle_query,
                oracle_records=oracle["records"],
                outcome=planner_outcome,
                ingestion=ingestion_by_system["structured_exact_planner"],
                extraction=extraction,
                persistent_records=persistence["structured_exact_planner"][0],
                persistent_bytes=persistence["structured_exact_planner"][1],
            )
        )

        iterative_outcome = run_iterative_need(
            client,
            history_id=str(public["history_id"]),
            query=public_query,
            extracted_records=extraction["records"],
        )
        rows.append(
            score_query_result(
                system="iterative_need_retrieval",
                public=public,
                public_query=public_query,
                oracle_query=oracle_query,
                oracle_records=oracle["records"],
                outcome=iterative_outcome,
                ingestion=ingestion_by_system["iterative_need_retrieval"],
                extraction=extraction,
                persistent_records=persistence["iterative_need_retrieval"][0],
                persistent_bytes=persistence["iterative_need_retrieval"][1],
            )
        )

    history_summary = {
        "history_id": public["history_id"],
        "extraction": extraction["metrics"],
        "extraction_usage": extraction["usage"],
        "shared_extraction_sha256": extraction["shared_extraction_sha256"],
        "indexing": extraction["indexing"],
        "summary_usage": summary["usage"],
        "summary_selected_record_ids": summary["selected_record_ids"],
        "rag_index_bytes": rag.persistent_bytes,
        "rag_index_wall_time_seconds": rag.build_wall_time_seconds,
        "raw_persistent_bytes": raw_bytes,
        "structured_persistent_bytes": extracted_bytes,
    }
    return rows, history_summary


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.exists():
        return {"pass": False, "errors": ["missing-freeze"], "files": []}
    freeze = read_json(FREEZE_PATH)
    errors: list[str] = []
    files: list[dict[str, Any]] = []
    if freeze.get("status") != "FROZEN_BEFORE_SCIENTIFIC_INFERENCE":
        errors.append("freeze-status")
    for relative, expected in freeze.get("files", {}).items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        passed = observed == expected
        if not passed:
            errors.append(f"hash:{relative}")
        files.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "pass": passed,
            }
        )
    return {"pass": not errors, "errors": errors, "files": files}


def preflight(*, deep_corpus: bool = True, require_freeze: bool = True) -> dict[str, Any]:
    cfg = read_json(CONFIG_PATH)
    receipt = read_json(MCO01_RECEIPT_PATH)
    corpus = verify_corpus(deep=deep_corpus)
    identity = model_identity()
    freeze = verify_freeze() if require_freeze else {"pass": True, "errors": [], "files": []}
    checks = {
        "config_preregistered": cfg.get("status")
        == "PREREGISTERED_BEFORE_LANGUAGE_CORPUS_AND_SCIENTIFIC_INFERENCE",
        "mco01_permanently_frozen": receipt.get("status") == "PERMANENTLY_FROZEN",
        "mco01_successor_authorized": receipt.get("authorized_successor")
        == "MCO-02 — LANGUAGE / INFERENCE BOUNDARY",
        "model_identity": identity["pass"],
        "corpus_identity_and_integrity": corpus["pass"],
        "freeze_identity": freeze["pass"],
    }
    errors = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not errors,
        "checks": checks,
        "model_identity": identity,
        "corpus": corpus,
        "freeze": freeze,
        "errors": errors,
    }


def normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in RUNTIME_FIELDS}


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_call_manifest() -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    purpose_counts: Counter[str] = Counter()
    input_tokens = 0
    output_tokens = 0
    for path in sorted(CALL_CACHE_ROOT.rglob("*.json")):
        record = read_json(path)
        relative = str(path.relative_to(ROOT))
        purpose = str(record.get("purpose"))
        purpose_counts[purpose] += 1
        input_tokens += int(record.get("accounting", {}).get("prompt_eval_count", 0))
        output_tokens += int(record.get("accounting", {}).get("eval_count", 0))
        entries[relative] = {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
            "purpose": purpose,
            "request_sha256": record.get("request_sha256"),
            "response_content_sha256": record.get("response_content_sha256"),
        }
    manifest = {
        "experiment_id": "MCO-02",
        "entry_count": len(entries),
        "purpose_counts": dict(sorted(purpose_counts.items())),
        "total_input_tokens_including_determinism_repeats": input_tokens,
        "total_output_tokens_including_determinism_repeats": output_tokens,
        "entries": entries,
    }
    write_json(OUT / "model_call_manifest.json", manifest)
    return manifest


def execute_run(*, mode: str, run_id: str) -> dict[str, Any]:
    if mode not in {"live", "replay"}:
        raise ValueError(mode)
    check = preflight(deep_corpus=False, require_freeze=True)
    if not check["pass"]:
        raise RuntimeError(f"preflight failed: {check['errors']}")
    run_root = LIVE_ROOT if mode == "live" else REPLAY_ROOT / run_id
    summary_path = run_root / "run_summary.json"
    if summary_path.exists():
        raise FileExistsError(f"completed run already exists: {summary_path}")
    run_root.mkdir(parents=True, exist_ok=True)
    client = FrozenOllamaClient(mode=mode)
    rows: list[dict[str, Any]] = []
    history_summaries: list[dict[str, Any]] = []
    started = time.perf_counter()
    for history_index, (public, oracle) in enumerate(load_corpus(), start=1):
        history_rows, history_summary = evaluate_history(
            client,
            public,
            oracle,
            artifact_root=run_root / "prepared",
        )
        rows.extend(history_rows)
        history_summaries.append(history_summary)
        print(
            f"MCO-02 {mode} {history_index}/{EXPECTED_HISTORIES}: "
            f"{public['history_id']} extraction={history_summary['extraction']['extraction_recall']:.4f}",
            flush=True,
        )
    expected_rows = EXPECTED_QUERIES * len(SYSTEMS)
    if len(rows) != expected_rows:
        raise RuntimeError(f"expected {expected_rows} result rows, observed {len(rows)}")
    normalized = [normalized_row(row) for row in rows]
    write_jsonl(run_root / "results.jsonl", rows)
    write_jsonl(run_root / "normalized_results.jsonl", normalized)
    write_json(run_root / "history_summaries.json", history_summaries)
    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
        "model_identity": model_identity(),
    }
    write_json(run_root / "environment.json", environment)
    summary = {
        "experiment_id": "MCO-02",
        "run_id": run_id,
        "mode": mode,
        "status": "VALID_LIVE_MODEL_RUN" if mode == "live" else "VALID_FROZEN_RESPONSE_REPLAY",
        "row_count": len(rows),
        "history_count": EXPECTED_HISTORIES,
        "query_count": EXPECTED_QUERIES,
        "systems": list(SYSTEMS),
        "normalized_results_sha256": file_sha256(run_root / "normalized_results.jsonl"),
        "results_sha256": file_sha256(run_root / "results.jsonl"),
        "history_summaries_sha256": file_sha256(run_root / "history_summaries.json"),
        "corpus_manifest_sha256": file_sha256(CORPUS_MANIFEST_PATH),
        "freeze_sha256": file_sha256(FREEZE_PATH),
        "total_wall_time_seconds": time.perf_counter() - started,
        "runtime_fields_excluded_from_replay": sorted(RUNTIME_FIELDS),
    }
    write_json(summary_path, summary)
    if mode == "live":
        build_call_manifest()
    return summary


def select_stratified_calls(fraction: float = 0.1) -> list[Path]:
    by_purpose: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(CALL_CACHE_ROOT.rglob("*.json")):
        record = read_json(path)
        purpose = str(record.get("purpose"))
        if purpose == "determinism_repeat":
            continue
        by_purpose[purpose].append(path)
    selected: list[Path] = []
    for purpose, paths in sorted(by_purpose.items()):
        ordered = sorted(paths, key=lambda path: mco01.stable_int(str(path), "repeat-selection"))
        count = max(1, math.ceil(len(paths) * fraction))
        selected.extend(ordered[:count])
    return selected


def run_determinism_recheck(fraction: float = 0.1) -> dict[str, Any]:
    selected = select_stratified_calls(fraction)
    client = FrozenOllamaClient(mode="live")
    comparisons: list[dict[str, Any]] = []
    for index, path in enumerate(selected, start=1):
        original = read_json(path)
        request = original["request"]
        repeated = client.call(
            purpose="determinism_repeat",
            key=f"repeat-{original['purpose']}-{original['call_id']}",
            messages=request["messages"],
            num_ctx=int(request["options"]["num_ctx"]),
            num_predict=int(request["options"]["num_predict"]),
            format_spec=request.get("format"),
            stop=request["options"].get("stop"),
            force_live_repeat=True,
        )
        original_content = str(original["response"].get("message", {}).get("content", ""))
        repeated_content = str(repeated["response"].get("message", {}).get("content", ""))
        comparisons.append(
            {
                "original": str(path.relative_to(ROOT)),
                "repeat_call_id": f"determinism_repeat/{repeated['call_id']}",
                "content_identical": original_content == repeated_content,
                "prompt_tokens_identical": int(original["accounting"]["prompt_eval_count"])
                == int(repeated["accounting"]["prompt_eval_count"]),
                "output_tokens_identical": int(original["accounting"]["eval_count"])
                == int(repeated["accounting"]["eval_count"]),
            }
        )
        print(f"MCO-02 determinism repeat {index}/{len(selected)}", flush=True)
    stability = statistics.fmean(row["content_identical"] for row in comparisons) if comparisons else 0.0
    result = {
        "experiment_id": "MCO-02",
        "fraction": fraction,
        "selected_calls": len(selected),
        "content_stability": stability,
        "minimum_required": float(
            read_json(CONFIG_PATH)["acceptance_criteria"]["minimum_live_response_stability"]
        ),
        "pass": stability
        >= float(
            read_json(CONFIG_PATH)["acceptance_criteria"]["minimum_live_response_stability"]
        ),
        "comparisons": comparisons,
    }
    write_json(OUT / "determinism_recheck.json", result)
    build_call_manifest()
    return result


def summarize_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    feasible = [row for row in rows if row["status"] == "SCORED"]
    result: dict[str, Any] = {
        "n_total": len(rows),
        "n_scored": len(feasible),
        "n_infeasible": len(rows) - len(feasible),
        "histories": len({str(row["history_id"]) for row in rows}),
        "failure_counts": dict(
            sorted(
                Counter(
                    str(row["failure_class"])
                    for row in feasible
                    if row.get("failure_class") is not None
                ).items()
            )
        ),
    }
    for metric in (*QUALITY_METRICS, "retrieval_precision", "retrieval_recall"):
        result[metric] = (
            statistics.fmean(float(row[metric]) for row in feasible)
            if feasible
            else None
        )
    result.update(
        {
            "maximum_model_visible_records": (
                max(int(row["maximum_model_visible_records"]) for row in feasible)
                if feasible
                else None
            ),
            "maximum_model_visible_tokens": (
                max(int(row["maximum_model_visible_tokens"]) for row in feasible)
                if feasible
                else None
            ),
            "mean_retrieved_records": (
                statistics.fmean(float(row["retrieved_records"]) for row in feasible)
                if feasible
                else None
            ),
            "mean_retrieval_rounds": (
                statistics.fmean(float(row["retrieval_rounds"]) for row in feasible)
                if feasible
                else None
            ),
            "mean_query_model_calls": (
                statistics.fmean(float(row["query_model_calls"]) for row in feasible)
                if feasible
                else None
            ),
            "mean_query_input_tokens": (
                statistics.fmean(float(row["query_input_tokens"]) for row in feasible)
                if feasible
                else None
            ),
            "mean_query_output_tokens": (
                statistics.fmean(float(row["query_output_tokens"]) for row in feasible)
                if feasible
                else None
            ),
            "mean_query_expensive_token_units": (
                statistics.fmean(
                    float(row["query_expensive_token_units"]) for row in feasible
                )
                if feasible
                else None
            ),
            "mean_ingestion_model_calls_per_history": statistics.fmean(
                float(next(group)["ingestion_model_calls"])
                for _, group in _group_iter(rows, lambda row: str(row["history_id"]))
            ),
            "mean_ingestion_input_tokens_per_history": statistics.fmean(
                float(next(group)["ingestion_input_tokens"])
                for _, group in _group_iter(rows, lambda row: str(row["history_id"]))
            ),
            "mean_ingestion_output_tokens_per_history": statistics.fmean(
                float(next(group)["ingestion_output_tokens"])
                for _, group in _group_iter(rows, lambda row: str(row["history_id"]))
            ),
            "mean_ingestion_expensive_token_units_per_history": statistics.fmean(
                float(next(group)["ingestion_expensive_token_units"])
                for _, group in _group_iter(rows, lambda row: str(row["history_id"]))
            ),
            "mean_persistent_bytes": statistics.fmean(
                float(next(group)["persistent_bytes"])
                for _, group in _group_iter(rows, lambda row: str(row["history_id"]))
            ),
        }
    )
    extraction_values = [
        float(row["extraction_precision"])
        for row in rows
        if row.get("extraction_precision") is not None
    ]
    result["extraction_precision"] = (
        statistics.fmean(extraction_values) if extraction_values else None
    )
    result["extraction_recall"] = result["extraction_precision"]
    return result


def _group_iter(
    rows: Sequence[dict[str, Any]], key: Callable[[dict[str, Any]], str]
) -> Iterable[tuple[str, Iterable[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    for group_key in sorted(grouped):
        yield group_key, iter(grouped[group_key])


def amortization_for_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_history[str(row["history_id"])].append(row)
    history_costs: list[dict[str, Any]] = []
    for history_id, history_rows in sorted(by_history.items()):
        feasible = [row for row in history_rows if row["status"] == "SCORED"]
        first = history_rows[0]
        if not feasible:
            history_costs.append(
                {
                    "history_id": history_id,
                    "feasible": False,
                    "ingestion_input_tokens": first["ingestion_input_tokens"],
                    "ingestion_output_tokens": first["ingestion_output_tokens"],
                }
            )
            continue
        history_costs.append(
            {
                "history_id": history_id,
                "feasible": True,
                "ingestion_input_tokens": float(first["ingestion_input_tokens"]),
                "ingestion_output_tokens": float(first["ingestion_output_tokens"]),
                "ingestion_model_calls": float(first["ingestion_model_calls"]),
                "mean_query_input_tokens": statistics.fmean(
                    float(row["query_input_tokens"]) for row in feasible
                ),
                "mean_query_output_tokens": statistics.fmean(
                    float(row["query_output_tokens"]) for row in feasible
                ),
                "mean_query_model_calls": statistics.fmean(
                    float(row["query_model_calls"]) for row in feasible
                ),
            }
        )
    feasible_histories = [row for row in history_costs if row["feasible"]]
    if not feasible_histories:
        return {
            "feasible_histories": 0,
            "history_costs": history_costs,
            "query_horizons": {str(query_count): None for query_count in QUERY_COUNTS},
        }
    horizons: dict[str, Any] = {}
    for query_count in QUERY_COUNTS:
        by_weight: dict[str, float] = {}
        for weight in (1, OUTPUT_TOKEN_WEIGHT, 10):
            totals = []
            for row in feasible_histories:
                total_input = row["ingestion_input_tokens"] + query_count * row[
                    "mean_query_input_tokens"
                ]
                total_output = row["ingestion_output_tokens"] + query_count * row[
                    "mean_query_output_tokens"
                ]
                totals.append(expensive_token_units(total_input, total_output, weight))
            by_weight[str(weight)] = statistics.fmean(totals)
        horizons[str(query_count)] = {
            "mean_expensive_token_units": by_weight[str(OUTPUT_TOKEN_WEIGHT)],
            "sensitivity_output_weight_1": by_weight["1"],
            "sensitivity_output_weight_10": by_weight["10"],
            "mean_model_calls": statistics.fmean(
                row["ingestion_model_calls"]
                + query_count * row["mean_query_model_calls"]
                for row in feasible_histories
            ),
        }
    return {
        "feasible_histories": len(feasible_histories),
        "history_costs": history_costs,
        "query_horizons": horizons,
    }


def aggregate_rows(
    rows: Sequence[dict[str, Any]], history_summaries: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_load: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    by_hops: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        system = str(row["system"])
        by_system[system].append(row)
        by_load[int(row["history_size"])][system].append(row)
        by_hops[int(row["dependency_hops"])][system].append(row)
    extraction_records = sum(
        int(row["extraction"]["record_count"]) for row in history_summaries
    )
    extraction_exact = sum(
        int(row["extraction"]["exact_records"]) for row in history_summaries
    )
    aggregate = {
        "experiment_id": "MCO-02",
        "population": {
            "rows": len(rows),
            "histories": len({str(row["history_id"]) for row in rows}),
            "queries": len({str(row["query_id"]) for row in rows}),
            "systems": sorted(by_system),
        },
        "extraction": {
            "record_count": extraction_records,
            "exact_records": extraction_exact,
            "extraction_precision": extraction_exact / extraction_records,
            "extraction_recall": extraction_exact / extraction_records,
            "all_indexes_pass": all(
                bool(row["indexing"]["pass"]) for row in history_summaries
            ),
            "shared_artifact_hashes": {
                row["history_id"]: row["shared_extraction_sha256"]
                for row in history_summaries
            },
        },
        "overall": {
            system: summarize_rows(by_system[system]) for system in SYSTEMS
        },
        "by_history_size": {
            str(size): {
                system: summarize_rows(by_load[size][system]) for system in SYSTEMS
            }
            for size in HISTORY_SIZES
        },
        "by_dependency_hops": {
            str(hops): {
                system: summarize_rows(by_hops[hops][system]) for system in SYSTEMS
            }
            for hops in (2, 3, 4, 5)
        },
        "amortization": {
            "overall": {
                system: amortization_for_rows(by_system[system]) for system in SYSTEMS
            },
            "by_history_size": {
                str(size): {
                    system: amortization_for_rows(by_load[size][system])
                    for system in SYSTEMS
                }
                for size in HISTORY_SIZES
            },
        },
    }
    return aggregate


def population_check(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    expected_rows = EXPECTED_QUERIES * len(SYSTEMS)
    if len(rows) != expected_rows:
        errors.append("row-count")
    system_counts = Counter(str(row["system"]) for row in rows)
    if system_counts != Counter({system: EXPECTED_QUERIES for system in SYSTEMS}):
        errors.append("system-denominators")
    bounded_cap_violations = [
        f"{row['query_id']}:{row['system']}"
        for row in rows
        if row["system"] in BOUNDED_SYSTEMS
        and row["status"] == "SCORED"
        and (
            int(row["maximum_model_visible_records"]) > CAPACITY
            or int(row["maximum_model_visible_tokens"]) > BOUNDED_CONTEXT
        )
    ]
    if bounded_cap_violations:
        errors.append("bounded-context-cap")
    unclassified_wrong = [
        f"{row['query_id']}:{row['system']}"
        for row in rows
        if row["status"] == "SCORED"
        and (
            float(row["answer_accuracy"]) < 1.0
            or float(row["provenance_accuracy"]) < 1.0
        )
        and row.get("failure_class") is None
    ]
    if unclassified_wrong:
        errors.append("unclassified-failure")
    infeasible_scored = [
        f"{row['query_id']}:{row['system']}"
        for row in rows
        if row["status"] == "FULL_CONTEXT_INFEASIBLE"
        and any(row.get(metric) is not None for metric in QUALITY_METRICS)
    ]
    if infeasible_scored:
        errors.append("full-context-infeasible-scored")
    extraction_hash_mismatch: list[str] = []
    by_history_query: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_history_query[(str(row["history_id"]), str(row["query_id"]))][str(row["system"])] = row
    for key, systems in by_history_query.items():
        planner = systems.get("structured_exact_planner")
        iterative = systems.get("iterative_need_retrieval")
        if (
            planner is None
            or iterative is None
            or planner.get("shared_extraction_sha256")
            != iterative.get("shared_extraction_sha256")
        ):
            extraction_hash_mismatch.append(":".join(key))
    if extraction_hash_mismatch:
        errors.append("shared-extraction-mismatch")
    return {
        "pass": not errors,
        "row_count": len(rows),
        "expected_row_count": expected_rows,
        "system_counts": dict(sorted(system_counts.items())),
        "bounded_cap_violations": bounded_cap_violations,
        "unclassified_wrong": unclassified_wrong,
        "full_context_infeasible_scored": infeasible_scored,
        "shared_extraction_mismatches": extraction_hash_mismatch,
        "errors": errors,
    }


def replay_check() -> dict[str, Any]:
    roots = {
        "live": LIVE_ROOT,
        "replay1": REPLAY_ROOT / "replay1",
        "replay2": REPLAY_ROOT / "replay2",
    }
    hashes: dict[str, str | None] = {}
    errors: list[str] = []
    for name, root in roots.items():
        path = root / "normalized_results.jsonl"
        if not path.exists():
            hashes[name] = None
            errors.append(f"missing:{name}")
        else:
            hashes[name] = file_sha256(path)
    present = [value for value in hashes.values() if value is not None]
    if len(set(present)) > 1:
        errors.append("normalized-results-mismatch")
    return {
        "pass": not errors and len(present) == len(roots),
        "normalized_sha256": hashes,
        "byte_identical": len(set(present)) == 1 and len(present) == len(roots),
        "runtime_fields_excluded": sorted(RUNTIME_FIELDS),
        "errors": errors,
    }


def quality_equivalent(candidate: float | None, baseline: float | None, delta: float = 0.05) -> bool:
    return candidate is not None and baseline is not None and baseline >= candidate - delta


def horizon_units(aggregate: dict[str, Any], size: int, system: str, q: int = 128) -> float | None:
    value = aggregate["amortization"]["by_history_size"][str(size)][system][
        "query_horizons"
    ][str(q)]
    return None if value is None else float(value["mean_expensive_token_units"])


def evaluate_verdict(
    aggregate: dict[str, Any], *, integrity_pass: bool
) -> tuple[str, dict[str, Any]]:
    criteria = read_json(CONFIG_PATH)["acceptance_criteria"]
    extraction_precision = float(aggregate["extraction"]["extraction_precision"])
    extraction_recall = float(aggregate["extraction"]["extraction_recall"])
    planner = aggregate["overall"]["structured_exact_planner"]
    iterative = aggregate["overall"]["iterative_need_retrieval"]
    rag = aggregate["overall"]["conventional_rag"]
    planner_accuracy = float(planner["answer_accuracy"] or 0.0)
    iterative_accuracy = float(iterative["answer_accuracy"] or 0.0)
    rag_accuracy = float(rag["answer_accuracy"] or 0.0)
    planner_each_load = {
        str(size): float(
            aggregate["by_history_size"][str(size)]["structured_exact_planner"][
                "answer_accuracy"
            ]
            or 0.0
        )
        for size in HISTORY_SIZES
    }
    structured_quality = bool(
        extraction_precision >= float(criteria["minimum_extraction_precision"])
        and extraction_recall >= float(criteria["minimum_extraction_recall"])
        and planner_accuracy
        >= float(criteria["minimum_structured_answer_accuracy_overall"])
        and all(
            value >= float(criteria["minimum_structured_answer_accuracy_each_load"])
            for value in planner_each_load.values()
        )
        and float(planner["critical_recall"] or 0.0)
        >= float(criteria["minimum_structured_critical_recall"])
        and float(planner["provenance_accuracy"] or 0.0)
        >= float(criteria["minimum_structured_provenance_accuracy"])
        and int(planner["maximum_model_visible_records"] or CAPACITY + 1) <= CAPACITY
        and int(planner["maximum_model_visible_tokens"] or BOUNDED_CONTEXT + 1)
        <= BOUNDED_CONTEXT
    )
    rag_quality_equivalent = rag_accuracy >= planner_accuracy - float(
        criteria["rag_dominance_quality_delta"]
    )
    planner_query_units = float(planner["mean_query_expensive_token_units"] or math.inf)
    iterative_query_units = float(iterative["mean_query_expensive_token_units"] or math.inf)
    planner_query_calls = float(planner["mean_query_model_calls"] or math.inf)
    iterative_query_calls = float(iterative["mean_query_model_calls"] or math.inf)
    planner_matches_or_beats_iterative = planner_accuracy >= iterative_accuracy - float(
        criteria["planner_iterative_equivalence_delta"]
    )
    planner_query_cheaper = bool(
        planner_query_units
        <= float(criteria["planner_cost_advantage_ratio"]) * iterative_query_units
        or planner_query_calls
        <= float(criteria["planner_cost_advantage_ratio"]) * iterative_query_calls
    )

    rag_cost_ratios: dict[str, float | None] = {}
    qualified_nonstructured_pairs: list[dict[str, Any]] = []
    for size in HISTORY_SIZES:
        planner_units = horizon_units(aggregate, size, "structured_exact_planner")
        rag_units = horizon_units(aggregate, size, "conventional_rag")
        rag_cost_ratios[str(size)] = (
            rag_units / planner_units
            if rag_units is not None and planner_units not in {None, 0.0}
            else None
        )
        planner_load_accuracy = planner_each_load[str(size)]
        for baseline in ("full_context", "rolling_summary", "conventional_rag"):
            baseline_summary = aggregate["by_history_size"][str(size)][baseline]
            baseline_accuracy = baseline_summary["answer_accuracy"]
            baseline_units = horizon_units(aggregate, size, baseline)
            if (
                quality_equivalent(planner_load_accuracy, baseline_accuracy)
                and planner_units is not None
                and baseline_units is not None
            ):
                qualified_nonstructured_pairs.append(
                    {
                        "history_size": size,
                        "baseline": baseline,
                        "planner_units_q128": planner_units,
                        "baseline_units_q128": baseline_units,
                        "planner_to_baseline_ratio": planner_units / baseline_units,
                    }
                )
    rag_dominates = bool(
        structured_quality
        and rag_quality_equivalent
        and all(
            ratio is not None
            and ratio <= float(criteria["rag_dominance_cost_ratio"])
            for ratio in rag_cost_ratios.values()
        )
    )
    extraction_cost_dominates = bool(
        structured_quality
        and qualified_nonstructured_pairs
        and all(
            float(row["planner_to_baseline_ratio"])
            >= float(criteria["extraction_cost_dominance_ratio"])
            for row in qualified_nonstructured_pairs
        )
    )
    material_cost_advantage_pairs = [
        row
        for row in qualified_nonstructured_pairs
        if float(row["planner_to_baseline_ratio"])
        <= float(criteria["material_total_cost_ratio"])
    ]
    gates = {
        "integrity_pass": integrity_pass,
        "extraction_precision": extraction_precision,
        "extraction_recall": extraction_recall,
        "planner_answer_accuracy": planner_accuracy,
        "iterative_answer_accuracy": iterative_accuracy,
        "rag_answer_accuracy": rag_accuracy,
        "planner_each_load": planner_each_load,
        "structured_quality": structured_quality,
        "rag_quality_equivalent": rag_quality_equivalent,
        "rag_cost_ratios_q128": rag_cost_ratios,
        "rag_dominates": rag_dominates,
        "qualified_nonstructured_pairs": qualified_nonstructured_pairs,
        "extraction_cost_dominates": extraction_cost_dominates,
        "planner_matches_or_beats_iterative": planner_matches_or_beats_iterative,
        "planner_query_expensive_token_units": planner_query_units,
        "iterative_query_expensive_token_units": iterative_query_units,
        "planner_query_model_calls": planner_query_calls,
        "iterative_query_model_calls": iterative_query_calls,
        "planner_query_cheaper": planner_query_cheaper,
        "material_cost_advantage_pairs": material_cost_advantage_pairs,
    }
    if not integrity_pass:
        return "MCO_02_ACCOUNTING_INVALID", gates
    if not structured_quality:
        return "MCO_02_LANGUAGE_TRANSFER_FAILS", gates
    if rag_dominates:
        return "MCO_02_RAG_DOMINATES", gates
    if extraction_cost_dominates:
        return "MCO_02_EXTRACTION_COST_DOMINATES", gates
    if planner_matches_or_beats_iterative and planner_query_cheaper:
        return "MCO_02_STRUCTURED_PLANNER_DOMINATES", gates
    if material_cost_advantage_pairs:
        return "MCO_02_LANGUAGE_BOUNDARY_ADVANCES", gates
    return "MCO_02_INCONCLUSIVE", gates


def reproduce_corpus() -> dict[str, Any]:
    frozen = read_json(CORPUS_MANIFEST_PATH)
    with tempfile.TemporaryDirectory(prefix="mco02-corpus-replay-") as temporary:
        replay = generate_corpus(Path(temporary) / "corpus")
        files_match = all(
            left["public_path"] == right["public_path"]
            and left["public_sha256"] == right["public_sha256"]
            and left["oracle_path"] == right["oracle_path"]
            and left["oracle_sha256"] == right["oracle_sha256"]
            for left, right in zip(frozen["files"], replay["files"], strict=True)
        )
        result = {
            "pass": bool(
                files_match
                and frozen["corpus_digest"] == replay["corpus_digest"]
                and frozen["counts"] == replay["counts"]
            ),
            "files_match": files_match,
            "file_count": len(frozen["files"]),
            "frozen_corpus_digest": frozen["corpus_digest"],
            "replayed_corpus_digest": replay["corpus_digest"],
            "frozen_manifest_sha256": file_sha256(CORPUS_MANIFEST_PATH),
        }
    write_json(OUT / "corpus_replay.json", result)
    return result


def dev_smoke() -> dict[str, Any]:
    public, oracle = build_language_history(2601, 100)
    public = dict(public)
    oracle = dict(oracle)
    public["queries"] = public["queries"][:2]
    oracle["queries"] = oracle["queries"][:2]
    root = OUT / "engineering/dev_smoke"
    client = FrozenOllamaClient(
        cache_root=OUT / "engineering/model_calls", mode="live"
    )
    rows, history_summary = evaluate_history(
        client, public, oracle, artifact_root=root / "prepared"
    )
    result = {
        "status": "ENGINEERING_ONLY_NOT_SCIENTIFIC",
        "history_id": public["history_id"],
        "query_count": len(public["queries"]),
        "row_count": len(rows),
        "extraction": history_summary["extraction"],
        "systems": {
            system: {
                "answer_accuracy": statistics.fmean(
                    float(row["answer_accuracy"])
                    for row in rows
                    if row["system"] == system and row["answer_accuracy"] is not None
                )
                if any(
                    row["system"] == system and row["answer_accuracy"] is not None
                    for row in rows
                )
                else None,
                "maximum_model_visible_records": max(
                    int(row["maximum_model_visible_records"])
                    for row in rows
                    if row["system"] == system
                ),
                "failure_classes": dict(
                    Counter(
                        str(row["failure_class"])
                        for row in rows
                        if row["system"] == system and row["failure_class"] is not None
                    )
                ),
            }
            for system in SYSTEMS
        },
    }
    write_json(root / "dev_smoke.json", result)
    write_jsonl(root / "results.jsonl", rows)
    return result


def format_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{100.0 * value:.2f}%"


def format_number(value: float | int | None, digits: int = 1) -> str:
    return "N/A" if value is None else f"{float(value):,.{digits}f}"


def render_report(
    verdict: dict[str, Any], aggregate: dict[str, Any], verification: dict[str, Any]
) -> str:
    table_rows: list[str] = []
    for system in SYSTEMS:
        row = aggregate["overall"][system]
        table_rows.append(
            "| {system} | {scored}/{total} | {answer} | {critical} | {prov} | {records} | {tokens} | {calls} | {units} |".format(
                system=system,
                scored=row["n_scored"],
                total=row["n_total"],
                answer=format_percent(row["answer_accuracy"]),
                critical=format_percent(row["critical_recall"]),
                prov=format_percent(row["provenance_accuracy"]),
                records=row["maximum_model_visible_records"] if row["maximum_model_visible_records"] is not None else "N/A",
                tokens=row["maximum_model_visible_tokens"] if row["maximum_model_visible_tokens"] is not None else "N/A",
                calls=format_number(row["mean_query_model_calls"], 2),
                units=format_number(row["mean_query_expensive_token_units"], 1),
            )
        )
    outcome = str(verdict["verdict"])
    overall_status = str(verdict["overall_verification"])
    gates = verdict["gates"]
    world_answer = (
        "No evidence in this project establishes that it will change the world. MCO-02 can raise or lower confidence in a mechanism, but societal impact remains a long-horizon, externally contingent claim."
    )
    stop = str(verdict["stop_decision"])
    return f"""# MCO-02 — LANGUAGE / INFERENCE BOUNDARY

## Claim under test

Complete externally stored natural-language history can preserve equivalent task quality with bounded model-visible state and materially lower total expensive inference than context-heavy or conventional retrieval after ingestion is amortized.

## Check

Self-verified frozen local-model experiment using `llama3.1:8b` blob `{MODEL_BLOB_SHA256}`, the embedded `llama-bpe` tokenizer, {EXPECTED_HISTORIES} histories, {EXPECTED_RECORDS:,} language events, {EXPECTED_QUERIES} questions, six systems, one complete live inference run, a stratified live determinism repeat, and two byte-identical replays from frozen raw responses.

| System | Scored | Answer | Critical recall | Provenance | Max visible records | Max prompt tokens | Query calls | Query expensive units |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(table_rows)}

Shared extraction precision/recall: **{format_percent(float(aggregate['extraction']['extraction_precision']))}** over {aggregate['extraction']['record_count']:,} records. Full-context infeasibility is excluded from accuracy, not counted as failure.

## Verdict — {overall_status}

`{outcome}`

Planner answer accuracy was {format_percent(float(gates['planner_answer_accuracy']))}; iterative accuracy was {format_percent(float(gates['iterative_answer_accuracy']))}; conventional RAG accuracy was {format_percent(float(gates['rag_answer_accuracy']))}. Planner and iterative consume the identical extraction artifact per history.

## Criteria

- Frozen code, corpus, model, and tokenizer identity: **{'PASS' if verification['preflight']['pass'] else 'FAIL'}**
- Exact population, context caps, failure reconciliation, and shared extraction: **{'PASS' if verification['population']['pass'] else 'FAIL'}**
- Live response stability ≥95%: **{'PASS' if verification['determinism']['pass'] else 'FAIL'}** ({format_percent(float(verification['determinism']['content_stability']))})
- Two byte-identical frozen-response replays: **{'PASS' if verification['replay']['pass'] else 'FAIL'}**
- Extraction quality gate: **{'PASS' if gates['extraction_precision'] >= 0.95 and gates['extraction_recall'] >= 0.95 else 'FAIL'}**
- Structured quality gate: **{'PASS' if gates['structured_quality'] else 'FAIL'}**
- Conventional RAG dominance gate: **{'PASS' if gates['rag_dominates'] else 'FAIL'}**
- Extraction-cost dominance gate: **{'PASS' if gates['extraction_cost_dominates'] else 'FAIL'}**
- Transparent planner cheaper than iterative acquisition: **{'PASS' if gates['planner_query_cheaper'] else 'FAIL'}**

## Assumption register

- **Verified here:** renderer semantic preservation, opaque provenance IDs, shared extraction identity, local model/token accounting, bounded query contexts, failure attribution, and deterministic replay.
- **Checkable but unchecked:** open-domain extraction, approximate/vector embedding variants, other models/tokenizers, concurrency, mutable stores, security boundaries, energy use, and real user workloads.
- **Unfalsifiable here:** future adoption and societal impact.
- The extraction boundary is hybrid: explicit IDs, values, sources, and updates are scaffolded deterministically; the model normalizes relation language. Credit must not be generalized to unconstrained document understanding.
- The full-context deployment limit is 32,768 tokens on this hardware even though the model metadata advertises a 131,072-token native context.
- Local inference has zero billed API cost; no fictional USD estimate is reported. Token units, calls, and wall time are the measured cost evidence.

## Credit assignment

Credit belongs only to components that survive the frozen nulls. If exact planning matches iterative acquisition more cheaply, the transparent planner receives credit and iterative `NEED(...)` does not. Learned retention, DMC, model strength, scientific novelty, and production economics receive no credit.

## Verification gap

No independent verifier was available, so this is explicitly self-verified. Frozen-response replay validates the harness but is not an independent second model run. The 10% live repeat measures local determinism. Controlled generated language with explicit opaque IDs remains materially easier than real documents.

## Stop/continue

{stop}

## Is this going to change the world?

**NOT ESTABLISHED.** {world_answer}

## Maturity status

`MATURE_CONTROLLED_SYNTHETIC_LANGUAGE_EXPERIMENT`; `EARLY_UNVALIDATED_REAL_WORLD_SYSTEM`; `WORLD_IMPACT_CLAIM_NOT_MATURE`
"""


def build_artifact_manifest() -> dict[str, Any]:
    manifest_path = OUT / "SHA256SUMS.json"
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        relative = str(path.relative_to(ROOT))
        entries[relative] = {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
    manifest = {
        "experiment_id": "MCO-02",
        "entry_count": len(entries),
        "entries": entries,
    }
    write_json(manifest_path, manifest)
    return manifest


def finalize() -> dict[str, Any]:
    preflight_result = preflight(deep_corpus=True, require_freeze=True)
    live_rows = read_jsonl(LIVE_ROOT / "normalized_results.jsonl")
    live_raw = read_jsonl(LIVE_ROOT / "results.jsonl")
    replay1_rows = read_jsonl(REPLAY_ROOT / "replay1/normalized_results.jsonl")
    replay2_rows = read_jsonl(REPLAY_ROOT / "replay2/normalized_results.jsonl")
    history_summaries = read_json(LIVE_ROOT / "history_summaries.json")
    population = population_check(live_rows)
    replay1_population = population_check(replay1_rows)
    replay2_population = population_check(replay2_rows)
    replay = replay_check()
    determinism_path = OUT / "determinism_recheck.json"
    determinism = (
        read_json(determinism_path)
        if determinism_path.exists()
        else {"pass": False, "content_stability": 0.0, "error": "missing"}
    )
    corpus_replay_path = OUT / "corpus_replay.json"
    corpus_replay = (
        read_json(corpus_replay_path)
        if corpus_replay_path.exists()
        else {"pass": False, "error": "missing"}
    )
    aggregate = aggregate_rows(live_rows, history_summaries)
    aggregate1 = aggregate_rows(replay1_rows, read_json(REPLAY_ROOT / "replay1/history_summaries.json"))
    aggregate2 = aggregate_rows(replay2_rows, read_json(REPLAY_ROOT / "replay2/history_summaries.json"))
    aggregate_match = aggregate == aggregate1 == aggregate2
    integrity_pass = bool(
        preflight_result["pass"]
        and population["pass"]
        and replay1_population["pass"]
        and replay2_population["pass"]
        and replay["pass"]
        and determinism.get("pass")
        and corpus_replay.get("pass")
        and aggregate_match
    )
    outcome, gates = evaluate_verdict(aggregate, integrity_pass=integrity_pass)
    if outcome in {
        "MCO_02_LANGUAGE_BOUNDARY_ADVANCES",
        "MCO_02_STRUCTURED_PLANNER_DOMINATES",
    }:
        overall_verification = "PASS"
    elif outcome == "MCO_02_INCONCLUSIVE":
        overall_verification = "INCONCLUSIVE"
    else:
        overall_verification = "FAIL"
    gate_pass = overall_verification == "PASS"
    if outcome == "MCO_02_STRUCTURED_PLANNER_DOMINATES":
        stop_decision = (
            "STOP iterative `NEED(...)` development for this structured synthetic family. "
            "The next bounded gate, if authorized, is a real-document extraction and exact-planner replication; do not add learning or agents."
        )
    elif outcome == "MCO_02_LANGUAGE_BOUNDARY_ADVANCES":
        stop_decision = (
            "STOP MCO-02 at this terminal pass. The next bounded gate is independent real-document replication with production accounting."
        )
    elif outcome == "MCO_02_LANGUAGE_TRANSFER_FAILS":
        stop_decision = (
            "STOP the architecture branch at the language boundary unless a new experiment targets the mechanically dominant failure class."
        )
    else:
        stop_decision = "STOP at the frozen terminal verdict and follow only its smallest named repair."
    verification = {
        "experiment_id": "MCO-02",
        "status": "PASS" if integrity_pass else "FAIL",
        "verification_mode": "SELF_VERIFIED",
        "preflight": preflight_result,
        "population": population,
        "replay1_population": replay1_population,
        "replay2_population": replay2_population,
        "replay": replay,
        "determinism": determinism,
        "corpus_replay": corpus_replay,
        "aggregate_replay_match": aggregate_match,
        "all_integrity_checks_pass": integrity_pass,
    }
    verdict = {
        "experiment_id": "MCO-02",
        "status": "TERMINAL_VALID" if integrity_pass else "TERMINAL_INVALID",
        "verdict": outcome,
        "overall_verification": overall_verification,
        "gate_pass": gate_pass,
        "gates": gates,
        "population": aggregate["population"],
        "world_impact_disposition": "NOT_ESTABLISHED",
        "world_impact_reason": (
            "Controlled mechanism evidence cannot establish novelty, independent replication, "
            "real demand, production reliability, adoption, or long-horizon societal impact."
        ),
        "stop_decision": stop_decision,
        "training_accounting": {
            "optimizer_steps": 0,
            "backward_calls": 0,
            "learned_retention_components": 0,
            "frozen_pretrained_model": MODEL_NAME,
            "dmc_historical_optimizer_steps_preserved": 10880,
            "dmc_historical_training_label": "TRAINING_COST_UNKNOWN",
        },
    }
    write_json(OUT / "aggregate.json", aggregate)
    write_json(OUT / "verification.json", verification)
    write_json(OUT / "MCO02_VERDICT.json", verdict)
    report = render_report(verdict, aggregate, verification)
    (OUT / "MCO02_REPORT.md").write_text(report, encoding="utf-8")
    build_call_manifest()
    build_artifact_manifest()
    return verdict


def verify_final_artifacts() -> dict[str, Any]:
    manifest_path = OUT / "SHA256SUMS.json"
    if not manifest_path.exists():
        return {"pass": False, "errors": ["missing-artifact-manifest"]}
    manifest = read_json(manifest_path)
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    for relative, expected in manifest.get("entries", {}).items():
        path = ROOT / relative
        observed = file_sha256(path) if path.exists() else None
        passed = observed == expected.get("sha256")
        if not passed:
            errors.append(f"hash:{relative}")
        checks.append(
            {
                "path": relative,
                "expected_sha256": expected.get("sha256"),
                "observed_sha256": observed,
                "pass": passed,
            }
        )
    verification = read_json(OUT / "verification.json")
    verdict = read_json(OUT / "MCO02_VERDICT.json")
    if not verification.get("all_integrity_checks_pass"):
        errors.append("verification")
    if verdict.get("status") != "TERMINAL_VALID":
        errors.append("verdict-status")
    return {
        "pass": not errors,
        "entry_count": len(checks),
        "verdict": verdict.get("verdict"),
        "world_impact_disposition": verdict.get("world_impact_disposition"),
        "checks": checks,
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate-corpus")
    generate_parser.add_argument("--output", type=Path, default=CORPUS_ROOT)
    verify_corpus_parser = subparsers.add_parser("verify-corpus")
    verify_corpus_parser.add_argument("--shallow", action="store_true")
    subparsers.add_parser("reproduce-corpus")
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--shallow", action="store_true")
    preflight_parser.add_argument("--no-freeze", action="store_true")
    subparsers.add_parser("dev-smoke")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--mode", choices=("live", "replay"), required=True)
    run_parser.add_argument("--run-id", required=True)
    repeat_parser = subparsers.add_parser("determinism-recheck")
    repeat_parser.add_argument("--fraction", type=float, default=0.1)
    subparsers.add_parser("finalize")
    subparsers.add_parser("verify")
    args = parser.parse_args(argv)

    if args.command == "generate-corpus":
        result = generate_corpus(args.output)
    elif args.command == "verify-corpus":
        result = verify_corpus(deep=not args.shallow)
    elif args.command == "reproduce-corpus":
        result = reproduce_corpus()
    elif args.command == "preflight":
        result = preflight(
            deep_corpus=not args.shallow, require_freeze=not args.no_freeze
        )
    elif args.command == "dev-smoke":
        result = dev_smoke()
    elif args.command == "run":
        result = execute_run(mode=args.mode, run_id=args.run_id)
    elif args.command == "determinism-recheck":
        result = run_determinism_recheck(args.fraction)
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
