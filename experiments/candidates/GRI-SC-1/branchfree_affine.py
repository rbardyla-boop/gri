"""GRI-SC-1 DEV_SMOKE candidate A: the existing branch-free affine tanh cell."""
from __future__ import annotations

import io
import torch
from torch import nn


class BranchFreeAffineCell(nn.Module):
    """Token-dependent arithmetic with no explicit semantic selector."""

    state_width = 8

    def __init__(self, alphabet_size: int, state_width: int = 8):
        super().__init__()
        if state_width != self.state_width:
            raise ValueError("state width differs from SC-1 declaration")
        self.input = nn.Embedding(alphabet_size, state_width)
        self.transition = nn.Linear(state_width, state_width, bias=True)
        self.readout_layer = nn.Linear(state_width, 2, bias=True)

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.state_width, dtype=dtype, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.transition(state) + self.input(token_ids))

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        return self.readout_layer(state)

    def serialize_state(self, state: torch.Tensor) -> bytes:
        buffer = io.BytesIO()
        torch.save(state.detach().cpu(), buffer)
        return buffer.getvalue()

    def restore_state(self, payload: bytes, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        buffer = io.BytesIO(payload)
        value = torch.load(buffer, map_location=device, weights_only=True)
        return value.to(dtype=dtype, device=device)
