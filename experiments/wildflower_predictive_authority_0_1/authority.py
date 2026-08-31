"""Machine-native authority policies and diagnostic contexts.

Policy functions receive only signals that exist before truth is revealed.
Evaluator errors are deliberately not fields on :class:`AuthorityContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from . import design

POLICIES = (
    "P0_NULL_ONLY",
    "P1_LEARNED_ONLY",
    "P2_CURRENT_POLICY",
    "P3_DELAYED_AUTHORITY",
    "P4_CAPPED_AUTHORITY",
    "P5_HORIZON_AWARE_DIAGNOSTIC",
    "DISAGREEMENT_GATED",
    "P6_ORACLE_UPPER_BOUND",
)
SUCCESSOR_CANDIDATES = (
    "HORIZON_CONDITIONED",
    "DISAGREEMENT_GATED",
)


@dataclass(frozen=True)
class AuthorityContext:
    """Signals available to a mechanism at one rollout step.

    None of these fields is derived from the future target or evaluator error.
    ``current_authority`` is the frozen historical signal at the rollout
    origin, and the remaining fields are sensor/model-derived diagnostics.
    """

    rollout_horizon: int
    horizon_step: int
    current_authority: float
    delayed_authority: float
    innovation_score: float
    disagreement: float
    instability: float
    residual_history: float
    saturation_duration: int
    state_change: float
    recurrence_sensitivity: float

    def validate(self) -> None:
        if self.rollout_horizon not in design.HORIZONS:
            raise ValueError("unsupported rollout horizon")
        if self.horizon_step < 0 or self.horizon_step >= self.rollout_horizon:
            raise ValueError("invalid horizon step")
        values = (
            self.current_authority,
            self.delayed_authority,
            self.innovation_score,
            self.disagreement,
            self.instability,
            self.residual_history,
            self.state_change,
            self.recurrence_sensitivity,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("authority context contains NaN or Inf")
        if not 0.0 <= self.current_authority <= 1.0:
            raise ValueError("current authority outside [0, 1]")
        if not 0.0 <= self.delayed_authority <= 1.0:
            raise ValueError("delayed authority outside [0, 1]")


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _current(context: AuthorityContext) -> float:
    return _clip01(
        context.current_authority * design.AUTHORITY_DECAY**context.horizon_step
    )


def authority_for(policy: str, context: AuthorityContext) -> float:
    """Return authority using no evaluator-side information."""

    context.validate()
    if policy == "P0_NULL_ONLY":
        return 0.0
    if policy == "P1_LEARNED_ONLY":
        return 1.0
    if policy == "P2_CURRENT_POLICY":
        return _current(context)
    if policy == "P3_DELAYED_AUTHORITY":
        if context.horizon_step == 0:
            return 0.0
        return _clip01(
            context.delayed_authority
            * design.AUTHORITY_DECAY ** (context.horizon_step - 1)
        )
    if policy == "P4_CAPPED_AUTHORITY":
        return min(design.CAPPED_AUTHORITY_CAP, _current(context))
    if policy == "P5_HORIZON_AWARE_DIAGNOSTIC":
        factor = {
            1: 1.0,
            8: design.HORIZON_8_FACTOR,
            32: design.HORIZON_32_FACTOR,
        }[context.rollout_horizon]
        return _clip01(_current(context) * factor)
    if policy == "HORIZON_CONDITIONED":
        return authority_for("P5_HORIZON_AWARE_DIAGNOSTIC", context)
    if policy == "DISAGREEMENT_GATED":
        penalty = max(0.0, context.disagreement - design.DISAGREEMENT_FLOOR)
        return _clip01(_current(context) * (1.0 - penalty))
    if policy == "P6_ORACLE_UPPER_BOUND":
        raise ValueError("oracle policy requires evaluator-only scoring")
    raise ValueError(f"unknown authority policy: {policy}")


def oracle_authority(null_error: float, learned_error: float) -> float:
    """Evaluator-only lower-error selector; never a mechanism candidate."""

    if not math.isfinite(null_error) or not math.isfinite(learned_error):
        raise ValueError("oracle errors must be finite")
    return 1.0 if learned_error < null_error else 0.0
