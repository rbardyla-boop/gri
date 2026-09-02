#!/usr/bin/env python3
"""Run HEART01 locally. No GPU, no network, no APIs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.heart01.scoring import format_scoreboard, run_heart


def main() -> int:
    result = run_heart()
    print(format_scoreboard(result))
    board = result["board"]
    if not all(board["F"].values()):
        return 1
    for name in "ABCDE":
        if all(board[name].values()):
            print(f"ABLATION {name} unexpectedly passed all six")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
