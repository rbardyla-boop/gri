from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .data import GraphExample
from .train import set_seed


def make_optimizer(model: nn.Module, *, learning_rate: float = 3e-3) -> torch.optim.Optimizer:
    return torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)


def _capture_rng_state() -> dict[str, Any]:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }


def _restore_rng_state(state: dict[str, Any]) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])


def begin_training(seed: int) -> dict[str, Any]:
    # Matches the existing train_model behavior: training RNG is reset after
    # model construction, so data order is controlled independently of RNG
    # consumed during initialization.
    set_seed(seed)
    return _capture_rng_state()


def train_epoch_range(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    examples: list[GraphExample],
    *,
    start_epoch: int,
    end_epoch: int,
    steps: int = 4,
    batch_size: int = 16,
    rng_state: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    if start_epoch < 0 or end_epoch < start_epoch:
        raise ValueError("invalid epoch range")
    _restore_rng_state(rng_state)
    loss_fn = nn.CrossEntropyLoss()
    final_loss = 0.0
    for _epoch in range(start_epoch, end_epoch):
        model.train()
        order = list(range(len(examples)))
        random.shuffle(order)
        total = 0.0
        count = 0
        for start in range(0, len(order), batch_size):
            batch = order[start:start + batch_size]
            optimizer.zero_grad(set_to_none=True)
            losses = []
            for idx in batch:
                ex = examples[idx]
                logits = model(ex, steps=steps).unsqueeze(0)
                target = torch.tensor([ex.label], device=logits.device)
                losses.append(loss_fn(logits, target))
            loss = torch.stack(losses).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += float(loss.item()) * len(batch)
            count += len(batch)
        final_loss = total / max(1, count)
    return final_loss, _capture_rng_state()


def checkpoint_payload(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    *,
    epoch: int,
    rng_state: dict[str, Any],
    model_kind: str,
    seed: int,
) -> dict[str, Any]:
    return {
        "format": "GRI_RESUME_V1",
        "model_kind": model_kind,
        "seed": int(seed),
        "epoch": int(epoch),
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "rng_state": rng_state,
    }


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def load_checkpoint(path: Path) -> dict[str, Any]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("format") != "GRI_RESUME_V1":
        raise ValueError("unsupported resume checkpoint format")
    return payload


def restore_checkpoint(
    payload: dict[str, Any],
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
) -> tuple[int, dict[str, Any]]:
    model.load_state_dict(payload["model_state"])
    optimizer.load_state_dict(payload["optimizer_state"])
    return int(payload["epoch"]), payload["rng_state"]
