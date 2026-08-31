"""Lazy access to the frozen historical predictor and Nursery world."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any

LEGACY_ROOT = Path(__file__).resolve().parents[1] / "wildflower0_prelock"


def load_legacy() -> dict[str, Any]:
    """Load only frozen numeric components; no epistemic code is imported."""

    root = str(LEGACY_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    model = importlib.import_module("probe_innovation_model")
    nursery = importlib.import_module("wildflower0.nursery1")
    return {
        "InnovationModel": model.InnovationModel,
        "pre": model.pre,
        "train": model.train,
        "collect_pairs": nursery.collect_pairs,
        "select_balanced_episode_seeds": nursery.select_balanced_episode_seeds,
        "set_seed": nursery.set_seed,
        "MODES": nursery.MODES,
    }
