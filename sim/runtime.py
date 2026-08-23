"""Small deterministic execution primitives owned by GRI-SIM-0.

This module is an execution shell, not a candidate mechanism.  It calls only
the narrow candidate protocol, owns restart/replay checks, and exposes a
decoder helper that accepts fit states only.
"""
from __future__ import annotations

import hashlib
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np
import torch


CellFactory = Callable[[], torch.nn.Module]


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tensor_digest(value: torch.Tensor) -> str:
    tensor = value.detach().cpu().contiguous()
    payload = {
        "dtype": str(tensor.dtype),
        "shape": list(tensor.shape),
        "bytes": tensor.numpy().tobytes().hex(),
    }
    return digest_bytes(canonical(payload).encode("utf-8"))


@dataclass(frozen=True)
class Decoder:
    """Deterministic nearest-centroid decoder fitted from fit states only."""

    labels: tuple[str, ...]
    centroids: tuple[tuple[float, ...], ...]

    def predict(self, states: np.ndarray) -> list[str]:
        values = np.asarray(states, dtype=np.float64)
        centers = np.asarray(self.centroids, dtype=np.float64)
        distances = ((values[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        return [self.labels[index] for index in distances.argmin(axis=1)]


def fit_fixed_decoder(states: Sequence[Sequence[float]], labels: Sequence[str]) -> Decoder:
    """Fit a fixed decoder without accepting held-out data or task metadata."""
    values = np.asarray(states, dtype=np.float64)
    if values.ndim != 2 or len(values) != len(labels) or not len(values):
        raise ValueError("fit states and labels must be a non-empty aligned matrix")
    grouped: dict[str, list[np.ndarray]] = defaultdict(list)
    for state, label in zip(values, labels):
        grouped[str(label)].append(state)
    ordered = sorted(grouped)
    centroids = tuple(tuple(np.mean(grouped[label], axis=0).tolist()) for label in ordered)
    return Decoder(labels=tuple(ordered), centroids=centroids)


def _fresh_state(model: torch.nn.Module) -> torch.Tensor:
    dtype = getattr(model, "state_dtype", torch.float64)
    return model.initial_state(1, dtype=dtype, device=torch.device("cpu"))


def run_recurrent_trace(factory: CellFactory, token_ids: Iterable[int], query_positions: Iterable[int] = ()) -> dict:
    """Run a candidate and verify restart at every token boundary.

    The runner supplies only ``token_id`` and persistent ``state`` to
    ``step``.  Labels, fixture ids, delays, split names, and query metadata do
    not cross this boundary.  A fresh model object restores each serialized
    prefix before running its suffix.
    """
    ids = tuple(int(value) for value in token_ids)
    query_set = {int(value) for value in query_positions}
    model = factory()
    state = _fresh_state(model)
    states = [state.detach().clone()]
    outputs: dict[str, str] = {}
    for position, token_id in enumerate(ids):
        token = torch.tensor([token_id], dtype=torch.long)
        state = model.step(token, state)
        states.append(state.detach().clone())
        if position in query_set:
            outputs[str(position)] = tensor_digest(model.readout(state))
    final_digest = tensor_digest(state)

    failures: list[dict[str, int]] = []
    for split in range(len(ids) + 1):
        resumed_model = factory()
        payload = model.serialize_state(states[split])
        dtype = getattr(resumed_model, "state_dtype", torch.float64)
        resumed = resumed_model.restore_state(payload, dtype=dtype, device=torch.device("cpu"))
        for token_id in ids[split:]:
            token = torch.tensor([token_id], dtype=torch.long)
            resumed = resumed_model.step(token, resumed)
        if not torch.equal(state, resumed):
            failures.append({"split": split})

    trace = {
        "token_ids": list(ids),
        "query_positions": sorted(query_set),
        "state_digests": [tensor_digest(value) for value in states],
        "query_digests": outputs,
        "final_state_digest": final_digest,
    }
    return {
        "status": "PASS" if not failures else "FAIL",
        "restart_cases": len(ids) + 1,
        "restart_failures": failures,
        "trace": trace,
        "trace_sha256": digest_bytes(canonical(trace).encode("utf-8")),
    }


def replay_recurrent_trace(factory: CellFactory, token_ids: Iterable[int], query_positions: Iterable[int] = ()) -> dict:
    """Run the same shell twice and compare machine-readable traces."""
    first = run_recurrent_trace(factory, token_ids, query_positions)
    second = run_recurrent_trace(factory, token_ids, query_positions)
    matched = canonical(first) == canonical(second)
    return {
        "status": "PASS" if matched and first["status"] == "PASS" else "FAIL",
        "matched": matched,
        "first_trace_sha256": first["trace_sha256"],
        "second_trace_sha256": second["trace_sha256"],
        "first": first,
        "second": second,
    }
