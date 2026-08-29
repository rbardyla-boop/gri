from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

import probe_innovation_model
import qualify_authority190
from probe_innovation_model import InnovationModel
from wildflower0.nursery1 import collect_pairs, replace_evaluator_metadata


ROOT = Path(__file__).resolve().parents[1]
FROZEN_HASHES = {
    "probe_innovation_model.py": "97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1",
    "qualify_authority190.py": "13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_authority_sources_are_byte_locked() -> None:
    for name, expected in FROZEN_HASHES.items():
        assert _sha256(ROOT / name) == expected


def test_authority_config_is_frozen() -> None:
    assert qualify_authority190.THRESHOLD == 0.30
    assert qualify_authority190.WIDTH == 0.30
    assert qualify_authority190.DECAY == 0.998
    assert qualify_authority190.BURN == 12
    assert qualify_authority190.TRAIN_PER_MODE == 2
    assert qualify_authority190.TEST_PER_MODE == 2
    assert qualify_authority190.EPISODE_LENGTH == 420
    assert qualify_authority190.TRAIN_STEPS == 80


def test_training_path_does_not_read_evaluator_only_metadata() -> None:
    source = inspect.getsource(probe_innovation_model.train)
    for forbidden in (".mode", ".rule_event", ".collision", ".boundary"):
        assert forbidden not in source


def test_authority_model_projection_ignores_mode_metadata() -> None:
    pairs = collect_pairs(123456, 24)
    altered = [replace_evaluator_metadata(pair, (pair.mode + 1) % 3) for pair in pairs]
    original = probe_innovation_model.pre(pairs)
    changed = probe_innovation_model.pre(altered)
    for left, right in zip(original, changed, strict=True):
        assert np.array_equal(left, right)


def test_zero_innovation_cannot_bypass_velocity_authority(monkeypatch) -> None:
    count = 48
    x = np.linspace(-0.6, 0.6, count, dtype=np.float32)
    current = np.stack([x, x, x, x, x, x], axis=1)
    # Exactly constant velocity: historical innovation score is zero.
    step = current[1] - current[0]
    target = np.clip(current + step, -1.0, 1.0)
    actions = np.zeros(count, dtype=np.int64)

    monkeypatch.setattr(qualify_authority190, "pre", lambda pairs: (current, target, actions))

    class AdversarialModel:
        def eval(self) -> "AdversarialModel":
            return self

        def step(self, state, velocity, action, innovation, hidden):
            # Deliberately terrible model proposal. Authority=0 must block it.
            proposal = torch.full_like(state, -0.95)
            return proposal, hidden, torch.ones((state.shape[0], 1)), proposal

    pairs = [SimpleNamespace() for _ in range(count)]
    metrics = qualify_authority190.eval_authority(AdversarialModel(), pairs, 1)
    assert metrics["authority_mean"] == 0.0
    assert metrics["innovation_mean"] < qualify_authority190.THRESHOLD
    assert abs(metrics["model"] - metrics["baseline"]) < 1e-9


def test_authority_formula_is_convex_and_decays() -> None:
    base = torch.tensor([[0.2, -0.2]])
    model = torch.tensor([[0.8, -0.8]])
    for alpha in (0.0, 0.25, 0.5, 1.0):
        mixed = base + alpha * (model - base)
        lo = torch.minimum(base, model)
        hi = torch.maximum(base, model)
        assert bool((mixed >= lo).all()) and bool((mixed <= hi).all())
    assert 0.0 < qualify_authority190.DECAY < 1.0
