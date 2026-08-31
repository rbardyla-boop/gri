"""Evaluator-side predictive instrumentation schema; no cognitive-path text."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


def _finite(values: tuple[float, ...], label: str) -> None:
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{label} contains NaN or Inf")


@dataclass(frozen=True)
class PredictiveTraceRow:
    episode_seed: int
    mode: int
    step: int
    innovation_score: float
    authority: float
    null_error: float
    ungated_learned_error: float
    gated_error: float
    h8_prediction: tuple[float, ...]
    event_location: int | None = None

    def validate(self) -> None:
        _finite(
            (
                self.innovation_score,
                self.authority,
                self.null_error,
                self.ungated_learned_error,
                self.gated_error,
            ),
            "predictive trace",
        )
        _finite(self.h8_prediction, "h8 prediction")


@dataclass
class PredictiveTrace:
    rows: list[PredictiveTraceRow] = field(default_factory=list)

    def append(self, row: PredictiveTraceRow) -> None:
        row.validate()
        self.rows.append(row)

    def for_episode(self, episode_seed: int) -> tuple[PredictiveTraceRow, ...]:
        return tuple(row for row in self.rows if row.episode_seed == episode_seed)

    def event_locations(self, episode_seed: int) -> tuple[int, ...]:
        return tuple(
            row.step
            for row in self.for_episode(episode_seed)
            if row.event_location is not None
        )
