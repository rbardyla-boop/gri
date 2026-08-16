from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

from .data import GraphExample


@dataclass(frozen=True)
class TrainResult:
    final_loss: float
    train_accuracy: float


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def accuracy(model: nn.Module, examples: list[GraphExample], *, steps: int) -> float:
    model.eval()
    correct = 0
    with torch.no_grad():
        for ex in examples:
            pred = int(model(ex, steps=steps).argmax().item())
            correct += pred == ex.label
    return correct / max(1, len(examples))


def train_model(
    model: nn.Module,
    examples: list[GraphExample],
    *, epochs: int = 120,
    steps: int = 4,
    learning_rate: float = 3e-3,
    seed: int = 1337,
    batch_size: int = 16,
) -> TrainResult:
    set_seed(seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    final_loss = 0.0
    for _ in range(epochs):
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
    return TrainResult(final_loss, accuracy(model, examples, steps=steps))
