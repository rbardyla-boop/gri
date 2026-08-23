from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEM0 = ROOT / "experiments" / "sem0"
EXPECTED_CASES_SHA256 = "74be062f249dabea4a2fef2aa5837438dcff8bd03115cff993e607dd398262f2"
EXPECTED_GOLD_SHA256 = "01a4bee6a7ad70fa93f96a10fc4e5b5e62a86a3fb8e653b1af55c7c61b573aa0"
EXPECTED_REPLAY_SHA256 = "cc091f871755b80c52e767c8d39a878aa2944f5080bed6b5c0531ddadb449906"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _generate(tmp_path: Path):
    cases = tmp_path / "cases.jsonl"
    gold = tmp_path / "gold.jsonl"
    replay = tmp_path / "replay.jsonl"
    subprocess.run(
        [sys.executable, str(SEM0 / "generate_sem0.py"), "--cases", str(cases), "--gold", str(gold)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, str(SEM0 / "make_replay_subset.py"), "--cases", str(cases), "--output", str(replay)],
        check=True,
        capture_output=True,
        text=True,
    )
    return cases, gold, replay


def _perfect_predictions(cases_path: Path, gold_path: Path, only_ids=None):
    cases = {x["id"]: x for x in _load_jsonl(cases_path)}
    gold = {x["id"]: x for x in _load_jsonl(gold_path)}
    ids = list(cases) if only_ids is None else list(only_ids)
    out = []
    for cid in ids:
        case = cases[cid]
        row = gold[cid]
        answers = []
        for prop in case["propositions"]:
            g = row["gold"][prop["id"]]
            answers.append({"id": prop["id"], "label": g["label"], "evidence": g["evidence"]})
        out.append({"id": cid, "answers": answers})
    return out


def test_generator_is_exactly_reproducible_and_replay_is_frozen(tmp_path: Path) -> None:
    cases, gold, replay = _generate(tmp_path)
    assert _sha(cases) == EXPECTED_CASES_SHA256
    assert _sha(gold) == EXPECTED_GOLD_SHA256
    assert _sha(replay) == EXPECTED_REPLAY_SHA256
    assert len(_load_jsonl(cases)) == 56
    assert len(_load_jsonl(gold)) == 56
    assert len(_load_jsonl(replay)) == 14


def test_labels_are_balanced_and_presentation_position_is_not_a_label_code(tmp_path: Path) -> None:
    cases_path, gold_path, _ = _generate(tmp_path)
    cases = _load_jsonl(cases_path)
    gold = {x["id"]: x for x in _load_jsonl(gold_path)}
    label_counts = Counter()
    position_counts = defaultdict(Counter)
    for case in cases:
        row = gold[case["id"]]
        for index, prop in enumerate(case["propositions"]):
            label = row["gold"][prop["id"]]["label"]
            label_counts[label] += 1
            position_counts[index][label] += 1
            assert re.fullmatch(r"P_[0-9A-F]{8}", prop["id"])
        for stmt in case["context"]:
            assert re.fullmatch(r"S_[0-9A-F]{8}", stmt["id"])
    assert max(label_counts.values()) - min(label_counts.values()) <= 12
    for counts in position_counts.values():
        assert max(counts.values()) / sum(counts.values()) < 0.25


def test_perfect_fixture_passes_every_frozen_gate(tmp_path: Path) -> None:
    cases, gold, replay_cases = _generate(tmp_path)
    scorer = _load_module("score_sem0_perfect", SEM0 / "score_sem0.py")
    live_path = tmp_path / "perfect-live.jsonl"
    replay_path = tmp_path / "perfect-replay.jsonl"
    live = _perfect_predictions(cases, gold)
    replay_ids = [x["id"] for x in _load_jsonl(replay_cases)]
    replay = _perfect_predictions(cases, gold, replay_ids)
    live_path.write_text("".join(json.dumps(x) + "\n" for x in live), encoding="utf-8")
    replay_path.write_text("".join(json.dumps(x) + "\n" for x in replay), encoding="utf-8")
    result = scorer.score(cases, gold, live_path, replay_cases, replay_path)
    assert result["verdict"] == "SEM_0_MEANING_RELATION_COMPETENCE"
    assert all(result["gates"].values())
    assert result["metrics"]["accuracy"] == 1.0
    assert result["metrics"]["replay"]["agreement"] == 1.0


def test_always_unknown_fixture_fails_scientific_claim(tmp_path: Path) -> None:
    cases, gold, replay_cases = _generate(tmp_path)
    scorer = _load_module("score_sem0_unknown", SEM0 / "score_sem0.py")
    all_cases = _load_jsonl(cases)
    predictions = [
        {"id": case["id"], "answers": [{"id": p["id"], "label": "UNKNOWN", "evidence": []} for p in case["propositions"]]}
        for case in all_cases
    ]
    pred_path = tmp_path / "unknown.jsonl"
    pred_path.write_text("".join(json.dumps(x) + "\n" for x in predictions), encoding="utf-8")
    replay_ids = {x["id"] for x in _load_jsonl(replay_cases)}
    replay_path = tmp_path / "unknown-replay.jsonl"
    replay_path.write_text("".join(json.dumps(x) + "\n" for x in predictions if x["id"] in replay_ids), encoding="utf-8")
    result = scorer.score(cases, gold, pred_path, replay_cases, replay_path)
    assert result["verdict"] == "SEM_0_NOT_ESTABLISHED"
    assert not result["gates"]["overall_accuracy"]
    assert not result["gates"]["macro_f1"]
    assert not result["gates"]["nonce_transfer"]


def test_replay_drift_fails_replay_gate(tmp_path: Path) -> None:
    cases, gold, replay_cases = _generate(tmp_path)
    scorer = _load_module("score_sem0_replay", SEM0 / "score_sem0.py")
    live = _perfect_predictions(cases, gold)
    replay_ids = [x["id"] for x in _load_jsonl(replay_cases)]
    replay = _perfect_predictions(cases, gold, replay_ids)
    replay[0]["answers"][0]["label"] = "UNKNOWN" if replay[0]["answers"][0]["label"] != "UNKNOWN" else "ASSERTED"
    live_path = tmp_path / "live.jsonl"
    replay_path = tmp_path / "replay-drift.jsonl"
    live_path.write_text("".join(json.dumps(x) + "\n" for x in live), encoding="utf-8")
    replay_path.write_text("".join(json.dumps(x) + "\n" for x in replay), encoding="utf-8")
    result = scorer.score(cases, gold, live_path, replay_cases, replay_path)
    assert result["verdict"] == "SEM_0_NOT_ESTABLISHED"
    assert result["gates"]["semantic_replay"] is False


def test_model_identity_fails_closed_while_placeholder(tmp_path: Path) -> None:
    runner = _load_module("run_sem0_identity", SEM0 / "run_sem0.py")
    path = tmp_path / "model.json"
    path.write_text((SEM0 / "SEM0_MODEL_IDENTITY.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError):
        runner.load_identity(path)


def test_runner_accepts_json_object_wrapped_in_extra_text() -> None:
    runner = _load_module("run_sem0_json", SEM0 / "run_sem0.py")
    value = runner.extract_json_object('prefix {"id":"C","answers":[]} suffix')
    assert value == {"id": "C", "answers": []}
