from pathlib import Path

import numpy as np
import torch

from gri_models.data import load_examples
from gri_models.geometric import SO4GeometricReasoner
from gri_world0.frames import frames_for_entities
from gri_world0.serialization import read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _frames_tensor(sample, seed):
    frames = frames_for_entities(sample.sample_id, seed, tuple(sorted(sample.entities)))
    return torch.tensor(np.stack([frames[e] for e in sorted(sample.entities)]), dtype=torch.float32)


def test_geometric_forward_is_frame_invariant():
    path = ROOT / "artifacts/frozen/world0_v0_1/train.jsonl"
    sample = read_jsonl(path)[5]
    ex = load_examples(path)[5]
    torch.manual_seed(7)
    model = SO4GeometricReasoner(semantic_dim=16, channels=2, message_dim=16)
    model.eval()
    with torch.no_grad():
        canonical = model(ex, steps=3)
        rotated_a = model(ex, steps=3, frames=_frames_tensor(sample, 111))
        rotated_b = model(ex, steps=3, frames=_frames_tensor(sample, 222))
    assert torch.allclose(canonical, rotated_a, atol=2e-5, rtol=2e-5)
    assert torch.allclose(canonical, rotated_b, atol=2e-5, rtol=2e-5)


def test_geometric_connections_transport_canonical_state_exactly():
    path = ROOT / "artifacts/frozen/world0_v0_1/train.jsonl"
    sample = read_jsonl(path)[0]
    ex = load_examples(path)[0]
    model = SO4GeometricReasoner(semantic_dim=8, channels=2, message_dim=8)
    frames = _frames_tensor(sample, 123)
    _, v, q = model.initialize(ex, frames)
    u = model.connections(q)
    j, i = 0, min(1, len(sample.entities) - 1)
    transported = u[j, i] @ v[j]
    # Recover canonical Z_j then express it in frame i.
    z_j = q[j].T @ v[j]
    expected = q[i] @ z_j
    assert torch.allclose(transported, expected, atol=1e-5, rtol=1e-5)
