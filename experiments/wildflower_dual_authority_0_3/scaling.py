"""Scaling adversary for the no-DAG recompute-everything control."""

from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class ScalingRow:
    history_events: int
    correction_work: int
    elapsed_seconds: float
    retained_events: int


class RecomputeEverythingAdversary:
    """A deliberately serious flat competitor.

    Every correction scans every retained prior event.  It has no graph and no
    provenance query, but its work is measured honestly rather than replaced
    with an evaluator-side constant.
    """

    def __init__(self) -> None:
        self.history: list[int] = []
        self.correction_work = 0

    def append_history(self, value: int) -> None:
        self.history.append(int(value))

    def correct(self, value: int) -> None:
        for index in range(len(self.history)):
            self.history[index] = int(value)
            self.correction_work += 1


def benchmark_recompute_everything(
    history_sizes: tuple[int, ...] = (100, 1_000, 10_000, 100_000),
) -> tuple[ScalingRow, ...]:
    rows: list[ScalingRow] = []
    for history_size in history_sizes:
        adversary = RecomputeEverythingAdversary()
        for index in range(history_size):
            adversary.append_history(index)
        start = time.perf_counter()
        adversary.correct(-1)
        elapsed = time.perf_counter() - start
        rows.append(
            ScalingRow(
                history_events=history_size,
                correction_work=adversary.correction_work,
                elapsed_seconds=elapsed,
                retained_events=len(adversary.history),
            )
        )
    return tuple(rows)
