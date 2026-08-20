from __future__ import annotations

from typing import Any

import torch

from .data import GraphExample


TRACE_STEPS = (1, 2, 4, 8, 16, 32, 64)
GRADIENT_STEPS = (1, 2, 4, 8, 16, 32, 64, 128)
ANALYSIS_STEPS = tuple(range(1, 129))
TRACE_TOLERANCE = 1e-6


def readout_from_hidden(model: torch.nn.Module, h: torch.Tensor, example: GraphExample) -> torch.Tensor:
    a = h[example.query_subject]
    b = h[example.query_object]
    features = torch.cat([a, b, a - b, a * b], dim=-1)
    return model.readout(features)


def traced_forward(
    model: torch.nn.Module, example: GraphExample, *, steps: int
) -> tuple[torch.Tensor, list[torch.Tensor]]:
    """Analysis-only wrapper around the frozen initialize/recurrent/readout path."""
    h = model.initialize(example)
    states = [h]
    edges = example.edges.to(h.device)
    for _ in range(steps):
        h = model.recurrent_step(h, edges)
        states.append(h)
    return readout_from_hidden(model, h, example), states


def tensor_state_hash(state: dict[str, Any]) -> str:
    import io
    import hashlib

    normalized = {name: state[name].detach().cpu().clone() for name in sorted(state)}
    buf = io.BytesIO()
    torch.save(normalized, buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def model_state_equal(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(torch.equal(before[name], after[name]) for name in before)
