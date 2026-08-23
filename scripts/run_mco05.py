#!/usr/bin/env python3
"""MCO-05: frozen disjoint change-attribution state-compiler gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import tomllib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import run_mco03 as mco03  # noqa: E402


CONFIG_PATH = REPO_ROOT / "experiments" / "mco05" / "MCO05_CONFIG.json"
CONTRACT_PATH = REPO_ROOT / "experiments" / "mco05" / "MCO05_CONTRACT.md"
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "mco05"
FREEZE_PATH = ARTIFACT_ROOT / "MCO05_FREEZE.json"
SOURCE_ROOT = ARTIFACT_ROOT / "source" / "root-cause-bench"
DATA_ROOT = ARTIFACT_ROOT / "data"
PUBLIC_ROOT = DATA_ROOT / "public"
SCORER_ROOT = DATA_ROOT / "scorer_only"
RUN_ROOT = ARTIFACT_ROOT / "scientific"
MODEL_CALL_ROOT = ARTIFACT_ROOT / "model_calls"
REPORT_PATH = REPO_ROOT / "experiments" / "mco05" / "MCO05_FINAL_REPORT.md"
VERDICT_PATH = RUN_ROOT / "MCO05_VERDICT.json"
HEX_PATTERN = re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?![A-Za-z])")
WORD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_.:/-]{2,}")
REASONING_VARIANTS = ("state_packet", "hybrid_rag_16", "max_context")
REMEDIATIONS = (
    "rollback",
    "roll-forward",
    "config-revert",
    "scale",
    "feature-flag-disable",
    "unknown",
)
SCORER_READ_GUARD_ACTIVE = False


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


def config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def _relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, FileNotFoundError):
        return False


def install_scorer_read_guard() -> None:
    global SCORER_READ_GUARD_ACTIVE
    if SCORER_READ_GUARD_ACTIVE:
        return

    protected = (SCORER_ROOT.resolve(), SOURCE_ROOT.resolve())

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event != "open" or not args:
            return
        raw = args[0]
        if not isinstance(raw, (str, bytes, os.PathLike)):
            return
        try:
            path = Path(raw).resolve()
        except (OSError, TypeError, ValueError):
            return
        if any(_path_is_within(path, root) for root in protected):
            raise PermissionError(f"MCO-05 scorer/source read guard blocked: {path}")

    sys.addaudithook(audit)
    SCORER_READ_GUARD_ACTIVE = True


def _run(command: Sequence[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def remote_head() -> str:
    output = _run(["git", "ls-remote", config()["benchmark"]["repository"], "HEAD"])
    return output.split()[0]


def ollama_version() -> str:
    output = _run(["ollama", "--version"])
    match = re.search(r"(\d+\.\d+\.\d+)", output)
    return match.group(1) if match else output


def _model_clients(mode: str, variant: str, *, stability: bool = False) -> mco03.FrozenModelClient:
    cfg = config()
    mco03.MODEL_SEED = int(cfg["reasoner"]["seed"])
    base = MODEL_CALL_ROOT / ("stability" if stability else "reasoning") / variant
    return mco03.FrozenModelClient(
        model_name=cfg["reasoner"]["model"], cache_root=base, mode=mode
    )


def _embedding_client(mode: str, opaque_id: str) -> mco03.FrozenEmbeddingClient:
    cfg = config()
    mco03.EMBEDDING_BATCH_SIZE = int(cfg["retrieval"]["batch_size"])
    return mco03.FrozenEmbeddingClient(
        model_name=cfg["retrieval"]["model"],
        cache_root=MODEL_CALL_ROOT / "embeddings" / opaque_id,
        mode=mode,
    )


def _source_files() -> list[Path]:
    paths = [
        CONFIG_PATH,
        CONTRACT_PATH,
        REPO_ROOT / "scripts" / "run_mco03.py",
        REPO_ROOT / "scripts" / "run_mco05.py",
        REPO_ROOT / "tests" / "test_mco05.py",
        REPO_ROOT / "pyproject.toml",
    ]
    lock = REPO_ROOT / "uv.lock"
    if lock.is_file():
        paths.append(lock)
    return paths


def create_freeze() -> dict[str, Any]:
    cfg = config()
    if any(path.exists() for path in (SOURCE_ROOT, PUBLIC_ROOT, SCORER_ROOT, RUN_ROOT, MODEL_CALL_ROOT)):
        raise RuntimeError("MCO-05 scenario, run, or model-call state exists before freeze")
    expected = cfg["benchmark"]["commit"]
    observed = remote_head()
    if observed != expected:
        raise RuntimeError(f"benchmark HEAD changed: {observed} != {expected}")
    reasoner = mco03.model_identity(cfg["reasoner"]["model"])
    embedding = mco03.model_identity(cfg["retrieval"]["model"])
    if reasoner.get("blob_sha256") != cfg["reasoner"]["blob_sha256"]:
        raise RuntimeError("reasoner identity mismatch")
    if embedding.get("blob_sha256") != cfg["retrieval"]["blob_sha256"]:
        raise RuntimeError("embedding identity mismatch")
    source_hashes = {_relative(path): file_sha256(path) for path in _source_files()}
    body = {
        "schema_version": 1,
        "experiment_id": cfg["experiment_id"],
        "benchmark_head": observed,
        "source_hashes": source_hashes,
        "models": {"reasoner": reasoner, "embedding": embedding},
        "ollama_version": ollama_version(),
        "scientific_state_at_freeze": {
            "source_files": 0,
            "public_files": 0,
            "scorer_files": 0,
            "model_call_files": 0,
        },
    }
    body["freeze_sha256"] = digest(body)
    write_json(FREEZE_PATH, body)
    return body


def verify_freeze() -> dict[str, Any]:
    if not FREEZE_PATH.is_file():
        return {"pass": False, "checks": {"freeze_exists": False}, "mismatches": []}
    frozen = read_json(FREEZE_PATH)
    cfg = config()
    body = {key: value for key, value in frozen.items() if key != "freeze_sha256"}
    current_reasoner = mco03.model_identity(cfg["reasoner"]["model"])
    current_embedding = mco03.model_identity(cfg["retrieval"]["model"])
    mismatches = [
        path
        for path, expected in frozen["source_hashes"].items()
        if not (REPO_ROOT / path).is_file() or file_sha256(REPO_ROOT / path) != expected
    ]
    checks = {
        "freeze_digest": digest(body) == frozen["freeze_sha256"],
        "benchmark_commit": frozen["benchmark_head"] == cfg["benchmark"]["commit"],
        "source_hashes": not mismatches,
        "reasoner_identity": current_reasoner.get("blob_sha256")
        == frozen["models"]["reasoner"].get("blob_sha256"),
        "embedding_identity": current_embedding.get("blob_sha256")
        == frozen["models"]["embedding"].get("blob_sha256"),
        "ollama_version": ollama_version() == frozen["ollama_version"],
        "zero_data_at_freeze": all(
            value == 0 for value in frozen["scientific_state_at_freeze"].values()
        ),
    }
    return {"pass": all(checks.values()), "checks": checks, "mismatches": mismatches}


def _opaque_id(source_name: str) -> str:
    seed = str(config()["reasoner"]["seed"])
    return "incident_" + hashlib.sha256(f"{seed}:{source_name}".encode()).hexdigest()[:20]


def _task_metadata(path: Path) -> dict[str, Any]:
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    return dict(value.get("metadata", {}))


def _visible_file_manifest(root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(path.relative_to(root)): {"bytes": path.stat().st_size, "sha256": file_sha256(path)}
        for path in sorted(p for p in root.rglob("*") if p.is_file())
    }


def _clone_source() -> None:
    cfg = config()["benchmark"]
    SOURCE_ROOT.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCE_ROOT.exists():
        _run(["git", "init", str(SOURCE_ROOT)])
        _run(["git", "remote", "add", "origin", cfg["repository"]], cwd=SOURCE_ROOT)
        _run(["git", "fetch", "--depth=1", "origin", cfg["commit"]], cwd=SOURCE_ROOT)
        _run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=SOURCE_ROOT)
    observed = _run(["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT)
    if observed != cfg["commit"]:
        raise RuntimeError(f"staged benchmark commit mismatch: {observed}")


def stage() -> dict[str, Any]:
    freeze = verify_freeze()
    if not freeze["pass"]:
        raise RuntimeError(f"freeze verification failed: {freeze}")
    receipt_path = ARTIFACT_ROOT / "STAGING_RECEIPT.json"
    if receipt_path.is_file():
        return read_json(receipt_path)
    _clone_source()
    dataset = SOURCE_ROOT / "datasets" / "rootcausebench"
    scenarios = sorted(
        path
        for path in dataset.iterdir()
        if path.is_dir()
        and (path / "environment" / "data" / "alert.json").is_file()
        and (path / "tests" / "ground_truth.json").is_file()
    )
    expected = int(config()["benchmark"]["expected_cases"])
    if len(scenarios) != expected:
        raise RuntimeError(f"expected {expected} scenarios, found {len(scenarios)}")
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=False)
    SCORER_ROOT.mkdir(parents=True, exist_ok=False)
    labels: dict[str, Any] = {}
    public_receipts: list[dict[str, Any]] = []
    for number, scenario in enumerate(scenarios, start=1):
        opaque = _opaque_id(scenario.name)
        target = PUBLIC_ROOT / opaque
        target.mkdir()
        shutil.copytree(scenario / "environment" / "data", target / "data")
        instruction = (scenario / "instruction.md").read_text(encoding="utf-8")
        instruction = instruction.replace(scenario.name, "opaque incident")
        (target / "instruction.md").write_text(instruction, encoding="utf-8")
        visible_files = _visible_file_manifest(target)
        incident = {
            "schema_version": 1,
            "opaque_id": opaque,
            "benchmark_commit": config()["benchmark"]["commit"],
            "visible_files": visible_files,
            "visible_bytes": sum(row["bytes"] for row in visible_files.values()),
        }
        write_json(target / "incident.json", incident)
        ground_truth = read_json(scenario / "tests" / "ground_truth.json")
        metadata = _task_metadata(scenario / "task.toml")
        labels[opaque] = {
            "source_name": scenario.name,
            "ground_truth": ground_truth,
            "difficulty": str(metadata.get("difficulty", "unknown")),
            "tags": list(metadata.get("tags", [])),
        }
        public_receipts.append(
            {
                "opaque_id": opaque,
                "visible_bytes": incident["visible_bytes"],
                "incident_sha256": file_sha256(target / "incident.json"),
            }
        )
        print(f"staged MCO-05 {number}/{expected} {opaque}", flush=True)
    write_json(SCORER_ROOT / "labels.json", labels)
    source_identity = {
        "commit": _run(["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT),
        "license_sha256": file_sha256(SOURCE_ROOT / "LICENSE"),
    }
    write_json(SCORER_ROOT / "source_identity.json", source_identity)
    receipt = {
        "experiment_id": config()["experiment_id"],
        "count": len(public_receipts),
        "public_receipts": public_receipts,
        "public_manifest_sha256": digest(public_receipts),
        "source_identity": source_identity,
    }
    write_json(receipt_path, receipt)
    opacity = verify_opacity()
    if not opacity["pass"]:
        raise RuntimeError(f"opacity failed: {opacity}")
    return receipt


def verify_opacity() -> dict[str, Any]:
    if not (SCORER_ROOT / "labels.json").is_file():
        return {"pass": False, "failures": ["labels missing"]}
    labels = read_json(SCORER_ROOT / "labels.json")
    failures: list[str] = []
    static_paths = [
        CONFIG_PATH,
        CONTRACT_PATH,
        REPO_ROOT / "scripts" / "run_mco05.py",
        REPO_ROOT / "tests" / "test_mco05.py",
    ]
    static_text = "\n".join(path.read_text(encoding="utf-8") for path in static_paths)
    for opaque, label in labels.items():
        source_name = str(label["source_name"])
        if source_name in static_text:
            failures.append(f"source-name literal in frozen method: {source_name}")
        gt = label["ground_truth"]
        literals = [str(gt.get("root_cause_commit", ""))]
        literals.extend(str(value) for value in gt.get("decoy_deploy_commits", []))
        for literal in literals:
            if literal and literal != "none" and literal in static_text:
                failures.append(f"oracle SHA literal in frozen method: {opaque}")
        public = PUBLIC_ROOT / opaque
        if not public.is_dir():
            failures.append(f"public case missing: {opaque}")
            continue
        metadata_text = (public / "incident.json").read_text(encoding="utf-8")
        if source_name in metadata_text:
            failures.append(f"source name leaked into public metadata: {opaque}")
        if any(part == source_name for path in public.rglob("*") for part in path.parts):
            failures.append(f"source name leaked into public path: {opaque}")
    receipt = {"pass": not failures, "failures": failures, "checked_cases": len(labels)}
    write_json(ARTIFACT_ROOT / "OPACITY_RECEIPT.json", receipt)
    return receipt


def preflight() -> dict[str, Any]:
    freeze = verify_freeze()
    opacity = verify_opacity() if (SCORER_ROOT / "labels.json").is_file() else {"pass": False}
    cases = sorted(path for path in PUBLIC_ROOT.iterdir() if path.is_dir()) if PUBLIC_ROOT.is_dir() else []
    hashes = True
    for case in cases:
        metadata = read_json(case / "incident.json")
        for relative, identity in metadata["visible_files"].items():
            path = case / relative
            if not path.is_file() or file_sha256(path) != identity["sha256"]:
                hashes = False
    checks = {
        "freeze": freeze["pass"],
        "case_count": len(cases) == int(config()["benchmark"]["expected_cases"]),
        "opacity": opacity.get("pass", False),
        "file_hashes": hashes,
    }
    result = {"pass": all(checks.values()), "checks": checks, "freeze": freeze}
    write_json(RUN_ROOT / "PREFLIGHT.json", result)
    return result


def parse_time(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        try:
            return pd.Timestamp(text).timestamp()
        except (TypeError, ValueError):
            return None


def format_time(value: float | None) -> str:
    if value is None:
        return "unknown"
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def truncate_utf8(text: str, limit: int) -> str:
    payload = text.encode("utf-8")
    if len(payload) <= limit:
        return text
    suffix = " …[truncated]"
    keep = max(0, limit - len(suffix.encode("utf-8")))
    return payload[:keep].decode("utf-8", errors="ignore") + suffix


def normalize_signature(text: str) -> str:
    value = HEX_PATTERN.sub("<HEX>", text)
    value = NUMBER_PATTERN.sub("<N>", value)
    return re.sub(r"\s+", " ", value).strip()[:600]


def tokens(text: str) -> set[str]:
    stop = {
        "the", "and", "that", "with", "from", "this", "into", "service", "incident",
        "error", "alert", "commit", "change", "root", "cause", "identify", "data",
    }
    return {word.lower() for word in WORD_PATTERN.findall(text) if word.lower() not in stop}


def _evidence_id(identity: dict[str, Any]) -> str:
    return "ev_" + digest(identity)[:20]


def _record(
    *,
    case_root: Path,
    source_file: str,
    kind: str,
    identity_values: dict[str, Any],
    text: str,
    service: str | None = None,
    anomaly_score: float = 0.0,
    onset: float | None = None,
    commit_sha: str | None = None,
    deployed: bool = False,
    rank_key: Sequence[Any] = (),
) -> dict[str, Any]:
    source_path = case_root / source_file
    identity = {"source_file": source_file, "kind": kind, **identity_values}
    row = {
        "evidence_id": _evidence_id(identity),
        "source_file": source_file,
        "source_sha256": file_sha256(source_path),
        "kind": kind,
        "identity": identity,
        "text": truncate_utf8(text, int(config()["compiler"]["document_text_byte_limit"])),
        "service": service,
        "anomaly_score": float(anomaly_score),
        "onset": onset,
        "commit_sha": commit_sha,
        "deployed": bool(deployed),
        "rank_key": list(rank_key),
    }
    row["aggregate_digest"] = digest({key: value for key, value in row.items() if key != "aggregate_digest"})
    return row


def _safe_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return read_json(path)
    except (json.JSONDecodeError, OSError):
        return default


def _list_value(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("items", "records", "data", "spans", "patterns"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
    return []


def _metric_documents(case_root: Path) -> list[dict[str, Any]]:
    relative = "data/metrics.csv"
    path = case_root / relative
    if not path.is_file():
        return []
    frame = pd.read_csv(path)
    required = {"timestamp", "service", "metric", "value"}
    if not required.issubset(frame.columns):
        return []
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["epoch"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").astype("int64") / 1e9
    rows: list[dict[str, Any]] = []
    for (service, metric), group in frame.groupby(["service", "metric"], dropna=False):
        group = group.dropna(subset=["value", "epoch"]).sort_values("epoch")
        values = group["value"].to_numpy(dtype=float)
        epochs = group["epoch"].to_numpy(dtype=float)
        if len(values) < 6:
            continue
        width = max(3, len(values) // 3)
        before = values[:width]
        after = values[-width:]
        center = float(np.median(before))
        mad = float(np.median(np.abs(before - center))) * 1.4826
        q25, q75 = np.quantile(before, [0.25, 0.75])
        iqr = float(q75 - q25) / 1.349
        diff_scale = float(np.std(np.diff(before))) / math.sqrt(2) if len(before) > 1 else 0.0
        scale = max(mad, iqr, diff_scale, 0.01 * abs(center), 1e-8)
        shifts = {
            "median": float(np.median(after) - np.median(before)),
            "q10": float(np.quantile(after, 0.1) - np.quantile(before, 0.1)),
            "q90": float(np.quantile(after, 0.9) - np.quantile(before, 0.9)),
        }
        score = min(100.0, max(abs(value) for value in shifts.values()) / scale)
        deviations = np.abs(values - center) / scale
        start = max(width, len(values) // 5)
        onset_index = int(start + np.argmax(deviations[start:]))
        for index in range(start, max(start, len(values) - 2)):
            if int(np.sum(deviations[index : index + 3] >= 4.0)) >= 2:
                onset_index = index
                break
        onset = float(epochs[onset_index])
        text = (
            f"METRIC service={service} metric={metric}. Points={len(values)}. "
            f"Early median={np.median(before):.8g}, q10={np.quantile(before, .1):.8g}, "
            f"q90={np.quantile(before, .9):.8g}; late median={np.median(after):.8g}, "
            f"q10={np.quantile(after, .1):.8g}, q90={np.quantile(after, .9):.8g}. "
            f"Robust shift score={score:.5g}; strongest data-derived change at {format_time(onset)}."
        )
        rows.append(
            _record(
                case_root=case_root,
                source_file=relative,
                kind="metric",
                identity_values={"service": str(service), "metric": str(metric)},
                text=text,
                service=str(service),
                anomaly_score=score,
                onset=onset,
                rank_key=(-score, str(service), str(metric)),
            )
        )
    rows.sort(key=lambda row: tuple(row["rank_key"]))
    return rows[: int(config()["compiler"]["metric_document_capacity"])]


def _log_documents(case_root: Path) -> list[dict[str, Any]]:
    relative = "data/logs.ndjson"
    path = case_root / relative
    if not path.is_file():
        return []
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            service = str(row.get("service") or row.get("service_name") or "unknown")
            severity = str(row.get("severity_text") or row.get("level") or "unknown").upper()
            message = str(row.get("msg") or row.get("message") or row.get("body") or "")
            signature = normalize_signature(message)
            key = (service, severity, signature)
            epoch = parse_time(row.get("timestamp") or row.get("time"))
            state = groups.setdefault(
                key, {"count": 0, "first": epoch, "last": epoch, "example": message}
            )
            state["count"] += 1
            if epoch is not None:
                state["first"] = epoch if state["first"] is None else min(state["first"], epoch)
                state["last"] = epoch if state["last"] is None else max(state["last"], epoch)
    rows: list[dict[str, Any]] = []
    weights = {"FATAL": 8.0, "PANIC": 8.0, "ERROR": 6.0, "WARN": 3.0, "WARNING": 3.0}
    for (service, severity, signature), state in groups.items():
        score = weights.get(severity, 0.5) * math.log1p(int(state["count"]))
        text = (
            f"LOG-SIGNATURE service={service} severity={severity} count={state['count']} "
            f"first={format_time(state['first'])} last={format_time(state['last'])}. "
            f"Signature: {signature}. Example: {str(state['example'])[:900]}"
        )
        rows.append(
            _record(
                case_root=case_root,
                source_file=relative,
                kind="log",
                identity_values={"service": service, "severity": severity, "signature": signature},
                text=text,
                service=service,
                anomaly_score=score,
                onset=state["first"],
                rank_key=(-score, service, signature),
            )
        )
    rows.sort(key=lambda row: tuple(row["rank_key"]))
    return rows[: int(config()["compiler"]["log_signature_capacity"])]


def _trace_documents(case_root: Path) -> list[dict[str, Any]]:
    relative = "data/traces.json"
    path = case_root / relative
    values = _list_value(_safe_json(path, []))
    if not values:
        return []
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in values:
        service = str(row.get("service") or row.get("service_name") or "unknown")
        name = str(row.get("name") or row.get("operation") or row.get("span_name") or "unknown")
        state = groups.setdefault(
            (service, name), {"count": 0, "errors": 0, "durations": [], "first": None}
        )
        state["count"] += 1
        status = str(row.get("status") or row.get("status_code") or "").upper()
        if status not in {"", "OK", "UNSET", "0"}:
            state["errors"] += 1
        duration = row.get("duration_ms", row.get("duration"))
        try:
            state["durations"].append(float(duration))
        except (TypeError, ValueError):
            pass
        epoch = parse_time(row.get("start") or row.get("timestamp") or row.get("start_time"))
        if epoch is not None:
            state["first"] = epoch if state["first"] is None else min(state["first"], epoch)
    rows: list[dict[str, Any]] = []
    for (service, name), state in groups.items():
        durations = state["durations"]
        q95 = float(np.quantile(durations, 0.95)) if durations else 0.0
        score = 4.0 * math.log1p(state["errors"]) + math.log1p(max(0.0, q95))
        text = (
            f"TRACE-SUMMARY service={service} operation={name} spans={state['count']} "
            f"errors={state['errors']} duration_q95_ms={q95:.7g} first={format_time(state['first'])}."
        )
        rows.append(
            _record(
                case_root=case_root,
                source_file=relative,
                kind="trace",
                identity_values={"service": service, "operation": name},
                text=text,
                service=service,
                anomaly_score=score,
                onset=state["first"],
                rank_key=(-score, service, name),
            )
        )
    rows.sort(key=lambda row: tuple(row["rank_key"]))
    return rows[: int(config()["compiler"]["trace_document_capacity"])]


def _pattern_documents(case_root: Path) -> list[dict[str, Any]]:
    relative = "data/patterns.json"
    path = case_root / relative
    rows: list[dict[str, Any]] = []
    for number, value in enumerate(_list_value(_safe_json(path, []))):
        service = str(value.get("service") or value.get("service_name") or "unknown")
        count = int(value.get("count") or 0)
        delta = str(value.get("delta_vs_baseline") or value.get("delta") or "unknown")
        signature = str(value.get("signature") or value.get("pattern") or value.get("message") or "")
        score = 5.0 * math.log1p(max(0, count))
        text = (
            f"PATTERN service={service} count={count} delta={delta} "
            f"sentiment={value.get('sentiment', 'unknown')}. Signature: {signature}"
        )
        rows.append(
            _record(
                case_root=case_root,
                source_file=relative,
                kind="pattern",
                identity_values={"number": number, "service": service, "signature": signature},
                text=text,
                service=service,
                anomaly_score=score,
                rank_key=(-score, service, signature),
            )
        )
    rows.sort(key=lambda row: tuple(row["rank_key"]))
    return rows


def _context_documents(case_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    commits_relative = "data/context/commits.json"
    deploys_relative = "data/context/deploys.json"
    flags_relative = "data/context/flags.json"
    commits = _list_value(_safe_json(case_root / commits_relative, []))
    deploys = _list_value(_safe_json(case_root / deploys_relative, []))
    flags = _list_value(_safe_json(case_root / flags_relative, []))
    deploys_by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in deploys:
        sha = str(row.get("commit_sha") or row.get("sha") or "").lower()
        if sha:
            deploys_by_sha[sha].append(row)
    rows: list[dict[str, Any]] = []
    commit_rows: list[dict[str, Any]] = []
    for number, value in enumerate(commits):
        sha = str(value.get("sha") or value.get("commit_sha") or "").lower()
        if not sha:
            continue
        linked = sorted(
            deploys_by_sha.get(sha, []),
            key=lambda row: str(row.get("timestamp") or ""),
        )
        services = sorted(
            {str(row.get("service") or "unknown") for row in linked}
        )
        times = [str(row.get("timestamp") or "unknown") for row in linked]
        files = value.get("files_changed") or value.get("files") or []
        if not isinstance(files, list):
            files = [str(files)]
        diff = str(value.get("diff") or value.get("patch") or "")
        body = (
            f"COMMIT sha={sha} authored={value.get('timestamp', 'unknown')} "
            f"author={value.get('author', 'unknown')} message={value.get('message', '')}. "
            f"Files: {', '.join(str(item) for item in files)}. "
            f"Deployments: {', '.join(f'{service}@{timestamp}' for service, timestamp in zip(services, times)) or 'none'}. "
            f"Diff:\n{diff}"
        )
        row = _record(
            case_root=case_root,
            source_file=commits_relative,
            kind="commit",
            identity_values={"sha": sha, "number": number},
            text=body,
            service=services[0] if len(services) == 1 else None,
            commit_sha=sha,
            deployed=bool(linked),
            rank_key=(0 if linked else 1, min(times) if times else "", sha),
        )
        row["commit"] = {
            "sha": sha,
            "timestamp": str(value.get("timestamp") or ""),
            "message": str(value.get("message") or ""),
            "files_changed": [str(item) for item in files],
            "diff": diff,
            "deployments": linked,
        }
        row["aggregate_digest"] = digest(
            {key: item for key, item in row.items() if key != "aggregate_digest"}
        )
        commit_rows.append(row)
    rows.extend(commit_rows)
    for number, value in enumerate(deploys):
        sha = str(value.get("commit_sha") or value.get("sha") or "").lower()
        service = str(value.get("service") or "unknown")
        timestamp = str(value.get("timestamp") or "unknown")
        rows.append(
            _record(
                case_root=case_root,
                source_file=deploys_relative,
                kind="deploy",
                identity_values={"number": number, "sha": sha, "timestamp": timestamp},
                text=(
                    f"DEPLOY service={service} commit={sha or 'unknown'} timestamp={timestamp} "
                    f"version={value.get('version', 'unknown')}."
                ),
                service=service,
                onset=parse_time(timestamp),
                commit_sha=sha or None,
                deployed=True,
                rank_key=(timestamp, service, sha),
            )
        )
    for number, value in enumerate(flags):
        service = str(value.get("service") or "unknown")
        timestamp = str(value.get("timestamp") or "unknown")
        text = " ".join(f"{key}={item}" for key, item in sorted(value.items()))
        rows.append(
            _record(
                case_root=case_root,
                source_file=flags_relative,
                kind="flag",
                identity_values={"number": number, "timestamp": timestamp},
                text=f"FEATURE-FLAG {text}",
                service=service,
                onset=parse_time(timestamp),
                rank_key=(timestamp, service, number),
            )
        )
    return rows, {
        "commit_count": len(commit_rows),
        "deployed_commit_count": sum(bool(row["deployed"]) for row in commit_rows),
        "deploy_count": len(deploys),
        "flag_count": len(flags),
    }


def _alert_and_instruction(case_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    alert_relative = "data/alert.json"
    instruction_relative = "instruction.md"
    alert = _safe_json(case_root / alert_relative, {})
    if not isinstance(alert, dict):
        alert = {}
    alert_service = str(alert.get("service") or "unknown")
    fired = parse_time(alert.get("fired_at") or alert.get("timestamp"))
    alert_text = " ".join(f"{key}={value}" for key, value in sorted(alert.items()))
    alert_row = _record(
        case_root=case_root,
        source_file=alert_relative,
        kind="alert",
        identity_values={"alert": alert},
        text=f"ALERT {alert_text}",
        service=alert_service,
        anomaly_score=1000.0,
        onset=fired,
        rank_key=(0,),
    )
    instruction = (case_root / instruction_relative).read_text(encoding="utf-8", errors="replace")
    instruction_row = _record(
        case_root=case_root,
        source_file=instruction_relative,
        kind="instruction",
        identity_values={"sha256": file_sha256(case_root / instruction_relative)},
        text="TASK-INSTRUCTION " + instruction,
        anomaly_score=999.0,
        rank_key=(1,),
    )
    return [alert_row, instruction_row], {
        "alert": alert,
        "alert_service": alert_service,
        "fired_at": fired,
        "instruction": instruction,
    }


def _priority(row: dict[str, Any]) -> tuple[Any, ...]:
    order = {
        "alert": 0,
        "instruction": 1,
        "pattern": 2,
        "metric": 3,
        "log": 4,
        "trace": 5,
        "commit": 6,
        "deploy": 7,
        "flag": 8,
    }
    commit_order = 0 if row["kind"] == "commit" and row.get("deployed") else 1
    return (
        order.get(str(row["kind"]), 99),
        commit_order,
        -float(row.get("anomaly_score") or 0.0),
        str(row["evidence_id"]),
    )


def _limit_documents(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    maximum = int(config()["compiler"]["max_documents"])
    deployed = [row for row in rows if row["kind"] == "commit" and row.get("deployed")]
    mandatory = [row for row in rows if row["kind"] in {"alert", "instruction"}]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(mandatory + deployed, key=_priority):
        if row["evidence_id"] not in seen:
            selected.append(row)
            seen.add(row["evidence_id"])
    for row in sorted(rows, key=_priority):
        if len(selected) >= maximum:
            break
        if row["evidence_id"] not in seen:
            selected.append(row)
            seen.add(row["evidence_id"])
    return sorted(selected, key=_priority)


def _candidate_score(
    row: dict[str, Any],
    *,
    alert_service: str,
    symptom_terms: set[str],
    anomaly_services: set[str],
    estimated_onset: float | None,
    fired_at: float | None,
) -> tuple[float, dict[str, float]]:
    commit = row.get("commit", {})
    deployments = commit.get("deployments", []) if isinstance(commit, dict) else []
    services = {str(value.get("service") or "unknown") for value in deployments}
    service_score = (3.0 if alert_service in services else 0.0) + 2.0 * len(
        services & anomaly_services
    )
    text = " ".join(
        [
            str(commit.get("message") or ""),
            " ".join(commit.get("files_changed") or []),
            str(commit.get("diff") or ""),
        ]
    )
    overlap = len(tokens(text) & symptom_terms)
    lexical_score = min(4.0, 0.5 * overlap)
    temporal_score = 0.0
    reference = estimated_onset if estimated_onset is not None else fired_at
    deploy_epochs = [
        parse_time(value.get("timestamp")) for value in deployments if isinstance(value, dict)
    ]
    deploy_epochs = [value for value in deploy_epochs if value is not None]
    if reference is not None and deploy_epochs:
        before = [value for value in deploy_epochs if value <= reference]
        if before:
            hours = max(0.0, (reference - max(before)) / 3600.0)
            temporal_score = 3.0 / (1.0 + hours / 12.0)
        else:
            temporal_score = -2.0
    components = {
        "service": service_score,
        "lexical": lexical_score,
        "temporal": temporal_score,
        "deployed": 1.0 if deployments else 0.0,
    }
    return sum(components.values()), components


def _packet_record(row: dict[str, Any], *, score: float | None = None) -> dict[str, Any]:
    copy = {key: value for key, value in row.items() if key not in {"rank_key", "aggregate_digest"}}
    if row["kind"] == "commit":
        commit = row.get("commit", {})
        prefix = f"CANDIDATE selection_score={score:.6g}. " if score is not None else "CANDIDATE. "
        compact = (
            f"{prefix}sha={commit.get('sha', row.get('commit_sha'))}; "
            f"message={commit.get('message', '')}; files={', '.join(commit.get('files_changed', []))}; "
            f"deployments={canonical(commit.get('deployments', []))}; "
            f"diff={commit.get('diff', '')}"
        )
        copy["text"] = truncate_utf8(compact, 1450)
        copy["selection_score"] = float(score or 0.0)
    else:
        copy["text"] = truncate_utf8(str(copy["text"]), 1350)
    copy["aggregate_digest"] = digest(
        {key: value for key, value in copy.items() if key != "aggregate_digest"}
    )
    return copy


def _build_packet(
    documents: Sequence[dict[str, Any]], metadata: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None]:
    anomaly = [
        row
        for row in documents
        if row["kind"] in {"metric", "log", "trace", "pattern"}
    ]
    anomaly.sort(
        key=lambda row: (-float(row.get("anomaly_score") or 0.0), str(row["evidence_id"]))
    )
    telemetry_capacity = int(config()["compiler"]["packet_telemetry_capacity"])
    top_telemetry = anomaly[:telemetry_capacity]
    onsets = [row.get("onset") for row in top_telemetry if row.get("onset") is not None]
    estimated_onset = min(onsets) if onsets else metadata.get("fired_at")
    symptom_text = " ".join(
        [metadata.get("instruction", ""), canonical(metadata.get("alert", {}))]
        + [str(row["text"]) for row in top_telemetry]
    )
    symptom_terms = tokens(symptom_text)
    anomaly_services = {
        str(row["service"]) for row in anomaly[:20] if row.get("service")
    }
    candidates: list[tuple[float, dict[str, float], dict[str, Any]]] = []
    for row in documents:
        if row["kind"] != "commit" or not row.get("deployed"):
            continue
        score, components = _candidate_score(
            row,
            alert_service=str(metadata.get("alert_service") or "unknown"),
            symptom_terms=symptom_terms,
            anomaly_services=anomaly_services,
            estimated_onset=estimated_onset,
            fired_at=metadata.get("fired_at"),
        )
        candidates.append((score, components, row))
    candidates.sort(key=lambda item: (-item[0], str(item[2].get("commit_sha"))))
    selected_candidates = candidates[: int(config()["compiler"]["candidate_capacity"])]
    alert = next((row for row in documents if row["kind"] == "alert"), None)
    packet: list[dict[str, Any]] = []
    if alert is not None:
        packet.append(_packet_record(alert))
    packet.extend(_packet_record(row) for row in top_telemetry)
    packet.extend(_packet_record(row, score=score) for score, _components, row in selected_candidates)
    packet = packet[: int(config()["compiler"]["packet_capacity"])]
    byte_limit = int(config()["compiler"]["packet_prompt_byte_limit"])
    while sum(len(str(row["text"]).encode("utf-8")) for row in packet) > byte_limit:
        largest = max(packet, key=lambda row: len(str(row["text"]).encode("utf-8")))
        current = len(str(largest["text"]).encode("utf-8"))
        if current <= 500:
            break
        largest["text"] = truncate_utf8(str(largest["text"]), current - 250)
        largest["aggregate_digest"] = digest(
            {key: value for key, value in largest.items() if key != "aggregate_digest"}
        )
    ranking = [
        {
            "commit_sha": str(row.get("commit_sha")),
            "score": float(score),
            "components": components,
            "evidence_id": str(row["evidence_id"]),
        }
        for score, components, row in candidates
    ]
    return packet, ranking, estimated_onset


def _official_controls(metadata: dict[str, Any], context_rows: Sequence[dict[str, Any]]) -> dict[str, str]:
    alert = metadata["alert"]
    commits = [row["commit"] for row in context_rows if row["kind"] == "commit"]
    deploys = [
        {
            "timestamp": row["identity"].get("timestamp"),
            "service": row.get("service"),
            "commit_sha": row.get("commit_sha"),
        }
        for row in context_rows
        if row["kind"] == "deploy"
    ]
    fired = str(alert.get("fired_at") or alert.get("timestamp") or "")
    by_sha = {str(row.get("sha")): row for row in commits}
    pre = [row for row in deploys if str(row.get("timestamp") or "") <= fired]
    latest_commit = max(commits, key=lambda row: str(row.get("timestamp") or ""))["sha"] if commits else "none"
    latest_deploy = max(pre, key=lambda row: str(row.get("timestamp") or ""))["commit_sha"] if pre else "none"
    earliest_deploy = min(pre, key=lambda row: str(row.get("timestamp") or ""))["commit_sha"] if pre else "none"
    alert_pre = [row for row in pre if row.get("service") == alert.get("service")]
    alert_service_deploy = (
        max(alert_pre, key=lambda row: str(row.get("timestamp") or ""))["commit_sha"]
        if alert_pre
        else "none"
    )
    keyword_values = [str(alert.get("service") or ""), str(alert.get("metric") or "")]
    keyword_values.extend(
        word
        for word in str(alert.get("summary") or "").split()
        if len(word.strip(".,:;'\"()")) > 6
    )
    keywords = {word.lower().strip(".,:;'\"()") for word in keyword_values if word}
    best_sha, best_score, best_ts = "none", 0, ""
    for deploy in pre:
        commit = by_sha.get(str(deploy.get("commit_sha")))
        if not commit:
            continue
        hay = (
            str(commit.get("diff") or "")
            + " "
            + " ".join(commit.get("files_changed") or [])
        ).lower()
        score = 2 * (deploy.get("service") == alert.get("service"))
        score += sum(1 for word in keywords if word and word in hay)
        timestamp = str(deploy.get("timestamp") or "")
        if score > best_score or (score == best_score > 0 and timestamp > best_ts):
            best_sha, best_score, best_ts = str(deploy.get("commit_sha")), score, timestamp
    return {
        "latest_commit": str(latest_commit),
        "always_none": "none",
        "latest_deploy": str(latest_deploy),
        "earliest_deploy": str(earliest_deploy),
        "alert_service_deploy": str(alert_service_deploy),
        "scripted_rca": str(best_sha),
    }


def compile_case(case_root: Path) -> dict[str, Any]:
    base_rows, metadata = _alert_and_instruction(case_root)
    metric_rows = _metric_documents(case_root)
    log_rows = _log_documents(case_root)
    trace_rows = _trace_documents(case_root)
    pattern_rows = _pattern_documents(case_root)
    context_rows, context_counts = _context_documents(case_root)
    all_rows = base_rows + pattern_rows + metric_rows + log_rows + trace_rows + context_rows
    documents = _limit_documents(all_rows)
    packet, candidate_ranking, estimated_onset = _build_packet(documents, metadata)
    incident = read_json(case_root / "incident.json")
    query = truncate_utf8(
        "\n".join(
            [
                "Identify the exact causal commit, or none when the incident has no code cause.",
                metadata["instruction"],
                "Alert: " + canonical(metadata["alert"]),
            ]
        ),
        5000,
    )
    packet_prompt_limit = int(config()["compiler"]["packet_prompt_byte_limit"])
    while len(_reasoning_prompt(query, packet).encode("utf-8")) > packet_prompt_limit:
        largest = max(packet, key=lambda row: len(str(row["text"]).encode("utf-8")))
        current = len(str(largest["text"]).encode("utf-8"))
        if current <= 350:
            raise RuntimeError("cannot fit state packet below complete prompt byte limit")
        largest["text"] = truncate_utf8(str(largest["text"]), current - 200)
        largest["aggregate_digest"] = digest(
            {key: value for key, value in largest.items() if key != "aggregate_digest"}
        )
    result = {
        "schema_version": 1,
        "opaque_id": incident["opaque_id"],
        "documents": documents,
        "document_count_before_limit": len(all_rows),
        "state_packet": packet,
        "candidate_ranking": candidate_ranking,
        "direct_prediction": candidate_ranking[0]["commit_sha"] if candidate_ranking else "none",
        "official_controls": _official_controls(metadata, context_rows),
        "query": query,
        "services": sorted(
            {str(row["service"]) for row in documents if row.get("service")}
            | {str(metadata["alert_service"]), "unknown"}
        ),
        "estimated_onset": estimated_onset,
        "raw_visible_bytes": int(incident["visible_bytes"]),
        "packet_bytes": sum(len(canonical(row).encode("utf-8")) for row in packet),
        "packet_text_bytes": sum(len(str(row["text"]).encode("utf-8")) for row in packet),
        "context_counts": context_counts,
    }
    result["result_digest"] = digest(
        {key: value for key, value in result.items() if key != "result_digest"}
    )
    return result


def verify_case_provenance(case_root: Path, result: dict[str, Any]) -> dict[str, Any]:
    rerun = compile_case(case_root)
    exact = rerun == result
    source_hashes = all(
        file_sha256(case_root / row["source_file"]) == row["source_sha256"]
        for row in result["documents"] + result["state_packet"]
    )
    aggregates = all(
        digest({key: value for key, value in row.items() if key != "aggregate_digest"})
        == row["aggregate_digest"]
        for row in result["documents"] + result["state_packet"]
    )
    capacity = len(result["state_packet"]) <= int(config()["criteria"]["maximum_packet_records"])
    return {
        "pass": exact and source_hashes and aggregates and capacity,
        "exact_recomputation": exact,
        "source_hashes": source_hashes,
        "aggregate_hashes": aggregates,
        "capacity": capacity,
    }


def _mechanical_root(run_id: str) -> Path:
    return RUN_ROOT / run_id


def run_mechanical(run_id: str) -> dict[str, Any]:
    preflight_path = RUN_ROOT / "PREFLIGHT.json"
    if not preflight_path.is_file() or not read_json(preflight_path).get("pass"):
        raise RuntimeError("passing preflight receipt required before guarded mechanical run")
    freeze = verify_freeze()
    if not freeze["pass"]:
        raise RuntimeError(f"freeze verification failed: {freeze}")
    output = _mechanical_root(run_id)
    output.mkdir(parents=True, exist_ok=True)
    predictions: list[dict[str, Any]] = []
    timings: list[float] = []
    for number, case_root in enumerate(sorted(path for path in PUBLIC_ROOT.iterdir() if path.is_dir()), start=1):
        started = time.perf_counter()
        compiled = compile_case(case_root)
        provenance = verify_case_provenance(case_root, compiled)
        elapsed = time.perf_counter() - started
        if not provenance["pass"]:
            raise RuntimeError(f"provenance failure: {case_root.name}: {provenance}")
        write_json(output / "cases" / f"{case_root.name}.json", compiled)
        predictions.append(
            {
                "opaque_id": case_root.name,
                "direct_prediction": compiled["direct_prediction"],
                "candidate_shas": [row["commit_sha"] for row in compiled["candidate_ranking"][: int(config()["compiler"]["candidate_capacity"])]],
                "official_controls": compiled["official_controls"],
                "packet_evidence_ids": [row["evidence_id"] for row in compiled["state_packet"]],
                "packet_count": len(compiled["state_packet"]),
                "packet_bytes": compiled["packet_bytes"],
                "raw_visible_bytes": compiled["raw_visible_bytes"],
                "result_digest": compiled["result_digest"],
            }
        )
        timings.append(elapsed)
        print(f"mechanical MCO-05 {number}/{config()['benchmark']['expected_cases']} {case_root.name}", flush=True)
    seal = digest(predictions)
    sealed = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "case_count": len(predictions),
        "predictions": predictions,
        "seal_sha256": seal,
    }
    write_json(output / "SEALED_MECHANICAL_PREDICTIONS.json", sealed)
    reductions = [row["raw_visible_bytes"] / max(1, row["packet_bytes"]) for row in predictions]
    summary = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "case_count": len(predictions),
        "seal_sha256": seal,
        "scorer_read_guard_active": SCORER_READ_GUARD_ACTIVE,
        "all_capacity_pass": all(row["packet_count"] <= int(config()["compiler"]["packet_capacity"]) for row in predictions),
        "median_raw_to_packet_byte_reduction": statistics.median(reductions),
        "minimum_raw_to_packet_byte_reduction": min(reductions),
        "compiler_seconds": {
            "sum": sum(timings),
            "median": statistics.median(timings),
        },
    }
    write_json(output / "MECHANICAL_SUMMARY.json", summary)
    return summary


def _exact_commit(prediction: str | None, truth: str) -> bool:
    got = str(prediction or "").strip().lower()
    want = truth.strip().lower()
    return got == want or (want != "none" and len(got) >= 7 and want.startswith(got))


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def _metric(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    n = len(rows)
    successes = sum(bool(row[field]) for row in rows)
    return {"n": n, "correct": successes, "accuracy": successes / n if n else 0.0, "wilson95": _wilson(successes, n)}


def score_mechanical(run_id: str) -> dict[str, Any]:
    output = _mechanical_root(run_id)
    sealed = read_json(output / "SEALED_MECHANICAL_PREDICTIONS.json")
    if digest(sealed["predictions"]) != sealed["seal_sha256"]:
        raise RuntimeError("mechanical prediction seal mismatch")
    labels = read_json(SCORER_ROOT / "labels.json")
    rows: list[dict[str, Any]] = []
    for prediction in sealed["predictions"]:
        opaque = prediction["opaque_id"]
        label = labels[opaque]
        gt = label["ground_truth"]
        truth = str(gt["root_cause_commit"]).lower()
        decoys = {str(value).lower() for value in gt.get("decoy_deploy_commits", [])}
        control_results = {
            name: {
                "prediction": value,
                "correct": _exact_commit(value, truth),
                "hit_decoy": str(value).lower() in decoys,
            }
            for name, value in prediction["official_controls"].items()
        }
        candidate_covered = truth == "none" or any(
            _exact_commit(value, truth) for value in prediction["candidate_shas"]
        )
        rows.append(
            {
                "opaque_id": opaque,
                "difficulty": label["difficulty"],
                "no_code_cause": truth == "none",
                "truth": truth,
                "candidate_covered": candidate_covered,
                "direct_correct": _exact_commit(prediction["direct_prediction"], truth),
                "direct_hit_decoy": str(prediction["direct_prediction"]).lower() in decoys,
                "controls": control_results,
            }
        )
    metrics: dict[str, Any] = {
        "candidate_coverage": _metric(
            [row for row in rows if not row["no_code_cause"]], "candidate_covered"
        ),
        "direct_compiler": _metric(rows, "direct_correct"),
    }
    for name in config()["baselines"]["deterministic"]:
        mapped = [
            {"correct": row["controls"][name]["correct"], "hit_decoy": row["controls"][name]["hit_decoy"]}
            for row in rows
        ]
        metrics[name] = {
            **_metric(mapped, "correct"),
            "decoy_hits": sum(item["hit_decoy"] for item in mapped),
        }
    report = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "seal_sha256": sealed["seal_sha256"],
        "rows": rows,
        "metrics": metrics,
    }
    write_json(output / "SCORED_MECHANICAL.json", report)
    return report


class HybridIndex:
    def __init__(self, documents: Sequence[dict[str, Any]], embeddings: np.ndarray) -> None:
        self.documents = list(documents)
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(self.documents):
            raise ValueError("document/embedding count mismatch")
        text_values = [str(row["text"]) for row in self.documents]
        self.vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True, norm="l2")
        self.sparse = self.vectorizer.fit_transform(text_values)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        self.dense = matrix / np.maximum(norms, 1e-12)

    def retrieve(self, query: str, query_embedding: np.ndarray, capacity: int) -> dict[str, Any]:
        sparse_query = self.vectorizer.transform([query])
        sparse_scores = (self.sparse @ sparse_query.T).toarray().ravel()
        dense_query = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        dense_query = dense_query / max(float(np.linalg.norm(dense_query)), 1e-12)
        dense_scores = self.dense @ dense_query
        sparse_order = sorted(
            range(len(self.documents)),
            key=lambda index: (-float(sparse_scores[index]), str(self.documents[index]["evidence_id"])),
        )
        dense_order = sorted(
            range(len(self.documents)),
            key=lambda index: (-float(dense_scores[index]), str(self.documents[index]["evidence_id"])),
        )
        sparse_rank = np.empty(len(self.documents), dtype=np.int64)
        dense_rank = np.empty(len(self.documents), dtype=np.int64)
        sparse_rank[np.asarray(sparse_order)] = np.arange(len(self.documents))
        dense_rank[np.asarray(dense_order)] = np.arange(len(self.documents))
        rrf = 1.0 / (int(config()["retrieval"]["rrf_k"]) + sparse_rank) + 1.0 / (
            int(config()["retrieval"]["rrf_k"]) + dense_rank
        )
        hybrid_order = sorted(
            range(len(self.documents)),
            key=lambda index: (-float(rrf[index]), int(sparse_rank[index] + dense_rank[index]), str(self.documents[index]["evidence_id"])),
        )
        selected = hybrid_order[:capacity]
        return {
            "documents": [self.documents[index] for index in selected],
            "sparse_top_ids": [self.documents[index]["evidence_id"] for index in sparse_order[:capacity]],
            "dense_top_ids": [self.documents[index]["evidence_id"] for index in dense_order[:capacity]],
            "hybrid_top_ids": [self.documents[index]["evidence_id"] for index in selected],
        }


def _candidate_shas(evidence: Sequence[dict[str, Any]]) -> list[str]:
    values = {
        str(row["commit_sha"]).lower()
        for row in evidence
        if row.get("commit_sha") and row["kind"] in {"commit", "deploy"}
    }
    return sorted(values | {"none"})


def _schema(
    evidence: Sequence[dict[str, Any]], services: Sequence[str]
) -> dict[str, Any]:
    evidence_ids = sorted({str(row["evidence_id"]) for row in evidence})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "root_cause_commit",
            "first_failing_service",
            "blast_radius",
            "remediation",
            "evidence_ids",
            "diagnosis",
        ],
        "properties": {
            "root_cause_commit": {"type": "string", "enum": _candidate_shas(evidence)},
            "first_failing_service": {"type": "string", "enum": sorted(set(services) | {"unknown"})},
            "blast_radius": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(set(services) | {"unknown"})},
                "maxItems": 10,
                "uniqueItems": True,
            },
            "remediation": {"type": "string", "enum": list(REMEDIATIONS)},
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string", "enum": evidence_ids},
                "minItems": 1,
                "maxItems": 6,
                "uniqueItems": True,
            },
            "diagnosis": {"type": "string", "maxLength": 900},
        },
    }


def _reasoning_prompt(query: str, evidence: Sequence[dict[str, Any]]) -> str:
    lines = [
        query,
        "Use only the supplied evidence. Separate the causal code change from downstream victims and innocent near-onset deploys. Read diff semantics, anomaly direction, and timing together. Choose none only when the evidence supports a non-code cause. Cite 1-6 supplied evidence IDs.",
        "EVIDENCE:",
    ]
    lines.extend(f"[{row['evidence_id']}] {row['text']}" for row in evidence)
    return "\n".join(lines)


def _parse_response(record: dict[str, Any]) -> dict[str, Any]:
    content = str(record.get("response", {}).get("message", {}).get("content", ""))
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return {"valid": False, "raw_content": content}
    required = {
        "root_cause_commit",
        "first_failing_service",
        "blast_radius",
        "remediation",
        "evidence_ids",
        "diagnosis",
    }
    if not isinstance(value, dict) or set(value) != required:
        return {"valid": False, "raw_content": content}
    return {"valid": True, **value}


def _reason_once(
    *,
    client: mco03.FrozenModelClient,
    variant: str,
    opaque_id: str,
    query: str,
    services: Sequence[str],
    evidence: Sequence[dict[str, Any]],
    force_live_repeat: bool = False,
) -> dict[str, Any]:
    cfg = config()
    prompt = _reasoning_prompt(query, evidence)
    record = client.call(
        purpose="calls",
        key=opaque_id,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a constrained incident change-attribution component. Return only the requested JSON. Do not assume the latest deploy is causal."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        num_ctx=int(cfg["baselines"]["max_context"]["context_limit_tokens"]),
        num_predict=int(cfg["reasoner"]["max_output_tokens"]),
        format_spec=_schema(evidence, services),
        force_live_repeat=force_live_repeat,
    )
    parsed = _parse_response(record)
    evidence_ids = [str(row["evidence_id"]) for row in evidence]
    parsed.update(
        {
            "variant": variant,
            "provided_evidence_ids": evidence_ids,
            "provided_candidate_shas": _candidate_shas(evidence),
            "prompt_bytes": len(prompt.encode("utf-8")),
            "call_id": f"calls/{record['call_id']}",
            "accounting": record["accounting"],
        }
    )
    parsed["citation_subset_valid"] = bool(parsed.get("valid")) and set(
        parsed.get("evidence_ids", [])
    ).issubset(evidence_ids)
    return parsed


def _safe_context(query: str, documents: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    limit = int(config()["baselines"]["max_context"]["prompt_byte_limit"])
    selected: list[dict[str, Any]] = []
    for row in documents:
        candidate = selected + [row]
        if len(_reasoning_prompt(query, candidate).encode("utf-8")) > limit:
            continue
        selected = candidate
    return selected


def _call_orders(opaque_ids: Sequence[str]) -> dict[str, list[str]]:
    seed = str(config()["reasoner"]["seed"])
    ranked = sorted(opaque_ids, key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest())
    rotations = [
        list(REASONING_VARIANTS),
        [REASONING_VARIANTS[1], REASONING_VARIANTS[2], REASONING_VARIANTS[0]],
        [REASONING_VARIANTS[2], REASONING_VARIANTS[0], REASONING_VARIANTS[1]],
    ]
    return {opaque: rotations[index % 3] for index, opaque in enumerate(ranked)}


def _reasoning_root(run_id: str) -> Path:
    return RUN_ROOT / run_id


def _row_digest(row: dict[str, Any]) -> str:
    semantic = {
        "opaque_id": row["opaque_id"],
        "variant_call_order": row["variant_call_order"],
        "variants": row["variants"],
        "retrieval": row["retrieval"],
        "max_context_document_count": row["max_context_document_count"],
    }
    return digest(semantic)


def run_reasoning(mechanical_run_id: str, run_id: str, mode: str) -> dict[str, Any]:
    mechanical_root = _mechanical_root(mechanical_run_id)
    sealed_mechanical = read_json(mechanical_root / "SEALED_MECHANICAL_PREDICTIONS.json")
    if digest(sealed_mechanical["predictions"]) != sealed_mechanical["seal_sha256"]:
        raise RuntimeError("mechanical seal mismatch")
    output = _reasoning_root(run_id)
    output.mkdir(parents=True, exist_ok=True)
    opaque_ids = [row["opaque_id"] for row in sealed_mechanical["predictions"]]
    orders = _call_orders(opaque_ids)
    reason_clients = {variant: _model_clients(mode, variant) for variant in REASONING_VARIANTS}
    predictions: list[dict[str, Any]] = []
    embedding_totals = {"model_calls": 0, "input_tokens": 0, "wall_seconds": 0.0}
    usage_totals = {
        variant: {
            "model_calls": 0,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "wall_seconds": 0.0,
            "maximum_prompt_tokens": 0,
            "maximum_output_tokens": 0,
        }
        for variant in REASONING_VARIANTS
    }
    timing_totals = {
        "document_embedding_wall_seconds": 0.0,
        "query_embedding_wall_seconds": 0.0,
        "retrieval_cpu_seconds": 0.0,
        "max_context_selection_seconds": 0.0,
        "online_query_seconds": {variant: 0.0 for variant in REASONING_VARIANTS},
    }
    for number, opaque in enumerate(opaque_ids, start=1):
        compiled = read_json(mechanical_root / "cases" / f"{opaque}.json")
        documents = compiled["documents"]
        query = compiled["query"]
        embed_client = _embedding_client(mode, opaque)
        embedded_docs = embed_client.embed(key=f"{opaque}-documents", inputs=[str(row["text"]) for row in documents])
        embedded_query = embed_client.embed(key=f"{opaque}-query", inputs=[query])
        for result in (embedded_docs, embedded_query):
            embedding_totals["model_calls"] += int(result["usage"]["model_calls"])
            embedding_totals["input_tokens"] += int(result["usage"]["input_tokens"])
            embedding_totals["wall_seconds"] += float(result["usage"]["wall_time_seconds"])
        timing_totals["document_embedding_wall_seconds"] += float(embedded_docs["usage"]["wall_time_seconds"])
        timing_totals["query_embedding_wall_seconds"] += float(embedded_query["usage"]["wall_time_seconds"])
        retrieval_started = time.perf_counter()
        retrieval = HybridIndex(documents, embedded_docs["matrix"]).retrieve(
            query,
            embedded_query["matrix"][0],
            int(config()["baselines"]["hybrid_rag"]["capacity"]),
        )
        retrieval_cpu = time.perf_counter() - retrieval_started
        timing_totals["retrieval_cpu_seconds"] += retrieval_cpu
        context_started = time.perf_counter()
        max_context = _safe_context(query, documents)
        context_cpu = time.perf_counter() - context_started
        timing_totals["max_context_selection_seconds"] += context_cpu
        evidence_by_variant = {
            "state_packet": compiled["state_packet"],
            "hybrid_rag_16": retrieval["documents"],
            "max_context": max_context,
        }
        variants: dict[str, Any] = {}
        for variant in orders[opaque]:
            result = _reason_once(
                client=reason_clients[variant],
                variant=variant,
                opaque_id=opaque,
                query=query,
                services=compiled["services"],
                evidence=evidence_by_variant[variant],
            )
            variants[variant] = result
            accounting = result["accounting"]
            totals = usage_totals[variant]
            totals["model_calls"] += 1
            totals["prompt_tokens"] += int(accounting["prompt_eval_count"])
            totals["output_tokens"] += int(accounting["eval_count"])
            totals["wall_seconds"] += float(accounting["wall_time_seconds"])
            totals["maximum_prompt_tokens"] = max(totals["maximum_prompt_tokens"], int(accounting["prompt_eval_count"]))
            totals["maximum_output_tokens"] = max(totals["maximum_output_tokens"], int(accounting["eval_count"]))
            online = float(accounting["wall_time_seconds"])
            if variant == "hybrid_rag_16":
                online += float(embedded_query["usage"]["wall_time_seconds"]) + retrieval_cpu
            if variant == "max_context":
                online += context_cpu
            timing_totals["online_query_seconds"][variant] += online
        row = {
            "opaque_id": opaque,
            "variant_call_order": orders[opaque],
            "variants": {variant: variants[variant] for variant in REASONING_VARIANTS},
            "retrieval": {
                "sparse_top_ids": retrieval["sparse_top_ids"],
                "dense_top_ids": retrieval["dense_top_ids"],
                "hybrid_top_ids": retrieval["hybrid_top_ids"],
                "document_matrix_sha256": embedded_docs["matrix_sha256"],
                "query_matrix_sha256": embedded_query["matrix_sha256"],
            },
            "max_context_document_count": len(max_context),
        }
        row["row_digest"] = _row_digest(row)
        write_json(output / "cases" / f"{opaque}.json", row)
        predictions.append(row)
        print(f"reasoning MCO-05 {number}/{len(opaque_ids)} {opaque}", flush=True)
    sealed_rows = [
        {"opaque_id": row["opaque_id"], "row_digest": row["row_digest"], "variants": row["variants"]}
        for row in predictions
    ]
    seal = digest(sealed_rows)
    sealed = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "mechanical_run_id": mechanical_run_id,
        "mode": mode,
        "case_count": len(predictions),
        "predictions": sealed_rows,
        "seal_sha256": seal,
    }
    write_json(output / "SEALED_REASONING_PREDICTIONS.json", sealed)
    first_counts = Counter(row["variant_call_order"][0] for row in predictions)
    summary = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "mechanical_run_id": mechanical_run_id,
        "mode": mode,
        "case_count": len(predictions),
        "seal_sha256": seal,
        "all_outputs_valid": all(value["valid"] for row in predictions for value in row["variants"].values()),
        "all_citation_subsets_valid": all(value["citation_subset_valid"] for row in predictions for value in row["variants"].values()),
        "scorer_read_guard_active": SCORER_READ_GUARD_ACTIVE,
        "usage": usage_totals,
        "embedding_usage": embedding_totals,
        "timing": {**timing_totals, "call_order_first_counts": dict(first_counts)},
    }
    write_json(output / "REASONING_SUMMARY.json", summary)
    return summary


def score_reasoning(run_id: str) -> dict[str, Any]:
    output = _reasoning_root(run_id)
    sealed = read_json(output / "SEALED_REASONING_PREDICTIONS.json")
    if digest(sealed["predictions"]) != sealed["seal_sha256"]:
        raise RuntimeError("reasoning seal mismatch")
    labels = read_json(SCORER_ROOT / "labels.json")
    mechanical_run = sealed["mechanical_run_id"]
    rows: list[dict[str, Any]] = []
    for prediction in sealed["predictions"]:
        opaque = prediction["opaque_id"]
        label = labels[opaque]
        truth = str(label["ground_truth"]["root_cause_commit"]).lower()
        decoys = {str(value).lower() for value in label["ground_truth"].get("decoy_deploy_commits", [])}
        compiled = read_json(_mechanical_root(mechanical_run) / "cases" / f"{opaque}.json")
        candidate_covered = truth == "none" or any(
            _exact_commit(row["commit_sha"], truth)
            for row in compiled["candidate_ranking"][: int(config()["compiler"]["candidate_capacity"])]
        )
        variants: dict[str, Any] = {}
        for variant, value in prediction["variants"].items():
            got = str(value.get("root_cause_commit") or "")
            correct = bool(value.get("valid")) and _exact_commit(got, truth)
            if not value.get("valid"):
                failure = "OUTPUT_FAILURE"
            elif not value.get("citation_subset_valid"):
                failure = "PROVENANCE_FAILURE"
            elif correct:
                failure = "NONE"
            elif truth == "none":
                failure = "ABSTENTION_FAILURE"
            elif variant == "state_packet" and not candidate_covered:
                failure = "SELECTION_FAILURE"
            else:
                failure = "REASONING_FAILURE"
            variants[variant] = {
                "prediction": got,
                "correct": correct,
                "hit_decoy": got.lower() in decoys,
                "valid": bool(value.get("valid")),
                "citation_subset_valid": bool(value.get("citation_subset_valid")),
                "failure_class": failure,
            }
        rows.append(
            {
                "opaque_id": opaque,
                "difficulty": label["difficulty"],
                "no_code_cause": truth == "none",
                "candidate_covered": candidate_covered,
                "variants": variants,
            }
        )
    metrics: dict[str, Any] = {}
    for variant in REASONING_VARIANTS:
        mapped = [
            {
                "correct": row["variants"][variant]["correct"],
                "valid": row["variants"][variant]["valid"],
                "citations": row["variants"][variant]["citation_subset_valid"],
                "hit_decoy": row["variants"][variant]["hit_decoy"],
                "adversarial": row["difficulty"] == "adversarial",
                "no_code": row["no_code_cause"],
            }
            for row in rows
        ]
        adversarial = [row for row in mapped if row["adversarial"]]
        no_code = [row for row in mapped if row["no_code"]]
        metrics[variant] = {
            **_metric(mapped, "correct"),
            "validity": _metric(mapped, "valid")["accuracy"],
            "citation_subset_valid": _metric(mapped, "citations")["accuracy"],
            "decoy_hits": sum(row["hit_decoy"] for row in mapped),
            "adversarial_accuracy": _metric(adversarial, "correct")["accuracy"],
            "no_code_accuracy": _metric(no_code, "correct")["accuracy"],
            "failure_classes": dict(Counter(row["variants"][variant]["failure_class"] for row in rows)),
        }
    report = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "seal_sha256": sealed["seal_sha256"],
        "rows": rows,
        "metrics": metrics,
    }
    write_json(output / "SCORED_REASONING.json", report)
    return report


def _repeat_ids(opaque_ids: Sequence[str]) -> list[str]:
    cfg = config()
    count = math.ceil(len(opaque_ids) * float(cfg["reasoner"]["repeat_fraction"]))
    seed = str(cfg["reasoner"]["seed"])
    return sorted(
        opaque_ids,
        key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest(),
    )[:count]


def run_stability(mechanical_run_id: str, live_reasoning_run_id: str, run_id: str) -> dict[str, Any]:
    live_root = _reasoning_root(live_reasoning_run_id)
    sealed_live = read_json(live_root / "SEALED_REASONING_PREDICTIONS.json")
    live_by_id = {row["opaque_id"]: row for row in sealed_live["predictions"]}
    selected = _repeat_ids(list(live_by_id))
    clients = {variant: _model_clients("live", variant, stability=True) for variant in REASONING_VARIANTS}
    output = RUN_ROOT / run_id
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    comparisons = 0
    semantic_matches = 0
    exact_matches = 0
    started = time.perf_counter()
    for number, opaque in enumerate(selected, start=1):
        compiled = read_json(_mechanical_root(mechanical_run_id) / "cases" / f"{opaque}.json")
        live_case = read_json(live_root / "cases" / f"{opaque}.json")
        doc_map = {row["evidence_id"]: row for row in compiled["documents"]}
        packet_map = {row["evidence_id"]: row for row in compiled["state_packet"]}
        repeated: dict[str, Any] = {}
        comparison: dict[str, Any] = {}
        for variant in _call_orders([opaque])[opaque]:
            original = live_by_id[opaque]["variants"][variant]
            ids = original["provided_evidence_ids"]
            source = packet_map if variant == "state_packet" else doc_map
            evidence = [source[value] for value in ids]
            repeat = _reason_once(
                client=clients[variant],
                variant=variant,
                opaque_id=opaque,
                query=compiled["query"],
                services=compiled["services"],
                evidence=evidence,
                force_live_repeat=True,
            )
            repeated[variant] = repeat
            semantic_fields = ("valid", "root_cause_commit", "first_failing_service", "remediation")
            semantic = all(original.get(field) == repeat.get(field) for field in semantic_fields)
            exact = {
                key: value for key, value in original.items() if key not in {"accounting", "call_id"}
            } == {key: value for key, value in repeat.items() if key not in {"accounting", "call_id"}}
            comparison[variant] = {"semantic_match": semantic, "exact_structured_match": exact}
            comparisons += 1
            semantic_matches += int(semantic)
            exact_matches += int(exact)
        row = {
            "opaque_id": opaque,
            "variants": repeated,
            "comparisons": comparison,
            "live_row_digest": live_case["row_digest"],
        }
        row["row_digest"] = digest({key: value for key, value in row.items() if key != "row_digest"})
        write_json(output / "cases" / f"{opaque}.json", row)
        rows.append(row)
        print(f"stability MCO-05 {number}/{len(selected)} {opaque}", flush=True)
    seal_rows = [{"opaque_id": row["opaque_id"], "row_digest": row["row_digest"]} for row in rows]
    seal = digest(seal_rows)
    write_json(
        output / "SEALED_STABILITY.json",
        {"experiment_id": config()["experiment_id"], "run_id": run_id, "rows": seal_rows, "seal_sha256": seal},
    )
    summary = {
        "experiment_id": config()["experiment_id"],
        "run_id": run_id,
        "population_case_count": len(live_by_id),
        "selected_case_count": len(selected),
        "selected_ids": selected,
        "comparison_count": comparisons,
        "semantic_matches": semantic_matches,
        "semantic_agreement": semantic_matches / comparisons if comparisons else 0.0,
        "exact_structured_matches": exact_matches,
        "exact_structured_agreement": exact_matches / comparisons if comparisons else 0.0,
        "all_repeat_outputs_valid": all(value["valid"] for row in rows for value in row["variants"].values()),
        "all_repeat_citations_valid": all(value["citation_subset_valid"] for row in rows for value in row["variants"].values()),
        "scorer_read_guard_active": SCORER_READ_GUARD_ACTIVE,
        "seal_sha256": seal,
        "wall_seconds": time.perf_counter() - started,
    }
    write_json(output / "STABILITY_SUMMARY.json", summary)
    return summary


def verify_reasoning_receipts(run_id: str, *, stability: bool = False) -> dict[str, Any]:
    root = RUN_ROOT / run_id
    if stability:
        cases = [read_json(path) for path in sorted((root / "cases").glob("*.json"))]
        variants = [value for row in cases for value in row["variants"].values()]
    else:
        sealed = read_json(root / "SEALED_REASONING_PREDICTIONS.json")
        variants = [value for row in sealed["predictions"] for value in row["variants"].values()]
    failures: list[str] = []
    checked = 0
    for value in variants:
        variant = value["variant"]
        client = _model_clients("replay", variant, stability=stability)
        try:
            record = client.resolve(value["call_id"])
        except (FileNotFoundError, ValueError) as exc:
            failures.append(str(exc))
            continue
        request_ok = digest(record["request"]) == record["request_sha256"]
        content = str(record.get("response", {}).get("message", {}).get("content", ""))
        response_ok = hashlib.sha256(content.encode("utf-8")).hexdigest() == record["response_content_sha256"]
        if not request_ok or not response_ok:
            failures.append(f"receipt hash mismatch: {variant}/{record['call_id']}")
        checked += 1
    return {"pass": not failures, "checked_calls": checked, "failures": failures, "run_id": run_id}


def verify_mechanical_recomputation(run_id: str) -> dict[str, Any]:
    root = _mechanical_root(run_id)
    failures: list[str] = []
    checked = 0
    for case_root in sorted(path for path in PUBLIC_ROOT.iterdir() if path.is_dir()):
        stored = read_json(root / "cases" / f"{case_root.name}.json")
        result = verify_case_provenance(case_root, stored)
        if not result["pass"]:
            failures.append(f"{case_root.name}: {result}")
        checked += 1
    return {"pass": not failures, "checked_cases": checked, "failures": failures, "run_id": run_id}


def verify_replay() -> dict[str, Any]:
    cfg = config()["execution"]
    mechanical_live = read_json(_mechanical_root(cfg["mechanical_live_run_id"]) / "SEALED_MECHANICAL_PREDICTIONS.json")
    mechanical_replay = read_json(_mechanical_root(cfg["mechanical_replay_run_id"]) / "SEALED_MECHANICAL_PREDICTIONS.json")
    reasoning_live = read_json(_reasoning_root(cfg["reasoning_live_run_id"]) / "SEALED_REASONING_PREDICTIONS.json")
    reasoning_replay = read_json(_reasoning_root(cfg["reasoning_replay_run_id"]) / "SEALED_REASONING_PREDICTIONS.json")
    checks = {
        "mechanical_live_seal": digest(mechanical_live["predictions"]) == mechanical_live["seal_sha256"],
        "mechanical_replay_seal": digest(mechanical_replay["predictions"]) == mechanical_replay["seal_sha256"],
        "mechanical_predictions_identical": mechanical_live["predictions"] == mechanical_replay["predictions"],
        "reasoning_live_seal": digest(reasoning_live["predictions"]) == reasoning_live["seal_sha256"],
        "reasoning_replay_seal": digest(reasoning_replay["predictions"]) == reasoning_replay["seal_sha256"],
        "reasoning_predictions_identical": reasoning_live["predictions"] == reasoning_replay["predictions"],
    }
    result = {"pass": all(checks.values()), "checks": checks}
    write_json(RUN_ROOT / "REPLAY_CHECK.json", result)
    return result


def _verification_bundle() -> dict[str, Any]:
    cfg = config()
    ids = cfg["execution"]
    freeze = verify_freeze()
    pre = read_json(RUN_ROOT / "PREFLIGHT.json")
    opacity = read_json(ARTIFACT_ROOT / "OPACITY_RECEIPT.json")
    mechanical_live = read_json(_mechanical_root(ids["mechanical_live_run_id"]) / "MECHANICAL_SUMMARY.json")
    mechanical_replay = read_json(_mechanical_root(ids["mechanical_replay_run_id"]) / "MECHANICAL_SUMMARY.json")
    reasoning_live = read_json(_reasoning_root(ids["reasoning_live_run_id"]) / "REASONING_SUMMARY.json")
    reasoning_replay = read_json(_reasoning_root(ids["reasoning_replay_run_id"]) / "REASONING_SUMMARY.json")
    stability = read_json(RUN_ROOT / ids["stability_run_id"] / "STABILITY_SUMMARY.json")
    replay = read_json(RUN_ROOT / "REPLAY_CHECK.json")
    live_receipts = verify_reasoning_receipts(ids["reasoning_live_run_id"])
    replay_receipts = verify_reasoning_receipts(ids["reasoning_replay_run_id"])
    stability_receipts = verify_reasoning_receipts(ids["stability_run_id"], stability=True)
    mech_live_recompute = verify_mechanical_recomputation(ids["mechanical_live_run_id"])
    mech_replay_recompute = verify_mechanical_recomputation(ids["mechanical_replay_run_id"])
    all_usage = reasoning_live["usage"]
    first_counts = reasoning_live["timing"]["call_order_first_counts"]
    checks = {
        "freeze": freeze["pass"],
        "preflight": pre["pass"],
        "opacity": opacity["pass"],
        "case_count": reasoning_live["case_count"] == int(cfg["benchmark"]["expected_cases"]),
        "mechanical_capacity": mechanical_live["all_capacity_pass"],
        "mechanical_scorer_guard": mechanical_live["scorer_read_guard_active"],
        "mechanical_replay_scorer_guard": mechanical_replay["scorer_read_guard_active"],
        "reasoning_outputs": reasoning_live["all_outputs_valid"],
        "reasoning_citations": reasoning_live["all_citation_subsets_valid"],
        "reasoning_scorer_guard": reasoning_live["scorer_read_guard_active"],
        "reasoning_replay_scorer_guard": reasoning_replay["scorer_read_guard_active"],
        "call_order_balanced": max(first_counts.values()) - min(first_counts.values()) <= 1,
        "all_variants_below_context_limit": all(
            int(usage["maximum_prompt_tokens"]) + int(usage["maximum_output_tokens"])
            < int(cfg["baselines"]["max_context"]["context_limit_tokens"])
            for usage in all_usage.values()
        ),
        "stability_selection": stability["selected_ids"]
        == _repeat_ids(sorted(path.name for path in PUBLIC_ROOT.iterdir() if path.is_dir())),
        "stability_semantic": float(stability["semantic_agreement"])
        >= float(cfg["criteria"]["minimum_semantic_stability"]),
        "stability_outputs": stability["all_repeat_outputs_valid"],
        "stability_citations": stability["all_repeat_citations_valid"],
        "stability_scorer_guard": stability["scorer_read_guard_active"],
        "replay": replay["pass"],
        "live_receipts": live_receipts["pass"],
        "replay_receipts": replay_receipts["pass"],
        "stability_receipts": stability_receipts["pass"],
        "mechanical_live_recomputation": mech_live_recompute["pass"],
        "mechanical_replay_recomputation": mech_replay_recompute["pass"],
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "freeze": freeze,
        "live_receipts": live_receipts,
        "replay_receipts": replay_receipts,
        "stability_receipts": stability_receipts,
        "mechanical_live_recomputation": mech_live_recompute,
        "mechanical_replay_recomputation": mech_replay_recompute,
    }


def _outcome(
    verification: dict[str, Any], mechanical: dict[str, Any], reasoning: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    cfg = config()["criteria"]
    candidate = mechanical["metrics"]["candidate_coverage"]
    packet = reasoning["metrics"]["state_packet"]
    controls = {name: reasoning["metrics"][name] for name in ("hybrid_rag_16", "max_context")}
    best_control_name, best_control = max(controls.items(), key=lambda item: float(item[1]["accuracy"]))
    advantage = float(packet["accuracy"]) - float(best_control["accuracy"])
    compiler_transfer = bool(
        float(candidate["accuracy"]) >= float(cfg["minimum_candidate_recall"])
    )
    packet_quality = bool(
        float(packet["accuracy"]) >= float(cfg["minimum_packet_accuracy"])
        and float(packet["wilson95"][0]) >= float(cfg["minimum_wilson95_lower"])
        and float(packet["adversarial_accuracy"]) >= float(cfg["minimum_adversarial_accuracy"])
        and float(packet["no_code_accuracy"]) >= float(cfg["minimum_no_code_accuracy"])
        and float(packet["validity"]) >= float(cfg["minimum_reasoning_validity"])
        and float(packet["citation_subset_valid"]) >= float(cfg["minimum_provenance"])
    )
    conventional_dominates = bool(
        float(best_control["accuracy"])
        >= float(packet["accuracy"]) - float(cfg["quality_equivalence_margin"])
        or advantage < float(cfg["minimum_packet_advantage"])
    )
    advance = bool(verification["pass"] and compiler_transfer and packet_quality and not conventional_dominates)
    gates = {
        "integrity_pass": verification["pass"],
        "compiler_transfer": compiler_transfer,
        "packet_quality": packet_quality,
        "conventional_dominates": conventional_dominates,
        "bounded_inference_advance": advance,
        "candidate_recall": float(candidate["accuracy"]),
        "candidate_recall_count": int(candidate["correct"]),
        "candidate_recall_n": int(candidate["n"]),
        "packet_accuracy": float(packet["accuracy"]),
        "packet_wilson95": packet["wilson95"],
        "packet_adversarial_accuracy": float(packet["adversarial_accuracy"]),
        "packet_no_code_accuracy": float(packet["no_code_accuracy"]),
        "best_reasoning_control": best_control_name,
        "best_reasoning_control_accuracy": float(best_control["accuracy"]),
        "packet_quality_advantage": advantage,
    }
    if not verification["pass"]:
        outcome = "MCO_05_BENCHMARK_INVALID"
    elif not compiler_transfer:
        outcome = "MCO_05_DISJOINT_COMPILER_TRANSFER_FAILURE"
    elif not packet_quality:
        outcome = "MCO_05_DISJOINT_REASONING_FAILURE"
    elif conventional_dominates:
        outcome = "MCO_05_CONVENTIONAL_RETRIEVAL_DOMINATES"
    else:
        outcome = "MCO_05_DISJOINT_BOUNDED_INFERENCE_ADVANCE"
    return outcome, gates


def render_report(verdict: dict[str, Any]) -> str:
    gates = verdict["gates"]
    checks = verdict["verification"]["checks"]
    outcome = verdict["verdict"]
    claim_pass = outcome == "MCO_05_DISJOINT_BOUNDED_INFERENCE_ADVANCE"
    mechanical = verdict["mechanical_metrics"]
    reasoning = verdict["reasoning_metrics"]
    lines = [
        "# MCO-05 — DISJOINT CHANGE-ATTRIBUTION GATE",
        "",
        "## Claim under test",
        "",
        "A frozen transparent state compiler can select at most 16 auditable incident/change records on an unseen benchmark and enable exact causal-commit attribution better than equally informed conventional controls.",
        "",
        "## Check",
        "",
        f"All {verdict['case_count']} RootCauseBench scenarios at pinned commit `{verdict['benchmark_commit']}` were scientific-only. Scenario files were cloned only after method freeze, staged under opaque IDs, model-scored only after prediction seals, repeated on a fresh hash-selected subset, and replayed from content-addressed receipts.",
        "",
        "| Method | Exact commit | Adversarial | No-code |",
        "|---|---:|---:|---:|",
        f"| compiler candidate coverage | {mechanical['candidate_coverage']['accuracy']:.2%} | — | — |",
        f"| direct compiler top-1 | {mechanical['direct_compiler']['accuracy']:.2%} | — | — |",
        f"| model over state packet | {reasoning['state_packet']['accuracy']:.2%} | {reasoning['state_packet']['adversarial_accuracy']:.2%} | {reasoning['state_packet']['no_code_accuracy']:.2%} |",
        f"| hybrid RAG-16 | {reasoning['hybrid_rag_16']['accuracy']:.2%} | {reasoning['hybrid_rag_16']['adversarial_accuracy']:.2%} | {reasoning['hybrid_rag_16']['no_code_accuracy']:.2%} |",
        f"| maximum safe context | {reasoning['max_context']['accuracy']:.2%} | {reasoning['max_context']['adversarial_accuracy']:.2%} | {reasoning['max_context']['no_code_accuracy']:.2%} |",
        "",
        f"## Verdict — {'PASS' if claim_pass else 'FAIL'}",
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
            f"- code-cause candidate recall: {gates['candidate_recall']:.2%} ({gates['candidate_recall_count']}/{gates['candidate_recall_n']})",
            f"- packet exact-commit accuracy: {gates['packet_accuracy']:.2%}",
            f"- packet Wilson 95% interval: {gates['packet_wilson95'][0]:.2%}–{gates['packet_wilson95'][1]:.2%}",
            f"- packet advantage over {gates['best_reasoning_control']}: {gates['packet_quality_advantage']:.2%}",
            f"- fresh semantic stability: {verdict['stability_semantic_agreement']:.2%}",
            "",
            "## Assumption register",
            "",
            "- Verified: pinned source identity, post-freeze staging, static/runtime oracle isolation, exact compiler recomputation, bounded packets, model receipts, scorer binding, fresh repeats, and exact replay.",
            "- Not verified: organic production incidents, live schema drift, access controls, concurrent ingestion, operator usefulness, deployment economics, prospective causality, customer adoption, or independent replication.",
            "- RootCauseBench contains fictional reconstructions and fault injections. It changes task structure but is not a production pilot.",
            "- Public benchmark documentation describes scenario mechanisms. Isolation is executable, not experimenter blinding.",
            "- The local 8B reasoner tests this frozen implementation; a failure does not prove every possible model would fail, but it does falsify the tested product claim.",
            "",
            "## Credit assignment",
            "",
            "Candidate coverage is credited to transparent selection. Exact commit attribution beyond direct rank is credited to the frozen reasoner. Hybrid RAG and safe context receive the same compiled visible documents and model. DMC, learned retention, and MCO-04's service-localization heuristic receive no credit.",
            "",
            "## Verification gap",
            "",
            "This remains self-verified public-benchmark evidence. Even a positive result requires a preregistered independently operated prospective incident pilot. A negative result stops the tested state-compiler product branch unless a genuinely new falsifiable mechanism is proposed.",
            "",
            "## Stop/continue",
            "",
            (
                "Continue only to an independently operated prospective pilot; do not tune on these scientific cases."
                if claim_pass
                else "Stop the tested product-architecture branch. Preserve the failure taxonomy and do not redesign around scientific labels under the same claim."
            ),
            "",
            "## Maturity status",
            "",
            (
                "Disjoint reconstructed-benchmark advance; pre-product and pre-impact."
                if claim_pass
                else "Terminal negative on disjoint change attribution for the frozen implementation; no product or impact claim."
            ),
            "",
            "## Accounting",
            "",
            f"Hybrid ingestion used {verdict['embedding_usage']['model_calls']:,} embedding calls and {verdict['embedding_usage']['input_tokens']:,} embedding input tokens. The live reasoner used {sum(value['model_calls'] for value in verdict['reasoning_usage'].values()):,} calls. Local billed API cost was $0.00, not zero compute cost.",
            "",
            "DMC's 10,880 reconstructed optimizer steps and `TRAINING_COST_UNKNOWN` remain preserved. MCO-05 used zero online optimizer steps; pretrained-model training cost remains unknown and nonzero.",
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
    ids = cfg["execution"]
    verification = _verification_bundle()
    mechanical = read_json(_mechanical_root(ids["mechanical_live_run_id"]) / "SCORED_MECHANICAL.json")
    reasoning = read_json(_reasoning_root(ids["reasoning_live_run_id"]) / "SCORED_REASONING.json")
    reasoning_summary = read_json(_reasoning_root(ids["reasoning_live_run_id"]) / "REASONING_SUMMARY.json")
    stability = read_json(RUN_ROOT / ids["stability_run_id"] / "STABILITY_SUMMARY.json")
    adversarial_count = sum(row["difficulty"] == "adversarial" for row in reasoning["rows"])
    no_code_count = sum(row["no_code_cause"] for row in reasoning["rows"])
    count_checks = {
        "expected_adversarial_count": adversarial_count == int(cfg["benchmark"]["expected_adversarial_cases"]),
        "expected_no_code_count": no_code_count == int(cfg["benchmark"]["expected_no_code_cases"]),
    }
    verification["checks"].update(count_checks)
    verification["pass"] = verification["pass"] and all(count_checks.values())
    outcome, gates = _outcome(verification, mechanical, reasoning)
    result = {
        "experiment_id": cfg["experiment_id"],
        "verdict": outcome,
        "claim_verification": "PASS" if outcome == "MCO_05_DISJOINT_BOUNDED_INFERENCE_ADVANCE" else "FAIL",
        "overall_integrity": "PASS" if verification["pass"] else "FAIL",
        "world_impact_disposition": "NOT_ESTABLISHED",
        "benchmark_commit": cfg["benchmark"]["commit"],
        "case_count": len(reasoning["rows"]),
        "gates": gates,
        "mechanical_metrics": mechanical["metrics"],
        "reasoning_metrics": reasoning["metrics"],
        "reasoning_usage": reasoning_summary["usage"],
        "embedding_usage": reasoning_summary["embedding_usage"],
        "reasoning_timing": reasoning_summary["timing"],
        "stability_semantic_agreement": stability["semantic_agreement"],
        "verification": verification,
        "training_accounting": {
            "dmc_historical_optimizer_steps_preserved": 10880,
            "dmc_historical_training_label": "TRAINING_COST_UNKNOWN",
            "mco05_online_optimizer_steps": 0,
            "pretrained_model_training_cost": "UNKNOWN_NOT_ZERO",
        },
    }
    write_json(VERDICT_PATH, result)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_report(result), encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("freeze")
    commands.add_parser("verify-freeze")
    commands.add_parser("stage")
    commands.add_parser("preflight")
    commands.add_parser("verify-opacity")
    mechanical = commands.add_parser("run-mechanical")
    mechanical.add_argument("--run-id", required=True)
    mechanical_score = commands.add_parser("score-mechanical")
    mechanical_score.add_argument("--run-id", required=True)
    reasoning = commands.add_parser("run-reasoning")
    reasoning.add_argument("--mechanical-run-id", required=True)
    reasoning.add_argument("--run-id", required=True)
    reasoning.add_argument("--mode", choices=("live", "replay"), default="live")
    reasoning_score = commands.add_parser("score-reasoning")
    reasoning_score.add_argument("--run-id", required=True)
    stability = commands.add_parser("run-stability")
    stability.add_argument("--mechanical-run-id", required=True)
    stability.add_argument("--live-reasoning-run-id", required=True)
    stability.add_argument("--run-id", required=True)
    commands.add_parser("verify-replay")
    commands.add_parser("finalize")
    args = parser.parse_args(argv)
    if args.command in {"run-mechanical", "run-reasoning", "run-stability"}:
        install_scorer_read_guard()
    if args.command == "freeze":
        value = create_freeze()
    elif args.command == "verify-freeze":
        value = verify_freeze()
    elif args.command == "stage":
        value = stage()
    elif args.command == "preflight":
        value = preflight()
    elif args.command == "verify-opacity":
        value = verify_opacity()
    elif args.command == "run-mechanical":
        value = run_mechanical(args.run_id)
    elif args.command == "score-mechanical":
        value = score_mechanical(args.run_id)
    elif args.command == "run-reasoning":
        value = run_reasoning(args.mechanical_run_id, args.run_id, args.mode)
    elif args.command == "score-reasoning":
        value = score_reasoning(args.run_id)
    elif args.command == "run-stability":
        value = run_stability(args.mechanical_run_id, args.live_reasoning_run_id, args.run_id)
    elif args.command == "verify-replay":
        value = verify_replay()
    elif args.command == "finalize":
        value = finalize()
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
