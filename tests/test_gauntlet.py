from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from gauntlet.core import audit_result, create_freeze, replay_run, run_frozen, verify_freeze, verdict_frozen


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _python_command(script: str) -> str:
    return json.dumps([sys.executable, script])


def test_freeze_detects_input_mutation(tmp_path: Path) -> None:
    _write(tmp_path / "runner.py", "print('ok')\n")
    _write(tmp_path / "data.txt", "alpha\n")
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "mutation-check"
require_same_commit = false

[freeze]
inputs = ["runner.py", "data.txt"]

[run]
mode = "subprocess"
command = {_python_command("runner.py")}
outputs = []
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    manifest = Path(frozen["manifest_path"])
    assert verify_freeze(manifest)["pass"]
    _write(tmp_path / "data.txt", "changed\n")
    checked = verify_freeze(manifest)
    assert not checked["pass"]
    assert "input:data.txt" in checked["failures"]


def test_retrospective_audit_respects_absolute_gate_before_relative_win(tmp_path: Path) -> None:
    spec = tmp_path / "audit.toml"
    result = tmp_path / "result.json"
    _write(
        spec,
        f"""
[experiment]
id = "gate-ordering"
require_same_commit = false

[freeze]
inputs = []

[run]
mode = "subprocess"
command = {_python_command("noop.py")}
outputs = []

[[gates]]
name = "candidate_quality"
path = "candidate"
op = ">="
value = 0.90
required = true

[comparison]
candidate_path = "candidate"
baseline_path = "baseline"
direction = "greater"
minimum_delta = 0.05
""".strip()
        + "\n",
    )
    result.write_text(json.dumps({"candidate": 0.60, "baseline": 0.50}), encoding="utf-8")
    audited = audit_result(spec, result)
    assert audited["comparison"]["pass"]
    assert not audited["required_gates_pass"]
    assert audited["state"] == "NO_ESTABLISHED_ADVANTAGE"
    assert audited["evidence_class"] == "RETROSPECTIVE_AUDIT"


def test_frozen_run_replay_and_verdict_are_bound_to_same_result(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    _write(
        runner,
        "import json\n"
        "from pathlib import Path\n"
        "Path('result.json').write_text(json.dumps({'candidate': 0.8, 'baseline': 0.5}) + '\\n')\n",
    )
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "deterministic-run"
require_same_commit = false

[freeze]
inputs = ["runner.py"]

[run]
mode = "subprocess"
command = {_python_command("runner.py")}
outputs = ["result.json"]

[verdict]
result_file = "result.json"
require_replay = true

[[gates]]
name = "quality"
path = "candidate"
op = ">="
value = 0.70
required = true

[comparison]
candidate_path = "candidate"
baseline_path = "baseline"
direction = "greater"
minimum_delta = 0.20
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    manifest = Path(frozen["manifest_path"])
    run = run_frozen(manifest, "live")
    assert run["run_status"] == "PASS"
    replay = replay_run(manifest, run["receipt_path"], "replay")
    assert replay["pass"]
    verdict = verdict_frozen(manifest, run["receipt_path"], replay["replay_path"])
    assert all(verdict["integrity"].values())
    assert verdict["state"] == "ADVANCE"
    assert verdict["evidence_class"] == "PREREGISTERED_RUN"


def test_python_guard_blocks_holdout_read(tmp_path: Path) -> None:
    protected = tmp_path / "private_labels"
    protected.mkdir()
    _write(protected / "answers.json", '{"answer": 42}\n')
    _write(
        tmp_path / "cheat.py",
        "from pathlib import Path\n"
        "Path('private_labels/answers.json').read_text()\n",
    )
    spec = tmp_path / "guard.toml"
    _write(
        spec,
        """
[experiment]
id = "guard-test"
require_same_commit = false

[freeze]
inputs = ["cheat.py"]
protected = ["private_labels"]

[run]
mode = "python"
entry = "cheat.py"
args = []
outputs = []
deny_subprocess = true
deny_network = true
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    env = dict(os.environ)
    repo_src = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = os.pathsep.join([str(repo_src), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    completed = subprocess.run(
        [sys.executable, "-m", "gauntlet._guard_exec", frozen["manifest_path"]],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode != 0
    assert "GAUNTLET_HOLDOUT_VIOLATION" in completed.stderr


def test_tampered_run_receipt_forces_integrity_failure(tmp_path: Path) -> None:
    _write(
        tmp_path / "runner.py",
        "import json\nfrom pathlib import Path\nPath('result.json').write_text(json.dumps({'score': 1.0}) + '\\n')\n",
    )
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "receipt-tamper"
require_same_commit = false

[freeze]
inputs = ["runner.py"]

[run]
mode = "subprocess"
command = {_python_command("runner.py")}
outputs = ["result.json"]

[verdict]
result_file = "result.json"

[[gates]]
name = "score"
path = "score"
op = ">="
value = 1.0
required = true
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    run = run_frozen(frozen["manifest_path"], "live")
    receipt_path = Path(run["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["exit_code"] = 99
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    verdict = verdict_frozen(frozen["manifest_path"], receipt_path)
    assert verdict["state"] == "INTEGRITY_FAIL"
    assert not verdict["integrity"]["receipt_digest"]
