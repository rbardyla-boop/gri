from __future__ import annotations

from experiments.wildflower_dual_authority_0_2 import store as d
from experiments.wildflower_dual_authority_0_2.controls import (
    CONTROL_SPECS,
    RecordedTransition,
    StreamClaim,
    score_recorded_stream,
)


def _packet(reference: int, value: int, act: int, relation: int = d.REL_X) -> d.Packet:
    return d.Packet(reference, act, reference, relation, 0, value)


def _stream() -> tuple[RecordedTransition, ...]:
    wrong_left = StreamClaim(_packet(1, 0, d.ACT_PROPOSE))
    wrong_right = StreamClaim(_packet(2, 0, d.ACT_PROPOSE))
    wrong_child = StreamClaim(
        _packet(10, 0, d.ACT_DERIVE, d.REL_ORDER_PARITY),
        ((1, 0), (2, 0)),
    )
    correct_child = StreamClaim(
        _packet(10, 1, d.ACT_DERIVE, d.REL_ORDER_PARITY),
        ((1, 1), (2, 1)),
    )
    correct_left = StreamClaim(_packet(1, 1, d.ACT_PROPOSE))
    correct_right = StreamClaim(_packet(2, 1, d.ACT_PROPOSE))
    return (
        RecordedTransition(
            tick=0,
            predictions=(wrong_left, wrong_right, wrong_child),
            witnesses=(),
            recomputed=(),
            authority=1.0,
            truth_packets=(),
        ),
        RecordedTransition(
            tick=1,
            predictions=(),
            witnesses=(
                _packet(1, 1, d.ACT_OBSERVE),
                _packet(2, 1, d.ACT_OBSERVE),
            ),
            recomputed=(correct_left, correct_right, correct_child),
            authority=1.0,
            truth_packets=(
                _packet(1, 1, d.ACT_OBSERVE),
                _packet(2, 1, d.ACT_OBSERVE),
                _packet(10, 1, d.ACT_OBSERVE, d.REL_ORDER_PARITY),
            ),
            recomputation_targets=(correct_child,),
        ),
    )


def test_all_seven_controls_are_independent_and_reported() -> None:
    scores = score_recorded_stream(_stream())
    assert tuple(scores) == tuple(spec.name for spec in CONTROL_SPECS)
    assert all(score.runtime_steps == 2 for score in scores.values())
    assert scores["DUAL_AUTHORITY"].provenance_query_capability is True
    assert scores["DAG_NO_WITNESS"].provenance_query_capability is True
    assert scores["DAG_PLUS_WITNESS_NO_RECOMPUTE"].provenance_query_capability is True
    assert scores["WITNESS_PLUS_RECOMPUTE_NO_DAG"].provenance_query_capability is False


def test_no_dag_recompute_can_be_correct_without_fake_provenance() -> None:
    scores = score_recorded_stream(_stream())
    flat = scores["WITNESS_PLUS_RECOMPUTE_NO_DAG"]
    dual = scores["DUAL_AUTHORITY"]
    assert flat.durable_coverage == 1.0
    assert flat.metric_b_successes == 0
    assert flat.metric_b_false_positive_reconstructions == 1
    assert dual.metric_b_successes == 1
    assert dual.metric_b_precision == 1.0
    assert dual.metric_b_recall == 1.0


def test_witness_without_dag_leaves_derived_stale() -> None:
    scores = score_recorded_stream(_stream())
    witness = scores["WITNESS_NO_DAG"]
    assert witness.stale_descendants >= 1
    assert witness.metric_b_successes == 0


def test_dag_without_witness_does_not_commit_unwitnessed_predictions() -> None:
    scores = score_recorded_stream(_stream())
    dag = scores["DAG_NO_WITNESS"]
    assert dag.correct_durable_slots == 0
    assert dag.provenance_query_capability is True
