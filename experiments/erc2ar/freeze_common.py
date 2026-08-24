from __future__ import annotations

CRITICAL_FILES = (
    "experiments/erc1/compiler.py",
    "experiments/erc2ar/contract.py",
    "experiments/erc2ar/stage_live.py",
    "experiments/erc2ar/baseline.py",
    "experiments/erc2ar/score_live.py",
    "experiments/erc2ar/test_pre_live.py",
    "experiments/erc2ar/freeze_common.py",
    "experiments/erc2ar/freeze_candidate.py",
    "experiments/erc2ar/verify_freeze.py",
    ".github/workflows/erc2ar-pre-live.yml",
    ".github/workflows/erc2ar-live.yml",
)

RUNTIME = {
    "python": "3.11",
    "numpy": "2.0.2",
    "pandas": "2.2.2",
    "pyarrow": "17.0.0",
}
