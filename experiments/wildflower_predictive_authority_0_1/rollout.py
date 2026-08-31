"""Predictive rollouts with explicit null, learned-only, and gated paths."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from . import design
from .authority import AuthorityContext, authority_for
from .trace import OriginTrace, RolloutStep


def _mean_abs(left: torch.Tensor, right: torch.Tensor) -> float:
    return float((left - right).abs().mean().item() * 5.5)


def _clip_fraction(before: torch.Tensor, after: torch.Tensor) -> float:
    return float(((before < -1.0) | (before > 1.0)).float().mean().item())


def _origin_state(
    model: Any,
    current: np.ndarray,
    actions: np.ndarray,
    index: int,
) -> tuple[torch.Tensor, float, torch.Tensor, torch.Tensor, float]:
    if index < design.BURN + 2:
        raise ValueError("insufficient burn history")
    hidden = torch.zeros((1, 64), dtype=torch.float32)
    history: list[float] = []
    with torch.no_grad():
        for observed_index in range(index - design.BURN, index):
            state = torch.tensor(current[observed_index][None])
            previous = torch.tensor(current[observed_index - 1][None])
            velocity = state - previous
            previous2 = torch.tensor(current[observed_index - 2][None])
            innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
            _, hidden, _, _ = model.step(
                state,
                velocity,
                torch.tensor([actions[observed_index]]),
                innovation,
                hidden,
            )
            history.append(float(innovation.abs().mean().item() * 5.5))
        weights = np.geomspace(0.35, 1.0, len(history))
        score = float(np.dot(weights, history) / weights.sum())
        origin_authority = float(
            np.clip(
                (score - design.AUTHORITY_THRESHOLD) / design.AUTHORITY_WIDTH,
                0.0,
                1.0,
            )
        )
        state = torch.tensor(current[index][None])
        previous = torch.tensor(current[index - 1][None])
        velocity = state - previous
        previous2 = torch.tensor(current[index - 2][None])
        innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
    return hidden, score, state, velocity, origin_authority


def _path(
    model: Any,
    current: np.ndarray,
    target: np.ndarray,
    actions: np.ndarray,
    index: int,
    horizon: int,
    policy: str,
    initial_hidden: torch.Tensor,
    innovation_score: float,
    origin_authority: float,
    delayed_authority: float,
) -> tuple[RolloutStep, ...]:
    state = torch.tensor(current[index][None])
    previous = torch.tensor(current[index - 1][None])
    velocity = state - previous
    previous2 = torch.tensor(current[index - 2][None])
    innovation = state - (previous + (previous - previous2)).clamp(-1.0, 1.0)
    base_state = state.clone()
    base_velocity = velocity.clone()
    learned_state = state.clone()
    learned_velocity = velocity.clone()
    learned_hidden = initial_hidden.clone()
    learned_innovation = innovation.clone()
    gated_state = state.clone()
    gated_velocity = velocity.clone()
    gated_hidden = initial_hidden.clone()
    gated_innovation = innovation.clone()
    rows: list[RolloutStep] = []
    prior_disagreement = 0.0
    saturation_duration = 0
    with torch.no_grad():
        for offset in range(horizon):
            action = torch.tensor([actions[index + offset]])
            learned, learned_hidden, _, _ = model.step(
                learned_state,
                learned_velocity,
                action,
                learned_innovation,
                learned_hidden,
            )
            gated_learned, gated_hidden, _, _ = model.step(
                gated_state,
                gated_velocity,
                action,
                gated_innovation,
                gated_hidden,
            )
            null = (base_state + base_velocity).clamp(-1.0, 1.0)
            disagreement = float((gated_learned - null).abs().mean().item())
            instability = abs(disagreement - prior_disagreement)
            context = AuthorityContext(
                rollout_horizon=horizon,
                horizon_step=offset,
                current_authority=origin_authority,
                delayed_authority=delayed_authority,
                innovation_score=innovation_score,
                disagreement=min(1.0, disagreement),
                instability=min(1.0, instability),
                residual_history=min(1.0, innovation_score),
                saturation_duration=saturation_duration,
                state_change=min(1.0, float(velocity.abs().mean().item())),
                recurrence_sensitivity=min(1.0, disagreement + instability),
            )
            authority = authority_for(policy, context)
            if authority >= 0.99:
                saturation_duration += 1
            gated_raw = null + authority * (gated_learned - null)
            gated = gated_raw.clamp(-1.0, 1.0)
            target_row = torch.tensor(target[index + offset][None])
            rows.append(
                RolloutStep(
                    offset=offset,
                    null_prediction=tuple(float(v) for v in null[0].numpy()),
                    learned_only_prediction=tuple(
                        float(v) for v in learned[0].numpy()
                    ),
                    gated_prediction=tuple(float(v) for v in gated[0].numpy()),
                    target_evaluator_only=tuple(
                        float(v) for v in target_row[0].numpy()
                    ),
                    innovation_score=innovation_score,
                    authority=authority,
                    null_local_error_evaluator_only=_mean_abs(null, target_row),
                    learned_only_local_error_evaluator_only=_mean_abs(
                        learned, target_row
                    ),
                    gated_local_error_evaluator_only=_mean_abs(gated, target_row),
                    clipping_fraction=_clip_fraction(gated_raw, gated),
                )
            )
            base_velocity = null - base_state
            base_state = null
            learned_velocity = learned - learned_state
            learned_state = learned
            gated_velocity = gated - gated_state
            gated_state = gated
            velocity = gated_velocity
            learned_innovation = learned_innovation * 0.90
            gated_innovation = gated_innovation * 0.90
            prior_disagreement = disagreement
    return tuple(rows)


def generate_origin_trace(
    model: Any,
    pairs: list[Any],
    mode: int,
    episode_seed: int,
    index: int,
    policy: str = "HORIZON_CONDITIONED",
) -> OriginTrace:
    """Generate all preregistered horizons for one ordinary rollout origin."""

    if policy == "P6_ORACLE_UPPER_BOUND":
        raise ValueError("oracle policy is evaluator-only and not a mechanism trace")
    legacy_pre = getattr(model, "_predictive_authority_pre", None)
    if legacy_pre is None:
        from .legacy import load_legacy

        current, target, actions = load_legacy()["pre"](pairs)
    else:
        current, target, actions = legacy_pre(pairs)
    initial_hidden, score, _, _, origin_authority = _origin_state(
        model, current, actions, index
    )
    delayed_authority = origin_authority
    rollouts = {
        horizon: _path(
            model,
            current,
            target,
            actions,
            index,
            horizon,
            policy,
            initial_hidden,
            score,
            origin_authority,
            delayed_authority,
        )
        for horizon in design.HORIZONS
    }
    event_locations = tuple(
        index + offset
        for offset in range(32)
        if pairs[index + offset].rule_event
        or pairs[index + offset].collision
        or pairs[index + offset].boundary
    )
    one = rollouts[1][0]
    trace = OriginTrace(
        episode_seed=episode_seed,
        mode=mode,
        step=index,
        event_locations_evaluator_only=event_locations,
        rollout_horizons=rollouts,
        one_step_innovation_score=score,
        one_step_authority=origin_authority,
        one_step_null_error_evaluator_only=one.null_local_error_evaluator_only,
        one_step_learned_error_evaluator_only=one.learned_only_local_error_evaluator_only,
        one_step_gated_error_evaluator_only=one.gated_local_error_evaluator_only,
    )
    trace.validate()
    return trace
