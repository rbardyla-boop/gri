"""Narrow plugin protocol for GRI-SIM-0 candidates.

This file defines interfaces only. It contains no candidate mechanism.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable
import torch
from torch import nn


@runtime_checkable
class RecurrentCellProtocol(Protocol):
    """The simulator owns time, fixtures, labels, splits, and recurrence looping."""

    state_width: int

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        ...

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        """Advance one active token. No task/delay/step metadata is provided."""
        ...

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        ...

    def serialize_state(self, state: torch.Tensor) -> bytes:
        ...

    def restore_state(self, payload: bytes, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        ...


class CandidateFactoryProtocol(Protocol):
    def build(self, *, alphabet_size: int, state_width: int, seed: int) -> nn.Module:
        ...

    def make_ablation(self, trained_model: nn.Module, name: str) -> nn.Module:
        ...
