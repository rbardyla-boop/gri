from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import random
from typing import Iterable

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

HEIGHT = 12
WIDTH = 12
ACTIONS = np.array(((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)), dtype=np.int64)
MODES = (0, 1, 2)


@dataclass(frozen=True)
class Nursery1Event:
    tick: int
    frame: np.ndarray
    audio: np.ndarray
    action: int

    def validate(self) -> None:
        if self.tick < 0:
            raise ValueError("tick must be non-negative")
        if self.frame.shape != (3, HEIGHT, WIDTH):
            raise ValueError(f"unexpected frame shape {self.frame.shape}")
        if self.audio.shape != (64,):
            raise ValueError(f"unexpected audio shape {self.audio.shape}")
        if not 0 <= self.action < len(ACTIONS):
            raise ValueError("action out of range")
        if not np.isfinite(self.frame).all() or not np.isfinite(self.audio).all():
            raise ValueError("non-finite sensor value")


@dataclass(frozen=True)
class Nursery1Pair:
    current: Nursery1Event
    nxt: Nursery1Event
    mode: int
    rule_event: bool
    collision: bool
    boundary: bool


@dataclass(frozen=True)
class ProbeMetrics:
    model_seed: int
    train_selection: dict[int, tuple[int, ...]]
    test_selection: dict[int, tuple[int, ...]]
    ratios_by_mode: dict[int, tuple[dict[str, float], ...]]
    aggregate: dict[str, float]
    gates: dict[str, bool]
    passed: bool
    receipt_sha256: str


def _sign(value: int) -> int:
    if value == 0:
        return 0
    return 1 if value > 0 else -1


class Nursery1World:
    """Multi-object numeric world with a hidden episode dynamics mode.

    The hidden mode and event flags are evaluator-only metadata. Learner-visible
    data remain pixels, waveform samples, and machine action IDs.
    """

    def __init__(self, seed: int, surprise: bool = False) -> None:
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.surprise = surprise
        self.mode = int(self.rng.integers(0, 3))
        self.pos = np.array(((2, 2), (8, 3), (5, 8)), dtype=np.int64)
        self.pos += self.rng.integers(-1, 2, size=self.pos.shape)
        choices = np.array(
            ((-1, -1), (-1, 1), (1, -1), (1, 1), (1, 0), (0, 1), (-1, 0), (0, -1)),
            dtype=np.int64,
        )
        self.vel = np.zeros((3, 2), dtype=np.int64)
        self.vel[1] = choices[int(self.rng.integers(len(choices)))]
        self.vel[2] = choices[int(self.rng.integers(len(choices)))]
        self.pending_action = np.zeros(2, dtype=np.int64)

    def _frame(self) -> np.ndarray:
        frame = np.zeros((3, HEIGHT, WIDTH), dtype=np.float32)
        for channel, (x, y) in enumerate(self.pos):
            intensity = 0.75 + 0.10 * channel
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                frame[channel, y + dy, x + dx] = intensity
        return frame

    def _audio(self) -> np.ndarray:
        t = np.linspace(0.0, 1.0, 64, endpoint=False, dtype=np.float32)
        wave = np.zeros(64, dtype=np.float32)
        for channel, (x, y) in enumerate(self.pos):
            amplitude = 0.40 + 0.02 * x + 0.015 * y
            frequency = 2.3 + 1.4 * channel
            phase = 0.11 * self.tick * (channel + 1)
            wave += amplitude * np.sin(2 * np.pi * frequency * t + phase).astype(np.float32)
        return wave / (np.linalg.norm(wave) + 1e-6)

    def observe(self, action: int = 0) -> Nursery1Event:
        event = Nursery1Event(self.tick, self._frame(), self._audio(), action)
        event.validate()
        return event

    def _apply_hidden_rule(self) -> bool:
        before = self.vel.copy()
        if self.mode == 1:
            x_toward = _sign(int(self.pos[0, 0] - self.pos[1, 0]))
            y_away = -_sign(int(self.pos[1, 1] - self.pos[2, 1]))
            if x_toward:
                self.vel[1, 0] = x_toward
            if y_away:
                self.vel[2, 1] = y_away
        elif self.mode == 2:
            y_toward = _sign(int(self.pos[2, 1] - self.pos[1, 1]))
            x_away = -_sign(int(self.pos[0, 0] - self.pos[2, 0]))
            if y_toward:
                self.vel[1, 1] = y_toward
            if x_away:
                self.vel[2, 0] = x_away
        return not np.array_equal(before[1:], self.vel[1:])

    def step(self, action: int) -> tuple[Nursery1Event, bool, bool, bool]:
        if not 0 <= action < len(ACTIONS):
            raise ValueError("action out of range")
        self.vel[0] = self.pending_action
        self.pending_action = ACTIONS[action].copy()
        rule_event = self._apply_hidden_rule()

        if self.surprise and self.tick > 0 and self.tick % 23 == 0:
            index = 1 + (self.tick // 23) % 2
            self.vel[index] = -self.vel[index][::-1]
            rule_event = True

        proposed = self.pos + self.vel
        boundary = False
        for obj in range(3):
            for axis in range(2):
                if proposed[obj, axis] < 1 or proposed[obj, axis] > 10:
                    self.vel[obj, axis] *= -1
                    boundary = True
            proposed[obj] = self.pos[obj] + self.vel[obj]

        collision = False
        for left in range(3):
            for right in range(left + 1, 3):
                same_target = np.array_equal(proposed[left], proposed[right])
                crossed = np.array_equal(proposed[left], self.pos[right]) and np.array_equal(
                    proposed[right], self.pos[left]
                )
                if same_target or crossed:
                    self.vel[[left, right]] = self.vel[[right, left]]
                    proposed[left] = self.pos[left] + self.vel[left]
                    proposed[right] = self.pos[right] + self.vel[right]
                    collision = True

        self.pos = np.clip(proposed, 1, 10)
        self.tick += 1
        return self.observe(action), rule_event, collision, boundary


def collect_pairs(seed: int, count: int, surprise: bool = False) -> list[Nursery1Pair]:
    if count <= 0:
        raise ValueError("count must be positive")
    world = Nursery1World(seed, surprise=surprise)
    current = world.observe(0)
    pairs: list[Nursery1Pair] = []
    for _ in range(count):
        action = int(world.rng.integers(0, len(ACTIONS)))
        nxt, rule_event, collision, boundary = world.step(action)
        current = Nursery1Event(current.tick, current.frame, current.audio, action)
        pairs.append(Nursery1Pair(current, nxt, world.mode, rule_event, collision, boundary))
        current = nxt
    return pairs


def select_balanced_episode_seeds(
    root: int, per_mode: int, start: int = 0
) -> dict[int, tuple[int, ...]]:
    """Generator-only stratification. Hidden mode is never passed to the learner."""
    if per_mode <= 0:
        raise ValueError("per_mode must be positive")
    found: dict[int, list[int]] = {mode: [] for mode in MODES}
    offset = start
    while any(len(found[mode]) < per_mode for mode in MODES):
        candidate = root * 100_000 + offset
        mode = Nursery1World(candidate).mode
        if len(found[mode]) < per_mode:
            found[mode].append(candidate)
        offset += 1
        if offset - start > 10_000:
            raise RuntimeError("balanced selector exhausted")
    return {mode: tuple(found[mode]) for mode in MODES}


def extract_object_state(frame: np.ndarray) -> np.ndarray:
    """Numeric scaffold: six centroid coordinates derived only from sensor pixels."""
    if frame.shape != (3, HEIGHT, WIDTH):
        raise ValueError("unexpected frame shape")
    yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH]
    values: list[float] = []
    for channel in range(3):
        weight = frame[channel]
        mass = float(weight.sum())
        if mass <= 0.0:
            raise ValueError("object channel has zero mass")
        x = float((weight * xx).sum() / mass) / (WIDTH - 1) * 2.0 - 1.0
        y = float((weight * yy).sum() / mass) / (HEIGHT - 1) * 2.0 - 1.0
        values.extend((x, y))
    return np.asarray(values, dtype=np.float32)


def learner_projection(pairs: Iterable[Nursery1Pair]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return only numeric learner-visible state/action/target arrays."""
    rows = list(pairs)
    current = np.stack([extract_object_state(pair.current.frame) for pair in rows])
    target = np.stack([extract_object_state(pair.nxt.frame) for pair in rows])
    actions = np.asarray([pair.current.action for pair in rows], dtype=np.int64)
    return current, target, actions


class DominanceResidual(nn.Module):
    """Learned residual that competes against a transparent velocity null."""

    def __init__(self) -> None:
        super().__init__()
        self.action_embedding = nn.Embedding(5, 8)
        self.context = nn.GRUCell(20, 64)
        self.correction = nn.Sequential(
            nn.Linear(84, 96),
            nn.SiLU(),
            nn.Linear(96, 6),
        )
        self.gate = nn.Sequential(
            nn.Linear(84, 48),
            nn.SiLU(),
            nn.Linear(48, 6),
        )
        nn.init.zeros_(self.correction[-1].weight)
        nn.init.zeros_(self.correction[-1].bias)
        nn.init.zeros_(self.gate[-1].weight)
        nn.init.constant_(self.gate[-1].bias, -3.0)

    def step(
        self,
        state: torch.Tensor,
        velocity: torch.Tensor,
        action: torch.Tensor,
        hidden: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        embedded = self.action_embedding(action.long())
        hidden = self.context(torch.cat((state, velocity, embedded), dim=1), hidden)
        features = torch.cat((hidden, state, velocity, embedded), dim=1)
        gate = torch.sigmoid(self.gate(features))
        residual = 0.18 * torch.tanh(self.correction(features)) * gate
        prediction = (state + velocity + residual).clamp(-1.0, 1.0)
        return prediction, hidden, residual, gate


def _precompute(pairs: list[Nursery1Pair]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    current, target, actions = learner_projection(pairs)
    return current, target, actions


def train_residual(
    model: DominanceResidual,
    pairs: list[Nursery1Pair],
    steps: int,
    seed: int,
    burn: int = 10,
    horizon: int = 8,
) -> None:
    if len(pairs) <= burn + horizon + 24:
        raise ValueError("not enough pairs")
    current, target, actions = _precompute(pairs)
    rng = np.random.default_rng(seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1.25e-3, weight_decay=1e-4)
    max_start = len(pairs) - horizon
    model.train()

    for _ in range(steps):
        starts = rng.choice(np.arange(burn + 1, max_start), size=24, replace=False)
        hidden = torch.zeros((24, 64), dtype=torch.float32)
        for offset in range(-burn, 0):
            index = starts + offset
            state = torch.tensor(current[index])
            previous = torch.tensor(current[index - 1])
            velocity = state - previous
            _, hidden, _, _ = model.step(state, velocity, torch.tensor(actions[index]), hidden)

        state = torch.tensor(current[starts])
        previous = torch.tensor(current[starts - 1])
        velocity = state - previous
        baseline_state = state.clone()
        baseline_velocity = velocity.clone()
        loss = torch.zeros((), dtype=torch.float32)

        for offset in range(horizon):
            action = torch.tensor(actions[starts + offset])
            prediction, hidden, residual, gate = model.step(state, velocity, action, hidden)
            baseline_prediction = (baseline_state + baseline_velocity).clamp(-1.0, 1.0)
            expected = torch.tensor(target[starts + offset])

            model_error = (prediction - expected).abs().mean(dim=1)
            baseline_error = (baseline_prediction - expected).abs().mean(dim=1)
            dominance_penalty = F.relu(model_error - baseline_error).mean()
            multiplier = 3.0 if offset == 0 else 1.5
            loss = loss + (1.0 + 0.12 * offset) * F.smooth_l1_loss(prediction, expected)
            loss = loss + multiplier * dominance_penalty
            loss = loss + 0.02 * gate.mean() + 0.01 * residual.abs().mean()

            velocity = prediction - state
            state = prediction
            baseline_velocity = baseline_prediction - baseline_state
            baseline_state = baseline_prediction

        loss = loss / horizon
        if not torch.isfinite(loss):
            raise FloatingPointError("non-finite Nursery-1 loss")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()


def state_mae(
    model: DominanceResidual,
    pairs: list[Nursery1Pair],
    horizon: int,
    burn: int = 10,
    event_only: bool = False,
) -> float:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    current, target, actions = _precompute(pairs)
    errors: list[float] = []
    scale = (WIDTH - 1) / 2.0
    model.eval()
    with torch.no_grad():
        for start in range(burn + 1, len(pairs) - horizon, max(horizon, 4)):
            if event_only and not any(
                pairs[start + offset].rule_event
                or pairs[start + offset].collision
                or pairs[start + offset].boundary
                for offset in range(horizon)
            ):
                continue
            hidden = torch.zeros((1, 64), dtype=torch.float32)
            for index in range(start - burn, start):
                state = torch.tensor(current[index][None])
                previous = torch.tensor(current[index - 1][None])
                velocity = state - previous
                _, hidden, _, _ = model.step(
                    state,
                    velocity,
                    torch.tensor([actions[index]]),
                    hidden,
                )
            state = torch.tensor(current[start][None])
            previous = torch.tensor(current[start - 1][None])
            velocity = state - previous
            for offset in range(horizon):
                prediction, hidden, _, _ = model.step(
                    state,
                    velocity,
                    torch.tensor([actions[start + offset]]),
                    hidden,
                )
                velocity = prediction - state
                state = prediction
            expected = torch.tensor(target[start + horizon - 1][None])
            errors.append(float((state - expected).abs().mean() * scale))
    return float(np.mean(errors)) if errors else float("nan")


def velocity_baseline_mae(
    pairs: list[Nursery1Pair],
    horizon: int,
    burn: int = 10,
    event_only: bool = False,
) -> float:
    current, target, _ = _precompute(pairs)
    errors: list[float] = []
    scale = (WIDTH - 1) / 2.0
    for start in range(burn + 1, len(pairs) - horizon, max(horizon, 4)):
        if event_only and not any(
            pairs[start + offset].rule_event
            or pairs[start + offset].collision
            or pairs[start + offset].boundary
            for offset in range(horizon)
        ):
            continue
        state = current[start].copy()
        velocity = current[start] - current[start - 1]
        for _ in range(horizon):
            prediction = np.clip(state + velocity, -1.0, 1.0)
            velocity = prediction - state
            state = prediction
        errors.append(float(np.abs(state - target[start + horizon - 1]).mean() * scale))
    return float(np.mean(errors)) if errors else float("nan")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def stable_hash(data: object) -> str:
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def run_balanced_probe(
    model_seed: int,
    train_per_mode: int = 2,
    test_per_mode: int = 2,
    episode_length: int = 400,
    train_steps_per_episode: int = 70,
) -> ProbeMetrics:
    set_seed(model_seed)
    train_selection = select_balanced_episode_seeds(model_seed + 9000, train_per_mode, start=0)
    test_selection = select_balanced_episode_seeds(model_seed + 19000, test_per_mode, start=50_000)
    model = DominanceResidual()

    training_order = [
        train_selection[mode][index]
        for index in range(train_per_mode)
        for mode in MODES
    ]
    for index, episode_seed in enumerate(training_order):
        train_residual(
            model,
            collect_pairs(episode_seed, episode_length),
            train_steps_per_episode,
            model_seed + 10_000 + index,
        )

    ratios_by_mode: dict[int, tuple[dict[str, float], ...]] = {}
    ratio_h1: list[float] = []
    ratio_h8: list[float] = []
    ratio_h32: list[float] = []
    event_h8: list[float] = []

    for mode in MODES:
        mode_rows: list[dict[str, float]] = []
        for episode_seed in test_selection[mode]:
            pairs = collect_pairs(episode_seed, episode_length + 100)
            model_h1 = state_mae(model, pairs, 1)
            model_h8 = state_mae(model, pairs, 8)
            model_h32 = state_mae(model, pairs, 32)
            base_h1 = velocity_baseline_mae(pairs, 1)
            base_h8 = velocity_baseline_mae(pairs, 8)
            base_h32 = velocity_baseline_mae(pairs, 32)
            model_event = state_mae(model, pairs, 8, event_only=True)
            base_event = velocity_baseline_mae(pairs, 8, event_only=True)
            row = {
                "episode_seed": float(episode_seed),
                "h1_ratio": model_h1 / max(base_h1, 1e-8),
                "h8_ratio": model_h8 / max(base_h8, 1e-8),
                "h32_ratio": model_h32 / max(base_h32, 1e-8),
                "event_h8_ratio": model_event / max(base_event, 1e-8),
            }
            ratio_h1.append(row["h1_ratio"])
            ratio_h8.append(row["h8_ratio"])
            ratio_h32.append(row["h32_ratio"])
            event_h8.append(row["event_h8_ratio"])
            mode_rows.append(row)
        ratios_by_mode[mode] = tuple(mode_rows)

    aggregate = {
        "h1_ratio_mean": float(np.mean(ratio_h1)),
        "h1_ratio_max": float(np.max(ratio_h1)),
        "h8_ratio_mean": float(np.mean(ratio_h8)),
        "h8_ratio_max": float(np.max(ratio_h8)),
        "h32_ratio_mean": float(np.mean(ratio_h32)),
        "h32_ratio_max": float(np.max(ratio_h32)),
        "event_h8_ratio_mean": float(np.mean(event_h8)),
        "event_h8_ratio_max": float(np.max(event_h8)),
    }
    gates = {
        "h1_noninferior_all": aggregate["h1_ratio_max"] <= 1.10,
        "h8_better_all": aggregate["h8_ratio_max"] <= 1.00,
        "h8_mean_10pct": aggregate["h8_ratio_mean"] <= 0.90,
        "h32_better_all": aggregate["h32_ratio_max"] <= 1.00,
        "h32_mean_15pct": aggregate["h32_ratio_mean"] <= 0.85,
        "event_h8_mean_10pct": aggregate["event_h8_ratio_mean"] <= 0.90,
    }
    payload = {
        "model_seed": model_seed,
        "train_selection": train_selection,
        "test_selection": test_selection,
        "ratios_by_mode": ratios_by_mode,
        "aggregate": aggregate,
        "gates": gates,
        "passed": all(gates.values()),
    }
    return ProbeMetrics(
        model_seed=model_seed,
        train_selection=train_selection,
        test_selection=test_selection,
        ratios_by_mode=ratios_by_mode,
        aggregate=aggregate,
        gates=gates,
        passed=all(gates.values()),
        receipt_sha256=stable_hash(payload),
    )


def replace_evaluator_metadata(pair: Nursery1Pair, mode: int) -> Nursery1Pair:
    """Test helper proving learner projection ignores evaluator-only mode metadata."""
    return replace(pair, mode=mode)
