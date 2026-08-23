from __future__ import annotations

import io

import torch
from torch import nn

from sim.runtime import fit_fixed_decoder, replay_recurrent_trace, run_recurrent_trace


class ToyCell(nn.Module):
    state_width = 2

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        return torch.zeros(batch_size, self.state_width, dtype=dtype, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        delta = token_ids.to(dtype=state.dtype).unsqueeze(1)
        return state + torch.cat([delta, delta * 2], dim=1)

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        return state

    def serialize_state(self, state: torch.Tensor) -> bytes:
        buffer = io.BytesIO()
        torch.save(state.detach().cpu(), buffer)
        return buffer.getvalue()

    def restore_state(self, payload: bytes, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        value = torch.load(io.BytesIO(payload), map_location=device, weights_only=True)
        return value.to(dtype=dtype, device=device)


def test_runtime_calls_only_token_and_state_and_restarts_every_boundary() -> None:
    result = run_recurrent_trace(ToyCell, [1, 2, 3], query_positions=[1])
    assert result["status"] == "PASS"
    assert result["restart_cases"] == 4
    assert result["restart_failures"] == []
    assert result["trace"]["query_positions"] == [1]


def test_runtime_replay_is_exact() -> None:
    result = replay_recurrent_trace(ToyCell, [1, 2, 3], query_positions=[0, 2])
    assert result["status"] == "PASS"
    assert result["matched"] is True
    assert result["first_trace_sha256"] == result["second_trace_sha256"]


def test_fixed_decoder_is_fit_only_and_deterministic() -> None:
    decoder = fit_fixed_decoder([[0.0, 0.0], [2.0, 2.0], [0.1, 0.0], [2.1, 2.0]], ["a", "b", "a", "b"])
    assert decoder.predict([[0.05, 0.0], [2.05, 2.0]]) == ["a", "b"]
