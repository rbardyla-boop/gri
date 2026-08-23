"""GRI-SC-1 DEV_SMOKE candidate B: branch-free token-coded residual update."""
from __future__ import annotations

import io
import torch
from torch import nn


class BranchFreeResidualCell(nn.Module):
    """Uses one fixed embedding coordinate as a 0/1 residual coefficient.

    WAIT has coefficient 0 and information-changing tokens coefficient 1. The
    runtime performs no equality test or branch; the coefficient is delivered
    by the same token lookup used by the transform.
    """

    state_width = 8

    def __init__(self, alphabet_size: int, state_width: int = 8, wait_index: int = 6):
        super().__init__()
        if state_width != self.state_width:
            raise ValueError("state width differs from SC-1 declaration")
        self.wait_index = wait_index
        self.input = nn.Embedding(alphabet_size, state_width)
        self.diagonal = nn.Parameter(torch.ones(state_width))
        self.readout_layer = nn.Linear(state_width, 2, bias=True)
        codes = torch.ones(alphabet_size, 1)
        codes[wait_index, 0] = 0.0
        with torch.no_grad():
            self.input.weight[:, :1].copy_(codes)
        frozen_code_mask = torch.ones_like(self.input.weight)
        frozen_code_mask[:, :1] = 0.0
        self.input.weight.register_hook(lambda grad: grad * frozen_code_mask)

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.state_width, dtype=dtype, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        embedded = self.input(token_ids)
        transformed = torch.tanh(state * self.diagonal + embedded)
        residual = transformed - state
        return state + embedded[:, :1] * residual

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
