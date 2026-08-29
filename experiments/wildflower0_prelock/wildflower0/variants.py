from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import nn

from .core import weighted_frame_mse
from .sim import EvalPair, collect_pairs, set_seed, stack_batch, stable_hash


class PixelDynamics(nn.Module):
    """Transparent alternative: predict sensor-frame change directly from action."""

    def __init__(self) -> None:
        super().__init__()
        self.action_embedding = nn.Embedding(5, 8)
        self.net = nn.Sequential(
            nn.Conv2d(11, 32, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(32, 32, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(32, 3, 3, padding=1),
        )

    def forward(self, frame: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        embedded = self.action_embedding(action.long()).unsqueeze(-1).unsqueeze(-1)
        action_map = embedded.expand(-1, -1, 12, 12)
        delta = torch.tanh(self.net(torch.cat((frame, action_map), dim=1)))
        return (frame + 0.5 * delta).clamp(0.0, 1.0)


@dataclass(frozen=True)
class PixelProbeMetrics:
    seed: int
    one_step_model: float
    one_step_copy: float
    one_step_ratio: float
    h4: float
    h8: float
    h16: float
    h32: float
    growth_h32_over_h1: float
    finite: bool


def _train_pixel(model: PixelDynamics, pairs: list[EvalPair], steps: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    model.train()
    for _ in range(steps):
        idx = rng.choice(len(pairs), 32, replace=False)
        frames, _, actions, next_frames = stack_batch([pairs[int(i)] for i in idx])
        loss = weighted_frame_mse(model(frames, actions), next_frames)
        if not torch.isfinite(loss):
            raise FloatingPointError("non-finite pixel-dynamics loss")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()


def _rollout(model: PixelDynamics, pairs: list[EvalPair], horizon: int) -> float:
    errors: list[float] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(pairs) - horizon, max(horizon, 4)):
            frame = torch.tensor(pairs[start].current.frame[None], dtype=torch.float32)
            for offset in range(horizon):
                action = torch.tensor([pairs[start + offset].current.action], dtype=torch.long)
                frame = model(frame, action)
            target = torch.tensor(pairs[start + horizon - 1].nxt.frame[None], dtype=torch.float32)
            errors.append(float(weighted_frame_mse(frame, target)))
    return float(np.mean(errors))


def run_pixel_probe(seed: int, steps: int = 220) -> PixelProbeMetrics:
    set_seed(seed)
    train_pairs = collect_pairs(seed * 101 + 5, 320, (0, 1, 2, 3))
    test_pairs = collect_pairs(seed * 101 + 4, 256, (0, 1, 2, 3))
    model = PixelDynamics()
    _train_pixel(model, train_pairs, steps, seed + 99)
    frames, _, actions, next_frames = stack_batch(test_pairs)
    with torch.no_grad():
        model_one = float(weighted_frame_mse(model(frames, actions), next_frames))
        copy_one = float(weighted_frame_mse(frames, next_frames))
    horizons = {h: _rollout(model, test_pairs, h) for h in (1, 4, 8, 16, 32)}
    return PixelProbeMetrics(
        seed=seed,
        one_step_model=model_one,
        one_step_copy=copy_one,
        one_step_ratio=model_one / max(copy_one, 1e-8),
        h4=horizons[4],
        h8=horizons[8],
        h16=horizons[16],
        h32=horizons[32],
        growth_h32_over_h1=horizons[32] / max(horizons[1], 1e-8),
        finite=all(bool(torch.isfinite(p).all()) for p in model.parameters()),
    )


def aggregate_pixel_probe(metrics: list[PixelProbeMetrics]) -> dict[str, object]:
    result: dict[str, object] = {"seeds": [m.seed for m in metrics]}
    for key in ("one_step_model", "one_step_copy", "one_step_ratio", "h4", "h8", "h16", "h32", "growth_h32_over_h1"):
        vals = np.array([float(getattr(m, key)) for m in metrics])
        result[key] = {"mean": float(vals.mean()), "min": float(vals.min()), "max": float(vals.max())}
    result["all_finite"] = all(m.finite for m in metrics)
    result["engineering_gates"] = {
        "finite": bool(result["all_finite"]),
        "one_step_beats_copy": max(m.one_step_ratio for m in metrics) < 1.0,
        "open_loop_h32_growth_under_10x": max(m.growth_h32_over_h1 for m in metrics) < 10.0,
    }
    receipt_payload = {
        "metrics": [asdict(m) for m in metrics],
        "aggregate_without_receipt": result,
    }
    result["receipt_sha256"] = stable_hash(receipt_payload)
    return result
