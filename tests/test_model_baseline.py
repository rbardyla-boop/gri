from pathlib import Path

import torch

from gri_models.baseline import WeightTiedGraphReasoner
from gri_models.data import load_examples

ROOT = Path(__file__).resolve().parents[1]


def test_baseline_forward_and_weight_tied_depth():
    ex = load_examples(ROOT / "artifacts/frozen/world0_v0_1/train.jsonl")[0]
    model = WeightTiedGraphReasoner(hidden_dim=16, message_dim=16)
    y1 = model(ex, steps=1)
    y4 = model(ex, steps=4)
    assert y1.shape == (8,)
    assert y4.shape == (8,)
    assert torch.isfinite(y4).all()


def test_model_initialization_is_seed_replayable():
    from gri_models.train import set_seed
    set_seed(2026)
    a = WeightTiedGraphReasoner(hidden_dim=8, message_dim=8)
    set_seed(2026)
    b = WeightTiedGraphReasoner(hidden_dim=8, message_dim=8)
    for pa, pb in zip(a.parameters(), b.parameters()):
        assert torch.equal(pa, pb)
