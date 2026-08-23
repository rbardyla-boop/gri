"""GRI-SIM-0 candidate template.

INTENTIONALLY NON-FUNCTIONAL AS A RESEARCH CANDIDATE.
A new mechanism requires separate authorization before this file is specialized.
"""
from __future__ import annotations

import io
import torch
from torch import nn


class CandidateCell(nn.Module):
    state_width = 8

    def __init__(self, alphabet_size: int, state_width: int = 8):
        super().__init__()
        if state_width != self.state_width:
            raise ValueError("state width differs from frozen candidate declaration")
        # No research mechanism is implemented here.

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.state_width, dtype=dtype, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError("candidate mechanism not authorized")

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError("candidate mechanism not authorized")

    def serialize_state(self, state: torch.Tensor) -> bytes:
        buffer = io.BytesIO()
        torch.save(state.detach().cpu(), buffer)
        return buffer.getvalue()

    def restore_state(self, payload: bytes, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        buffer = io.BytesIO(payload)
        value = torch.load(buffer, map_location=device, weights_only=True)
        return value.to(dtype=dtype, device=device)
