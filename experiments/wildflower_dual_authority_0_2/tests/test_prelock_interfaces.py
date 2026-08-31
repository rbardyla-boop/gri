from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.wildflower_dual_authority_0_2 import store as d
from experiments.wildflower_dual_authority_0_2.controls import (
    RecordedTransition,
    StreamClaim,
)
from experiments.wildflower_dual_authority_0_2.design import (
    DEVELOPMENT_SEEDS,
    QUALIFICATION_SEEDS,
    selector_ranges,
    selector_starts,
)
from experiments.wildflower_dual_authority_0_2.qualification_guard import (
    assert_qualification_locked,
    assert_seed_is_registered,
    development_seed_is_allowed,
    qualification_is_locked,
)
from experiments.wildflower_dual_authority_0_2.predictive_trace import (
    PredictiveTrace,
    PredictiveTraceRow,
)
from experiments.wildflower_dual_authority_0_2.recorded_stream import (
    canonical_stream_bytes,
    read_stream,
    transition_from_dict,
    transition_to_dict,
    write_stream,
)
from experiments.wildflower_dual_authority_0_2.scaling import (
    benchmark_recompute_everything,
)


def _frame() -> RecordedTransition:
    claim = StreamClaim(d.Packet(1, d.ACT_PROPOSE, 1, d.REL_X, 0, 1))
    return RecordedTransition(
        tick=0,
        predictions=(claim,),
        witnesses=(),
        recomputed=(),
        authority=0.75,
        truth_packets=(d.Packet(1, d.ACT_OBSERVE, 1, d.REL_X, 0, 1),),
    )


def test_recorded_stream_round_trip_is_canonical(tmp_path: Path) -> None:
    frame = _frame()
    assert transition_from_dict(transition_to_dict(frame)) == frame
    first = canonical_stream_bytes((frame,))
    second = canonical_stream_bytes((frame,))
    assert first == second
    path = tmp_path / "stream.json"
    digest = write_stream(path, (frame,))
    assert read_stream(path) == (frame,)
    assert len(digest) == 64
    assert json.loads(path.read_text())


def test_recorded_stream_rejects_nonfinite_authority() -> None:
    frame = _frame()
    with pytest.raises(ValueError, match="finite"):
        transition_to_dict(
            RecordedTransition(
                tick=frame.tick,
                predictions=frame.predictions,
                witnesses=frame.witnesses,
                recomputed=frame.recomputed,
                authority=float("nan"),
                truth_packets=frame.truth_packets,
            )
        )


def test_scaling_adversary_scans_every_retained_event() -> None:
    rows = benchmark_recompute_everything((100, 1_000, 10_000))
    assert [row.correction_work for row in rows] == [100, 1_000, 10_000]
    assert [row.retained_events for row in rows] == [100, 1_000, 10_000]


def test_predictive_trace_is_finite_and_keeps_event_locations() -> None:
    trace = PredictiveTrace()
    trace.append(
        PredictiveTraceRow(
            episode_seed=320,
            mode=1,
            step=8,
            innovation_score=0.1,
            authority=0.8,
            null_error=1.0,
            ungated_learned_error=0.9,
            gated_error=0.85,
            h8_prediction=(0.1, 0.2),
            event_location=8,
        )
    )
    assert trace.event_locations(320) == (8,)


def test_selector_ranges_are_disjoint_and_seed_guard_is_fail_closed() -> None:
    ranges = selector_ranges()
    starts = [start for seed in ranges.values() for start, _ in seed.values()]
    assert len(starts) == len(set(starts))
    assert min(starts) >= 2_000_000
    assert selector_starts(320)["training"] == 2_000_000
    assert set(DEVELOPMENT_SEEDS).isdisjoint(QUALIFICATION_SEEDS)
    assert qualification_is_locked()
    assert development_seed_is_allowed(320)
    for spent_seed in (312, 313, 314, 315):
        with pytest.raises(ValueError, match="0.1 seed"):
            assert_seed_is_registered(spent_seed)
    with pytest.raises(RuntimeError, match="locked"):
        assert_qualification_locked(330)
