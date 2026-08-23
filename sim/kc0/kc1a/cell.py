"""KC-1A — the smallest lifecycle-only knowledge cell.

This candidate is intentionally non-learning and non-reproductive.  Its
persistent state is eight integer value slots plus eight explicit occupancy
bits.  A consumed token deterministically replaces one slot selected by the
token modulo eight.  No global step counter or auxiliary history exists.
"""
from __future__ import annotations

import struct

import numpy as np
import torch
from torch import nn


SLOT_COUNT = 8
STATE_WIDTH = SLOT_COUNT * 2
STATE_DTYPE = torch.int64
STATE_BYTES_MAX = STATE_WIDTH * 8
SERIAL_MAGIC = b"KC1A"
SERIAL_VERSION = 1


class KC1ACell(nn.Module):
    """Deterministic lifecycle probe with explicit bounded persistent state."""

    state_width = STATE_WIDTH
    state_dtype = STATE_DTYPE

    def __init__(self) -> None:
        super().__init__()
        # This cell has no trainable or mutable module parameters.

    def initial_state(self, batch_size: int, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        if dtype != STATE_DTYPE:
            raise ValueError("KC-1A state requires torch.int64")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        return torch.zeros(batch_size, STATE_WIDTH, dtype=STATE_DTYPE, device=device)

    def step(self, token_ids: torch.Tensor, state: torch.Tensor) -> torch.Tensor:
        """Consume only ``token_ids`` and the persistent ``state``."""
        if token_ids.ndim != 1 or state.ndim != 2 or state.shape[0] != token_ids.shape[0]:
            raise ValueError("token_ids and state batch shapes are incompatible")
        if state.shape[1] != STATE_WIDTH or state.dtype != STATE_DTYPE:
            raise ValueError("state shape or dtype differs from KC-1A declaration")
        if torch.any(token_ids < 0):
            raise ValueError("token ids must be non-negative")

        slots = state[:, :SLOT_COUNT]
        occupancy = state[:, SLOT_COUNT:]
        selected = torch.remainder(token_ids, SLOT_COUNT)
        one_hot = torch.nn.functional.one_hot(selected, num_classes=SLOT_COUNT).to(dtype=STATE_DTYPE)
        value = (torch.remainder(token_ids, 65535) + 1).to(dtype=STATE_DTYPE).unsqueeze(1)
        next_slots = slots * (1 - one_hot) + one_hot * value
        next_occupancy = torch.maximum(occupancy, one_hot)
        return torch.cat([next_slots, next_occupancy], dim=1)

    def readout(self, state: torch.Tensor) -> torch.Tensor:
        if state.ndim != 2 or state.shape[1] != STATE_WIDTH or state.dtype != STATE_DTYPE:
            raise ValueError("state shape or dtype differs from KC-1A declaration")
        return state.detach().clone()

    def serialize_state(self, state: torch.Tensor) -> bytes:
        if state.ndim != 2 or state.shape[0] != 1 or state.shape[1] != STATE_WIDTH or state.dtype != STATE_DTYPE:
            raise ValueError("KC-1A serialization requires one state row")
        value = state.detach().cpu().contiguous().numpy().astype("<i8", copy=False)
        header = SERIAL_MAGIC + struct.pack("<BHH", SERIAL_VERSION, 1, STATE_WIDTH)
        payload = header + value.tobytes(order="C")
        if len(payload) != len(header) + STATE_BYTES_MAX:
            raise ValueError("serialized KC-1A state has unexpected size")
        return payload

    def restore_state(self, payload: bytes, *, dtype: torch.dtype, device: torch.device) -> torch.Tensor:
        header_size = len(SERIAL_MAGIC) + struct.calcsize("<BHH")
        expected_size = header_size + STATE_BYTES_MAX
        if len(payload) != expected_size or payload[: len(SERIAL_MAGIC)] != SERIAL_MAGIC:
            raise ValueError("invalid KC-1A state payload")
        version, rows, width = struct.unpack("<BHH", payload[len(SERIAL_MAGIC) : header_size])
        if version != SERIAL_VERSION or rows != 1 or width != STATE_WIDTH:
            raise ValueError("unsupported KC-1A state payload")
        value = np.frombuffer(payload[header_size:], dtype="<i8").reshape(1, STATE_WIDTH).copy()
        tensor = torch.from_numpy(value).to(device=device)
        if dtype != STATE_DTYPE:
            raise ValueError("KC-1A state requires torch.int64")
        return tensor

    def resource_manifest(self) -> dict[str, object]:
        return {
            "candidate_id": "KC-1A-ISOLATED-KNOWLEDGE-CELL",
            "candidate_version": "0.1.0",
            "state_bytes_max": STATE_BYTES_MAX,
            "persistent_scalar_count": STATE_WIDTH,
            "value_slots": SLOT_COUNT,
            "occupancy_bits": SLOT_COUNT,
            "step_operation_budget": 12,
            "readout_operation_budget": STATE_WIDTH,
            "uses_rng": False,
            "uses_wall_clock": False,
            "uses_filesystem": False,
            "uses_network": False,
            "uses_environment": False,
            "uses_optimizer": False,
            "uses_external_model": False,
            "has_step_counter": False,
            "has_history_buffer": False,
            "has_population_logic": False,
        }
