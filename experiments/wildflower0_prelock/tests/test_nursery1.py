from __future__ import annotations

import numpy as np
import pytest
import torch

from wildflower0.nursery1 import (
    DominanceResidual,
    Nursery1Event,
    Nursery1World,
    collect_pairs,
    extract_object_state,
    learner_projection,
    replace_evaluator_metadata,
    select_balanced_episode_seeds,
    state_mae,
    velocity_baseline_mae,
)


def test_world_replay_is_deterministic() -> None:
    a = collect_pairs(12345, 80)
    b = collect_pairs(12345, 80)
    assert len(a) == len(b)
    for left, right in zip(a, b, strict=True):
        assert left.mode == right.mode
        assert left.rule_event == right.rule_event
        assert left.collision == right.collision
        assert left.boundary == right.boundary
        assert np.array_equal(left.current.frame, right.current.frame)
        assert np.array_equal(left.current.audio, right.current.audio)
        assert np.array_equal(left.nxt.frame, right.nxt.frame)


def test_balanced_selector_is_exact_and_deterministic() -> None:
    first = select_balanced_episode_seeds(777, 2, start=100)
    second = select_balanced_episode_seeds(777, 2, start=100)
    assert first == second
    assert set(first) == {0, 1, 2}
    assert all(len(first[mode]) == 2 for mode in first)
    for mode, seeds in first.items():
        assert all(Nursery1World(seed).mode == mode for seed in seeds)


def test_evaluator_mode_is_not_in_learner_projection() -> None:
    pairs = collect_pairs(998, 12)
    altered = [replace_evaluator_metadata(pair, (pair.mode + 1) % 3) for pair in pairs]
    original_projection = learner_projection(pairs)
    altered_projection = learner_projection(altered)
    for original, changed in zip(original_projection, altered_projection, strict=True):
        assert np.array_equal(original, changed)


def test_object_state_is_numeric_and_finite() -> None:
    pair = collect_pairs(12, 1)[0]
    state = extract_object_state(pair.current.frame)
    assert state.shape == (6,)
    assert state.dtype == np.float32
    assert np.isfinite(state).all()


def test_model_step_is_finite_and_shaped() -> None:
    model = DominanceResidual()
    state = torch.zeros((3, 6))
    velocity = torch.zeros((3, 6))
    action = torch.tensor([0, 1, 4])
    hidden = torch.zeros((3, 64))
    prediction, next_hidden, residual, gate = model.step(state, velocity, action, hidden)
    assert prediction.shape == (3, 6)
    assert next_hidden.shape == (3, 64)
    assert residual.shape == gate.shape == (3, 6)
    assert torch.isfinite(prediction).all()
    assert torch.isfinite(next_hidden).all()
    assert torch.isfinite(residual).all()
    assert torch.isfinite(gate).all()


def test_smoke_metrics_are_finite() -> None:
    pairs = collect_pairs(321, 80)
    model = DominanceResidual()
    candidate = state_mae(model, pairs, 1, burn=5)
    baseline = velocity_baseline_mae(pairs, 1, burn=5)
    assert np.isfinite(candidate)
    assert np.isfinite(baseline)
    assert baseline >= 0.0


def test_bad_event_fails_closed() -> None:
    with pytest.raises(ValueError):
        Nursery1Event(0, np.zeros((3, 10, 10), np.float32), np.zeros(64, np.float32), 0).validate()
