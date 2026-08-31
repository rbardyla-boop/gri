from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.wildflower_dual_authority_0_1 import store as d
from experiments.wildflower_dual_authority_0_1.metrics import (
    StoreSnapshot,
    SupportSnapshot,
    classify_derived_transition,
)


ROOT = Path(__file__).parents[1]
ARTIFACT = ROOT / "artifacts" / "development_seed311.json"
TRACE = ROOT / "artifacts" / "seed311_autopsy_trace.json"
ARTIFACT_SHA256 = (
    "b51de9e7e7221c23226f95507fea4464446445fc9279d5e99398049c81e78c58"
)


def _snapshot(
    *,
    parent_status: tuple[int, int],
    parent_supports: tuple[tuple[int, ...], tuple[int, ...]],
    parent_effective: tuple[tuple[bool, ...], tuple[bool, ...]],
    child_status: int,
    child_supports: tuple[int, ...],
    child_effective: tuple[bool, ...],
) -> StoreSnapshot:
    parent_a = (100, 1)
    parent_b = (101, 1)
    child = (200, 1)
    claims = {
        parent_a: (parent_status[0], parent_supports[0]),
        parent_b: (parent_status[1], parent_supports[1]),
        child: (child_status, child_supports),
    }
    support_specs = {
        1: (100, d.SUPPORT_WORLD, (), parent_effective[0][0]),
        2: (101, d.SUPPORT_WORLD, (), parent_effective[1][0]),
        3: (200, d.SUPPORT_DERIVED, (parent_a, parent_b), child_effective[0]),
    }
    if len(parent_supports[0]) > 1:
        support_specs[4] = (100, d.SUPPORT_WORLD, (), parent_effective[0][1])
    if len(parent_supports[1]) > 1:
        support_specs[5] = (101, d.SUPPORT_WORLD, (), parent_effective[1][1])
    if len(child_supports) > 1:
        support_specs[6] = (
            200,
            d.SUPPORT_DERIVED,
            (parent_a, parent_b),
            child_effective[1],
        )
    supports = {}
    for support_id, (reference, kind, parents, effective) in support_specs.items():
        supports[support_id] = SupportSnapshot(
            support_id=support_id,
            packet=(reference, d.ACT_OBSERVE if kind == d.SUPPORT_WORLD else d.ACT_DERIVE,
                    reference, d.REL_X if kind == d.SUPPORT_WORLD else d.REL_ORDER_PARITY,
                    0, 1),
            kind=kind,
            parents=parents,
            enabled=True,
            effective=effective,
        )
    return StoreSnapshot(claims=claims, supports=supports, ledger_head_sha256="0")


def test_smallest_transitive_parity_case_reproduces_seed311_metric_b_miss() -> None:
    predicted = d.Packet(200, d.ACT_DERIVE, 1, d.REL_ORDER_PARITY, 2, 1)
    truth = d.Packet(200, d.ACT_OBSERVE, 1, d.REL_ORDER_PARITY, 2, 1)
    before = _snapshot(
        parent_status=(d.STATUS_COMMITTED, d.STATUS_COMMITTED),
        parent_supports=((1,), (2,)),
        parent_effective=((True,), (True,)),
        child_status=d.STATUS_PROVISIONAL,
        child_supports=(3,),
        child_effective=(True,),
    )
    after_witness = _snapshot(
        parent_status=(d.STATUS_REVOKED, d.STATUS_REVOKED),
        parent_supports=((1,), (2,)),
        parent_effective=((False,), (False,)),
        child_status=d.STATUS_REVOKED,
        child_supports=(3,),
        child_effective=(False,),
    )
    after_recompute = _snapshot(
        parent_status=(d.STATUS_COMMITTED, d.STATUS_COMMITTED),
        parent_supports=((1, 4), (2, 5)),
        parent_effective=((False, True), (False, True)),
        child_status=d.STATUS_COMMITTED,
        child_supports=(3, 6),
        child_effective=(True, True),
    )

    transition = classify_derived_transition(
        predicted, truth, 3, before, after_witness, after_recompute
    )

    assert transition.recomputation_opportunity
    assert transition.reconstructed_support_ids == (6,)
    assert transition.parent_keys_changed
    assert not transition.recomputation_success
    assert after_witness.status((200, 1)) == d.STATUS_REVOKED
    assert after_recompute.status((200, 1)) == d.STATUS_COMMITTED
    assert after_recompute.supports[3].parents == after_recompute.supports[6].parents


def test_seed311_trace_has_exact_metric_b_and_duplicate_breakdown() -> None:
    trace = json.loads(TRACE.read_text())
    summary = trace["transition_summary"]
    assert summary["metric_a_opportunities"] == 1784
    assert summary["metric_a_successes"] == 1784
    assert summary["metric_b_opportunities"] == 2708
    assert summary["metric_b_successes"] == 2306
    assert summary["metric_b_failures"] == 402
    assert summary["reconstruction_true_positives"] == 2306
    assert summary["reconstruction_false_positives"] == 2223
    assert summary["reconstruction_precision_boolean_denominator"] == 4529
    assert summary["metric_b_failure_classes"] == {
        "no_reconstructed_support": 0,
        "reconstructed_but_claim_not_committed": 0,
        "reconstructed_and_committed_but_parent_signature_unchanged": 402,
    }
    assert all(
        row["original_support"]["packet"][3] == d.REL_ORDER_PARITY
        for row in trace["transition_summary"]["metric_b_failure_rows"]
    )
    assert trace["duplicate_audit"]["total_exact_duplicate_supports"] == 2223


def test_seed311_artifact_is_byte_identical_to_audited_checkpoint() -> None:
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == ARTIFACT_SHA256
    artifact = json.loads(ARTIFACT.read_text())
    aggregate = artifact["developmental_epistemic_challenge"]["aggregate"]
    assert aggregate["alternate_support_preservation"] == {
        "opportunities": 1784,
        "successes": 1784,
        "rate": 1.0,
    }
    assert aggregate["recomputed_after_parent_change"] == {
        "opportunities": 2708,
        "successes": 2306,
        "rate": 0.8515509601181684,
    }
