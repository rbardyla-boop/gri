from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import run_mco04 as mco04


def test_direct_script_bootstraps_shared_client_namespace(tmp_path: Path) -> None:
    script = mco04.REPO_ROOT / "scripts" / "run_mco04.py"
    probe = (
        "import runpy, sys; "
        f"runpy.run_path({str(script)!r}); "
        "from scripts import run_mco03; "
        "assert run_mco03.__file__"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _write_case(root: Path) -> Path:
    case = root / "incident_0123456789abcdefabcd"
    case.mkdir(parents=True)
    alert = 1_000
    times = np.arange(alert - 300, alert + 300)
    before = times < alert
    frame = pd.DataFrame(
        {
            "time": times,
            "root_cpu": np.where(before, 1.0, 8.0),
            "root_mem": np.where(before, 100.0, 500.0),
            "root_socket": np.where(before, 2.0, 9.0),
            "victim_cpu": np.where(before, 2.0, 2.1),
            "victim_mem": np.where(before, 200.0, 201.0),
            "victim_error": np.where(before, 0.0, 100.0),
        }
    )
    frame.to_parquet(case / "metrics.parquet", index=False)
    logs = pd.DataFrame(
        {
            "timestamp": [alert - 1, alert, alert + 1],
            "container_name": ["root", "victim", "victim"],
            "message": ["healthy", "request failed", "timeout error"],
        }
    )
    logs.to_parquet(case / "logs.parquet", index=False)
    (case / "inject_time.txt").write_text(str(alert), encoding="utf-8")
    files = {}
    for path in case.iterdir():
        files[path.name] = {"sha256": mco04.file_sha256(path), "bytes": path.stat().st_size}
    mco04.write_json(
        case / "incident.json",
        {
            "opaque_id": case.name,
            "dataset": "TEST",
            "alert_time": alert,
            "files": files,
        },
    )
    return case


def test_opaque_id_is_deterministic_and_label_free() -> None:
    first = mco04.opaque_id("synthetic_cartservice_f1_alpha")
    assert first == mco04.opaque_id("synthetic_cartservice_f1_alpha")
    assert first != mco04.opaque_id("synthetic_cartservice_f1_beta")
    assert "cartservice" not in first
    assert first.startswith("incident_")
    assert len(first) == len("incident_") + 20


def test_resource_corroboration_avoids_loud_victim(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    result = mco04.compile_case(case)
    assert result["prediction"] == "root"
    assert result["packet_count"] <= 16
    assert result["raw_to_packet_byte_reduction"] > 1
    assert mco04.verify_case_provenance(case, result)["pass"]
    assert mco04.post_error_volume(case)["prediction"] == "victim"


def test_fixed_documents_and_hybrid_retrieval_are_bounded(tmp_path: Path) -> None:
    case = _write_case(tmp_path)
    documents = mco04.build_fixed_documents(case)
    assert documents
    assert len({row["evidence_id"] for row in documents}) == len(documents)
    embeddings = np.eye(len(documents), dtype=np.float32)
    index = mco04.TelemetryHybridIndex(documents, embeddings)
    query = mco04.incident_query(["root", "victim"])
    result = index.retrieve(query, embeddings[0], capacity=16)
    assert 0 < len(result["documents"]) <= 16
    assert set(result["hybrid_top_ids"]) <= {row["evidence_id"] for row in documents}


def test_robust_feature_requires_enough_points() -> None:
    stats = mco04.robust_feature_stats([1.0] * 19, [2.0] * 19, mco04.config())
    assert not stats["valid"]
    assert stats["score"] == 0.0


def test_wilson_interval_contains_observed_rate() -> None:
    low, high = mco04._wilson_interval(9, 10)
    assert low < 0.9 < high
    assert mco04._wilson_interval(0, 0) == [0.0, 0.0]


def test_scientific_stage_requires_freeze(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mco04, "FREEZE_PATH", tmp_path / "absent-freeze.json")
    with pytest.raises(RuntimeError, match="cannot be staged"):
        mco04.stage_split("scientific", tmp_path)


def test_opacity_checks_structure_not_short_fault_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    public = tmp_path / "public"
    scorer = tmp_path / "scorer"
    case = public / "engineering" / "incident_0123456789abcdefabcd"
    case.mkdir(parents=True)
    mco04.write_json(
        case / "incident.json",
        {
            "opaque_id": case.name,
            "dataset": "RE3-OB",
            "alert_time": 10,
            "files": {"metrics.parquet": {"sha256": "f1" * 32, "bytes": 1}},
        },
    )
    scorer.mkdir(parents=True)
    (scorer / "engineering_labels.json").write_text(
        json.dumps(
            {
                case.name: {
                    "source_case": "re3ob_root_f1_1",
                    "fault": "f1",
                    "root_cause_service": "root",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mco04, "PUBLIC_DATA_ROOT", public)
    monkeypatch.setattr(mco04, "SCORER_ROOT", scorer)
    assert mco04.verify_opacity("engineering")["pass"]


def test_repeat_selection_is_deterministic_and_ceil_sized() -> None:
    case_ids = [f"incident_{number:020x}" for number in range(63)]
    selected = mco04.repeat_case_ids(case_ids)
    assert len(selected) == 7
    assert selected == mco04.repeat_case_ids(list(reversed(case_ids)))
    assert set(selected) <= set(case_ids)


def test_variant_call_order_is_input_invariant_and_balanced() -> None:
    case_ids = [f"incident_{number:020x}" for number in range(63)]
    forward = mco04.balanced_variant_call_orders(case_ids)
    reverse = mco04.balanced_variant_call_orders(list(reversed(case_ids)))
    assert forward == reverse
    counts = {
        variant: sum(order[0] == variant for order in forward.values())
        for variant in mco04.REASONING_VARIANTS
    }
    assert max(counts.values()) - min(counts.values()) <= 1


def test_scientific_case_literals_are_isolated_from_method_sources() -> None:
    result = mco04.verify_scientific_literal_isolation()
    assert result["pass"], result["failures"]


def _verdict_inputs(
    *, compiler_top1: float = 1.0, control_top1: float = 0.5, packet_top1: float = 1.0
) -> dict[str, object]:
    mechanical_summary = {
        "all_provenance_pass": True,
        "all_capacity_pass": True,
        "median_raw_to_packet_byte_reduction": 1500.0,
        "minimum_raw_to_packet_byte_reduction": 200.0,
    }
    metric = {
        "n": 63,
        "top1": compiler_top1,
        "top3": 1.0,
        "wilson95_top1": [0.81, 1.0],
        "per_system": {
            "RE3-OB": {"top1": compiler_top1},
            "RE3-SS": {"top1": compiler_top1},
            "RE3-TT": {"top1": compiler_top1},
        },
    }
    control = {**metric, "top1": control_top1}
    mechanical_score = {
        "metrics": {
            "compiler": metric,
            "author_style_baro": control,
            "single_feature_robust": control,
            "post_error_volume": control,
        }
    }
    usage = {
        name: {
            "prompt_tokens": 100 if name == "compiler_packet" else 2000,
            "output_tokens": 20,
            "wall_seconds": 1.0,
        }
        for name in mco04.REASONING_VARIANTS
    }
    reasoning_summary = {
        "usage": usage,
        "timing": {
            "online_query_seconds": {
                "compiler_packet": 1.0,
                "hybrid_rag_16": 2.0,
                "max_context": 2.0,
            }
        },
    }
    reasoning_metric = {
        "valid": 1.0,
        "root_top1": packet_top1,
        "fault_exact": 0.0,
        "citation_subset_valid": 1.0,
    }
    reasoning_score = {
        "metrics": {
            "compiler_packet": reasoning_metric,
            "hybrid_rag_16": {**reasoning_metric, "root_top1": control_top1},
            "max_context": {**reasoning_metric, "root_top1": control_top1},
        }
    }
    return {
        "mechanical_summary": mechanical_summary,
        "mechanical_score": mechanical_score,
        "reasoning_summary": reasoning_summary,
        "reasoning_score": reasoning_score,
        "stability": {"semantic_agreement": 1.0},
        "integrity_pass": True,
    }


def test_verdict_credit_assignment_branches() -> None:
    inputs = _verdict_inputs()
    outcome, gates = mco04.evaluate_mco04_verdict(**inputs)
    assert outcome == "MCO_04_TRANSPARENT_STATE_COMPILER_REPLICATION_ADVANCE"

    report = mco04.render_report(
        {
            "verdict": outcome,
            "overall_verification": "PASS",
            "case_count": 63,
            "gates": gates,
            "verification": {"checks": {"freeze": True}},
            "packet_fault_exact": 0.0,
            "stability_semantic_agreement": 1.0,
            "median_compression": 1500.0,
            "minimum_compression": 200.0,
            "reasoning_usage": inputs["reasoning_summary"]["usage"],
            "reasoning_timing": inputs["reasoning_summary"]["timing"],
            "embedding_usage": {
                "model_calls": 10,
                "input_tokens": 1000,
                "wall_seconds": 1.0,
            },
            "compiler_ingestion_seconds": 1.0,
        }
    )
    for heading in (
        "Claim under test",
        "Check",
        "Verdict",
        "Criteria",
        "Assumption register",
        "Credit assignment",
        "Verification gap",
        "Stop/continue",
        "Maturity status",
    ):
        assert f"## {heading}" in report

    outcome, _ = mco04.evaluate_mco04_verdict(
        **_verdict_inputs(control_top1=0.98)
    )
    assert outcome == "MCO_04_CONVENTIONAL_RCA_DOMINATES"

    outcome, _ = mco04.evaluate_mco04_verdict(
        **_verdict_inputs(compiler_top1=0.9, control_top1=0.5, packet_top1=0.96)
    )
    assert outcome == "MCO_04_BOUNDED_INFERENCE_REPLICATION_ADVANCE"

    invalid = _verdict_inputs()
    invalid["integrity_pass"] = False
    outcome, _ = mco04.evaluate_mco04_verdict(**invalid)
    assert outcome == "MCO_04_BENCHMARK_INVALID"
