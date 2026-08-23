from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gauntlet.core import create_freeze, replay_run, run_frozen, verify_freeze, verdict_frozen


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _command(script: str) -> str:
    return json.dumps([sys.executable, script])


def _guard_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_src = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = os.pathsep.join([str(repo_src), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


def _run_guarded(manifest: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "gauntlet._guard_exec", manifest],
        cwd=cwd,
        env=_guard_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_spec_edit_after_freeze_is_detected(tmp_path: Path) -> None:
    _write(tmp_path / "runner.py", "print('ok')\n")
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "spec-mutation"
require_same_commit = false
[freeze]
inputs = ["runner.py"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = []
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    spec.write_text(spec.read_text(encoding="utf-8") + "# post-freeze edit\n", encoding="utf-8")
    result = verify_freeze(frozen["manifest_path"])
    assert not result["pass"]
    assert "spec_hash" in result["failures"]


def test_manifest_edit_is_detected(tmp_path: Path) -> None:
    _write(tmp_path / "runner.py", "print('ok')\n")
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "manifest-mutation"
require_same_commit = false
[freeze]
inputs = ["runner.py"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = []
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    path = Path(frozen["manifest_path"])
    value = json.loads(path.read_text(encoding="utf-8"))
    value["experiment_id"] = "tampered"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    result = verify_freeze(path)
    assert not result["pass"]
    assert "manifest_digest" in result["failures"]


def test_replay_detects_non_deterministic_declared_output(tmp_path: Path) -> None:
    _write(
        tmp_path / "runner.py",
        "from pathlib import Path\n"
        "p=Path('counter.txt')\n"
        "n=int(p.read_text())+1 if p.exists() else 1\n"
        "p.write_text(str(n))\n"
        "Path('result.json').write_text('{\\"n\\": %d}\\n' % n)\n",
    )
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "replay-drift"
require_same_commit = false
[freeze]
inputs = ["runner.py"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = ["result.json"]
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    run = run_frozen(frozen["manifest_path"], "live")
    replay = replay_run(frozen["manifest_path"], run["receipt_path"], "replay")
    assert not replay["pass"]
    assert not replay["checks"]["outputs"]


def test_result_edit_after_run_breaks_result_binding(tmp_path: Path) -> None:
    _write(
        tmp_path / "runner.py",
        "import json\nfrom pathlib import Path\nPath('result.json').write_text(json.dumps({'score': 1.0}) + '\\n')\n",
    )
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "result-tamper"
require_same_commit = false
[freeze]
inputs = ["runner.py"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = ["result.json"]
[verdict]
result_file = "result.json"
[[gates]]
name = "score"
path = "score"
op = ">="
value = 1.0
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    run = run_frozen(frozen["manifest_path"], "live")
    (tmp_path / "result.json").write_text('{"score": 0.0}\n', encoding="utf-8")
    verdict = verdict_frozen(frozen["manifest_path"], run["receipt_path"])
    assert verdict["state"] == "INTEGRITY_FAIL"
    assert not verdict["integrity"]["result_binding"]


def test_missing_declared_output_fails_run(tmp_path: Path) -> None:
    _write(tmp_path / "runner.py", "print('no result')\n")
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "missing-output"
require_same_commit = false
[freeze]
inputs = ["runner.py"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = ["must_exist.json"]
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    run = run_frozen(frozen["manifest_path"], "live")
    assert run["run_status"] == "FAIL"
    assert run["missing_outputs"] == ["must_exist.json"]


def test_protected_root_cannot_be_declared_for_unenforced_subprocess_mode(tmp_path: Path) -> None:
    (tmp_path / "private").mkdir()
    _write(tmp_path / "runner.py", "print('ok')\n")
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "false-isolation-claim"
require_same_commit = false
[freeze]
inputs = ["runner.py"]
protected = ["private"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = []
""".strip()
        + "\n",
    )
    with pytest.raises(ValueError, match="protected roots require"):
        create_freeze(spec)


def test_guard_blocks_subprocess_escape(tmp_path: Path) -> None:
    (tmp_path / "private").mkdir()
    _write(
        tmp_path / "escape.py",
        "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'print(1)'], check=True)\n",
    )
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        """
[experiment]
id = "subprocess-escape"
require_same_commit = false
[freeze]
inputs = ["escape.py"]
protected = ["private"]
[run]
mode = "python"
entry = "escape.py"
outputs = []
deny_subprocess = true
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    completed = _run_guarded(frozen["manifest_path"], tmp_path)
    assert completed.returncode != 0
    assert "GAUNTLET_SUBPROCESS_VIOLATION" in completed.stderr


def test_guard_blocks_network_when_frozen_policy_denies_it(tmp_path: Path) -> None:
    (tmp_path / "private").mkdir()
    _write(
        tmp_path / "network.py",
        "import socket\ns=socket.socket()\ns.connect(('127.0.0.1', 9))\n",
    )
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        """
[experiment]
id = "network-escape"
require_same_commit = false
[freeze]
inputs = ["network.py"]
protected = ["private"]
[run]
mode = "python"
entry = "network.py"
outputs = []
deny_subprocess = true
deny_network = true
""".strip()
        + "\n",
    )
    frozen = create_freeze(spec)
    completed = _run_guarded(frozen["manifest_path"], tmp_path)
    assert completed.returncode != 0
    assert "GAUNTLET_NETWORK_VIOLATION" in completed.stderr


def test_declared_input_cannot_escape_experiment_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-gauntlet.txt"
    outside.write_text("secret\n", encoding="utf-8")
    _write(tmp_path / "runner.py", "print('ok')\n")
    spec = tmp_path / "gauntlet.toml"
    _write(
        spec,
        f"""
[experiment]
id = "path-escape"
require_same_commit = false
[freeze]
inputs = ["../{outside.name}"]
[run]
mode = "subprocess"
command = {_command("runner.py")}
outputs = []
""".strip()
        + "\n",
    )
    with pytest.raises(ValueError, match="path escapes experiment root"):
        create_freeze(spec)
