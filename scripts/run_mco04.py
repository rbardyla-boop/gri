#!/usr/bin/env python3
"""MCO-04: opaque real-telemetry state-compiler replication gate.

The module deliberately separates public telemetry from scorer-only labels.
Engineering and scientific runs use the same compiler, but scientific scoring is
a separate command so predictions can be sealed before labels are read.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
import shutil
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


REPO_ROOT = Path(__file__).resolve().parents[1]
# Direct execution puts ``scripts/`` rather than the repository root on
# ``sys.path``.  The reasoning stage imports the frozen shared client through
# the ``scripts`` namespace, so make that namespace resolvable for both
# ``python scripts/run_mco04.py ...`` and package-style test imports.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
CONFIG_PATH = REPO_ROOT / "experiments" / "mco04" / "MCO04_CONFIG.json"
CONTRACT_PATH = REPO_ROOT / "experiments" / "mco04" / "MCO04_CONTRACT.md"
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "mco04"
DATA_ROOT = ARTIFACT_ROOT / "data"
PUBLIC_DATA_ROOT = DATA_ROOT / "public"
SCORER_ROOT = DATA_ROOT / "scorer_only"
ENGINEERING_ROOT = ARTIFACT_ROOT / "engineering"
SCIENTIFIC_ROOT = ARTIFACT_ROOT / "scientific"
SOURCE_MANIFEST_PATH = SCORER_ROOT / "source_manifest.json"
FREEZE_PATH = REPO_ROOT / "experiments" / "mco04" / "MCO04_FREEZE.json"

INDEX_API = (
    "https://datasets-server.huggingface.co/rows?"
    "dataset=phamquiluan%2FRCAEval&config=cases&split=train"
)
TREE_API = "https://huggingface.co/api/datasets/phamquiluan/RCAEval/tree"
RESOLVE_URL = "https://huggingface.co/datasets/phamquiluan/RCAEval/resolve"
EXPECTED_FILES = ("inject_time.txt", "logs.parquet", "metrics.parquet")
OPTIONAL_FILES = ("traces.parquet",)
ERROR_PATTERN = re.compile(
    r"(?:error|exception|fail(?:ed|ure)?|fatal|panic|timeout|refused|"
    r"unavailable|stack\s*trace)",
    flags=re.IGNORECASE,
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    flags=re.IGNORECASE,
)
HEX_PATTERN = re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b", flags=re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?![A-Za-z])")
REASONING_VARIANTS = ("compiler_packet", "hybrid_rag_16", "max_context")
SCORER_READ_GUARD_ACTIVE = False


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(payload, encoding="utf-8")


def config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def install_scorer_read_guard() -> None:
    """Fail closed if a label-blind run attempts to open scorer-only data."""

    global SCORER_READ_GUARD_ACTIVE
    protected = SCORER_ROOT.resolve()

    def guard(event: str, args: tuple[Any, ...]) -> None:
        if event != "open" or not args:
            return
        raw_path = args[0]
        if not isinstance(raw_path, (str, bytes, os.PathLike)):
            return
        try:
            candidate = Path(raw_path).resolve()
            candidate.relative_to(protected)
        except (OSError, ValueError):
            return
        raise PermissionError(f"label-blind run attempted scorer read: {candidate}")

    sys.addaudithook(guard)
    SCORER_READ_GUARD_ACTIVE = True


def opaque_id(source_case: str, cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or config()
    namespace = cfg["benchmark"]["opaque_id_namespace"]
    token = hashlib.sha256(f"{namespace}|{source_case}".encode("utf-8")).hexdigest()[:20]
    return f"incident_{token}"


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "gri-research-mco04/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def ollama_version() -> str:
    value = _get_json("http://127.0.0.1:11434/api/version")
    return str(value.get("version", ""))


def fetch_index_rows() -> list[dict[str, Any]]:
    cfg = config()
    benchmark = cfg["benchmark"]
    url = f"{RESOLVE_URL}/{benchmark['dataset_revision']}/cases.parquet"
    request = urllib.request.Request(url, headers={"User-Agent": "gri-research-mco04/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    observed = hashlib.sha256(payload).hexdigest()
    if observed != benchmark["index_sha256"]:
        raise RuntimeError(
            f"pinned index hash mismatch: {observed} != {benchmark['index_sha256']}"
        )
    return pd.read_parquet(io.BytesIO(payload)).to_dict(orient="records")


def _case_tree(source_case: str, revision: str) -> list[dict[str, Any]]:
    quoted_case = urllib.parse.quote(source_case, safe="")
    url = f"{TREE_API}/{revision}/{quoted_case}?recursive=true&expand=false&limit=100"
    return _get_json(url)


def build_source_manifest() -> dict[str, Any]:
    cfg = config()
    benchmark = cfg["benchmark"]
    rows = [row for row in fetch_index_rows() if row["suite"] == benchmark["suite"]]
    if len(rows) != benchmark["expected_cases"]:
        raise RuntimeError(f"expected {benchmark['expected_cases']} RE3 cases, got {len(rows)}")

    incidents: list[dict[str, Any]] = []
    for index, row in enumerate(sorted(rows, key=lambda item: item["case"]), start=1):
        source_case = str(row["case"])
        files: dict[str, dict[str, Any]] = {}
        for item in _case_tree(source_case, benchmark["dataset_revision"]):
            if item.get("type") != "file":
                continue
            name = Path(str(item["path"])).name
            if name not in EXPECTED_FILES + OPTIONAL_FILES:
                continue
            lfs = item.get("lfs") or {}
            oid = lfs.get("oid")
            if isinstance(oid, str) and oid.startswith("sha256:"):
                oid = oid.split(":", 1)[1]
            if not oid and int(item.get("size", 0)) <= 1024:
                raw_url = (
                    f"{RESOLVE_URL}/{benchmark['dataset_revision']}/"
                    f"{urllib.parse.quote(source_case)}/{urllib.parse.quote(name)}"
                )
                with urllib.request.urlopen(raw_url, timeout=60) as response:
                    payload = response.read()
                oid = hashlib.sha256(payload).hexdigest()
            files[name] = {"sha256": oid, "size": int(item.get("size", 0))}
        missing = [name for name in EXPECTED_FILES if name not in files]
        if missing:
            raise RuntimeError(f"{source_case} missing files: {missing}")
        split = "engineering" if int(row["repetition"]) == 1 else "scientific"
        incidents.append(
            {
                "ordinal": index,
                "opaque_id": opaque_id(source_case, cfg),
                "source_case": source_case,
                "split": split,
                "dataset": row["dataset"],
                "system": row["system"],
                "root_cause_service": row["root_cause_service"],
                "fault": row["fault"],
                "fault_description": row["fault_description"],
                "repetition": int(row["repetition"]),
                "inject_time": int(row["inject_time"]),
                "files": files,
            }
        )

    counts = {
        split: sum(item["split"] == split for item in incidents)
        for split in ("engineering", "scientific")
    }
    if counts != {
        "engineering": benchmark["expected_engineering_cases"],
        "scientific": benchmark["expected_scientific_cases"],
    }:
        raise RuntimeError(f"split counts mismatch: {counts}")
    manifest = {
        "experiment_id": "MCO-04",
        "dataset_revision": benchmark["dataset_revision"],
        "index_sha256": benchmark["index_sha256"],
        "counts": counts,
        "incidents": incidents,
    }
    write_json(SOURCE_MANIFEST_PATH, manifest)
    return manifest


def _copy_verified(source: Path, target: Path, expected_sha256: str | None) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    observed = file_sha256(source)
    if expected_sha256 and observed != expected_sha256:
        raise RuntimeError(f"hash mismatch for {source}: {observed} != {expected_sha256}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def _download_verified(url: str, target: Path, expected_sha256: str | None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "gri-research-mco04/1"})
    with urllib.request.urlopen(request, timeout=240) as response, temporary.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    observed = file_sha256(temporary)
    if expected_sha256 and observed != expected_sha256:
        raise RuntimeError(f"hash mismatch for {url}: {observed} != {expected_sha256}")
    os.replace(temporary, target)


def stage_split(split: str, source_root: Path | None = None) -> dict[str, Any]:
    if split not in {"engineering", "scientific"}:
        raise ValueError(split)
    if split == "scientific" and not FREEZE_PATH.is_file():
        raise RuntimeError("scientific telemetry cannot be staged before MCO04_FREEZE.json exists")
    manifest = read_json(SOURCE_MANIFEST_PATH) if SOURCE_MANIFEST_PATH.is_file() else build_source_manifest()
    cfg = config()
    selected = [item for item in manifest["incidents"] if item["split"] == split]
    public_root = PUBLIC_DATA_ROOT / split
    labels: dict[str, Any] = {}
    receipts: list[dict[str, Any]] = []
    for number, item in enumerate(selected, start=1):
        case_root = public_root / item["opaque_id"]
        observed_files: dict[str, Any] = {}
        for name, identity in sorted(item["files"].items()):
            expected_sha = identity.get("sha256")
            target = case_root / name
            if source_root is not None:
                source = source_root / item["source_case"] / name
                _copy_verified(source, target, expected_sha)
            else:
                url = (
                    f"{RESOLVE_URL}/{cfg['benchmark']['dataset_revision']}/"
                    f"{urllib.parse.quote(item['source_case'])}/{urllib.parse.quote(name)}"
                )
                _download_verified(url, target, expected_sha)
            observed_files[name] = {
                "sha256": file_sha256(target),
                "bytes": target.stat().st_size,
            }
        public_metadata = {
            "opaque_id": item["opaque_id"],
            "dataset": item["dataset"],
            "alert_time": item["inject_time"],
            "files": observed_files,
        }
        write_json(case_root / "incident.json", public_metadata)
        labels[item["opaque_id"]] = {
            "source_case": item["source_case"],
            "dataset": item["dataset"],
            "root_cause_service": item["root_cause_service"],
            "fault": item["fault"],
            "fault_description": item["fault_description"],
        }
        receipts.append(public_metadata)
        print(f"staged {split} {number}/{len(selected)} {item['opaque_id']}", flush=True)
    label_path = SCORER_ROOT / f"{split}_labels.json"
    write_json(label_path, labels)
    receipt = {
        "split": split,
        "count": len(receipts),
        "public_root": str(public_root.relative_to(REPO_ROOT)),
        "labels_path": str(label_path.relative_to(REPO_ROOT)),
        "public_manifest_sha256": digest(receipts),
        "receipts": receipts,
    }
    write_json(ARTIFACT_ROOT / f"{split}_staging_receipt.json", receipt)
    return receipt


def _window_frame(frame: pd.DataFrame, alert_time: int, seconds: int, before: bool) -> pd.DataFrame:
    if before:
        return frame.loc[(frame.index >= alert_time - seconds) & (frame.index < alert_time)]
    return frame.loc[(frame.index >= alert_time) & (frame.index < alert_time + seconds)]


def _finite(values: Iterable[Any]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def robust_feature_stats(
    before: Iterable[Any], after: Iterable[Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    compiler_cfg = cfg["compiler"]
    left = _finite(before)
    right = _finite(after)
    minimum = int(compiler_cfg["minimum_points_per_window"])
    if len(left) < minimum or len(right) < minimum:
        return {
            "valid": False,
            "before_n": int(len(left)),
            "after_n": int(len(right)),
            "score": 0.0,
        }
    median = float(np.median(left))
    before_q10, before_q75, before_q90 = np.quantile(left, [0.1, 0.75, 0.9])
    after_q10, after_q90 = np.quantile(right, [0.1, 0.9])
    mad_scale = float(np.median(np.abs(left - median)) * 1.4826)
    q25 = float(np.quantile(left, 0.25))
    iqr_scale = float((before_q75 - q25) / 1.349)
    difference_scale = (
        float(np.std(np.diff(left)) / math.sqrt(2.0)) if len(left) > 1 else 0.0
    )
    scale = max(
        mad_scale,
        iqr_scale,
        difference_scale,
        abs(median) * float(compiler_cfg["relative_scale_floor"]),
        float(np.quantile(np.abs(left), 0.75))
        * float(compiler_cfg["magnitude_scale_floor"]),
        float(compiler_cfg["absolute_scale_floor"]),
    )
    after_median = float(np.median(right))
    shifts = {
        "median": abs(after_median - median),
        "q10": abs(float(after_q10) - float(before_q10)),
        "q90": abs(float(after_q90) - float(before_q90)),
    }
    score = min(float(compiler_cfg["feature_score_cap"]), max(shifts.values()) / scale)
    return {
        "valid": True,
        "before_n": int(len(left)),
        "after_n": int(len(right)),
        "before_median": median,
        "after_median": after_median,
        "before_q10": float(before_q10),
        "after_q10": float(after_q10),
        "before_q90": float(before_q90),
        "after_q90": float(after_q90),
        "robust_scale": float(scale),
        "largest_shift": max(shifts, key=lambda key: (shifts[key], key)),
        "score": float(score),
    }


def _weighted_sum(values: Sequence[float], weights: Sequence[float]) -> float:
    return float(sum(value * weight for value, weight in zip(values, weights)))


def compact_packet(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": row["evidence_id"],
            "service": row["service"],
            "metric": row["metric"],
            "kind": row["kind"],
            "score": round(float(row["score"]), 6),
            "before_median": row.get("before_median"),
            "after_median": row.get("after_median"),
            "largest_shift": row.get("largest_shift"),
        }
        for row in records
    ]


def compile_case(case_root: Path) -> dict[str, Any]:
    cfg = config()
    compiler_cfg = cfg["compiler"]
    incident = read_json(case_root / "incident.json")
    opaque = str(incident["opaque_id"])
    alert_time = int(incident["alert_time"])
    metrics_path = case_root / "metrics.parquet"
    metrics_sha = file_sha256(metrics_path)
    metrics = pd.read_parquet(metrics_path).set_index("time")
    seconds = int(compiler_cfg["pre_window_seconds"])
    before = _window_frame(metrics, alert_time, seconds, before=True)
    after = _window_frame(metrics, alert_time, int(compiler_cfg["post_window_seconds"]), before=False)
    resource_suffixes = set(compiler_cfg["resource_metric_suffixes"])
    features: list[dict[str, Any]] = []
    for column in metrics.columns:
        if "_" not in column:
            continue
        service, suffix = column.rsplit("_", 1)
        stats = robust_feature_stats(before[column], after[column], cfg)
        kind = "resource" if suffix in resource_suffixes else "symptom"
        identity = {
            "opaque_id": opaque,
            "source_sha256": metrics_sha,
            "column": column,
            "before": [alert_time - seconds, alert_time],
            "after": [alert_time, alert_time + int(compiler_cfg["post_window_seconds"])],
            "stats": stats,
        }
        row = {
            "evidence_id": f"ev_{digest(identity)[:20]}",
            "source_file": "metrics.parquet",
            "source_sha256": metrics_sha,
            "service": service,
            "metric": suffix,
            "column": column,
            "kind": kind,
            "before_window": identity["before"],
            "after_window": identity["after"],
            **stats,
        }
        row["aggregate_digest"] = digest(
            {key: value for key, value in row.items() if key != "aggregate_digest"}
        )
        features.append(row)

    by_service: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in features:
        bucket = by_service.setdefault(row["service"], {"resource": [], "symptom": []})
        bucket[row["kind"]].append(row)
    service_rows: list[dict[str, Any]] = []
    for service, groups in by_service.items():
        resources = sorted(groups["resource"], key=lambda row: (-row["score"], row["column"]))
        symptoms = sorted(groups["symptom"], key=lambda row: (-row["score"], row["column"]))
        resource_scores = [float(row["score"]) for row in resources]
        symptom_scores = [float(row["score"]) for row in symptoms]
        service_score = _weighted_sum(
            resource_scores, compiler_cfg["service_score"]["top_resource_weights"]
        ) + _weighted_sum(
            symptom_scores, compiler_cfg["service_score"]["top_symptom_weights"]
        )
        service_rows.append(
            {
                "service": service,
                "score": float(service_score),
                "resources": resources,
                "symptoms": symptoms,
            }
        )
    service_rows.sort(key=lambda row: (-row["score"], row["service"]))

    capacity = int(compiler_cfg["packet_capacity_records"])
    selected: list[dict[str, Any]] = []
    if service_rows:
        leader = service_rows[0]
        selected.extend(leader["resources"][: int(compiler_cfg["top_candidate_resource_records"])])
        selected.extend(leader["symptoms"][: int(compiler_cfg["top_candidate_symptom_records"])])
        for candidate in service_rows[1:]:
            if len(selected) >= capacity:
                break
            combined = sorted(
                candidate["resources"] + candidate["symptoms"],
                key=lambda row: (-row["score"], row["column"]),
            )
            selected.extend(combined[: int(compiler_cfg["other_candidate_records"])])
    selected = selected[:capacity]
    compact = compact_packet(selected)
    raw_bytes = sum(
        path.stat().st_size
        for path in case_root.iterdir()
        if path.is_file() and path.name != "incident.json"
    )
    packet_bytes = len(canonical(compact).encode("utf-8"))
    result = {
        "opaque_id": opaque,
        "dataset": incident["dataset"],
        "alert_time": alert_time,
        "prediction": service_rows[0]["service"] if service_rows else None,
        "top3": [row["service"] for row in service_rows[:3]],
        "service_ranking": [
            {"service": row["service"], "score": row["score"]} for row in service_rows
        ],
        "evidence_records": selected,
        "model_packet": compact,
        "packet_count": len(selected),
        "raw_bytes": raw_bytes,
        "packet_bytes": packet_bytes,
        "raw_to_packet_byte_reduction": raw_bytes / max(packet_bytes, 1),
    }
    result["result_digest"] = digest(
        {key: value for key, value in result.items() if key != "result_digest"}
    )
    return result


def author_style_baro(case_root: Path) -> dict[str, Any]:
    cfg = config()
    incident = read_json(case_root / "incident.json")
    alert = int(incident["alert_time"])
    seconds = int(cfg["compiler"]["pre_window_seconds"])
    frame = pd.read_parquet(case_root / "metrics.parquet").set_index("time")
    before = _window_frame(frame, alert, seconds, before=True)
    after = _window_frame(frame, alert, seconds, before=False)
    ranks: list[tuple[float, str, str]] = []
    for column in frame.columns:
        if "_" not in column:
            continue
        left = _finite(before[column])
        right = _finite(after[column])
        if not len(left) or not len(right):
            continue
        median = float(np.median(left))
        scale = float(np.quantile(left, 0.75) - np.quantile(left, 0.25))
        if abs(scale) < 1e-12:
            scale = 1.0
        score = float(np.max((right - median) / scale))
        service = column.rsplit("_", 1)[0]
        ranks.append((score, service, column))
    ranks.sort(key=lambda item: (-item[0], item[2]))
    service_order = list(dict.fromkeys(item[1] for item in ranks))
    return {
        "prediction": service_order[0] if service_order else None,
        "top3": service_order[:3],
        "feature_ranking": [item[2] for item in ranks[:16]],
    }


def single_feature_robust(case_root: Path) -> dict[str, Any]:
    cfg = config()
    incident = read_json(case_root / "incident.json")
    alert = int(incident["alert_time"])
    seconds = int(cfg["compiler"]["pre_window_seconds"])
    frame = pd.read_parquet(case_root / "metrics.parquet").set_index("time")
    before = _window_frame(frame, alert, seconds, before=True)
    after = _window_frame(frame, alert, seconds, before=False)
    ranks: list[tuple[float, str, str]] = []
    for column in frame.columns:
        if "_" not in column:
            continue
        score = float(robust_feature_stats(before[column], after[column], cfg)["score"])
        service = column.rsplit("_", 1)[0]
        ranks.append((score, service, column))
    ranks.sort(key=lambda item: (-item[0], item[2]))
    service_order = list(dict.fromkeys(item[1] for item in ranks))
    return {
        "prediction": service_order[0] if service_order else None,
        "top3": service_order[:3],
        "feature_ranking": [item[2] for item in ranks[:16]],
    }


def post_error_volume(case_root: Path) -> dict[str, Any]:
    cfg = config()
    incident = read_json(case_root / "incident.json")
    alert = int(incident["alert_time"])
    seconds = int(cfg["compiler"]["post_window_seconds"])
    logs = pd.read_parquet(case_root / "logs.parquet")
    window = logs.loc[(logs["timestamp"] >= alert) & (logs["timestamp"] < alert + seconds)]
    matched = window[window["message"].fillna("").str.contains(ERROR_PATTERN, regex=True)]
    counts = matched.groupby("container_name").size().to_dict()
    candidates = sorted(set(str(value) for value in logs["container_name"].dropna().unique()))
    ranked = sorted(candidates, key=lambda service: (-int(counts.get(service, 0)), service))
    return {
        "prediction": ranked[0] if ranked else None,
        "top3": ranked[:3],
        "post_error_counts": {key: int(value) for key, value in sorted(counts.items())},
    }


def normalize_log_message(value: Any) -> str:
    text = str(value or "").strip()
    text = UUID_PATTERN.sub("<UUID>", text)
    text = HEX_PATTERN.sub("<HEX>", text)
    text = NUMBER_PATTERN.sub("<NUM>", text)
    text = re.sub(r"\s+", " ", text)
    return text[:800]


def _document_id(identity: dict[str, Any]) -> str:
    return f"doc_{digest(identity)[:20]}"


def build_fixed_documents(case_root: Path) -> list[dict[str, Any]]:
    """Build deterministic, unranked telemetry documents for retrieval controls."""

    cfg = config()
    incident = read_json(case_root / "incident.json")
    opaque = str(incident["opaque_id"])
    alert = int(incident["alert_time"])
    before_seconds = int(cfg["compiler"]["pre_window_seconds"])
    after_seconds = int(cfg["compiler"]["post_window_seconds"])
    documents: list[dict[str, Any]] = []

    metrics_path = case_root / "metrics.parquet"
    metrics_sha = file_sha256(metrics_path)
    metrics = pd.read_parquet(metrics_path).set_index("time")
    metric_before = _window_frame(metrics, alert, before_seconds, before=True)
    metric_after = _window_frame(metrics, alert, after_seconds, before=False)
    for column in sorted(metrics.columns):
        if "_" not in column:
            continue
        service, metric = column.rsplit("_", 1)
        left = _finite(metric_before[column])
        right = _finite(metric_after[column])
        if not len(left) or not len(right):
            continue
        values = {
            "before_median": float(np.median(left)),
            "before_q10": float(np.quantile(left, 0.1)),
            "before_q90": float(np.quantile(left, 0.9)),
            "after_median": float(np.median(right)),
            "after_q10": float(np.quantile(right, 0.1)),
            "after_q90": float(np.quantile(right, 0.9)),
            "before_n": int(len(left)),
            "after_n": int(len(right)),
        }
        identity = {
            "opaque_id": opaque,
            "source": "metrics.parquet",
            "source_sha256": metrics_sha,
            "column": column,
            "window": [alert - before_seconds, alert + after_seconds],
        }
        doc_id = _document_id(identity)
        text = (
            f"METRIC evidence {doc_id}. Service {service}; metric {metric}. "
            f"Five-minute baseline median {values['before_median']:.9g}, "
            f"q10 {values['before_q10']:.9g}, q90 {values['before_q90']:.9g}; "
            f"incident median {values['after_median']:.9g}, "
            f"q10 {values['after_q10']:.9g}, q90 {values['after_q90']:.9g}."
        )
        documents.append(
            {
                "evidence_id": doc_id,
                "source": "metric",
                "source_file": "metrics.parquet",
                "source_sha256": metrics_sha,
                "service": service,
                "identity": identity,
                "values": values,
                "text": text,
            }
        )

    logs_path = case_root / "logs.parquet"
    logs_sha = file_sha256(logs_path)
    logs = pd.read_parquet(logs_path)
    logs = logs.loc[
        (logs["timestamp"] >= alert - before_seconds)
        & (logs["timestamp"] < alert + after_seconds),
        ["timestamp", "container_name", "message"],
    ].copy()
    logs["phase"] = np.where(logs["timestamp"] < alert, "before", "after")
    logs["template"] = logs["message"].map(normalize_log_message)
    grouped_logs = (
        logs.groupby(["container_name", "template", "phase"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
    )
    pivot_logs = grouped_logs.pivot_table(
        index=["container_name", "template"],
        columns="phase",
        values="count",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for row in pivot_logs.sort_values(["container_name", "template"]).to_dict(orient="records"):
        service = str(row["container_name"])
        template = str(row["template"])
        before_count = int(row.get("before", 0))
        after_count = int(row.get("after", 0))
        identity = {
            "opaque_id": opaque,
            "source": "logs.parquet",
            "source_sha256": logs_sha,
            "service": service,
            "template": template,
            "window": [alert - before_seconds, alert + after_seconds],
        }
        doc_id = _document_id(identity)
        documents.append(
            {
                "evidence_id": doc_id,
                "source": "log",
                "source_file": "logs.parquet",
                "source_sha256": logs_sha,
                "service": service,
                "identity": identity,
                "values": {"before_count": before_count, "after_count": after_count},
                "text": (
                    f"LOG evidence {doc_id}. Service {service}; template: {template}. "
                    f"Five-minute baseline count {before_count}; incident count {after_count}."
                ),
            }
        )

    traces_path = case_root / "traces.parquet"
    if traces_path.is_file():
        traces_sha = file_sha256(traces_path)
        traces = pd.read_parquet(traces_path)
        traces["timestamp"] = (traces["startTimeMillis"] // 1000).astype("int64")
        traces = traces.loc[
            (traces["timestamp"] >= alert - before_seconds)
            & (traces["timestamp"] < alert + after_seconds)
        ].copy()
        traces["phase"] = np.where(traces["timestamp"] < alert, "before", "after")
        traces["operation"] = traces["operationName"].fillna("<none>").astype(str).str.slice(0, 300)
        traces["error"] = traces["statusCode"].fillna(0).astype(float).ne(0)
        trace_group = (
            traces.groupby(["serviceName", "operation", "phase"], dropna=False)
            .agg(
                count=("spanID", "size"),
                error_count=("error", "sum"),
                duration_median=("duration", "median"),
                duration_q95=("duration", lambda values: values.quantile(0.95)),
            )
            .reset_index()
        )
        trace_pivot = trace_group.set_index(["serviceName", "operation", "phase"]).unstack(
            fill_value=0
        )
        for (service_value, operation), values in trace_pivot.sort_index().iterrows():
            service = str(service_value)
            flattened: dict[str, Any] = {}
            for metric in ("count", "error_count", "duration_median", "duration_q95"):
                for phase in ("before", "after"):
                    try:
                        raw = values[(metric, phase)]
                    except KeyError:
                        raw = 0
                    flattened[f"{phase}_{metric}"] = float(raw)
            identity = {
                "opaque_id": opaque,
                "source": "traces.parquet",
                "source_sha256": traces_sha,
                "service": service,
                "operation": str(operation),
                "window": [alert - before_seconds, alert + after_seconds],
            }
            doc_id = _document_id(identity)
            documents.append(
                {
                    "evidence_id": doc_id,
                    "source": "trace",
                    "source_file": "traces.parquet",
                    "source_sha256": traces_sha,
                    "service": service,
                    "identity": identity,
                    "values": flattened,
                    "text": (
                        f"TRACE evidence {doc_id}. Service {service}; operation {operation}. "
                        f"Baseline spans {flattened['before_count']:.0f}, errors "
                        f"{flattened['before_error_count']:.0f}, median duration "
                        f"{flattened['before_duration_median']:.9g}, q95 "
                        f"{flattened['before_duration_q95']:.9g}; incident spans "
                        f"{flattened['after_count']:.0f}, errors "
                        f"{flattened['after_error_count']:.0f}, median duration "
                        f"{flattened['after_duration_median']:.9g}, q95 "
                        f"{flattened['after_duration_q95']:.9g}."
                    ),
                }
            )

    documents.sort(key=lambda row: row["evidence_id"])
    return documents


class TelemetryHybridIndex:
    def __init__(self, documents: Sequence[dict[str, Any]], embeddings: np.ndarray) -> None:
        self.documents = list(documents)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        if self.embeddings.shape[0] != len(self.documents):
            raise ValueError("document/embedding count mismatch")
        texts = [str(row["text"]) for row in self.documents]
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
            norm="l2",
        )
        self.sparse_matrix = self.vectorizer.fit_transform(texts)
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.normalized_embeddings = self.embeddings / np.maximum(norms, 1e-12)

    def retrieve(
        self, query: str, query_embedding: np.ndarray, capacity: int = 16, rrf_k: int = 60
    ) -> dict[str, Any]:
        sparse_query = self.vectorizer.transform([query])
        sparse_scores = (self.sparse_matrix @ sparse_query.T).toarray().ravel()
        dense_query = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        dense_query = dense_query / max(float(np.linalg.norm(dense_query)), 1e-12)
        dense_scores = self.normalized_embeddings @ dense_query
        sparse_order = sorted(
            range(len(self.documents)),
            key=lambda index: (-float(sparse_scores[index]), self.documents[index]["evidence_id"]),
        )
        dense_order = sorted(
            range(len(self.documents)),
            key=lambda index: (-float(dense_scores[index]), self.documents[index]["evidence_id"]),
        )
        sparse_rank = np.empty(len(self.documents), dtype=np.int64)
        dense_rank = np.empty(len(self.documents), dtype=np.int64)
        sparse_rank[np.asarray(sparse_order)] = np.arange(len(self.documents))
        dense_rank[np.asarray(dense_order)] = np.arange(len(self.documents))
        rrf_scores = 1.0 / (rrf_k + sparse_rank) + 1.0 / (rrf_k + dense_rank)
        hybrid_order = sorted(
            range(len(self.documents)),
            key=lambda index: (
                -float(rrf_scores[index]),
                int(sparse_rank[index] + dense_rank[index]),
                self.documents[index]["evidence_id"],
            ),
        )
        selected = hybrid_order[:capacity]
        return {
            "documents": [self.documents[index] for index in selected],
            "sparse_top_ids": [self.documents[index]["evidence_id"] for index in sparse_order[:capacity]],
            "dense_top_ids": [self.documents[index]["evidence_id"] for index in dense_order[:capacity]],
            "hybrid_top_ids": [self.documents[index]["evidence_id"] for index in selected],
        }


def incident_query(services: Sequence[str]) -> str:
    return (
        "A software incident began at the alert timestamp. Identify the originating "
        "root-cause service, not merely a noisy downstream victim. Look for exceptions, "
        "failed calls, missing service activity, abnormal CPU, memory, sockets, disk I/O, "
        "latency, or error responses corroborated across telemetry. Candidate services: "
        + ", ".join(sorted(services))
        + "."
    )


def _reasoning_schema(services: Sequence[str], evidence_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["root_cause_service", "fault_class", "evidence_ids", "diagnosis"],
        "properties": {
            "root_cause_service": {"type": "string", "enum": sorted(set(services))},
            "fault_class": {
                "type": "string",
                "enum": [
                    "incorrect_parameter_values",
                    "missing_parameters",
                    "missing_function_call",
                    "incorrect_return_values",
                    "missing_exception_handlers",
                    "unknown",
                ],
            },
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(set(evidence_ids))},
                "minItems": 1,
                "maxItems": 5,
                "uniqueItems": True,
            },
            "diagnosis": {"type": "string", "maxLength": 700},
        },
    }


def _reasoning_prompt(query: str, evidence: Sequence[dict[str, Any]]) -> str:
    lines = [
        query,
        "Use only the evidence below. Return the originating service. Cite 1-5 supplied "
        "evidence IDs. If the fine-grained code fault is not supported, use unknown.",
        "EVIDENCE:",
    ]
    for row in evidence:
        if "text" in row:
            lines.append(str(row["text"]))
        else:
            lines.append(
                f"METRIC evidence {row['evidence_id']}. Service {row['service']}; "
                f"metric {row['metric']}; kind {row['kind']}; robust score "
                f"{float(row['score']):.6g}; baseline median {row.get('before_median')}; "
                f"incident median {row.get('after_median')}; largest shift "
                f"{row.get('largest_shift')}."
            )
    return "\n".join(lines)


def _parse_reasoning_response(record: dict[str, Any]) -> dict[str, Any]:
    content = str(record.get("response", {}).get("message", {}).get("content", ""))
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return {"valid": False, "raw_content": content}
    required = {"root_cause_service", "fault_class", "evidence_ids", "diagnosis"}
    if not isinstance(value, dict) or set(value) != required:
        return {"valid": False, "raw_content": content}
    return {"valid": True, **value}


def _candidate_services(case_result: dict[str, Any]) -> list[str]:
    return [str(row["service"]) for row in case_result["service_ranking"]]


def _reason_once(
    *,
    client: Any,
    purpose: str,
    key: str,
    query: str,
    services: Sequence[str],
    evidence: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    evidence_ids = [str(row["evidence_id"]) for row in evidence]
    prompt = _reasoning_prompt(query, evidence)
    record = client.call(
        purpose=purpose,
        key=key,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a constrained incident-diagnosis component. Return only the "
                    "requested JSON. Distinguish the origin from downstream symptoms."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        num_ctx=int(config()["baselines"]["max_context"]["context_limit_tokens"]),
        num_predict=int(config()["reasoner"]["max_output_tokens"]),
        format_spec=_reasoning_schema(services, evidence_ids),
    )
    parsed = _parse_reasoning_response(record)
    parsed["provided_evidence_ids"] = evidence_ids
    parsed["prompt_bytes"] = len(prompt.encode("utf-8"))
    parsed["call_id"] = f"{purpose}/{record['call_id']}"
    parsed["accounting"] = record["accounting"]
    parsed["citation_subset_valid"] = bool(parsed.get("valid")) and set(
        parsed.get("evidence_ids", [])
    ).issubset(evidence_ids)
    return parsed


def verify_case_provenance(case_root: Path, result: dict[str, Any]) -> dict[str, Any]:
    rerun = compile_case(case_root)
    exact = rerun == result
    source_hashes = all(
        file_sha256(case_root / row["source_file"]) == row["source_sha256"]
        for row in result["evidence_records"]
    )
    aggregate_hashes = all(
        digest({key: value for key, value in row.items() if key != "aggregate_digest"})
        == row["aggregate_digest"]
        for row in result["evidence_records"]
    )
    return {
        "exact_recomputation": exact,
        "source_hashes": source_hashes,
        "aggregate_hashes": aggregate_hashes,
        "pass": exact and source_hashes and aggregate_hashes,
    }


def run_mechanical(split: str, run_id: str) -> dict[str, Any]:
    root = PUBLIC_DATA_ROOT / split
    if not root.is_dir():
        raise RuntimeError(f"split is not staged: {root}")
    output_root = (ENGINEERING_ROOT if split == "engineering" else SCIENTIFIC_ROOT) / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for number, case_root in enumerate(sorted(path for path in root.iterdir() if path.is_dir()), start=1):
        case_started = time.perf_counter()
        operation_started = time.perf_counter()
        compiler = compile_case(case_root)
        compiler_seconds = time.perf_counter() - operation_started
        operation_started = time.perf_counter()
        baro = author_style_baro(case_root)
        baro_seconds = time.perf_counter() - operation_started
        operation_started = time.perf_counter()
        single_feature = single_feature_robust(case_root)
        single_feature_seconds = time.perf_counter() - operation_started
        operation_started = time.perf_counter()
        error_volume = post_error_volume(case_root)
        error_volume_seconds = time.perf_counter() - operation_started
        operation_started = time.perf_counter()
        provenance = verify_case_provenance(case_root, compiler)
        provenance_seconds = time.perf_counter() - operation_started
        row = {
            "opaque_id": compiler["opaque_id"],
            "dataset": compiler["dataset"],
            "compiler": compiler,
            "author_style_baro": baro,
            "single_feature_robust": single_feature,
            "post_error_volume": error_volume,
            "provenance": provenance,
            "timing": {
                "compiler_seconds": compiler_seconds,
                "author_style_baro_seconds": baro_seconds,
                "single_feature_robust_seconds": single_feature_seconds,
                "post_error_volume_seconds": error_volume_seconds,
                "provenance_recomputation_seconds": provenance_seconds,
            },
            "wall_seconds": time.perf_counter() - case_started,
        }
        write_json(output_root / "cases" / f"{compiler['opaque_id']}.json", row)
        rows.append(row)
        print(f"mechanical {split} {number}/{len(list(root.iterdir()))} {compiler['opaque_id']}", flush=True)
    sealed_predictions = {
        "experiment_id": "MCO-04",
        "split": split,
        "run_id": run_id,
        "case_count": len(rows),
        "predictions": [
            {
                "opaque_id": row["opaque_id"],
                "dataset": row["dataset"],
                "compiler_prediction": row["compiler"]["prediction"],
                "compiler_top3": row["compiler"]["top3"],
                "baro_prediction": row["author_style_baro"]["prediction"],
                "baro_top3": row["author_style_baro"]["top3"],
                "single_feature_prediction": row["single_feature_robust"]["prediction"],
                "single_feature_top3": row["single_feature_robust"]["top3"],
                "error_volume_prediction": row["post_error_volume"]["prediction"],
                "error_volume_top3": row["post_error_volume"]["top3"],
                "result_digest": row["compiler"]["result_digest"],
            }
            for row in rows
        ],
    }
    sealed_predictions["seal_sha256"] = digest(sealed_predictions["predictions"])
    write_json(output_root / "SEALED_PREDICTIONS.json", sealed_predictions)
    summary = {
        "split": split,
        "run_id": run_id,
        "case_count": len(rows),
        "scorer_read_guard_active": SCORER_READ_GUARD_ACTIVE,
        "all_provenance_pass": all(row["provenance"]["pass"] for row in rows),
        "all_capacity_pass": all(
            row["compiler"]["packet_count"] <= config()["compiler"]["packet_capacity_records"]
            for row in rows
        ),
        "median_raw_to_packet_byte_reduction": statistics.median(
            row["compiler"]["raw_to_packet_byte_reduction"] for row in rows
        ),
        "minimum_raw_to_packet_byte_reduction": min(
            row["compiler"]["raw_to_packet_byte_reduction"] for row in rows
        ),
        "timing": {
            name: {
                "sum_seconds": sum(float(row["timing"][name]) for row in rows),
                "median_seconds": statistics.median(
                    float(row["timing"][name]) for row in rows
                ),
            }
            for name in (
                "compiler_seconds",
                "author_style_baro_seconds",
                "single_feature_robust_seconds",
                "post_error_volume_seconds",
                "provenance_recomputation_seconds",
            )
        },
        "wall_seconds": time.perf_counter() - started,
        "sealed_predictions_sha256": sealed_predictions["seal_sha256"],
    }
    write_json(output_root / "MECHANICAL_SUMMARY.json", summary)
    return summary


def _wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def score_mechanical(split: str, run_id: str) -> dict[str, Any]:
    output_root = (ENGINEERING_ROOT if split == "engineering" else SCIENTIFIC_ROOT) / run_id
    sealed = read_json(output_root / "SEALED_PREDICTIONS.json")
    if digest(sealed["predictions"]) != sealed["seal_sha256"]:
        raise RuntimeError("prediction seal mismatch")
    labels = read_json(SCORER_ROOT / f"{split}_labels.json")
    variants = {
        "compiler": ("compiler_prediction", "compiler_top3"),
        "author_style_baro": ("baro_prediction", "baro_top3"),
        "single_feature_robust": ("single_feature_prediction", "single_feature_top3"),
        "post_error_volume": ("error_volume_prediction", "error_volume_top3"),
    }
    scored_rows: list[dict[str, Any]] = []
    for prediction in sealed["predictions"]:
        opaque = prediction["opaque_id"]
        label = labels[opaque]
        row = {
            "opaque_id": opaque,
            "dataset": label["dataset"],
            "root_cause_service": label["root_cause_service"],
            "fault": label["fault"],
        }
        for variant, (prediction_key, top3_key) in variants.items():
            row[variant] = {
                "prediction": prediction[prediction_key],
                "top1_correct": prediction[prediction_key] == label["root_cause_service"],
                "top3_correct": label["root_cause_service"] in prediction[top3_key],
            }
        scored_rows.append(row)
    metrics: dict[str, Any] = {}
    for variant in variants:
        successes = sum(row[variant]["top1_correct"] for row in scored_rows)
        top3 = sum(row[variant]["top3_correct"] for row in scored_rows)
        per_system = {}
        for dataset in sorted({row["dataset"] for row in scored_rows}):
            subset = [row for row in scored_rows if row["dataset"] == dataset]
            per_system[dataset] = {
                "n": len(subset),
                "top1": sum(row[variant]["top1_correct"] for row in subset) / len(subset),
                "top3": sum(row[variant]["top3_correct"] for row in subset) / len(subset),
            }
        metrics[variant] = {
            "n": len(scored_rows),
            "top1": successes / len(scored_rows),
            "top3": top3 / len(scored_rows),
            "wilson95_top1": _wilson_interval(successes, len(scored_rows)),
            "per_system": per_system,
        }
    report = {
        "experiment_id": "MCO-04",
        "split": split,
        "run_id": run_id,
        "seal_sha256": sealed["seal_sha256"],
        "metrics": metrics,
        "rows": scored_rows,
    }
    write_json(output_root / "SCORED_MECHANICAL.json", report)
    return report


def _safe_context_documents(
    query: str, documents: Sequence[dict[str, Any]], byte_limit: int | None = None
) -> list[dict[str, Any]]:
    if byte_limit is None:
        byte_limit = int(config()["baselines"]["max_context"]["prompt_byte_limit"])
    selected: list[dict[str, Any]] = []
    for document in documents:
        candidate = selected + [document]
        if len(_reasoning_prompt(query, candidate).encode("utf-8")) > byte_limit:
            break
        selected = candidate
    return selected or list(documents[:1])


def _reasoning_output_root(split: str, run_id: str) -> Path:
    base = ENGINEERING_ROOT if split == "engineering" else SCIENTIFIC_ROOT
    return base / run_id


def verify_shared_client_contract() -> dict[str, Any]:
    from scripts import run_mco03 as mco03

    cfg = config()
    shared_source = (REPO_ROOT / "scripts" / "run_mco03.py").read_text(encoding="utf-8")
    embedding_context = int(
        cfg["baselines"]["hybrid_rag_16"]["embedding_context_limit"]
    )
    checks = {
        "model_seed": int(mco03.MODEL_SEED) == int(cfg["reasoner"]["seed"]),
        "embedding_batch_size": int(mco03.EMBEDDING_BATCH_SIZE)
        == int(cfg["baselines"]["hybrid_rag_16"]["embedding_batch_size"]),
        "embedding_context_limit": f'"options": {{"num_ctx": {embedding_context}}}'
        in shared_source,
    }
    return {"checks": checks, "pass": all(checks.values())}


def balanced_variant_call_orders(case_ids: Sequence[str]) -> dict[str, list[str]]:
    ordered = sorted(
        (str(value) for value in case_ids),
        key=lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest(),
    )
    result: dict[str, list[str]] = {}
    for index, opaque in enumerate(ordered):
        offset = index % len(REASONING_VARIANTS)
        result[opaque] = list(
            REASONING_VARIANTS[offset:] + REASONING_VARIANTS[:offset]
        )
    return result


def run_reasoning(
    *, split: str, mechanical_run_id: str, run_id: str, mode: str = "live"
) -> dict[str, Any]:
    if mode not in {"live", "replay"}:
        raise ValueError(mode)
    from scripts import run_mco03 as mco03

    cfg = config()
    shared_contract = verify_shared_client_contract()
    if not shared_contract["pass"]:
        raise RuntimeError(f"shared client contract mismatch: {shared_contract}")
    public_root = PUBLIC_DATA_ROOT / split
    mechanical_root = _reasoning_output_root(split, mechanical_run_id)
    output_root = _reasoning_output_root(split, run_id)
    output_root.mkdir(parents=True, exist_ok=True)
    cache_root = (ENGINEERING_ROOT if split == "engineering" else SCIENTIFIC_ROOT) / "model_calls"
    model_client = mco03.FrozenModelClient(
        model_name=cfg["reasoner"]["model"],
        cache_root=cache_root / "reasoning",
        mode=mode,
    )
    embedding_client = mco03.FrozenEmbeddingClient(
        model_name=cfg["baselines"]["hybrid_rag_16"]["embedding_model"],
        cache_root=cache_root / "hybrid_embeddings",
        mode=mode,
    )
    cases = sorted(path for path in public_root.iterdir() if path.is_dir())
    call_orders = balanced_variant_call_orders([path.name for path in cases])
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for number, case_root in enumerate(cases, start=1):
        opaque = case_root.name
        mechanical = read_json(mechanical_root / "cases" / f"{opaque}.json")
        compiler = mechanical["compiler"]
        services = _candidate_services(compiler)
        query = incident_query(services)
        operation_started = time.perf_counter()
        documents = build_fixed_documents(case_root)
        document_build_seconds = time.perf_counter() - operation_started
        document_texts = [str(row["text"]) for row in documents]
        embedded_docs = embedding_client.embed(key=f"{opaque}-documents", inputs=document_texts)
        embedded_query = embedding_client.embed(key=f"{opaque}-query", inputs=[query])
        operation_started = time.perf_counter()
        index = TelemetryHybridIndex(documents, embedded_docs["matrix"])
        retrieval = index.retrieve(
            query,
            embedded_query["matrix"][0],
            capacity=int(cfg["baselines"]["hybrid_rag_16"]["capacity_records"]),
            rrf_k=int(cfg["baselines"]["hybrid_rag_16"]["rrf_k"]),
        )
        retrieval_cpu_seconds = time.perf_counter() - operation_started
        operation_started = time.perf_counter()
        max_context = _safe_context_documents(query, documents)
        max_context_selection_seconds = time.perf_counter() - operation_started
        variants = {
            "compiler_packet": compiler["evidence_records"],
            "hybrid_rag_16": retrieval["documents"],
            "max_context": max_context,
        }
        call_order = call_orders[opaque]
        reasoned_unordered: dict[str, Any] = {}
        call_wrapper_seconds: dict[str, float] = {}
        for variant in call_order:
            operation_started = time.perf_counter()
            reasoned_unordered[variant] = _reason_once(
                client=model_client,
                purpose=variant,
                key=opaque,
                query=query,
                services=services,
                evidence=variants[variant],
            )
            call_wrapper_seconds[variant] = time.perf_counter() - operation_started
        reasoned = {variant: reasoned_unordered[variant] for variant in REASONING_VARIANTS}
        all_doc_ids = {str(row["evidence_id"]) for row in documents}
        retrieval_integrity = {
            "hybrid_ids_exist": set(retrieval["hybrid_top_ids"]).issubset(all_doc_ids),
            "source_hashes": all(
                file_sha256(case_root / row["source_file"]) == row["source_sha256"]
                for row in retrieval["documents"]
            ),
            "capacity": len(retrieval["documents"])
            <= int(cfg["baselines"]["hybrid_rag_16"]["capacity_records"]),
        }
        retrieval_integrity["pass"] = all(retrieval_integrity.values())
        row = {
            "opaque_id": opaque,
            "dataset": compiler["dataset"],
            "document_count": len(documents),
            "document_text_bytes": sum(len(text.encode("utf-8")) for text in document_texts),
            "retrieval": {
                "sparse_top_ids": retrieval["sparse_top_ids"],
                "dense_top_ids": retrieval["dense_top_ids"],
                "hybrid_top_ids": retrieval["hybrid_top_ids"],
                "integrity": retrieval_integrity,
            },
            "max_context_document_count": len(max_context),
            "variant_call_order": call_order,
            "variants": reasoned,
            "embedding_usage": {
                "documents": embedded_docs["usage"],
                "query": embedded_query["usage"],
            },
            "timing": {
                "fixed_document_build_seconds": document_build_seconds,
                "document_embedding_wall_seconds": float(
                    embedded_docs["usage"]["wall_time_seconds"]
                ),
                "query_embedding_wall_seconds": float(
                    embedded_query["usage"]["wall_time_seconds"]
                ),
                "retrieval_cpu_seconds": retrieval_cpu_seconds,
                "max_context_selection_seconds": max_context_selection_seconds,
                "reasoning_call_wrapper_seconds": call_wrapper_seconds,
                "online_query_seconds": {
                    "compiler_packet": float(
                        reasoned["compiler_packet"]["accounting"]["wall_time_seconds"]
                    ),
                    "hybrid_rag_16": float(
                        embedded_query["usage"]["wall_time_seconds"]
                    )
                    + retrieval_cpu_seconds
                    + float(reasoned["hybrid_rag_16"]["accounting"]["wall_time_seconds"]),
                    "max_context": max_context_selection_seconds
                    + float(reasoned["max_context"]["accounting"]["wall_time_seconds"]),
                },
            },
        }
        row["row_digest"] = digest(
            {key: value for key, value in row.items() if key not in {"row_digest", "timing"}}
        )
        write_json(output_root / "cases" / f"{opaque}.json", row)
        rows.append(row)
        print(f"reasoning {split} {number}/{len(cases)} {opaque}", flush=True)

    predictions = []
    for row in rows:
        predictions.append(
            {
                "opaque_id": row["opaque_id"],
                "dataset": row["dataset"],
                "variants": {
                    variant: {
                        "valid": value["valid"],
                        "root_cause_service": value.get("root_cause_service"),
                        "fault_class": value.get("fault_class"),
                        "evidence_ids": value.get("evidence_ids", []),
                        "citation_subset_valid": value["citation_subset_valid"],
                        "provided_evidence_ids": value["provided_evidence_ids"],
                        "call_id": value["call_id"],
                        "accounting": value["accounting"],
                    }
                    for variant, value in row["variants"].items()
                },
                "row_digest": row["row_digest"],
            }
        )
    sealed = {
        "experiment_id": "MCO-04",
        "split": split,
        "mechanical_run_id": mechanical_run_id,
        "run_id": run_id,
        "mode": mode,
        "case_count": len(predictions),
        "predictions": predictions,
    }
    sealed["seal_sha256"] = digest(predictions)
    write_json(output_root / "SEALED_REASONING_PREDICTIONS.json", sealed)
    summary = {
        "split": split,
        "run_id": run_id,
        "mode": mode,
        "case_count": len(rows),
        "scorer_read_guard_active": SCORER_READ_GUARD_ACTIVE,
        "shared_client_contract": shared_contract,
        "all_outputs_valid": all(
            value["valid"] for row in rows for value in row["variants"].values()
        ),
        "all_citation_subsets_valid": all(
            value["citation_subset_valid"]
            for row in rows
            for value in row["variants"].values()
        ),
        "all_retrieval_integrity_pass": all(row["retrieval"]["integrity"]["pass"] for row in rows),
        "usage": {
            variant: {
                "model_calls": len(rows),
                "prompt_tokens": sum(
                    int(row["variants"][variant]["accounting"]["prompt_eval_count"])
                    for row in rows
                ),
                "output_tokens": sum(
                    int(row["variants"][variant]["accounting"]["eval_count"])
                    for row in rows
                ),
                "wall_seconds": sum(
                    float(row["variants"][variant]["accounting"]["wall_time_seconds"])
                    for row in rows
                ),
                "model_load_seconds": sum(
                    float(row["variants"][variant]["accounting"]["load_duration_ns"])
                    / 1e9
                    for row in rows
                ),
                "model_compute_seconds": sum(
                    (
                        float(
                            row["variants"][variant]["accounting"][
                                "prompt_eval_duration_ns"
                            ]
                        )
                        + float(
                            row["variants"][variant]["accounting"]["eval_duration_ns"]
                        )
                    )
                    / 1e9
                    for row in rows
                ),
                "maximum_prompt_tokens": max(
                    int(row["variants"][variant]["accounting"]["prompt_eval_count"])
                    for row in rows
                ),
                "maximum_output_tokens": max(
                    int(row["variants"][variant]["accounting"]["eval_count"])
                    for row in rows
                ),
            }
            for variant in ("compiler_packet", "hybrid_rag_16", "max_context")
        },
        "embedding_usage": {
            "model_calls": sum(
                int(row["embedding_usage"][kind]["model_calls"])
                for row in rows
                for kind in ("documents", "query")
            ),
            "input_tokens": sum(
                int(row["embedding_usage"][kind]["input_tokens"])
                for row in rows
                for kind in ("documents", "query")
            ),
            "wall_seconds": sum(
                float(row["embedding_usage"][kind]["wall_time_seconds"])
                for row in rows
                for kind in ("documents", "query")
            ),
        },
        "timing": {
            "fixed_document_build_seconds": sum(
                float(row["timing"]["fixed_document_build_seconds"]) for row in rows
            ),
            "document_embedding_wall_seconds": sum(
                float(row["timing"]["document_embedding_wall_seconds"]) for row in rows
            ),
            "query_embedding_wall_seconds": sum(
                float(row["timing"]["query_embedding_wall_seconds"]) for row in rows
            ),
            "retrieval_cpu_seconds": sum(
                float(row["timing"]["retrieval_cpu_seconds"]) for row in rows
            ),
            "max_context_selection_seconds": sum(
                float(row["timing"]["max_context_selection_seconds"]) for row in rows
            ),
            "online_query_seconds": {
                variant: sum(
                    float(row["timing"]["online_query_seconds"][variant]) for row in rows
                )
                for variant in REASONING_VARIANTS
            },
            "call_order_first_counts": {
                variant: sum(row["variant_call_order"][0] == variant for row in rows)
                for variant in REASONING_VARIANTS
            },
        },
        "seal_sha256": sealed["seal_sha256"],
        "wall_seconds": time.perf_counter() - started,
    }
    write_json(output_root / "REASONING_SUMMARY.json", summary)
    return summary


def score_reasoning(split: str, run_id: str) -> dict[str, Any]:
    output_root = _reasoning_output_root(split, run_id)
    sealed = read_json(output_root / "SEALED_REASONING_PREDICTIONS.json")
    if digest(sealed["predictions"]) != sealed["seal_sha256"]:
        raise RuntimeError("reasoning prediction seal mismatch")
    labels = read_json(SCORER_ROOT / f"{split}_labels.json")
    fault_names = config()["task"]["fault_classes"]
    variants = ("compiler_packet", "hybrid_rag_16", "max_context")
    rows: list[dict[str, Any]] = []
    for prediction in sealed["predictions"]:
        opaque = prediction["opaque_id"]
        label = labels[opaque]
        row = {
            "opaque_id": opaque,
            "dataset": label["dataset"],
            "root_cause_service": label["root_cause_service"],
            "fault": label["fault"],
            "variants": {},
        }
        for variant in variants:
            value = prediction["variants"][variant]
            row["variants"][variant] = {
                "valid": value["valid"],
                "root_cause_service": value["root_cause_service"],
                "root_top1_correct": value["root_cause_service"] == label["root_cause_service"],
                "fault_class": value["fault_class"],
                "fault_exact": value["fault_class"] == fault_names[label["fault"]],
                "citation_subset_valid": value["citation_subset_valid"],
            }
        rows.append(row)
    metrics: dict[str, Any] = {}
    for variant in variants:
        successes = sum(row["variants"][variant]["root_top1_correct"] for row in rows)
        metrics[variant] = {
            "n": len(rows),
            "valid": sum(row["variants"][variant]["valid"] for row in rows) / len(rows),
            "root_top1": successes / len(rows),
            "root_wilson95": _wilson_interval(successes, len(rows)),
            "fault_exact": sum(row["variants"][variant]["fault_exact"] for row in rows)
            / len(rows),
            "citation_subset_valid": sum(
                row["variants"][variant]["citation_subset_valid"] for row in rows
            )
            / len(rows),
            "per_system_root_top1": {
                dataset: sum(
                    row["variants"][variant]["root_top1_correct"]
                    for row in rows
                    if row["dataset"] == dataset
                )
                / sum(row["dataset"] == dataset for row in rows)
                for dataset in sorted({row["dataset"] for row in rows})
            },
        }
    report = {
        "experiment_id": "MCO-04",
        "split": split,
        "run_id": run_id,
        "seal_sha256": sealed["seal_sha256"],
        "metrics": metrics,
        "rows": rows,
    }
    write_json(output_root / "SCORED_REASONING.json", report)
    return report


def repeat_case_ids(case_ids: Sequence[str]) -> list[str]:
    """Select the preregistered stability subset without reading labels."""

    cfg = config()
    fraction = float(cfg["reasoner"]["repeat_fraction"])
    count = max(1, math.ceil(len(case_ids) * fraction)) if case_ids else 0
    seed = int(cfg["reasoner"]["seed"])
    return sorted(
        (str(value) for value in case_ids),
        key=lambda value: hashlib.sha256(f"{seed}|{value}".encode("utf-8")).hexdigest(),
    )[:count]


def run_stability(
    *,
    mechanical_run_id: str,
    live_reasoning_run_id: str,
    run_id: str,
) -> dict[str, Any]:
    """Make fresh calls for the frozen, label-blind scientific repeat subset."""

    from scripts import run_mco03 as mco03

    cfg = config()
    public_root = PUBLIC_DATA_ROOT / "scientific"
    mechanical_root = SCIENTIFIC_ROOT / mechanical_run_id
    live_root = SCIENTIFIC_ROOT / live_reasoning_run_id
    output_root = SCIENTIFIC_ROOT / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    case_ids = sorted(path.name for path in public_root.iterdir() if path.is_dir())
    selected_ids = repeat_case_ids(case_ids)
    call_orders = balanced_variant_call_orders(case_ids)
    client = mco03.FrozenModelClient(
        model_name=cfg["reasoner"]["model"],
        cache_root=SCIENTIFIC_ROOT / "model_calls" / "stability_reasoning",
        mode="live",
    )
    semantic_fields = tuple(cfg["reasoner"]["semantic_repeat_fields"])
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for number, opaque in enumerate(selected_ids, start=1):
        case_root = public_root / opaque
        mechanical = read_json(mechanical_root / "cases" / f"{opaque}.json")
        live = read_json(live_root / "cases" / f"{opaque}.json")
        compiler = mechanical["compiler"]
        services = _candidate_services(compiler)
        query = incident_query(services)
        documents = build_fixed_documents(case_root)
        by_id = {str(row["evidence_id"]): row for row in documents}
        hybrid_ids = [str(value) for value in live["retrieval"]["hybrid_top_ids"]]
        if not set(hybrid_ids).issubset(by_id):
            raise RuntimeError(f"stability retrieval reconstruction failed: {opaque}")
        evidence_by_variant = {
            "compiler_packet": compiler["evidence_records"],
            "hybrid_rag_16": [by_id[value] for value in hybrid_ids],
            "max_context": _safe_context_documents(query, documents),
        }
        comparisons: dict[str, Any] = {}
        call_order = call_orders[opaque]
        for variant in call_order:
            repeated = _reason_once(
                client=client,
                purpose=f"stability_{variant}",
                key=opaque,
                query=query,
                services=services,
                evidence=evidence_by_variant[variant],
            )
            original = live["variants"][variant]
            semantic_match = all(
                repeated.get(field) == original.get(field) for field in semantic_fields
            )
            exact_structured_match = all(
                repeated.get(field) == original.get(field)
                for field in (
                    "valid",
                    "root_cause_service",
                    "fault_class",
                    "evidence_ids",
                    "diagnosis",
                )
            )
            comparisons[variant] = {
                "semantic_match": semantic_match,
                "exact_structured_match": exact_structured_match,
                "original": {
                    field: original.get(field)
                    for field in (
                        "valid",
                        "root_cause_service",
                        "fault_class",
                        "evidence_ids",
                        "diagnosis",
                    )
                },
                "repeat": repeated,
            }
        comparisons = {variant: comparisons[variant] for variant in REASONING_VARIANTS}
        row = {
            "opaque_id": opaque,
            "variant_call_order": call_order,
            "comparisons": comparisons,
        }
        row["row_digest"] = digest(row)
        write_json(output_root / "cases" / f"{opaque}.json", row)
        rows.append(row)
        print(f"stability scientific {number}/{len(selected_ids)} {opaque}", flush=True)
    total = len(rows) * len(REASONING_VARIANTS)
    semantic_matches = sum(
        row["comparisons"][variant]["semantic_match"]
        for row in rows
        for variant in REASONING_VARIANTS
    )
    exact_matches = sum(
        row["comparisons"][variant]["exact_structured_match"]
        for row in rows
        for variant in REASONING_VARIANTS
    )
    sealed = {
        "experiment_id": "MCO-04",
        "run_id": run_id,
        "selected_ids": selected_ids,
        "rows": rows,
    }
    sealed["seal_sha256"] = digest(rows)
    write_json(output_root / "SEALED_STABILITY.json", sealed)
    summary = {
        "run_id": run_id,
        "scorer_read_guard_active": SCORER_READ_GUARD_ACTIVE,
        "population_case_count": len(case_ids),
        "selected_case_count": len(selected_ids),
        "selected_ids": selected_ids,
        "variant_count": len(REASONING_VARIANTS),
        "comparison_count": total,
        "semantic_matches": semantic_matches,
        "semantic_agreement": semantic_matches / total if total else 0.0,
        "exact_structured_matches": exact_matches,
        "exact_structured_agreement": exact_matches / total if total else 0.0,
        "all_repeat_outputs_valid": all(
            row["comparisons"][variant]["repeat"]["valid"]
            for row in rows
            for variant in REASONING_VARIANTS
        ),
        "all_repeat_citations_valid": all(
            row["comparisons"][variant]["repeat"]["citation_subset_valid"]
            for row in rows
            for variant in REASONING_VARIANTS
        ),
        "seal_sha256": sealed["seal_sha256"],
        "wall_seconds": time.perf_counter() - started,
    }
    write_json(output_root / "STABILITY_SUMMARY.json", summary)
    return summary


def verify_replay() -> dict[str, Any]:
    execution = config()["execution"]
    mechanical_live = read_json(
        SCIENTIFIC_ROOT
        / execution["scientific_mechanical_live_run_id"]
        / "SEALED_PREDICTIONS.json"
    )
    mechanical_replay = read_json(
        SCIENTIFIC_ROOT
        / execution["scientific_mechanical_replay_run_id"]
        / "SEALED_PREDICTIONS.json"
    )
    reasoning_live = read_json(
        SCIENTIFIC_ROOT
        / execution["scientific_reasoning_live_run_id"]
        / "SEALED_REASONING_PREDICTIONS.json"
    )
    reasoning_replay = read_json(
        SCIENTIFIC_ROOT
        / execution["scientific_reasoning_replay_run_id"]
        / "SEALED_REASONING_PREDICTIONS.json"
    )
    checks = {
        "mechanical_live_seal_valid": digest(mechanical_live["predictions"])
        == mechanical_live["seal_sha256"],
        "mechanical_replay_seal_valid": digest(mechanical_replay["predictions"])
        == mechanical_replay["seal_sha256"],
        "mechanical_predictions_identical": mechanical_live["predictions"]
        == mechanical_replay["predictions"],
        "reasoning_live_seal_valid": digest(reasoning_live["predictions"])
        == reasoning_live["seal_sha256"],
        "reasoning_replay_seal_valid": digest(reasoning_replay["predictions"])
        == reasoning_replay["seal_sha256"],
        "reasoning_predictions_identical": reasoning_live["predictions"]
        == reasoning_replay["predictions"],
    }
    result = {"checks": checks, "pass": all(checks.values())}
    write_json(SCIENTIFIC_ROOT / "REPLAY_CHECK.json", result)
    return result


def verify_reasoning_receipts(split: str, run_id: str) -> dict[str, Any]:
    """Bind sealed scientific predictions back to raw model receipts."""

    if split not in {"engineering", "scientific"}:
        raise ValueError(split)
    base = ENGINEERING_ROOT if split == "engineering" else SCIENTIFIC_ROOT
    root = base / run_id
    sealed = read_json(root / "SEALED_REASONING_PREDICTIONS.json")
    cache_root = base / "model_calls" / "reasoning"
    failures: list[dict[str, str]] = []
    checked = 0
    for prediction in sealed["predictions"]:
        for variant, value in prediction["variants"].items():
            qualified = str(value["call_id"])
            if not qualified.startswith(f"{variant}/"):
                failures.append({"call_id": qualified, "failure": "purpose"})
                continue
            path = cache_root / f"{qualified}.json"
            if not path.is_file():
                failures.append({"call_id": qualified, "failure": "missing"})
                continue
            record = read_json(path)
            content = str(record.get("response", {}).get("message", {}).get("content", ""))
            parsed = _parse_reasoning_response(record)
            checks = {
                "request_digest": digest(record.get("request"))
                == record.get("request_sha256"),
                "response_digest": hashlib.sha256(content.encode("utf-8")).hexdigest()
                == record.get("response_content_sha256"),
                "accounting": value.get("accounting") == record.get("accounting"),
                "valid": value.get("valid") == parsed.get("valid"),
                "root": value.get("root_cause_service")
                == parsed.get("root_cause_service"),
                "fault": value.get("fault_class") == parsed.get("fault_class"),
                "evidence": value.get("evidence_ids") == parsed.get("evidence_ids", []),
                "nonnegative_accounting": all(
                    float(number) >= 0 for number in record.get("accounting", {}).values()
                ),
            }
            for name, passed in checks.items():
                if not passed:
                    failures.append({"call_id": qualified, "failure": name})
            checked += 1
    return {
        "split": split,
        "run_id": run_id,
        "checked_calls": checked,
        "failures": failures,
        "pass": not failures,
    }


def verify_stability_receipts(run_id: str) -> dict[str, Any]:
    sealed = read_json(SCIENTIFIC_ROOT / run_id / "SEALED_STABILITY.json")
    cache_root = SCIENTIFIC_ROOT / "model_calls" / "stability_reasoning"
    failures: list[dict[str, str]] = []
    checked = 0
    for row in sealed["rows"]:
        for variant, comparison in row["comparisons"].items():
            value = comparison["repeat"]
            qualified = str(value["call_id"])
            if not qualified.startswith(f"stability_{variant}/"):
                failures.append({"call_id": qualified, "failure": "purpose"})
                continue
            path = cache_root / f"{qualified}.json"
            if not path.is_file():
                failures.append({"call_id": qualified, "failure": "missing"})
                continue
            record = read_json(path)
            content = str(record.get("response", {}).get("message", {}).get("content", ""))
            parsed = _parse_reasoning_response(record)
            checks = {
                "request_digest": digest(record.get("request"))
                == record.get("request_sha256"),
                "response_digest": hashlib.sha256(content.encode("utf-8")).hexdigest()
                == record.get("response_content_sha256"),
                "accounting": value.get("accounting") == record.get("accounting"),
                "valid": value.get("valid") == parsed.get("valid"),
                "root": value.get("root_cause_service")
                == parsed.get("root_cause_service"),
                "fault": value.get("fault_class") == parsed.get("fault_class"),
                "evidence": value.get("evidence_ids") == parsed.get("evidence_ids", []),
            }
            for name, passed in checks.items():
                if not passed:
                    failures.append({"call_id": qualified, "failure": name})
            checked += 1
    return {"run_id": run_id, "checked_calls": checked, "failures": failures, "pass": not failures}


def verify_mechanical_artifacts(split: str, run_id: str) -> dict[str, Any]:
    """Recompute every compiler/control result and compare it with the sealed run."""

    if split not in {"engineering", "scientific"}:
        raise ValueError(split)
    base = ENGINEERING_ROOT if split == "engineering" else SCIENTIFIC_ROOT
    public_root = PUBLIC_DATA_ROOT / split
    output_root = base / run_id
    sealed = read_json(output_root / "SEALED_PREDICTIONS.json")
    failures: list[dict[str, str]] = []
    prediction_by_id = {str(row["opaque_id"]): row for row in sealed["predictions"]}
    if digest(sealed["predictions"]) != sealed["seal_sha256"]:
        failures.append({"opaque_id": "*", "failure": "seal"})
    checked = 0
    for case_root in sorted(path for path in public_root.iterdir() if path.is_dir()):
        opaque = case_root.name
        row_path = output_root / "cases" / f"{opaque}.json"
        if not row_path.is_file() or opaque not in prediction_by_id:
            failures.append({"opaque_id": opaque, "failure": "missing"})
            continue
        stored = read_json(row_path)
        compiler = compile_case(case_root)
        controls = {
            "author_style_baro": author_style_baro(case_root),
            "single_feature_robust": single_feature_robust(case_root),
            "post_error_volume": post_error_volume(case_root),
        }
        prediction = prediction_by_id[opaque]
        checks = {
            "compiler": stored.get("compiler") == compiler,
            "author_style_baro": stored.get("author_style_baro")
            == controls["author_style_baro"],
            "single_feature_robust": stored.get("single_feature_robust")
            == controls["single_feature_robust"],
            "post_error_volume": stored.get("post_error_volume")
            == controls["post_error_volume"],
            "provenance": stored.get("provenance", {}).get("pass") is True,
            "compiler_prediction": prediction.get("compiler_prediction")
            == compiler["prediction"],
            "compiler_top3": prediction.get("compiler_top3") == compiler["top3"],
            "compiler_digest": prediction.get("result_digest")
            == compiler["result_digest"],
            "baro_prediction": prediction.get("baro_prediction")
            == controls["author_style_baro"]["prediction"],
            "single_prediction": prediction.get("single_feature_prediction")
            == controls["single_feature_robust"]["prediction"],
            "error_prediction": prediction.get("error_volume_prediction")
            == controls["post_error_volume"]["prediction"],
        }
        for name, passed in checks.items():
            if not passed:
                failures.append({"opaque_id": opaque, "failure": name})
        checked += 1
    return {
        "split": split,
        "run_id": run_id,
        "checked_cases": checked,
        "failures": failures,
        "pass": not failures and checked == len(prediction_by_id),
    }


def evaluate_mco04_verdict(
    *,
    mechanical_summary: dict[str, Any],
    mechanical_score: dict[str, Any],
    reasoning_summary: dict[str, Any],
    reasoning_score: dict[str, Any],
    stability: dict[str, Any],
    integrity_pass: bool,
) -> tuple[str, dict[str, Any]]:
    criteria = config()["criteria"]
    compiler = mechanical_score["metrics"]["compiler"]
    compiler_top1 = float(compiler["top1"])
    compiler_quality = bool(
        compiler_top1 >= criteria["compiler_minimum_top1"]
        and float(compiler["top3"]) >= criteria["compiler_minimum_top3"]
        and float(compiler["wilson95_top1"][0])
        >= criteria["compiler_minimum_wilson95_lower_top1"]
        and all(
            float(values["top1"]) >= criteria["compiler_minimum_per_system_top1"]
            for values in compiler["per_system"].values()
        )
    )
    provenance = bool(mechanical_summary["all_provenance_pass"])
    capacity = bool(mechanical_summary["all_capacity_pass"])
    compression = bool(
        float(mechanical_summary["median_raw_to_packet_byte_reduction"])
        >= criteria["minimum_median_raw_to_packet_byte_reduction"]
        and float(mechanical_summary["minimum_raw_to_packet_byte_reduction"])
        >= criteria["minimum_case_raw_to_packet_byte_reduction"]
    )
    direct_compiler_gate = compiler_quality and provenance and capacity and compression
    packet = reasoning_score["metrics"]["compiler_packet"]
    packet_top1 = float(packet["root_top1"])
    packet_quality = bool(
        float(packet["valid"]) == 1.0
        and float(packet["citation_subset_valid"]) == 1.0
        and packet_top1 >= criteria["model_packet_minimum_top1"]
        and compiler_top1 - packet_top1
        <= criteria["model_packet_maximum_drop_from_compiler"]
    )
    stability_pass = bool(
        float(stability["semantic_agreement"])
        >= criteria["minimum_semantic_repeat_agreement"]
    )

    mechanical_controls = {
        name: mechanical_score["metrics"][name]
        for name in ("author_style_baro", "single_feature_robust", "post_error_volume")
    }
    best_mechanical_name, best_mechanical = max(
        mechanical_controls.items(), key=lambda item: float(item[1]["top1"])
    )
    reasoning_controls = {
        name: reasoning_score["metrics"][name]
        for name in ("hybrid_rag_16", "max_context")
    }
    best_reasoning_name, best_reasoning = max(
        reasoning_controls.items(), key=lambda item: float(item[1]["root_top1"])
    )
    minimum_advantage = float(criteria["minimum_quality_advantage"])
    compiler_advantage = compiler_top1 - float(best_mechanical["top1"])
    packet_advantage = packet_top1 - max(
        compiler_top1, float(best_reasoning["root_top1"])
    )
    bounded_inference_advance = bool(
        direct_compiler_gate
        and packet_quality
        and stability_pass
        and packet_advantage >= minimum_advantage
    )
    conventional_dominates = bool(
        not bounded_inference_advance
        and (
            compiler_advantage < minimum_advantage
            or float(best_reasoning["root_top1"])
            >= compiler_top1 + minimum_advantage
        )
    )

    packet_usage = reasoning_summary["usage"]["compiler_packet"]
    hybrid_usage = reasoning_summary["usage"]["hybrid_rag_16"]
    max_context_usage = reasoning_summary["usage"]["max_context"]
    online_latency = reasoning_summary["timing"]["online_query_seconds"]

    def ratio(numerator: float, denominator: float) -> float | None:
        return numerator / denominator if denominator > 0 else None

    hybrid_token_reduction = ratio(
        float(hybrid_usage["prompt_tokens"]), float(packet_usage["prompt_tokens"])
    )
    max_context_token_reduction = ratio(
        float(max_context_usage["prompt_tokens"]), float(packet_usage["prompt_tokens"])
    )
    hybrid_model_latency_reduction = ratio(
        float(hybrid_usage["wall_seconds"]), float(packet_usage["wall_seconds"])
    )
    max_context_model_latency_reduction = ratio(
        float(max_context_usage["wall_seconds"]), float(packet_usage["wall_seconds"])
    )
    hybrid_online_latency_reduction = ratio(
        float(online_latency["hybrid_rag_16"]),
        float(online_latency["compiler_packet"]),
    )
    max_context_online_latency_reduction = ratio(
        float(online_latency["max_context"]),
        float(online_latency["compiler_packet"]),
    )
    equivalence_margin = float(criteria["quality_equivalence_margin"])
    packet_hybrid_quality_equivalent = abs(
        packet_top1 - float(reasoning_controls["hybrid_rag_16"]["root_top1"])
    ) <= equivalence_margin
    packet_max_context_quality_equivalent = abs(
        packet_top1 - float(reasoning_controls["max_context"]["root_top1"])
    ) <= equivalence_margin
    packet_hybrid_cost_win = bool(
        packet_hybrid_quality_equivalent
        and hybrid_token_reduction is not None
        and hybrid_token_reduction
        >= float(criteria["minimum_model_token_reduction_at_equivalent_quality"])
        and hybrid_online_latency_reduction is not None
        and hybrid_online_latency_reduction
        >= float(criteria["minimum_latency_reduction_at_equivalent_quality"])
    )
    packet_max_context_cost_win = bool(
        packet_max_context_quality_equivalent
        and max_context_token_reduction is not None
        and max_context_token_reduction
        >= float(criteria["minimum_model_token_reduction_at_equivalent_quality"])
        and max_context_online_latency_reduction is not None
        and max_context_online_latency_reduction
        >= float(criteria["minimum_latency_reduction_at_equivalent_quality"])
    )

    gates = {
        "integrity_pass": integrity_pass,
        "compiler_quality": compiler_quality,
        "provenance": provenance,
        "capacity": capacity,
        "compression": compression,
        "direct_compiler_gate": direct_compiler_gate,
        "packet_quality": packet_quality,
        "stability_pass": stability_pass,
        "bounded_inference_advance": bounded_inference_advance,
        "conventional_dominates": conventional_dominates,
        "packet_hybrid_quality_equivalent": packet_hybrid_quality_equivalent,
        "packet_max_context_quality_equivalent": packet_max_context_quality_equivalent,
        "packet_hybrid_cost_win": packet_hybrid_cost_win,
        "packet_max_context_cost_win": packet_max_context_cost_win,
        "compiler_top1": compiler_top1,
        "compiler_top3": float(compiler["top3"]),
        "compiler_wilson95": compiler["wilson95_top1"],
        "best_mechanical_control": best_mechanical_name,
        "best_mechanical_top1": float(best_mechanical["top1"]),
        "compiler_quality_advantage": compiler_advantage,
        "packet_top1": packet_top1,
        "best_reasoning_control": best_reasoning_name,
        "best_reasoning_top1": float(best_reasoning["root_top1"]),
        "packet_quality_advantage": packet_advantage,
        "packet_vs_hybrid_prompt_token_reduction": hybrid_token_reduction,
        "packet_vs_max_context_prompt_token_reduction": max_context_token_reduction,
        "packet_vs_hybrid_model_latency_reduction": hybrid_model_latency_reduction,
        "packet_vs_max_context_model_latency_reduction": max_context_model_latency_reduction,
        "packet_vs_hybrid_online_latency_reduction": hybrid_online_latency_reduction,
        "packet_vs_max_context_online_latency_reduction": max_context_online_latency_reduction,
    }
    if not integrity_pass:
        outcome = "MCO_04_BENCHMARK_INVALID"
    elif not direct_compiler_gate:
        outcome = "MCO_04_REAL_WORKLOAD_FAILURE"
    elif bounded_inference_advance:
        outcome = "MCO_04_BOUNDED_INFERENCE_REPLICATION_ADVANCE"
    elif conventional_dominates:
        outcome = "MCO_04_CONVENTIONAL_RCA_DOMINATES"
    else:
        outcome = "MCO_04_TRANSPARENT_STATE_COMPILER_REPLICATION_ADVANCE"
    return outcome, gates


def render_report(verdict: dict[str, Any]) -> str:
    gates = verdict["gates"]
    checks = verdict["verification"]["checks"]
    outcome = verdict["verdict"]
    overall = verdict["overall_verification"]
    usage = verdict["reasoning_usage"]
    timing = verdict["reasoning_timing"]
    advance = outcome in {
        "MCO_04_TRANSPARENT_STATE_COMPILER_REPLICATION_ADVANCE",
        "MCO_04_BOUNDED_INFERENCE_REPLICATION_ADVANCE",
    }
    lines = [
        "# MCO-04 — OPAQUE REAL-TELEMETRY REPLICATION GATE",
        "",
        "## Claim under test",
        "",
        "A transparent compiler can reduce append-only incident telemetry to at most 16 auditable records while retaining root-cause localization quality on unseen executions of service/fault strata represented during engineering.",
        "",
        "## Check",
        "",
        (
            f"Frozen RCAEval RE3 replication: {verdict['case_count']} opaque scientific incidents across three systems, direct and model-mediated compiler outputs, three mechanical controls, hybrid retrieval, a 24 KB safe-context control, fresh stability repeats, and content-addressed replay."
        ),
        "",
        "| Method | Root-cause top-1 | Top-3 / fault exact |",
        "|---|---:|---:|",
        f"| transparent compiler | {gates['compiler_top1']:.2%} | {gates['compiler_top3']:.2%} top-3 |",
        f"| best mechanical control ({gates['best_mechanical_control']}) | {gates['best_mechanical_top1']:.2%} | — |",
        f"| model over compiler packet | {gates['packet_top1']:.2%} | {verdict['packet_fault_exact']:.2%} fault |",
        f"| best reasoned control ({gates['best_reasoning_control']}) | {gates['best_reasoning_top1']:.2%} | — |",
        "",
        "| Inference path | Prompt tokens | Output tokens | Model wall | Online query wall |",
        "|---|---:|---:|---:|---:|",
        f"| compiler packet | {usage['compiler_packet']['prompt_tokens']:,} | {usage['compiler_packet']['output_tokens']:,} | {usage['compiler_packet']['wall_seconds']:.2f}s | {timing['online_query_seconds']['compiler_packet']:.2f}s |",
        f"| hybrid RAG-16 | {usage['hybrid_rag_16']['prompt_tokens']:,} | {usage['hybrid_rag_16']['output_tokens']:,} | {usage['hybrid_rag_16']['wall_seconds']:.2f}s | {timing['online_query_seconds']['hybrid_rag_16']:.2f}s |",
        f"| maximum safe context | {usage['max_context']['prompt_tokens']:,} | {usage['max_context']['output_tokens']:,} | {usage['max_context']['wall_seconds']:.2f}s | {timing['online_query_seconds']['max_context']:.2f}s |",
        "",
        f"Hybrid ingestion used {verdict['embedding_usage']['model_calls']:,} embedding calls and {verdict['embedding_usage']['input_tokens']:,} embedding input tokens. Direct compiler ingestion took {verdict['compiler_ingestion_seconds']:.2f}s across the scientific set.",
        "",
        f"## Verdict — {overall}",
        "",
        f"`{outcome}`",
        "",
        "## Criteria",
        "",
    ]
    for key, value in gates.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: **{'PASS' if value else 'FAIL'}**")
    lines.extend(
        [
            f"- semantic repeat agreement: {verdict['stability_semantic_agreement']:.2%}",
            f"- median raw-to-packet byte reduction: {verdict['median_compression']:.1f}×",
            f"- minimum case reduction: {verdict['minimum_compression']:.1f}×",
            "",
            "## Assumption register",
            "",
            "- Verified: deterministic telemetry staging, source hashes, opaque label separation, exact packet recomputation, 16-record capacity, held-out-run quality, model receipts, stability, and replay on the pinned benchmark.",
            "- Not verified: unseen service/fault strata, organic production incidents, counterfactual causality, changing schemas, concurrent operations, access control, operator usefulness, deployment economics, or prospective impact.",
            "- The scientific split repeats every engineering service/fault stratum. It measures telemetry-run replication, not broad incident generalization.",
            "- The public index exposes labels. The holdout is protected by frozen executable isolation and a literal-leak audit, not by experimenter ignorance of ground truth.",
            "- RCAEval RE3 is fault-injection telemetry. Benchmark success can support mechanics but cannot establish market value or societal impact.",
            "",
            "## Credit assignment",
            "",
            "The transparent compiler receives credit only for direct root-cause ranking, bounded auditable evidence, and measured compression. The frozen reasoner receives separate credit only for any improvement over that direct ranking. Retrieval and maximum-context controls receive the same raw modalities. DMC and learned retention receive no credit in this gate.",
            "",
            "## Verification gap",
            "",
            "This is self-verified public-benchmark evidence with frozen replay, not independent replication. The benchmark repeats known strata and exposes an alert timestamp. A disjoint workload with held-out structures, followed by an independently operated prospective pilot, remains necessary.",
            "",
            "## Stop/continue",
            "",
            (
                "Continue only to a preregistered disjoint-workload gate; do not claim product or world impact from this result."
                if advance
                else "Stop this branch on the tested workload unless a new falsifiable mechanism addresses the terminal failure; do not tune on the scientific cases."
            ),
            "",
            "## Maturity status",
            "",
            (
                "Replicated benchmark mechanism; pre-product and pre-impact."
                if advance
                else "Terminal negative on this branch; no product or impact claim."
            ),
            "",
            "Historical accounting remains explicit: DMC used 10,880 reconstructed optimizer steps, and its wall-time, energy, and dollar training cost remain `TRAINING_COST_UNKNOWN`. MCO-04 performs zero optimizer steps; pretrained-model training cost is unknown, not zero.",
            "Local billed API cost is $0.00; this is not a claim of zero compute, energy, hardware, or opportunity cost. No dollar estimate is reported without a defensible rate.",
            "",
            "## Integrity checks",
            "",
        ]
    )
    for key, value in checks.items():
        lines.append(f"- {key}: **{'PASS' if value else 'FAIL'}**")
    return "\n".join(lines) + "\n"


def finalize() -> dict[str, Any]:
    cfg = config()
    execution = cfg["execution"]
    paths = {
        "preflight": SCIENTIFIC_ROOT / "PREFLIGHT.json",
        "mechanical_summary": SCIENTIFIC_ROOT
        / execution["scientific_mechanical_live_run_id"]
        / "MECHANICAL_SUMMARY.json",
        "mechanical_score": SCIENTIFIC_ROOT
        / execution["scientific_mechanical_live_run_id"]
        / "SCORED_MECHANICAL.json",
        "mechanical_replay_summary": SCIENTIFIC_ROOT
        / execution["scientific_mechanical_replay_run_id"]
        / "MECHANICAL_SUMMARY.json",
        "reasoning_summary": SCIENTIFIC_ROOT
        / execution["scientific_reasoning_live_run_id"]
        / "REASONING_SUMMARY.json",
        "reasoning_score": SCIENTIFIC_ROOT
        / execution["scientific_reasoning_live_run_id"]
        / "SCORED_REASONING.json",
        "reasoning_replay_summary": SCIENTIFIC_ROOT
        / execution["scientific_reasoning_replay_run_id"]
        / "REASONING_SUMMARY.json",
        "stability": SCIENTIFIC_ROOT
        / execution["scientific_stability_run_id"]
        / "STABILITY_SUMMARY.json",
        "stability_seal": SCIENTIFIC_ROOT
        / execution["scientific_stability_run_id"]
        / "SEALED_STABILITY.json",
        "replay": SCIENTIFIC_ROOT / "REPLAY_CHECK.json",
    }
    missing = [str(path.relative_to(REPO_ROOT)) for path in paths.values() if not path.is_file()]
    if missing:
        result = {
            "experiment_id": "MCO-04",
            "verdict": "MCO_04_INCOMPLETE",
            "overall_verification": "INCONCLUSIVE",
            "missing": missing,
        }
        write_json(SCIENTIFIC_ROOT / "MCO04_VERDICT.json", result)
        return result

    values = {key: read_json(path) for key, path in paths.items()}
    freeze = verify_freeze()
    opacity = verify_opacity("scientific")
    replay = values["replay"]
    reasoning_receipts_live = verify_reasoning_receipts(
        "scientific", execution["scientific_reasoning_live_run_id"]
    )
    reasoning_receipts_replay = verify_reasoning_receipts(
        "scientific", execution["scientific_reasoning_replay_run_id"]
    )
    stability_receipts = verify_stability_receipts(
        execution["scientific_stability_run_id"]
    )
    mechanical_audit_live = verify_mechanical_artifacts(
        "scientific", execution["scientific_mechanical_live_run_id"]
    )
    mechanical_audit_replay = verify_mechanical_artifacts(
        "scientific", execution["scientific_mechanical_replay_run_id"]
    )
    stability_seal = values["stability_seal"]
    stability = values["stability"]
    expected_count = int(cfg["benchmark"]["expected_scientific_cases"])
    expected_repeat_ids = repeat_case_ids(
        sorted(read_json(SCORER_ROOT / "scientific_labels.json").keys())
    )
    checks = {
        "freeze": freeze["pass"],
        "preflight": values["preflight"]["pass"],
        "opacity": opacity["pass"],
        "scientific_case_count": values["mechanical_summary"]["case_count"]
        == expected_count,
        "mechanical_scorer_guard": values["mechanical_summary"][
            "scorer_read_guard_active"
        ],
        "mechanical_score_count": values["mechanical_score"]["metrics"]["compiler"]["n"]
        == expected_count,
        "mechanical_scoring_binding": values["mechanical_score"]["seal_sha256"]
        == values["mechanical_summary"]["sealed_predictions_sha256"],
        "mechanical_replay_count": values["mechanical_replay_summary"]["case_count"]
        == expected_count,
        "mechanical_replay_scorer_guard": values["mechanical_replay_summary"][
            "scorer_read_guard_active"
        ],
        "reasoning_case_count": values["reasoning_summary"]["case_count"]
        == expected_count,
        "reasoning_scoring_binding": values["reasoning_score"]["seal_sha256"]
        == values["reasoning_summary"]["seal_sha256"],
        "reasoning_scorer_guard": values["reasoning_summary"][
            "scorer_read_guard_active"
        ],
        "reasoning_shared_client_contract": values["reasoning_summary"][
            "shared_client_contract"
        ]["pass"],
        "reasoning_replay_count": values["reasoning_replay_summary"]["case_count"]
        == expected_count,
        "reasoning_replay_scorer_guard": values["reasoning_replay_summary"][
            "scorer_read_guard_active"
        ],
        "reasoning_replay_shared_client_contract": values["reasoning_replay_summary"][
            "shared_client_contract"
        ]["pass"],
        "reasoning_call_order_balanced": max(
            values["reasoning_summary"]["timing"]["call_order_first_counts"].values()
        )
        - min(values["reasoning_summary"]["timing"]["call_order_first_counts"].values())
        <= 1,
        "reasoning_replay_call_order_balanced": max(
            values["reasoning_replay_summary"]["timing"][
                "call_order_first_counts"
            ].values()
        )
        - min(
            values["reasoning_replay_summary"]["timing"][
                "call_order_first_counts"
            ].values()
        )
        <= 1,
        "replay": replay["pass"],
        "live_receipts": reasoning_receipts_live["pass"],
        "replay_receipts": reasoning_receipts_replay["pass"],
        "stability_receipts": stability_receipts["pass"],
        "mechanical_live_recomputation": mechanical_audit_live["pass"],
        "mechanical_replay_recomputation": mechanical_audit_replay["pass"],
        "retrieval_integrity": values["reasoning_summary"]["all_retrieval_integrity_pass"],
        "max_context_below_limit": int(
            values["reasoning_summary"]["usage"]["max_context"]["maximum_prompt_tokens"]
        )
        + int(
            values["reasoning_summary"]["usage"]["max_context"]["maximum_output_tokens"]
        )
        < int(cfg["baselines"]["max_context"]["context_limit_tokens"]),
        "stability_selection": stability["selected_ids"] == expected_repeat_ids,
        "stability_scorer_guard": stability["scorer_read_guard_active"],
        "stability_seal": digest(stability_seal["rows"])
        == stability_seal["seal_sha256"]
        == stability["seal_sha256"],
        "stability_outputs": stability["all_repeat_outputs_valid"],
        "stability_citations": stability["all_repeat_citations_valid"],
    }
    integrity_pass = all(checks.values())
    outcome, gates = evaluate_mco04_verdict(
        mechanical_summary=values["mechanical_summary"],
        mechanical_score=values["mechanical_score"],
        reasoning_summary=values["reasoning_summary"],
        reasoning_score=values["reasoning_score"],
        stability=stability,
        integrity_pass=integrity_pass,
    )
    result = {
        "experiment_id": "MCO-04",
        "verdict": outcome,
        "overall_verification": "PASS"
        if outcome
        in {
            "MCO_04_TRANSPARENT_STATE_COMPILER_REPLICATION_ADVANCE",
            "MCO_04_BOUNDED_INFERENCE_REPLICATION_ADVANCE",
        }
        else "FAIL",
        "case_count": expected_count,
        "gates": gates,
        "verification": {
            "checks": checks,
            "freeze": freeze,
            "live_receipts": reasoning_receipts_live,
            "replay_receipts": reasoning_receipts_replay,
            "stability_receipts": stability_receipts,
            "mechanical_live_recomputation": mechanical_audit_live,
            "mechanical_replay_recomputation": mechanical_audit_replay,
        },
        "stability_semantic_agreement": stability["semantic_agreement"],
        "median_compression": values["mechanical_summary"][
            "median_raw_to_packet_byte_reduction"
        ],
        "minimum_compression": values["mechanical_summary"][
            "minimum_raw_to_packet_byte_reduction"
        ],
        "packet_fault_exact": values["reasoning_score"]["metrics"]["compiler_packet"][
            "fault_exact"
        ],
        "reasoning_usage": values["reasoning_summary"]["usage"],
        "reasoning_timing": values["reasoning_summary"]["timing"],
        "embedding_usage": values["reasoning_summary"]["embedding_usage"],
        "compiler_ingestion_seconds": values["mechanical_summary"]["timing"][
            "compiler_seconds"
        ]["sum_seconds"],
        "freeze_sha256": read_json(FREEZE_PATH)["freeze_sha256"],
        "world_impact_disposition": "NOT_ESTABLISHED",
        "training_accounting": {
            "mco04_online_optimizer_steps": 0,
            "dmc_historical_optimizer_steps_preserved": 10880,
            "dmc_historical_training_label": "TRAINING_COST_UNKNOWN",
            "pretrained_model_training_cost": "UNKNOWN_NOT_ZERO",
        },
        "cost_accounting": cfg["accounting"],
    }
    write_json(SCIENTIFIC_ROOT / "MCO04_VERDICT.json", result)
    (REPO_ROOT / "experiments" / "mco04" / "MCO04_FINAL_REPORT.md").write_text(
        render_report(result), encoding="utf-8"
    )
    return result


def verify_opacity(split: str) -> dict[str, Any]:
    root = PUBLIC_DATA_ROOT / split
    labels = read_json(SCORER_ROOT / f"{split}_labels.json")
    failures: list[str] = []
    for case_root in sorted(path for path in root.iterdir() if path.is_dir()):
        opaque = case_root.name
        label = labels[opaque]
        public_metadata = read_json(case_root / "incident.json")
        public_text = canonical(public_metadata)
        if label["source_case"] in public_text:
            failures.append(opaque)
        if set(public_metadata) != {"opaque_id", "dataset", "alert_time", "files"}:
            failures.append(opaque)
        if any(label["source_case"] in str(path.relative_to(root)) for path in case_root.rglob("*")):
            failures.append(opaque)
        if not re.fullmatch(r"incident_[0-9a-f]{20}", opaque):
            failures.append(opaque)
    receipt = {"split": split, "failures": sorted(set(failures)), "pass": not failures}
    write_json(ARTIFACT_ROOT / f"{split}_opacity_receipt.json", receipt)
    return receipt


def _relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def freeze_sources() -> list[Path]:
    return [
        CONFIG_PATH,
        CONTRACT_PATH,
        Path(__file__).resolve(),
        REPO_ROOT / "scripts" / "run_mco03.py",
        REPO_ROOT / "tests" / "test_mco04.py",
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "uv.lock",
        SOURCE_MANIFEST_PATH,
        ARTIFACT_ROOT / "engineering_staging_receipt.json",
        ARTIFACT_ROOT / "engineering_opacity_receipt.json",
        ENGINEERING_ROOT
        / config()["execution"]["engineering_mechanical_run_id"]
        / "MECHANICAL_SUMMARY.json",
        ENGINEERING_ROOT
        / config()["execution"]["engineering_mechanical_run_id"]
        / "SEALED_PREDICTIONS.json",
        ENGINEERING_ROOT
        / config()["execution"]["engineering_mechanical_run_id"]
        / "SCORED_MECHANICAL.json",
        ENGINEERING_ROOT
        / config()["execution"]["engineering_reasoning_run_id"]
        / "REASONING_SUMMARY.json",
        ENGINEERING_ROOT
        / config()["execution"]["engineering_reasoning_run_id"]
        / "SEALED_REASONING_PREDICTIONS.json",
        ENGINEERING_ROOT
        / config()["execution"]["engineering_reasoning_run_id"]
        / "SCORED_REASONING.json",
    ]


def verify_scientific_literal_isolation() -> dict[str, Any]:
    """Reject explicit scientific case identifiers in executable freeze sources."""

    manifest = read_json(SOURCE_MANIFEST_PATH)
    forbidden: list[tuple[str, str]] = []
    for row in manifest["incidents"]:
        if row["split"] == "scientific":
            forbidden.extend(
                (
                    ("opaque_id", str(row["opaque_id"])),
                    ("source_case", str(row["source_case"])),
                )
            )
    scan_paths = [
        CONFIG_PATH,
        CONTRACT_PATH,
        Path(__file__).resolve(),
        REPO_ROOT / "scripts" / "run_mco03.py",
        REPO_ROOT / "tests" / "test_mco04.py",
        REPO_ROOT / "pyproject.toml",
    ]
    failures: list[dict[str, str]] = []
    for path in scan_paths:
        text = path.read_text(encoding="utf-8")
        for kind, value in forbidden:
            if value and value in text:
                failures.append(
                    {"path": _relative(path), "kind": kind, "value": value}
                )
    return {
        "scanned_paths": [_relative(path) for path in scan_paths],
        "forbidden_literal_count": len(forbidden),
        "failures": failures,
        "pass": not failures,
    }


def verify_engineering() -> dict[str, Any]:
    cfg = config()
    execution = cfg["execution"]
    mechanical_root = ENGINEERING_ROOT / execution["engineering_mechanical_run_id"]
    reasoning_root = ENGINEERING_ROOT / execution["engineering_reasoning_run_id"]
    required = [
        SOURCE_MANIFEST_PATH,
        ARTIFACT_ROOT / "engineering_staging_receipt.json",
        mechanical_root / "MECHANICAL_SUMMARY.json",
        mechanical_root / "SEALED_PREDICTIONS.json",
        mechanical_root / "SCORED_MECHANICAL.json",
        reasoning_root / "REASONING_SUMMARY.json",
        reasoning_root / "SEALED_REASONING_PREDICTIONS.json",
        reasoning_root / "SCORED_REASONING.json",
    ]
    missing = [_relative(path) for path in required if not path.is_file()]
    opacity = verify_opacity("engineering")
    literal_isolation = verify_scientific_literal_isolation()
    checks: dict[str, Any] = {
        "required_files": not missing,
        "missing": missing,
        "opacity": opacity["pass"],
        "scientific_literal_isolation": literal_isolation["pass"],
    }
    if not missing:
        mechanical = read_json(mechanical_root / "MECHANICAL_SUMMARY.json")
        mechanical_score = read_json(mechanical_root / "SCORED_MECHANICAL.json")
        reasoning = read_json(reasoning_root / "REASONING_SUMMARY.json")
        reasoning_score = read_json(reasoning_root / "SCORED_REASONING.json")
        receipts = verify_reasoning_receipts(
            "engineering", execution["engineering_reasoning_run_id"]
        )
        mechanical_audit = verify_mechanical_artifacts(
            "engineering", execution["engineering_mechanical_run_id"]
        )
        checks.update(
            {
                "engineering_count": mechanical["case_count"]
                == cfg["benchmark"]["expected_engineering_cases"],
                "mechanical_scorer_guard": mechanical["scorer_read_guard_active"],
                "compiler_top1": mechanical_score["metrics"]["compiler"]["top1"] == 1.0,
                "provenance": mechanical["all_provenance_pass"],
                "capacity": mechanical["all_capacity_pass"],
                "reasoning_count": reasoning["case_count"]
                == cfg["benchmark"]["expected_engineering_cases"],
                "reasoning_scorer_guard": reasoning["scorer_read_guard_active"],
                "reasoning_shared_client_contract": reasoning[
                    "shared_client_contract"
                ]["pass"],
                "reasoning_call_order_balanced": max(
                    reasoning["timing"]["call_order_first_counts"].values()
                )
                - min(reasoning["timing"]["call_order_first_counts"].values())
                <= 1,
                "reasoning_score_count": reasoning_score["metrics"]["compiler_packet"]["n"]
                == cfg["benchmark"]["expected_engineering_cases"],
                "reasoning_outputs": reasoning["all_outputs_valid"],
                "reasoning_citations": reasoning["all_citation_subsets_valid"],
                "retrieval_integrity": reasoning["all_retrieval_integrity_pass"],
                "reasoning_receipts": receipts["pass"],
                "mechanical_recomputation": mechanical_audit["pass"],
                "max_context_below_limit": int(
                    reasoning["usage"]["max_context"]["maximum_prompt_tokens"]
                )
                + int(reasoning["usage"]["max_context"]["maximum_output_tokens"])
                < int(cfg["baselines"]["max_context"]["context_limit_tokens"]),
            }
        )
    scientific_public = PUBLIC_DATA_ROOT / "scientific"
    scientific_calls = SCIENTIFIC_ROOT / "model_calls"
    checks["no_scientific_telemetry"] = not scientific_public.exists() or not any(
        path.is_file() for path in scientific_public.rglob("*")
    )
    checks["no_scientific_model_calls"] = not scientific_calls.exists() or not any(
        path.is_file() for path in scientific_calls.rglob("*")
    )
    artifact_paths: list[Path] = []
    for root in (mechanical_root, reasoning_root, ENGINEERING_ROOT / "model_calls"):
        if root.exists():
            artifact_paths.extend(path for path in root.rglob("*") if path.is_file())
    receipt = {
        "checks": checks,
        "artifact_hashes": {
            _relative(path): file_sha256(path) for path in sorted(set(artifact_paths))
        },
        "scientific_literal_isolation": literal_isolation,
        "pass": all(value is True or key == "missing" for key, value in checks.items()),
    }
    write_json(ENGINEERING_ROOT / "ENGINEERING_VERIFICATION.json", receipt)
    return receipt


def create_freeze() -> dict[str, Any]:
    if FREEZE_PATH.exists():
        raise RuntimeError(f"freeze already exists: {FREEZE_PATH}")
    engineering = verify_engineering()
    if not engineering["pass"]:
        raise RuntimeError("engineering verification did not pass")
    sources = freeze_sources() + [ENGINEERING_ROOT / "ENGINEERING_VERIFICATION.json"]
    missing = [_relative(path) for path in sources if not path.is_file()]
    if missing:
        raise RuntimeError(f"freeze sources missing: {missing}")
    from scripts import run_mco03 as mco03

    cfg = config()
    shared_contract = verify_shared_client_contract()
    if not shared_contract["pass"]:
        raise RuntimeError(f"shared client contract mismatch: {shared_contract}")
    reasoner_identity = mco03.model_identity(cfg["reasoner"]["model"])
    embedding_identity = mco03.model_identity(
        cfg["baselines"]["hybrid_rag_16"]["embedding_model"]
    )
    if reasoner_identity.get("blob_sha256") != cfg["reasoner"]["blob_sha256"]:
        raise RuntimeError("reasoner identity mismatch")
    if (
        embedding_identity.get("blob_sha256")
        != cfg["baselines"]["hybrid_rag_16"]["embedding_blob_sha256"]
    ):
        raise RuntimeError("embedding identity mismatch")
    observed_ollama_version = ollama_version()
    if observed_ollama_version != cfg["runtime"]["ollama_version"]:
        raise RuntimeError("Ollama version mismatch")
    scientific_public = PUBLIC_DATA_ROOT / "scientific"
    scientific_calls = SCIENTIFIC_ROOT / "model_calls"
    freeze = {
        "experiment_id": "MCO-04",
        "schema_version": 1,
        "source_hashes": {_relative(path): file_sha256(path) for path in sources},
        "source_manifest_sha256": file_sha256(SOURCE_MANIFEST_PATH),
        "models": {"reasoner": reasoner_identity, "embedding": embedding_identity},
        "ollama_version": observed_ollama_version,
        "dependencies": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "pyarrow": importlib.metadata.version("pyarrow"),
            "scikit-learn": importlib.metadata.version("scikit-learn"),
            "python": sys.version,
        },
        "scientific_state_at_freeze": {
            "telemetry_files": (
                sum(path.is_file() for path in scientific_public.rglob("*"))
                if scientific_public.exists()
                else 0
            ),
            "model_call_files": (
                sum(path.is_file() for path in scientific_calls.rglob("*"))
                if scientific_calls.exists()
                else 0
            ),
        },
        "engineering_verification_sha256": file_sha256(
            ENGINEERING_ROOT / "ENGINEERING_VERIFICATION.json"
        ),
    }
    freeze["freeze_sha256"] = digest(
        {key: value for key, value in freeze.items() if key != "freeze_sha256"}
    )
    write_json(FREEZE_PATH, freeze)
    return freeze


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.is_file():
        return {"pass": False, "error": "freeze missing"}
    freeze = read_json(FREEZE_PATH)
    expected_freeze_sha = digest(
        {key: value for key, value in freeze.items() if key != "freeze_sha256"}
    )
    mismatches: list[dict[str, Any]] = []
    for relative, expected in freeze.get("source_hashes", {}).items():
        path = REPO_ROOT / relative
        observed = file_sha256(path) if path.is_file() else None
        if observed != expected:
            mismatches.append({"path": relative, "expected": expected, "observed": observed})
    engineering_receipt_path = ENGINEERING_ROOT / "ENGINEERING_VERIFICATION.json"
    if engineering_receipt_path.is_file():
        engineering_receipt = read_json(engineering_receipt_path)
        for relative, expected in engineering_receipt.get("artifact_hashes", {}).items():
            path = REPO_ROOT / relative
            observed = file_sha256(path) if path.is_file() else None
            if observed != expected:
                mismatches.append(
                    {"path": relative, "expected": expected, "observed": observed}
                )
    from scripts import run_mco03 as mco03

    reasoner = mco03.model_identity(config()["reasoner"]["model"])
    embedding = mco03.model_identity(config()["baselines"]["hybrid_rag_16"]["embedding_model"])
    checks = {
        "freeze_digest": freeze.get("freeze_sha256") == expected_freeze_sha,
        "source_hashes": not mismatches,
        "reasoner_identity": reasoner.get("blob_sha256")
        == freeze.get("models", {}).get("reasoner", {}).get("blob_sha256"),
        "embedding_identity": embedding.get("blob_sha256")
        == freeze.get("models", {}).get("embedding", {}).get("blob_sha256"),
        "ollama_version": ollama_version() == freeze.get("ollama_version"),
        "zero_scientific_telemetry_at_freeze": freeze.get("scientific_state_at_freeze", {}).get(
            "telemetry_files"
        )
        == 0,
        "zero_scientific_calls_at_freeze": freeze.get("scientific_state_at_freeze", {}).get(
            "model_call_files"
        )
        == 0,
    }
    return {"checks": checks, "mismatches": mismatches, "pass": all(checks.values())}


def preflight() -> dict[str, Any]:
    cfg = config()
    freeze = verify_freeze()
    public_root = PUBLIC_DATA_ROOT / "scientific"
    cases = sorted(path for path in public_root.iterdir() if path.is_dir()) if public_root.exists() else []
    opacity = verify_opacity("scientific") if cases else {"pass": False, "failures": ["not staged"]}
    file_hashes = True
    for case_root in cases:
        metadata = read_json(case_root / "incident.json")
        for name, identity in metadata["files"].items():
            if file_sha256(case_root / name) != identity["sha256"]:
                file_hashes = False
    checks = {
        "freeze": freeze["pass"],
        "scientific_count": len(cases) == cfg["benchmark"]["expected_scientific_cases"],
        "opacity": opacity["pass"],
        "file_hashes": file_hashes,
    }
    receipt = {"checks": checks, "freeze": freeze, "pass": all(checks.values())}
    write_json(SCIENTIFIC_ROOT / "PREFLIGHT.json", receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build-source-manifest")
    subparsers.add_parser("verify-engineering")
    subparsers.add_parser("freeze")
    subparsers.add_parser("verify-freeze")
    subparsers.add_parser("preflight")
    stage = subparsers.add_parser("stage")
    stage.add_argument("--split", choices=("engineering", "scientific"), required=True)
    stage.add_argument("--source-root", type=Path)
    run = subparsers.add_parser("run-mechanical")
    run.add_argument("--split", choices=("engineering", "scientific"), required=True)
    run.add_argument("--run-id", required=True)
    score = subparsers.add_parser("score-mechanical")
    score.add_argument("--split", choices=("engineering", "scientific"), required=True)
    score.add_argument("--run-id", required=True)
    reason = subparsers.add_parser("run-reasoning")
    reason.add_argument("--split", choices=("engineering", "scientific"), required=True)
    reason.add_argument("--mechanical-run-id", required=True)
    reason.add_argument("--run-id", required=True)
    reason.add_argument("--mode", choices=("live", "replay"), default="live")
    reason_score = subparsers.add_parser("score-reasoning")
    reason_score.add_argument("--split", choices=("engineering", "scientific"), required=True)
    reason_score.add_argument("--run-id", required=True)
    stability = subparsers.add_parser("run-stability")
    stability.add_argument("--mechanical-run-id", required=True)
    stability.add_argument("--live-reasoning-run-id", required=True)
    stability.add_argument("--run-id", required=True)
    subparsers.add_parser("verify-replay")
    subparsers.add_parser("finalize")
    opacity = subparsers.add_parser("verify-opacity")
    opacity.add_argument("--split", choices=("engineering", "scientific"), required=True)
    args = parser.parse_args(argv)
    if args.command in {"run-mechanical", "run-reasoning", "run-stability"}:
        install_scorer_read_guard()
    if args.command == "build-source-manifest":
        value = build_source_manifest()
    elif args.command == "verify-engineering":
        value = verify_engineering()
    elif args.command == "freeze":
        value = create_freeze()
    elif args.command == "verify-freeze":
        value = verify_freeze()
    elif args.command == "preflight":
        value = preflight()
    elif args.command == "stage":
        value = stage_split(args.split, args.source_root)
    elif args.command == "run-mechanical":
        value = run_mechanical(args.split, args.run_id)
    elif args.command == "score-mechanical":
        value = score_mechanical(args.split, args.run_id)
    elif args.command == "run-reasoning":
        value = run_reasoning(
            split=args.split,
            mechanical_run_id=args.mechanical_run_id,
            run_id=args.run_id,
            mode=args.mode,
        )
    elif args.command == "score-reasoning":
        value = score_reasoning(args.split, args.run_id)
    elif args.command == "run-stability":
        value = run_stability(
            mechanical_run_id=args.mechanical_run_id,
            live_reasoning_run_id=args.live_reasoning_run_id,
            run_id=args.run_id,
        )
    elif args.command == "verify-replay":
        value = verify_replay()
    elif args.command == "finalize":
        value = finalize()
    elif args.command == "verify-opacity":
        value = verify_opacity(args.split)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
