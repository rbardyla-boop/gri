from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import random
from typing import Sequence

import numpy as np
import torch
import torch.nn.functional as F

from .core import (
    AppendOnlyMemory, NurseryWorld, SensorEvent, WildflowerSeed, weighted_frame_mse
)


@dataclass(frozen=True)
class EvalPair:
    """The identity is evaluator-only metadata and is never passed to the learner."""

    current: SensorEvent
    nxt: SensorEvent
    identity: int


@dataclass(frozen=True)
class SeedMetrics:
    seed: int
    grounding_top1: float
    one_step_error: float
    one_step_copy_baseline: float
    one_step_model_vs_copy_ratio: float
    rollout_error_h1: float
    rollout_error_h4: float
    rollout_error_h8: float
    rollout_error_h16: float
    rollout_error_h32: float
    rollout_growth_16_over_1: float
    rollout_growth_32_over_1: float
    phase_a_before_b: float
    phase_a_after_b: float
    forgetting_delta: float
    finite: bool
    memory_integrity: bool
    active_memory_bounded: bool


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def collect_pairs(
    seed: int, n: int, identities: tuple[int, ...], switch_period: int | None = 19
) -> list[EvalPair]:
    world = NurseryWorld(seed, identities=identities, switch_period=switch_period)
    pairs: list[EvalPair] = []
    current = world.observe(0)
    for _ in range(n):
        action = int(world.rng.integers(0, 5))
        identity = int(world.identity)
        nxt = world.step(action)
        current = SensorEvent(current.tick, current.frame, current.audio, action)
        pairs.append(EvalPair(current, nxt, identity))
        current = nxt
    return pairs


def stack_batch(batch: Sequence[EvalPair]) -> tuple[torch.Tensor, ...]:
    frames = torch.tensor(np.stack([p.current.frame for p in batch]), dtype=torch.float32)
    audio = torch.tensor(np.stack([p.current.audio for p in batch]), dtype=torch.float32)
    actions = torch.tensor([p.current.action for p in batch], dtype=torch.long)
    next_frames = torch.tensor(np.stack([p.nxt.frame for p in batch]), dtype=torch.float32)
    return frames, audio, actions, next_frames


def train(model: WildflowerSeed, pairs: list[EvalPair], steps: int, seed: int) -> None:
    if len(pairs) < 32:
        raise ValueError("not enough pairs")
    rng = np.random.default_rng(seed)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    model.train()
    for _ in range(steps):
        idx = rng.choice(len(pairs), size=32, replace=False)
        batch = [pairs[int(i)] for i in idx]
        frames, audio, actions, next_frames = stack_batch(batch)
        loss = (
            model.grounding_loss(frames, audio)
            + 1.5 * model.reconstruction_loss(frames)
            + 1.2 * model.transition_loss(frames, actions, next_frames)
        )
        if not torch.isfinite(loss):
            raise FloatingPointError("non-finite training loss")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        opt.step()


def _prototype_accuracy(z_query: torch.Tensor, z_proto: torch.Tensor, labels: np.ndarray) -> float:
    unique = sorted(set(int(x) for x in labels.tolist()))
    prototypes = []
    for identity in unique:
        mask = torch.tensor(labels == identity)
        prototypes.append(F.normalize(z_proto[mask].mean(dim=0), dim=0))
    bank = torch.stack(prototypes)
    pred_idx = (z_query @ bank.T).argmax(dim=1).cpu().numpy()
    pred = np.array([unique[int(i)] for i in pred_idx], dtype=np.int64)
    return float((pred == labels).mean())


def grounding_accuracy(model: WildflowerSeed, pairs: list[EvalPair]) -> float:
    """Evaluator-only identity probes; identity never appears in training/model input."""
    model.eval()
    with torch.no_grad():
        frames, audio, _, _ = stack_batch(pairs)
        zv = model.vision.semantic(model.vision(frames))
        za = model.audio(audio)
        labels = np.array([p.identity for p in pairs], dtype=np.int64)
        va = _prototype_accuracy(zv, za, labels)
        av = _prototype_accuracy(za, zv, labels)
        return 0.5 * (va + av)


def transition_error(model: WildflowerSeed, pairs: list[EvalPair]) -> float:
    model.eval()
    with torch.no_grad():
        frames, _, actions, next_frames = stack_batch(pairs)
        z = model.vision(frames)
        pred = model.dynamics(z, actions)
        decoded = model.decoder(pred)
        return float(weighted_frame_mse(decoded, next_frames))


def copy_baseline_error(pairs: list[EvalPair]) -> float:
    frames, _, _, next_frames = stack_batch(pairs)
    return float(weighted_frame_mse(frames, next_frames))


def rollout_error(model: WildflowerSeed, pairs: list[EvalPair], horizon: int) -> float:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    model.eval()
    errors: list[float] = []
    with torch.no_grad():
        for start in range(0, len(pairs) - horizon, max(horizon, 4)):
            z = model.vision(torch.tensor(pairs[start].current.frame[None], dtype=torch.float32))
            valid = True
            for offset in range(horizon):
                event = pairs[start + offset].current
                action = torch.tensor([event.action], dtype=torch.long)
                z = model.dynamics(z, action)
                if not torch.isfinite(z).all():
                    valid = False
                    break
            if not valid:
                errors.append(float("inf"))
                continue
            target_event = pairs[start + horizon - 1].nxt
            decoded = model.decoder(z)
            target = torch.tensor(target_event.frame[None], dtype=torch.float32)
            errors.append(float(weighted_frame_mse(decoded, target).item()))
    return float(np.mean(errors)) if errors else float("inf")


def parameter_finite(model: WildflowerSeed) -> bool:
    return all(bool(torch.isfinite(p).all()) for p in model.parameters())


def memory_stress(seed: int, count: int = 10_000, active_limit: int = 32) -> tuple[bool, bool]:
    world = NurseryWorld(seed)
    mem = AppendOnlyMemory(active_limit=active_limit)
    event = world.observe(0)
    for i in range(count):
        action = i % 5
        event = SensorEvent(event.tick, event.frame, event.audio, action)
        mem.append(event)
        event = world.step(action)
    return mem.verify(), len(mem.active()) <= active_limit and len(mem) == count


def run_seed(seed: int, train_steps: int = 120) -> SeedMetrics:
    set_seed(seed)
    phase_a_train = collect_pairs(seed * 101 + 1, 224, (0, 1))
    phase_a_test = collect_pairs(seed * 101 + 2, 128, (0, 1))
    phase_b_train = collect_pairs(seed * 101 + 3, 224, (2, 3))
    mixed_test = collect_pairs(seed * 101 + 4, 192, (0, 1, 2, 3))

    model = WildflowerSeed()
    train(model, phase_a_train, train_steps, seed * 17 + 5)
    phase_a_before = grounding_accuracy(model, phase_a_test)

    train(model, phase_b_train, train_steps, seed * 17 + 6)
    phase_a_after = grounding_accuracy(model, phase_a_test)

    mixed_train = collect_pairs(seed * 101 + 5, 224, (0, 1, 2, 3))
    train(model, mixed_train, max(train_steps // 2, 1), seed * 17 + 7)

    top1 = grounding_accuracy(model, mixed_test)
    one = transition_error(model, mixed_test)
    copy_one = copy_baseline_error(mixed_test)
    model_copy_ratio = one / max(copy_one, 1e-8)
    horizons = {h: rollout_error(model, mixed_test, h) for h in (1, 4, 8, 16, 32)}
    growth16 = horizons[16] / max(horizons[1], 1e-8)
    growth32 = horizons[32] / max(horizons[1], 1e-8)
    integrity, bounded = memory_stress(seed)

    return SeedMetrics(
        seed=seed,
        grounding_top1=top1,
        one_step_error=one,
        one_step_copy_baseline=copy_one,
        one_step_model_vs_copy_ratio=model_copy_ratio,
        rollout_error_h1=horizons[1],
        rollout_error_h4=horizons[4],
        rollout_error_h8=horizons[8],
        rollout_error_h16=horizons[16],
        rollout_error_h32=horizons[32],
        rollout_growth_16_over_1=growth16,
        rollout_growth_32_over_1=growth32,
        phase_a_before_b=phase_a_before,
        phase_a_after_b=phase_a_after,
        forgetting_delta=phase_a_before - phase_a_after,
        finite=parameter_finite(model),
        memory_integrity=integrity,
        active_memory_bounded=bounded,
    )


def aggregate(metrics: list[SeedMetrics]) -> dict[str, object]:
    if not metrics:
        raise ValueError("metrics cannot be empty")
    numeric = [
        k for k, v in asdict(metrics[0]).items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "seed"
    ]
    out: dict[str, object] = {"seeds": [m.seed for m in metrics]}
    for key in numeric:
        vals = np.array([float(getattr(m, key)) for m in metrics], dtype=np.float64)
        out[key] = {"mean": float(vals.mean()), "max": float(vals.max()), "min": float(vals.min())}
    out["all_finite"] = all(m.finite for m in metrics)
    out["all_memory_integrity"] = all(m.memory_integrity for m in metrics)
    out["all_active_memory_bounded"] = all(m.active_memory_bounded for m in metrics)

    out["engineering_gates"] = {
        "finite": bool(out["all_finite"]),
        "memory_integrity": bool(out["all_memory_integrity"]),
        "bounded_active_memory": bool(out["all_active_memory_bounded"]),
        "rollout_nonexplosive_h16": max(m.rollout_growth_16_over_1 for m in metrics) < 12.0,
        "rollout_nonexplosive_h32": max(m.rollout_growth_32_over_1 for m in metrics) < 20.0,
        "rollout_absolute_h32": max(m.rollout_error_h32 for m in metrics) < 1.5,
        "forgetting_not_catastrophic": max(m.forgetting_delta for m in metrics) < 0.40,
        "one_step_beats_copy_baseline": max(m.one_step_model_vs_copy_ratio for m in metrics) < 1.0,
    }
    return out


def stable_hash(data: object) -> str:
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def train_dynamics_frozen(
    model: WildflowerSeed, pairs: list[EvalPair], steps: int, seed: int
) -> None:
    """Engineering variant: stop representation drift while fitting action dynamics."""
    rng = np.random.default_rng(seed)
    frozen = [model.vision, model.audio, model.decoder]
    old_flags = [[p.requires_grad for p in module.parameters()] for module in frozen]
    for module in frozen:
        for p in module.parameters():
            p.requires_grad_(False)
    opt = torch.optim.AdamW(model.dynamics.parameters(), lr=2.5e-3, weight_decay=1e-4)
    model.train()
    try:
        for _ in range(steps):
            idx = rng.choice(len(pairs), size=32, replace=False)
            batch = [pairs[int(i)] for i in idx]
            frames, _, actions, next_frames = stack_batch(batch)
            loss = model.transition_loss(frames, actions, next_frames)
            if not torch.isfinite(loss):
                raise FloatingPointError("non-finite frozen-dynamics loss")
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.dynamics.parameters(), max_norm=1.0)
            opt.step()
    finally:
        for module, flags in zip(frozen, old_flags, strict=True):
            for p, flag in zip(module.parameters(), flags, strict=True):
                p.requires_grad_(flag)


def run_seed_repaired(
    seed: int,
    train_steps: int = 140,
    replay_count: int = 64,
    dynamics_steps: int = 160,
) -> SeedMetrics:
    """Candidate repair: bounded episodic replay + representation-stable dynamics fitting."""
    set_seed(seed)
    phase_a_train = collect_pairs(seed * 101 + 1, 224, (0, 1))
    phase_a_test = collect_pairs(seed * 101 + 2, 128, (0, 1))
    phase_b_train = collect_pairs(seed * 101 + 3, 224, (2, 3))
    mixed_test = collect_pairs(seed * 101 + 4, 192, (0, 1, 2, 3))

    model = WildflowerSeed()
    train(model, phase_a_train, train_steps, seed * 17 + 5)
    phase_a_before = grounding_accuracy(model, phase_a_test)

    replay_rng = np.random.default_rng(seed * 19 + 11)
    replay_idx = replay_rng.choice(len(phase_a_train), size=min(replay_count, len(phase_a_train)), replace=False)
    phase_b_with_replay = phase_b_train + [phase_a_train[int(i)] for i in replay_idx]
    train(model, phase_b_with_replay, train_steps, seed * 17 + 6)
    phase_a_after = grounding_accuracy(model, phase_a_test)

    mixed_train = collect_pairs(seed * 101 + 5, 224, (0, 1, 2, 3))
    train(model, mixed_train, max(train_steps // 2, 1), seed * 17 + 7)
    train_dynamics_frozen(model, mixed_train, dynamics_steps, seed * 17 + 8)

    top1 = grounding_accuracy(model, mixed_test)
    one = transition_error(model, mixed_test)
    copy_one = copy_baseline_error(mixed_test)
    model_copy_ratio = one / max(copy_one, 1e-8)
    horizons = {h: rollout_error(model, mixed_test, h) for h in (1, 4, 8, 16, 32)}
    integrity, bounded = memory_stress(seed)

    return SeedMetrics(
        seed=seed,
        grounding_top1=top1,
        one_step_error=one,
        one_step_copy_baseline=copy_one,
        one_step_model_vs_copy_ratio=model_copy_ratio,
        rollout_error_h1=horizons[1],
        rollout_error_h4=horizons[4],
        rollout_error_h8=horizons[8],
        rollout_error_h16=horizons[16],
        rollout_error_h32=horizons[32],
        rollout_growth_16_over_1=horizons[16] / max(horizons[1], 1e-8),
        rollout_growth_32_over_1=horizons[32] / max(horizons[1], 1e-8),
        phase_a_before_b=phase_a_before,
        phase_a_after_b=phase_a_after,
        forgetting_delta=phase_a_before - phase_a_after,
        finite=parameter_finite(model),
        memory_integrity=integrity,
        active_memory_bounded=bounded,
    )
