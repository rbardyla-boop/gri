from __future__ import annotations

import torch

from experiments.wildflower_predictive_authority_0_1.legacy import load_legacy
from experiments.wildflower_predictive_authority_0_1.rollout import generate_origin_trace
from experiments.wildflower_predictive_authority_0_1.trace import origin_trace_to_dict


class _DeterministicModel:
    def step(self, state, velocity, action, innovation, hidden):
        del action, innovation
        correction = 0.02 * torch.tanh(velocity)
        prediction = (state + velocity + correction).clamp(-1.0, 1.0)
        authority = torch.full((state.shape[0], 1), 0.5)
        return prediction, hidden, authority, correction


def test_origin_trace_contains_explicit_recursive_components() -> None:
    legacy = load_legacy()
    pairs = legacy["collect_pairs"](424242, 60)
    trace = generate_origin_trace(
        _DeterministicModel(), pairs, mode=pairs[0].mode, episode_seed=424242, index=14
    )
    assert set(trace.rollout_horizons) == {1, 8, 32}
    assert len(trace.rollout_horizons[8]) == 8
    assert len(trace.rollout_horizons[32]) == 32
    row = trace.rollout_horizons[8][0]
    assert row.null_prediction != row.learned_only_prediction
    payload = origin_trace_to_dict(trace)
    assert "learned_only_prediction" in payload["rollout_horizons"]["8"][0]
    assert "gated_prediction" in payload["rollout_horizons"]["8"][0]


def test_origin_trace_is_deterministic() -> None:
    legacy = load_legacy()
    pairs = legacy["collect_pairs"](424242, 60)
    first = origin_trace_to_dict(
        generate_origin_trace(_DeterministicModel(), pairs, 0, 424242, 14)
    )
    second = origin_trace_to_dict(
        generate_origin_trace(_DeterministicModel(), pairs, 0, 424242, 14)
    )
    assert first == second
