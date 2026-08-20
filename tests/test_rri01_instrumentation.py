from pathlib import Path

import torch

from gri_models.data import load_examples
from gri_models.gri05 import build_model
from gri_models.rri01 import TRACE_STEPS, TRACE_TOLERANCE, model_state_equal, tensor_state_hash, traced_forward
from gri_models.resume import load_checkpoint

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINTS = ROOT / "artifacts/rri01r/checkpoints"


def test_traced_forward_matches_frozen_forward_at_required_steps():
    examples = load_examples(ROOT / "artifacts/frozen/world0_v0_1/test_depth_64.jsonl")[:2]
    for seed in (1337, 1341):
        model = build_model("baseline", seed)
        payload = load_checkpoint(CHECKPOINTS / f"baseline_seed{seed}_final.pt")
        model.load_state_dict(payload["model_state"])
        model.eval()
        before = {k: v.clone() for k, v in model.state_dict().items()}
        with torch.no_grad():
            for example in examples:
                for steps in TRACE_STEPS:
                    ordinary = model(example, steps=steps)
                    traced, states = traced_forward(model, example, steps=steps)
                    assert len(states) == steps + 1
                    assert torch.allclose(ordinary, traced, atol=TRACE_TOLERANCE, rtol=TRACE_TOLERANCE)
        after = model.state_dict()
        assert tensor_state_hash(before) == tensor_state_hash(after)
        assert model_state_equal(before, after)
