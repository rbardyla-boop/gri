from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F


@dataclass(frozen=True)
class SensorEvent:
    tick: int
    frame: np.ndarray
    audio: np.ndarray
    action: int

    def validate(self) -> None:
        if self.tick < 0:
            raise ValueError("tick must be non-negative")
        if self.frame.shape != (3, 12, 12):
            raise ValueError(f"unexpected frame shape {self.frame.shape}")
        if self.audio.shape != (64,):
            raise ValueError(f"unexpected audio shape {self.audio.shape}")
        if not 0 <= self.action < 5:
            raise ValueError("action out of range")
        if not np.isfinite(self.frame).all() or not np.isfinite(self.audio).all():
            raise ValueError("non-finite sensor value")


class NurseryWorld:
    """Small numeric world. Learner inputs are pixels, waveform samples, and action IDs only."""

    def __init__(
        self,
        seed: int,
        identities: tuple[int, ...] = (0, 1, 2, 3),
        switch_period: int | None = 19,
    ) -> None:
        if not identities:
            raise ValueError("identities cannot be empty")
        if switch_period is not None and switch_period <= 0:
            raise ValueError("switch_period must be positive or None")
        self.rng = np.random.default_rng(seed)
        self.identities = identities
        self.tick = 0
        self.switch_period = switch_period
        self.identity = int(self.rng.choice(identities))
        self.x = int(self.rng.integers(1, 10))
        self.y = int(self.rng.integers(1, 10))

    @staticmethod
    def _wave(identity: int, phase: float, noise: np.ndarray) -> np.ndarray:
        t = np.linspace(0.0, 1.0, 64, endpoint=False, dtype=np.float32)
        f1 = 2.0 + identity * 1.5
        f2 = 7.0 + identity * 0.75
        wave = np.sin(2 * np.pi * f1 * t + phase) + 0.35 * np.sin(2 * np.pi * f2 * t)
        wave = wave.astype(np.float32) + noise.astype(np.float32)
        return wave / (np.linalg.norm(wave) + 1e-6)

    def _frame(self) -> np.ndarray:
        frame = np.zeros((3, 12, 12), dtype=np.float32)
        channel = self.identity % 3
        intensity = 0.55 + 0.15 * self.identity
        pattern = self.identity % 4
        if pattern == 0:
            coords = [(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)]
        elif pattern == 1:
            coords = [(0, 0), (0, 2), (2, 0), (2, 2), (1, 1)]
        elif pattern == 2:
            coords = [(0, 0), (1, 1), (2, 2), (0, 2)]
        else:
            coords = [(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)]
        for dy, dx in coords:
            frame[channel, self.y + dy - 1, self.x + dx - 1] = intensity
        frame += self.rng.normal(0.0, 0.015, frame.shape).astype(np.float32)
        return np.clip(frame, 0.0, 1.0)

    def observe(self, action: int) -> SensorEvent:
        phase = float(self.rng.uniform(-math.pi, math.pi))
        noise = self.rng.normal(0.0, 0.025, 64)
        event = SensorEvent(self.tick, self._frame(), self._wave(self.identity, phase, noise), action)
        event.validate()
        return event

    def step(self, action: int) -> SensorEvent:
        if not 0 <= action < 5:
            raise ValueError("action out of range")
        dx, dy = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))[action]
        self.x = int(np.clip(self.x + dx, 1, 10))
        self.y = int(np.clip(self.y + dy, 1, 10))
        self.tick += 1
        if self.switch_period and self.tick % self.switch_period == 0:
            self.identity = int(self.rng.choice(self.identities))
        return self.observe(action)


class AppendOnlyMemory:
    """Unbounded episode ledger with bounded active view and hash-chain integrity."""

    def __init__(self, active_limit: int = 32) -> None:
        if active_limit <= 0:
            raise ValueError("active_limit must be positive")
        self.active_limit = active_limit
        self._records: list[dict[str, object]] = []
        self._head = "0" * 64

    @staticmethod
    def _digest_array(arr: np.ndarray) -> str:
        return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()

    def append(self, event: SensorEvent) -> str:
        event.validate()
        payload = {
            "tick": event.tick,
            "frame_sha": self._digest_array(event.frame),
            "audio_sha": self._digest_array(event.audio),
            "action": event.action,
            "prev": self._head,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        record_sha = hashlib.sha256(blob).hexdigest()
        payload["sha"] = record_sha
        self._records.append(payload)
        self._head = record_sha
        return record_sha

    def active(self) -> tuple[dict[str, object], ...]:
        return tuple(self._records[-self.active_limit :])

    def __len__(self) -> int:
        return len(self._records)

    def verify(self) -> bool:
        prev = "0" * 64
        for record in self._records:
            if record.get("prev") != prev:
                return False
            payload = {k: record[k] for k in ("tick", "frame_sha", "audio_sha", "action", "prev")}
            blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            expected = hashlib.sha256(blob).hexdigest()
            if record.get("sha") != expected:
                return False
            prev = expected
        return prev == self._head


class VisionEncoder(nn.Module):
    """Shared semantic subspace + private state subspace avoids modality/state conflict."""

    semantic_dim = 12
    state_dim = 20
    latent_dim = semantic_dim + state_dim

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 12, 3, padding=1),
            nn.SiLU(),
            nn.Conv2d(12, 16, 3, stride=2, padding=1),
            nn.SiLU(),
            nn.Flatten(),
            nn.Linear(16 * 6 * 6, self.latent_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        raw = self.net(x)
        sem = F.normalize(raw[:, : self.semantic_dim], dim=-1)
        state = torch.tanh(raw[:, self.semantic_dim :])
        return torch.cat((sem, state), dim=-1)

    @classmethod
    def semantic(cls, z: torch.Tensor) -> torch.Tensor:
        return z[:, : cls.semantic_dim]


class AudioEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(64, 96),
            nn.SiLU(),
            nn.Linear(96, VisionEncoder.semantic_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.net(x), dim=-1)


class VisionDecoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(VisionEncoder.latent_dim, 128),
            nn.SiLU(),
            nn.Linear(128, 3 * 12 * 12),
            nn.Sigmoid(),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        return self.net(z).reshape(-1, 3, 12, 12)


class Dynamics(nn.Module):
    def __init__(self, hidden_dim: int = 80) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(VisionEncoder.latent_dim + 5, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, VisionEncoder.latent_dim),
        )

    def forward(self, z: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        a = F.one_hot(action.long(), num_classes=5).float()
        raw = z + 0.25 * self.net(torch.cat((z, a), dim=-1))
        sem = F.normalize(raw[:, : VisionEncoder.semantic_dim], dim=-1)
        state = torch.tanh(raw[:, VisionEncoder.semantic_dim :])
        return torch.cat((sem, state), dim=-1)


def weighted_frame_mse(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Foreground-aware error; sparse background cannot make a blank prediction look good."""
    if pred.shape != target.shape:
        raise ValueError("frame tensors must have identical shape")
    weight = 1.0 + 24.0 * (target > 0.10).float()
    return (weight * (pred - target).square()).sum() / weight.sum()


class WildflowerSeed(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.vision = VisionEncoder()
        self.audio = AudioEncoder()
        self.decoder = VisionDecoder()
        self.dynamics = Dynamics()

    def grounding_loss(self, frames: torch.Tensor, audio: torch.Tensor) -> torch.Tensor:
        zv = VisionEncoder.semantic(self.vision(frames))
        za = self.audio(audio)
        align = 1.0 - (zv * za).sum(dim=-1).mean()

        def anti_collapse(z: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            centered = z - z.mean(dim=0, keepdim=True)
            std = torch.sqrt(centered.var(dim=0, unbiased=False) + 1e-4)
            std_loss = F.relu(0.10 - std).mean()
            cov = (centered.T @ centered) / max(z.shape[0] - 1, 1)
            offdiag = cov - torch.diag(torch.diag(cov))
            return std_loss, offdiag.square().mean()

        v_std, v_cov = anti_collapse(zv)
        a_std, a_cov = anti_collapse(za)
        return align + 3.0 * (v_std + a_std) + 0.05 * (v_cov + a_cov)

    def reconstruction_loss(self, frames: torch.Tensor) -> torch.Tensor:
        z = self.vision(frames)
        return weighted_frame_mse(self.decoder(z), frames)

    def transition_loss(
        self, frames: torch.Tensor, actions: torch.Tensor, next_frames: torch.Tensor
    ) -> torch.Tensor:
        z = self.vision(frames)
        with torch.no_grad():
            z_next = self.vision(next_frames)
        pred = self.dynamics(z, actions)
        latent = F.mse_loss(pred, z_next)
        pixel = weighted_frame_mse(self.decoder(pred), next_frames)
        return latent + 2.0 * pixel


def assert_numeric_payload(values: Iterable[object]) -> None:
    for value in values:
        if isinstance(value, str):
            raise TypeError("natural-language/string payload is forbidden in cognitive core")
