from __future__ import annotations

from dataclasses import fields
import inspect

import numpy as np

import dual_authority0
from dual_authority0 import (
    ACT_DERIVE,
    ACT_OBSERVE,
    ACT_PROPOSE,
    EpistemicStore,
    Packet,
    STATUS_COMMITTED,
    STATUS_PROVISIONAL,
    STATUS_REVOKED,
    decode_packet,
    derive_from_committed_coordinates,
    encode_packet,
    evaluator_truth,
    flatten_prediction_packets,
    flatten_truth_packets,
    flatten_witness_packets,
    materialize_prediction,
    materialize_world_witness,
)


def test_packet_contract_is_exactly_six_integer_fields() -> None:
    assert [field.name for field in fields(Packet)] == [
        "stable_reference",
        "act",
        "subject",
        "relation",
        "object",
        "value",
    ]
    packet = Packet(17, ACT_PROPOSE, 3, 4, 5, -7)
    assert all(isinstance(value, int) for value in packet.numeric_tuple())


def test_packet_varint_roundtrip_is_exact_and_deterministic() -> None:
    packet = Packet(987654321, ACT_OBSERVE, 44, 3, 99, -12)
    first = encode_packet(packet)
    second = encode_packet(packet)
    assert first == second
    assert decode_packet(first) == packet


def test_proposal_cannot_become_durable_without_world_root() -> None:
    store = EpistemicStore()
    packet = Packet(1, ACT_PROPOSE, 1, 1, 0, 4)
    store.propose(packet)
    assert store.status(1, 4) == STATUS_PROVISIONAL
    assert store.committed_values(1) == ()


def test_world_observation_replaces_matching_proposal_support() -> None:
    store = EpistemicStore()
    proposal = Packet(1, ACT_PROPOSE, 1, 1, 0, 4)
    proposal_support = store.propose(proposal)
    witness = Packet(1, ACT_OBSERVE, 1, 1, 0, 4)
    store.observe(witness)
    assert store.status(1, 4) == STATUS_COMMITTED
    assert store.committed_values(1) == (4,)
    assert not store.supports[proposal_support].enabled


def test_conflicting_world_witness_revokes_prediction_and_descendants() -> None:
    store = EpistemicStore()
    left = Packet(1, ACT_PROPOSE, 1, 1, 0, 3)
    right = Packet(2, ACT_PROPOSE, 2, 1, 0, 8)
    store.propose(left)
    store.propose(right)
    relation = Packet(3, ACT_DERIVE, 1, 3, 2, 1)
    relation_support = store.derive(
        relation,
        (store.claim_key(left), store.claim_key(right)),
    )
    parity = Packet(4, ACT_DERIVE, 1, 5, 2, 1)
    parity_support = store.derive(parity, (store.claim_key(relation),))

    assert store.status(3, 1) == STATUS_PROVISIONAL
    assert store.status(4, 1) == STATUS_PROVISIONAL
    store.observe(Packet(1, ACT_OBSERVE, 1, 1, 0, 9))

    assert store.status(1, 3) == STATUS_REVOKED
    assert not store.support_effective(relation_support)
    assert not store.support_effective(parity_support)
    assert store.status(3, 1) == STATUS_REVOKED
    assert store.status(4, 1) == STATUS_REVOKED
    assert store.cascaded_support_count >= 2


def test_claim_level_world_support_preserves_child_when_proposal_is_retired() -> None:
    store = EpistemicStore()
    left = Packet(1, ACT_PROPOSE, 1, 1, 0, 3)
    right = Packet(2, ACT_PROPOSE, 2, 1, 0, 8)
    store.propose(left)
    store.propose(right)
    relation = Packet(3, ACT_DERIVE, 1, 3, 2, 1)
    relation_support = store.derive(
        relation,
        (store.claim_key(left), store.claim_key(right)),
    )

    store.observe(Packet(1, ACT_OBSERVE, 1, 1, 0, 3))
    store.observe(Packet(2, ACT_OBSERVE, 2, 1, 0, 8))

    # Matching prediction supports were retired, but the parent claims now have
    # independent world roots. The existing child support survives and grounds.
    assert store.support_effective(relation_support)
    assert store.status(3, 1) == STATUS_COMMITTED


def test_world_witness_is_primary_coordinates_only() -> None:
    state = np.array([-0.5, -0.5, 0.0, 0.0, 0.5, 0.5], dtype=np.float32)
    store = EpistemicStore()
    bundle = materialize_world_witness(store, state, 0, 20)
    witness_packets = flatten_witness_packets(bundle)
    assert len(witness_packets) == 6
    assert all(packet.relation in (1, 2) for packet in witness_packets)
    assert all(
        store.committed_values(packet.stable_reference) == (packet.value,)
        for packet in witness_packets
    )


def test_prediction_then_witness_then_grounded_recompute_commits_truth() -> None:
    state = np.array([-0.5, -0.5, 0.0, 0.0, 0.5, 0.5], dtype=np.float32)
    store = EpistemicStore()
    prediction = materialize_prediction(store, state, 0, 20)
    predicted_packets = flatten_prediction_packets(prediction)
    assert len(predicted_packets) == 13
    assert all(
        store.status(packet.stable_reference, packet.value) == STATUS_PROVISIONAL
        for packet in predicted_packets
    )

    materialize_world_witness(store, state, 0, 20)
    derive_from_committed_coordinates(store, state, 0, 20)
    truth_packets = flatten_truth_packets(evaluator_truth(state, 0, 20))
    assert len(truth_packets) == 13
    assert all(
        store.committed_values(packet.stable_reference) == (packet.value,)
        for packet in truth_packets
    )


def test_wrong_prediction_is_rolled_back_without_direct_descendant_witness() -> None:
    predicted = np.array([-0.5, -0.5, 0.0, 0.0, 0.5, 0.5], dtype=np.float32)
    observed = np.array([0.5, -0.5, 0.0, 0.0, -0.5, 0.5], dtype=np.float32)
    store = EpistemicStore()
    prediction = materialize_prediction(store, predicted, 0, 21)
    predicted_packets = flatten_prediction_packets(prediction)
    truth_packets = flatten_truth_packets(evaluator_truth(observed, 0, 21))
    truth_by_reference = {
        packet.stable_reference: packet
        for packet in truth_packets
    }

    # Only six coordinate witnesses are admitted. Relations/parity are not
    # directly corrected by the witness interface.
    materialize_world_witness(store, observed, 0, 21)
    derive_from_committed_coordinates(store, observed, 0, 21)

    wrong = [
        packet
        for packet in predicted_packets
        if packet.value != truth_by_reference[packet.stable_reference].value
    ]
    assert wrong
    assert any(packet.relation not in (1, 2) for packet in wrong)
    for packet in wrong:
        assert store.status(packet.stable_reference, packet.value) == STATUS_REVOKED


def test_numeric_ledger_replays_exactly() -> None:
    store = EpistemicStore()
    state = np.array([-0.5, -0.5, 0.0, 0.0, 0.5, 0.5], dtype=np.float32)
    materialize_prediction(store, state, 0, 3)
    materialize_world_witness(store, state, 0, 3)
    derive_from_committed_coordinates(store, state, 0, 3)
    assert store.ledger.count > 0
    assert store.ledger.head_sha256 == store.ledger.replay_head()


def test_active_claim_bound_fails_closed() -> None:
    store = EpistemicStore(max_claims=2)
    store.propose(Packet(1, ACT_PROPOSE, 1, 1, 0, 1))
    store.propose(Packet(2, ACT_PROPOSE, 2, 1, 0, 1))
    try:
        store.propose(Packet(3, ACT_PROPOSE, 3, 1, 0, 1))
    except MemoryError:
        pass
    else:
        raise AssertionError("active claim bound was bypassed")


def test_epistemic_path_has_no_forbidden_model_or_evaluator_inputs() -> None:
    source = inspect.getsource(dual_authority0)
    lowered = source.lower()
    for forbidden in (
        "import transformers",
        "from transformers",
        "import whisper",
        "from whisper",
        "import clip",
        "from clip",
        "tokenizer(",
        "transcript",
        ".mode",
        ".rule_event",
        ".collision",
        ".boundary",
    ):
        assert forbidden not in lowered
