from __future__ import annotations

import numpy as np
import pytest
import torch

from wildflower0.core import AppendOnlyMemory, NurseryWorld, SensorEvent, WildflowerSeed, assert_numeric_payload
from wildflower0.sim import collect_pairs, rollout_error, set_seed, stable_hash


def test_world_replay_is_deterministic() -> None:
    a = collect_pairs(123, 30, (0, 1, 2, 3))
    b = collect_pairs(123, 30, (0, 1, 2, 3))
    for pa, pb in zip(a, b, strict=True):
        ea, na = pa.current, pa.nxt
        eb, nb = pb.current, pb.nxt
        assert pa.identity == pb.identity
        assert ea.tick == eb.tick and ea.action == eb.action
        assert np.array_equal(ea.frame, eb.frame)
        assert np.array_equal(ea.audio, eb.audio)
        assert np.array_equal(na.frame, nb.frame)
        assert np.array_equal(na.audio, nb.audio)


def test_memory_hash_chain_detects_tamper() -> None:
    world = NurseryWorld(4)
    mem = AppendOnlyMemory(active_limit=4)
    event = world.observe(0)
    for action in (1, 2, 3, 4, 0, 1):
        event = SensorEvent(event.tick, event.frame, event.audio, action)
        mem.append(event)
        event = world.step(action)
    assert mem.verify()
    assert len(mem.active()) == 4
    # Internal tamper is deliberate fault injection.
    records = mem._records  # noqa: SLF001 - fault injection test
    records[2]["action"] = 4
    assert not mem.verify()


def test_core_rejects_string_payload() -> None:
    assert_numeric_payload([1, 2.0, np.array([1.0])])
    with pytest.raises(TypeError):
        assert_numeric_payload([1, "reason in prose"])


def test_bad_sensor_shapes_fail_closed() -> None:
    with pytest.raises(ValueError):
        SensorEvent(0, np.zeros((3, 5, 5), np.float32), np.zeros(64, np.float32), 0).validate()


def test_model_forward_is_finite() -> None:
    set_seed(9)
    pairs = collect_pairs(9, 16, (0, 1, 2, 3))
    frames = torch.tensor(np.stack([p.current.frame for p in pairs]))
    audio = torch.tensor(np.stack([p.current.audio for p in pairs]))
    actions = torch.tensor([p.current.action for p in pairs])
    model = WildflowerSeed()
    zv = model.vision(frames)
    za = model.audio(audio)
    pred = model.dynamics(zv, actions)
    assert torch.isfinite(zv).all() and torch.isfinite(za).all() and torch.isfinite(pred).all()
    assert zv.shape == pred.shape == (16, 32)
    assert za.shape == (16, 12)


def test_rollout_validates_horizon() -> None:
    model = WildflowerSeed()
    pairs = collect_pairs(1, 20, (0, 1))
    with pytest.raises(ValueError):
        rollout_error(model, pairs, 0)


def test_report_hash_stable_for_key_order() -> None:
    a = {"x": 1, "nested": {"a": 2, "b": 3}}
    b = {"nested": {"b": 3, "a": 2}, "x": 1}
    assert stable_hash(a) == stable_hash(b)


def test_weighted_frame_error_penalizes_blank_foreground() -> None:
    from wildflower0.core import weighted_frame_mse
    target = torch.zeros((1, 3, 12, 12))
    target[0, 0, 5, 5] = 1.0
    blank = torch.zeros_like(target)
    near = target.clone()
    near[0, 0, 5, 5] = 0.8
    assert weighted_frame_mse(near, target) < weighted_frame_mse(blank, target)


def test_pixel_variant_forward_shape_and_finite() -> None:
    from wildflower0.variants import PixelDynamics
    model = PixelDynamics()
    frame = torch.zeros((2, 3, 12, 12))
    action = torch.tensor([1, 4])
    out = model(frame, action)
    assert out.shape == frame.shape
    assert torch.isfinite(out).all()
    assert bool((out >= 0).all()) and bool((out <= 1).all())
