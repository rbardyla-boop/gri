from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from scripts import run_mco05 as mco05


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "incident_fixture"
    data = root / "data"
    context = data / "context"
    context.mkdir(parents=True)
    _write_json(
        data / "alert.json",
        {
            "service": "checkoutservice",
            "metric": "db_conn_wait_ms",
            "threshold": 200,
            "observed": 2400,
            "fired_at": "2026-01-01T13:50:00Z",
            "summary": "checkout database waits increased",
        },
    )
    root.joinpath("instruction.md").write_text(
        "Investigate the checkout latency and identify the exact causal commit.",
        encoding="utf-8",
    )
    logs = [
        {
            "timestamp": "2026-01-01T13:42:00Z",
            "service": "checkoutservice",
            "severity_text": "ERROR",
            "msg": "database connection acquisition timed out after 3000ms",
        },
        {
            "timestamp": "2026-01-01T13:43:00Z",
            "service": "checkoutservice",
            "severity_text": "ERROR",
            "msg": "database connection acquisition timed out after 3001ms",
        },
    ]
    data.joinpath("logs.ndjson").write_text(
        "".join(json.dumps(row) + "\n" for row in logs), encoding="utf-8"
    )
    metric_lines = ["timestamp,service,metric,value"]
    for minute in range(18):
        value = 20 if minute < 8 else 700 + 20 * minute
        metric_lines.append(
            f"2026-01-01T13:{minute + 20:02d}:00Z,checkoutservice,db_conn_wait_ms,{value}"
        )
    data.joinpath("metrics.csv").write_text("\n".join(metric_lines) + "\n", encoding="utf-8")
    _write_json(
        data / "traces.json",
        [
            {
                "trace_id": "t1",
                "service": "checkoutservice",
                "name": "PlaceOrder",
                "start": "2026-01-01T13:42:00Z",
                "duration_ms": 2500,
                "status": "ERROR",
            }
        ],
    )
    _write_json(
        data / "patterns.json",
        [
            {
                "signature": "database connection acquisition timed out",
                "service": "checkoutservice",
                "count": 120,
                "delta_vs_baseline": "+120",
                "sentiment": "negative",
            }
        ],
    )
    culprit = "a" * 40
    decoy = "b" * 40
    _write_json(
        context / "commits.json",
        [
            {
                "sha": culprit,
                "author": "dev1",
                "timestamp": "2026-01-01T13:10:00Z",
                "message": "refactor database pool defaults",
                "files_changed": ["services/checkout/dbpool.go"],
                "diff": "- MaxConnections: 50\n+ MaxConnections: 10\n- AcquireTimeout: 30s\n+ AcquireTimeout: 3s",
            },
            {
                "sha": decoy,
                "author": "dev2",
                "timestamp": "2026-01-01T13:39:00Z",
                "message": "restyle checkout banner",
                "files_changed": ["services/frontend/banner.css"],
                "diff": "- color: blue\n+ color: green",
            },
        ],
    )
    _write_json(
        context / "deploys.json",
        [
            {
                "timestamp": "2026-01-01T13:12:00Z",
                "service": "checkoutservice",
                "commit_sha": culprit,
                "version": "v1",
            },
            {
                "timestamp": "2026-01-01T13:40:00Z",
                "service": "frontend",
                "commit_sha": decoy,
                "version": "v2",
            },
        ],
    )
    _write_json(
        context / "flags.json",
        [
            {
                "timestamp": "2026-01-01T13:35:00Z",
                "service": "checkoutservice",
                "flag": "new_banner",
                "change": "off->on",
            }
        ],
    )
    visible_files = mco05._visible_file_manifest(root)
    _write_json(
        root / "incident.json",
        {
            "schema_version": 1,
            "opaque_id": "incident_fixture",
            "benchmark_commit": "fixture",
            "visible_files": visible_files,
            "visible_bytes": sum(row["bytes"] for row in visible_files.values()),
        },
    )
    return root


def test_signature_normalization_is_deterministic() -> None:
    assert mco05.normalize_signature("timeout 123 at abcdef0123456789") == "timeout <N> at <HEX>"


def test_compile_case_is_bounded_and_recomputable(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    compiled = mco05.compile_case(root)
    assert compiled["opaque_id"] == "incident_fixture"
    assert len(compiled["state_packet"]) <= 16
    assert len(mco05._reasoning_prompt(compiled["query"], compiled["state_packet"]).encode("utf-8")) <= 15_000
    assert compiled["candidate_ranking"][0]["commit_sha"] == "a" * 40
    assert {row["kind"] for row in compiled["documents"]}.issuperset(
        {"alert", "instruction", "metric", "log", "trace", "pattern", "commit", "deploy", "flag"}
    )
    assert mco05.verify_case_provenance(root, compiled)["pass"]


def test_official_controls_preserve_decoy_pressure(tmp_path: Path) -> None:
    compiled = mco05.compile_case(_fixture(tmp_path))
    assert compiled["official_controls"]["latest_deploy"] == "b" * 40
    assert compiled["official_controls"]["alert_service_deploy"] == "a" * 40
    assert compiled["official_controls"]["always_none"] == "none"


def test_hybrid_index_returns_bounded_documents(tmp_path: Path) -> None:
    documents = mco05.compile_case(_fixture(tmp_path))["documents"]
    embeddings = np.eye(len(documents), dtype=np.float32)
    query = np.ones(len(documents), dtype=np.float32)
    result = mco05.HybridIndex(documents, embeddings).retrieve("database timeout", query, 4)
    assert len(result["documents"]) == 4
    assert len(set(result["hybrid_top_ids"])) == 4


def test_reasoning_schema_cannot_name_unseen_commit(tmp_path: Path) -> None:
    compiled = mco05.compile_case(_fixture(tmp_path))
    packet = compiled["state_packet"]
    schema = mco05._schema(packet, compiled["services"])
    allowed = schema["properties"]["root_cause_commit"]["enum"]
    packet_shas = {row["commit_sha"] for row in packet if row.get("commit_sha")}
    assert set(allowed) == packet_shas | {"none"}


def test_safe_context_obeys_byte_limit(tmp_path: Path) -> None:
    compiled = mco05.compile_case(_fixture(tmp_path))
    selected = mco05._safe_context(compiled["query"], compiled["documents"])
    assert len(mco05._reasoning_prompt(compiled["query"], selected).encode("utf-8")) <= 15_000


def test_call_order_is_balanced() -> None:
    values = [f"incident_{number:03d}" for number in range(36)]
    orders = mco05._call_orders(values)
    counts = {variant: 0 for variant in mco05.REASONING_VARIANTS}
    for order in orders.values():
        counts[order[0]] += 1
    assert set(counts.values()) == {12}


def test_scoring_helpers() -> None:
    assert mco05._exact_commit("abcdef0", "abcdef012345")
    assert not mco05._exact_commit("abcdef", "abcdef012345")
    assert mco05._exact_commit("none", "none")
    low, high = mco05._wilson(18, 36)
    assert 0 < low < 0.5 < high < 1


def _reason_metric(accuracy: float, *, adversarial: float = 0.5, no_code: float = 0.5) -> dict:
    return {
        "accuracy": accuracy,
        "wilson95": [0.4, 0.8],
        "adversarial_accuracy": adversarial,
        "no_code_accuracy": no_code,
        "validity": 1.0,
        "citation_subset_valid": 1.0,
    }


def test_outcome_precedence_is_frozen() -> None:
    verification = {"pass": True}
    mechanical = {"metrics": {"candidate_coverage": {"accuracy": 0.95, "correct": 27, "n": 28}}}
    reasoning = {
        "metrics": {
            "state_packet": _reason_metric(0.6),
            "hybrid_rag_16": _reason_metric(0.4),
            "max_context": _reason_metric(0.35),
        }
    }
    assert mco05._outcome(verification, mechanical, reasoning)[0] == "MCO_05_DISJOINT_BOUNDED_INFERENCE_ADVANCE"
    reasoning["metrics"]["hybrid_rag_16"] = _reason_metric(0.59)
    assert mco05._outcome(verification, mechanical, reasoning)[0] == "MCO_05_CONVENTIONAL_RETRIEVAL_DOMINATES"
    reasoning["metrics"]["state_packet"] = _reason_metric(0.4)
    assert mco05._outcome(verification, mechanical, reasoning)[0] == "MCO_05_DISJOINT_REASONING_FAILURE"
    mechanical["metrics"]["candidate_coverage"]["accuracy"] = 0.8
    assert mco05._outcome(verification, mechanical, reasoning)[0] == "MCO_05_DISJOINT_COMPILER_TRANSFER_FAILURE"


def test_runtime_guard_blocks_oracle_roots(tmp_path: Path) -> None:
    script = """
from pathlib import Path
import tempfile
from scripts import run_mco05 as m
root = Path(tempfile.mkdtemp())
m.SCORER_ROOT = root / 'scorer'
m.SOURCE_ROOT = root / 'source'
m.SCORER_ROOT.mkdir()
m.SOURCE_ROOT.mkdir()
(m.SCORER_ROOT / 'label.json').write_text('{}')
(root / 'public.txt').write_text('ok')
m.install_scorer_read_guard()
assert (root / 'public.txt').read_text() == 'ok'
try:
    (m.SCORER_ROOT / 'label.json').read_text()
except PermissionError:
    pass
else:
    raise AssertionError('guard did not block scorer file')
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=mco05.REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_config_and_contract_match_frozen_boundaries() -> None:
    cfg = mco05.config()
    assert cfg["benchmark"]["expected_cases"] == 36
    assert cfg["compiler"]["packet_capacity"] == 16
    assert cfg["baselines"]["hybrid_rag"]["capacity"] == 16
    assert cfg["benchmark"]["commit"] == "0c3c476e4627978dc54b5c047fd488d40561b4e5"
    contract = mco05.CONTRACT_PATH.read_text(encoding="utf-8")
    assert "zero benchmark engineering cases" in contract.lower()
    assert "world" in contract.lower()


def test_direct_script_bootstraps_shared_client_namespace() -> None:
    completed = subprocess.run(
        [sys.executable, str(mco05.REPO_ROOT / "scripts" / "run_mco05.py"), "--help"],
        cwd=mco05.REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert "run-mechanical" in completed.stdout
