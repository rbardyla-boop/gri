from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from .core import weighted_frame_mse
from .sim import EvalPair


class RecurrentWorldModel(nn.Module):
    """Observation-corrected recurrent state with a separate open-loop imagination transition."""

    latent_dim = 48
    state_dim = 64

    def __init__(self) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 16, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(16, 24, 3, stride=2, padding=1),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(24 * 6 * 6, self.latent_dim),
            nn.Tanh(),
        )
        self.obs_to_state = nn.Linear(self.latent_dim, self.state_dim)
        self.action_embedding = nn.Embedding(5, 16)
        self.transition = nn.GRUCell(16, self.state_dim)
        self.corrector = nn.GRUCell(self.latent_dim, self.state_dim)
        self.decoder = nn.Sequential(
            nn.Linear(self.state_dim, 192),
            nn.SiLU(),
            nn.Linear(192, 3 * 12 * 12),
            nn.Sigmoid(),
        )
        self.latent_head = nn.Linear(self.state_dim, self.latent_dim)
        self.error_head = nn.Sequential(
            nn.Linear(self.state_dim, 32),
            nn.SiLU(),
            nn.Linear(32, 1),
            nn.Softplus(),
        )

    def state_from_observation(self, frame: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.obs_to_state(self.encoder(frame)))

    def imagine_step(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        return self.transition(self.action_embedding(action.long()), state)

    def correct(self, predicted_state: torch.Tensor, observed_frame: torch.Tensor) -> torch.Tensor:
        return self.corrector(self.encoder(observed_frame), predicted_state)

    def decode(self, state: torch.Tensor) -> torch.Tensor:
        return self.decoder(state).reshape(-1, 3, 12, 12)

    def predicted_error(self, state: torch.Tensor) -> torch.Tensor:
        return self.error_head(state).squeeze(-1)


@dataclass(frozen=True)
class SequenceBatch:
    frames: torch.Tensor
    actions: torch.Tensor
    targets: torch.Tensor


def sequence_batch(pairs: list[EvalPair], starts: np.ndarray, horizon: int) -> SequenceBatch:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    frames = []
    actions = []
    targets = []
    for s in starts.tolist():
        if s + horizon > len(pairs):
            raise ValueError("sequence exceeds pair list")
        frames.append(pairs[s].current.frame)
        actions.append([pairs[s + k].current.action for k in range(horizon)])
        targets.append([pairs[s + k].nxt.frame for k in range(horizon)])
    return SequenceBatch(
        frames=torch.tensor(np.stack(frames), dtype=torch.float32),
        actions=torch.tensor(np.asarray(actions), dtype=torch.long),
        targets=torch.tensor(np.asarray(targets), dtype=torch.float32),
    )


def multihorizon_loss(model: RecurrentWorldModel, batch: SequenceBatch) -> torch.Tensor:
    state = model.state_from_observation(batch.frames)
    total = torch.zeros((), dtype=torch.float32)
    horizon = batch.actions.shape[1]
    for k in range(horizon):
        state = model.imagine_step(state, batch.actions[:, k])
        decoded = model.decode(state)
        target = batch.targets[:, k]
        pixel = weighted_frame_mse(decoded, target)
        with torch.no_grad():
            target_latent = model.encoder(target)
        latent = F.smooth_l1_loss(model.latent_head(state), target_latent)
        per_item = ((decoded - target).square().flatten(1)).mean(dim=1).detach()
        calibration = F.smooth_l1_loss(model.predicted_error(state), per_item)
        step_weight = 1.0 + 0.15 * k
        total = total + step_weight * (pixel + 0.35 * latent + 0.05 * calibration)
    return total / horizon


def train_recurrent(
    model: RecurrentWorldModel,
    pairs: list[EvalPair],
    steps: int,
    seed: int,
    horizon: int = 8,
    batch_size: int = 24,
) -> None:
    if len(pairs) <= horizon + batch_size:
        raise ValueError("not enough sequence data")
    rng = np.random.default_rng(seed)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    max_start = len(pairs) - horizon
    model.train()
    for _ in range(steps):
        starts = rng.choice(max_start, size=batch_size, replace=False)
        batch = sequence_batch(pairs, starts, horizon)
        loss = multihorizon_loss(model, batch)
        if not torch.isfinite(loss):
            raise FloatingPointError("non-finite recurrent loss")
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()


def rollout_recurrent(model: RecurrentWorldModel, pairs: list[EvalPair], horizon: int) -> float:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    errors: list[float] = []
    model.eval()
    with torch.no_grad():
        stride = max(horizon, 4)
        for start in range(0, len(pairs) - horizon, stride):
            frame = torch.tensor(pairs[start].current.frame[None], dtype=torch.float32)
            state = model.state_from_observation(frame)
            for k in range(horizon):
                action = torch.tensor([pairs[start + k].current.action], dtype=torch.long)
                state = model.imagine_step(state, action)
            target = torch.tensor(pairs[start + horizon - 1].nxt.frame[None], dtype=torch.float32)
            errors.append(float(weighted_frame_mse(model.decode(state), target)))
    return float(np.mean(errors)) if errors else float("inf")


def online_corrected_error(model: RecurrentWorldModel, pairs: list[EvalPair]) -> float:
    """Prediction is scored before the next observation corrects state."""
    if not pairs:
        return float("inf")
    model.eval()
    errors: list[float] = []
    with torch.no_grad():
        state = model.state_from_observation(
            torch.tensor(pairs[0].current.frame[None], dtype=torch.float32)
        )
        for pair in pairs:
            action = torch.tensor([pair.current.action], dtype=torch.long)
            predicted = model.imagine_step(state, action)
            target = torch.tensor(pair.nxt.frame[None], dtype=torch.float32)
            errors.append(float(weighted_frame_mse(model.decode(predicted), target)))
            state = model.correct(predicted, target)
    return float(np.mean(errors))


def kinematic_baseline_rollout(pairs: list[EvalPair], horizon: int) -> float:
    """Transparent hostile control: shift the observed frame according to known action semantics."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    errors: list[float] = []
    stride = max(horizon, 4)
    for start in range(0, len(pairs) - horizon, stride):
        pred = torch.tensor(pairs[start].current.frame[None], dtype=torch.float32)
        for k in range(horizon):
            action = pairs[start + k].current.action
            dx, dy = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))[action]
            shifted = torch.zeros_like(pred)
            src_y0 = max(0, -dy)
            src_y1 = min(12, 12 - dy)
            src_x0 = max(0, -dx)
            src_x1 = min(12, 12 - dx)
            dst_y0 = max(0, dy)
            dst_y1 = dst_y0 + (src_y1 - src_y0)
            dst_x0 = max(0, dx)
            dst_x1 = dst_x0 + (src_x1 - src_x0)
            shifted[:, :, dst_y0:dst_y1, dst_x0:dst_x1] = pred[
                :, :, src_y0:src_y1, src_x0:src_x1
            ]
            pred = shifted
        target = torch.tensor(pairs[start + horizon - 1].nxt.frame[None], dtype=torch.float32)
        errors.append(float(weighted_frame_mse(pred, target)))
    return float(np.mean(errors)) if errors else float("inf")
