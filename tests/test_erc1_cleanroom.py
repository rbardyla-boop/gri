from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.erc1.compiler import (
    PACKET_CAPACITY,
    compile_case,
    score_feature,
)
from experiments.erc1.download_lossless_repack import required_paths
from experiments.erc1.stage import parse_case_name, read_metrics


def test_case_name_parser_matches_public_rcaeval_convention():
    row = parse_case_name("re3tt_ts-order-service_f3_4")
    assert row == {
        "source_case": "re3tt_ts-order-service_f3_4",
        "system": "tt",
        "root_cause_service": "ts-order-service",
        "fault": "f3",
        "repetition": 4,
    }


def test_json_and_parquet_readers_are_value_equivalent(tmp_path: Path):
    raw = {
        "svc_cpu": [[1, 1.0], [2, 2.0], [4, 4.0]],
        "svc_latency": [[1, 10.0], [3, 30.0], [4, 40.0]],
    }
    json_dir = tmp_path / "json_case"
    parquet_dir = tmp_path / "parquet_case"
    json_dir.mkdir()
    parquet_dir.mkdir()
    (json_dir / "metrics.json").write_text(json.dumps(raw), encoding="utf-8")
    expected, _ = read_metrics(json_dir)
    expected.to_parquet(parquet_dir / "metrics.parquet", index=False)
    actual, _ = read_metrics(parquet_dir)
    pd.testing.assert_frame_equal(expected, actual)


def test_feature_score_implements_published_scale_formula():
    times = np.arange(600, dtype=np.int64)
    baseline = 10.0 + 0.1 * np.sin(np.arange(300) / 7.0)
    post = 11.0 + 0.1 * np.sin(np.arange(300) / 7.0)
    values = np.concatenate([baseline, post])
    record = score_feature(
        "E1-test",
        "orders_cpu",
        times,
        values,
        300,
        "a" * 64,
        "b" * 64,
    )
    assert record is not None
    assert record.pre_count == 300
    assert record.post_count == 300
    assert abs(record.median_shift - 1.0) < 0.02
    assert record.denominator == max(
        record.scaled_mad,
        record.scaled_iqr,
        record.scaled_diff_std,
        record.relative_median_floor,
        record.magnitude_floor,
        record.absolute_floor,
    )
    assert record.score == min(30.0, record.numerator / record.denominator)


def test_resource_aggregation_and_packet_capacity(tmp_path: Path):
    times = np.arange(600, dtype=np.int64)
    frame = {"time": times}
    # Root candidate has two strong resource channels. Comparator has one.
    for service, shifts in {
        "root": {"cpu": 1.0, "mem": 0.8, "latency": 0.2},
        "other": {"cpu": 0.45, "mem": 0.1, "latency": 0.5},
    }.items():
        for suffix, shift in shifts.items():
            base = 10.0 + 0.15 * np.sin(np.arange(300) / 5.0 + len(frame))
            post = base + shift
            frame[f"{service}_{suffix}"] = np.concatenate([base, post])
    df = pd.DataFrame(frame)
    metrics = tmp_path / "E1-test.parquet"
    df.to_parquet(metrics, index=False)
    import hashlib

    digest = hashlib.sha256(metrics.read_bytes()).hexdigest()
    meta = {
        "opaque_id": "E1-test",
        "system": "ob",
        "inject_time": 300,
        "source_metrics_sha256": "c" * 64,
        "staged_metrics_sha256": digest,
    }
    meta_path = tmp_path / "E1-test.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    result = compile_case(metrics, meta_path)
    assert result["root_cause_service_ranking"][0] == "root"
    assert result["packet_count"] <= PACKET_CAPACITY


def test_explicit_re3_transport_inventory_selection():
    repo_files = [
        "README.md",
        "re2ob_x_cpu_1/metrics.parquet",
        "re3ob_checkoutservice_f1_1/metrics.parquet",
        "re3ob_checkoutservice_f1_1/inject_time.txt",
        "re3ob_checkoutservice_f1_1/logs.parquet",
        "re3tt_ts-order-service_f3_4/inject_time.txt",
        "re3tt_ts-order-service_f3_4/metrics.parquet",
        "re3tt_ts-order-service_f3_4/traces.parquet",
    ]
    metrics, inject = required_paths(repo_files)
    assert metrics == [
        "re3ob_checkoutservice_f1_1/metrics.parquet",
        "re3tt_ts-order-service_f3_4/metrics.parquet",
    ]
    assert inject == [
        "re3ob_checkoutservice_f1_1/inject_time.txt",
        "re3tt_ts-order-service_f3_4/inject_time.txt",
    ]


def test_cleanroom_executable_modules_do_not_import_original_mco04_code():
    # Governance metadata is intentionally allowed to *name* the forbidden
    # historical files. The firewall applies to executable staging/compiler/
    # scoring/data-loading code, which must neither import nor reference them.
    runtime_modules = (
        Path("experiments/erc1/stage.py"),
        Path("experiments/erc1/compiler.py"),
        Path("experiments/erc1/score.py"),
        Path("experiments/erc1/download_lossless_repack.py"),
    )
    forbidden_literals = ("run_mco04", "test_mco04")
    forbidden_import_roots = {"scripts.run_mco04", "tests.test_mco04"}

    for path in runtime_modules:
        text = path.read_text(encoding="utf-8")
        for literal in forbidden_literals:
            assert literal not in text, f"{path} references forbidden historical implementation {literal}"

        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name for alias in node.names}
                assert not (imported & forbidden_import_roots), f"{path} imports historical MCO-04 code"
            elif isinstance(node, ast.ImportFrom):
                assert node.module not in forbidden_import_roots, f"{path} imports historical MCO-04 code"
