from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_terminal_verdict_matches_canonical_artifacts() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/verify_project_terminal_verdict.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["pass"] is True
    assert receipt["failures"] == []

