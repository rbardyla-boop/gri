from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def write_cases(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def test_development_freezes_only_after_grinder_and_ablation_gates(tmp_path: Path) -> None:
    build = tmp_path / "build.jsonl"
    dev = tmp_path / "dev.jsonl"
    output = tmp_path / "champion.json"
    write_cases(build, [
        {"case_id": "B1", "input": '{"label":"KAV","evidence":["E1"]}', "expected": {"label": "KAV", "evidence": ["E1"]}},
        {"case_id": "B2", "input": '{"label":"MIR","evidence":["E2"]}', "expected": {"label": "MIR", "evidence": ["E2"]}},
        {"case_id": "B3", "input": '{"label":"TOV","evidence":["E3"]}', "expected": {"label": "TOV", "evidence": ["E3"]}},
    ])
    write_cases(dev, [
        {"case_id": "D1", "input": 'answer: {"label":" kav ","evidence":["E2","E1","E2"]}', "expected": {"label": "KAV", "evidence": ["E1", "E2"]}},
        {"case_id": "D2", "input": '```json\n{"label":"mir","evidence":["E4","E4"]}\n```', "expected": {"label": "MIR", "evidence": ["E4"]}},
        {"case_id": "D3", "input": 'Result {"label":"tov","evidence":["E9","E7","E7"]} done', "expected": {"label": "TOV", "evidence": ["E7", "E9"]}},
        {"case_id": "D4", "input": '{"label":"KAV","evidence":["E8","E8"]}', "expected": {"label": "KAV", "evidence": ["E8"]}},
    ])
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.forge_e1.develop_te0_e1", "--build", str(build), "--dev", str(dev), "--output", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "TE0_E1_DEVELOPMENT_CHAMPION_FROZEN"
    assert all(report["gates"].values())
    assert report["repair_dev"]["grinder_failure_count"] == 0
    assert report["repair_dev"]["attack_set_exact_rate"] == 1.0
    assert report["unnecessary_tools"] == []
    tools = report["champion"]["tools"]
    assert "ts_extract_json_object" in tools
    assert "ts_json_parse_object" in tools
    assert "ts_normalize_label" in tools
    assert "ts_dedupe_sort_evidence" in tools


def test_development_stops_when_raw_producer_already_needs_no_repair(tmp_path: Path) -> None:
    build = tmp_path / "build.jsonl"
    dev = tmp_path / "dev.jsonl"
    output = tmp_path / "champion.json"
    rows = [
        {"case_id": f"C{i}", "input": json.dumps({"label": "KAV", "evidence": [f"E{i}"]}), "expected": {"label": "KAV", "evidence": [f"E{i}"]}}
        for i in range(10)
    ]
    write_cases(build, rows[:5])
    write_cases(dev, rows[5:])
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.forge_e1.develop_te0_e1", "--build", str(build), "--dev", str(dev), "--output", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "TE0_E1_REPAIR_NOT_NEEDED"
    assert "champion" not in report
