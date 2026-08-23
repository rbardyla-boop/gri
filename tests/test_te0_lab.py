from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "experiments" / "mbm_lab"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_candidate_view_hides_target():
    grinder = load_module("te0_grinder", LAB / "grinder.py")
    fixture = {"id": "x", "kind": "copy", "prompt": "p", "target": {"value": "SECRET"}}
    assert grinder.candidate_view(fixture) == {"id": "x", "kind": "copy", "prompt": "p"}
    assert "target" not in grinder.candidate_view(fixture)


def test_failure_classifier_localizes_interface_and_resource():
    fc = load_module("te0_failure_classifier", LAB / "failure_classifier.py")
    assert fc.classify({"schema_error": True}).klass == "INTERFACE_FAILURE"
    assert fc.classify({"oom": True}).klass == "RESOURCE_FAILURE"
    assert fc.classify({"valid_execution": True, "valid_measurement": True, "answer_wrong": True}).klass == "MODEL_FAILURE"


def test_fixture_forge_set_target_matches_extractor_contract():
    forge = load_module("te0_fixture_forge", LAB / "fixture_forge.py")
    import random
    row = forge.make_fixture(random.Random(1), 0, "set")
    assert set(row["target"]) == {"selected"}
    assert json.dumps(row["target"], sort_keys=True) in row["prompt"]


def test_toolsmith_rejects_extra_contract_fields():
    toolsmith = load_module("te0_toolsmith", LAB / "toolsmith.py")
    bad = {
        "name": "abc",
        "command": ["python", "x.py"],
        "timeout_seconds": 10,
        "network": False,
        "description": "x",
        "secret": "nope",
    }
    try:
        toolsmith.validate(bad)
    except ValueError as exc:
        assert "unexpected fields" in str(exc)
    else:
        raise AssertionError("extra fields accepted")


def test_recipe_tool_never_receives_gold(tmp_path: Path):
    search = load_module("te0_recipe_search", LAB / "recipe_search.py")
    tool = tmp_path / "tool.py"
    tool.write_text(
        "import json,sys\n"
        "x=json.load(sys.stdin)\n"
        "assert 'target' not in x['fixture']\n"
        "json.dump({'state': {'prediction': {'value':'A'}}},sys.stdout)\n",
        encoding="utf-8",
    )
    catalog = {"t": {"name": "t", "command": [sys.executable, str(tool)], "promotable": True}}
    fixture = {"id": "x", "kind": "copy", "prompt": "return A", "target": {"value": "A"}}
    pred, trace, latency, ok = search.run_recipe(["t"], catalog, fixture, 10)
    assert ok is True
    assert pred == {"value": "A"}


def test_consensus_tie_fails_closed(tmp_path: Path):
    payload = {"fixture": {"id":"x","kind":"copy","prompt":"p"}, "state": {"parsed_candidates": [{"value":"A"},{"value":"B"}]}}
    proc = subprocess.run(
        [sys.executable, str(LAB / "tools" / "consensus.py")],
        input=json.dumps(payload), text=True, capture_output=True, check=False,
    )
    assert proc.returncode != 0
    assert "consensus tie" in proc.stderr


def test_starter_catalog_has_no_harness_tools():
    cat = json.loads((LAB / "starter_catalog.json").read_text(encoding="utf-8"))
    assert cat["tools"]
    assert all(tool.get("promotable") is True for tool in cat["tools"])
    assert all("echo_target" not in tool["command"] for tool in cat["tools"])
