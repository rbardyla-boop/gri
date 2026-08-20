from pathlib import Path

import torch

from gri_models.baseline import WeightTiedGraphReasoner
from gri_models.data import load_examples
from gri_models.rri02pa import ImmutableRelationAnchorReasoner
from gri_models.train import set_seed


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = load_examples(ROOT / "artifacts/frozen/world0_v0_1/train.jsonl")[0]
HIDDEN = 49
MESSAGE = 51
EXPECTED_PARAMETERS = 30_912


def _models_with_identical_initialization():
    set_seed(9091)
    baseline = WeightTiedGraphReasoner(hidden_dim=HIDDEN, message_dim=MESSAGE)
    set_seed(9091)
    anchor = ImmutableRelationAnchorReasoner(hidden_dim=HIDDEN, message_dim=MESSAGE)
    return baseline, anchor


def test_anchor_has_exact_baseline_capacity_and_identical_initial_state():
    baseline, anchor = _models_with_identical_initialization()
    assert sum(p.numel() for p in baseline.parameters() if p.requires_grad) == EXPECTED_PARAMETERS
    assert sum(p.numel() for p in anchor.parameters() if p.requires_grad) == EXPECTED_PARAMETERS
    assert list(baseline.state_dict()) == list(anchor.state_dict())
    for left, right in zip(baseline.state_dict().values(), anchor.state_dict().values()):
        assert torch.equal(left, right)


def test_first_step_and_one_step_logits_match_at_anchor_initialization():
    baseline, anchor = _models_with_identical_initialization()
    baseline.eval()
    anchor.eval()
    with torch.no_grad():
        h0 = baseline.initialize(EXAMPLE)
        edges = EXAMPLE.edges
        baseline_h1 = baseline.recurrent_step(h0, edges)
        anchor_h1 = anchor.recurrent_step(h0.clone(), edges, h0.clone())
        baseline_logits = baseline(EXAMPLE, steps=1)
        anchor_logits = anchor(EXAMPLE, steps=1)
    assert torch.equal(baseline_h1, anchor_h1)
    assert torch.equal(baseline_logits, anchor_logits)


def test_anchor_is_immutable_and_not_aliased_over_all_protocol_depths():
    _, anchor = _models_with_identical_initialization()
    anchor.eval()
    with torch.no_grad():
        h0 = anchor.initialize(EXAMPLE)
        anchor_copy = anchor.make_anchor(h0)
    assert anchor_copy.data_ptr() != h0.data_ptr()
    anchor_before = anchor_copy.clone()
    edges = EXAMPLE.edges
    for steps in (1, 2, 4, 8, 16, 32, 64, 128):
        with torch.no_grad():
            _, states, anchors = anchor.forward_with_anchor_trace(EXAMPLE, steps=steps)
        assert len(states) == steps + 1
        assert len(anchors) == steps + 1
        for recorded in anchors:
            assert torch.equal(recorded, anchors[0])
            assert recorded.data_ptr() != states[0].data_ptr()
        assert torch.equal(anchors[0], anchor.initialize(EXAMPLE))
    with torch.no_grad():
        mutable = h0.clone()
        for _ in range(128):
            mutable = anchor.recurrent_step(mutable, edges, anchor_copy)
    assert torch.equal(anchor_copy, anchor_before)


def test_readout_firewall_uses_mutable_state_only():
    _, anchor = _models_with_identical_initialization()
    assert anchor.readout[0].in_features == HIDDEN * 4
    assert "anchor" not in anchor.readout_hidden.__code__.co_varnames
    with torch.no_grad():
        _, states, _ = anchor.forward_with_anchor_trace(EXAMPLE, steps=4)
        from_mutable = anchor.readout_hidden(states[-1], EXAMPLE.query_subject, EXAMPLE.query_object)
        perturbed = anchor.readout_hidden(states[-1] + 0.0, EXAMPLE.query_subject, EXAMPLE.query_object)
    assert torch.equal(from_mutable, perturbed)
