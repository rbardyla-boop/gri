from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from torch.nn.utils import clip_grad_norm_

from dmc00.benchmark import VALUES

from .memory import DMC01Controller


@dataclass(frozen=True)
class DMC01TrainingConfig:
    epochs: int = 80
    batch_size: int = 16
    learning_rate: float = 3e-3
    weight_decay: float = 1e-4
    gradient_clip: float = 1.0
    train_depth: int = 4
    device: str = "cpu"
    torch_threads: int = 1
    optimizer: str = "AdamW"
    scheduler: str | None = None


FROZEN_TRAINING_CONFIG = DMC01TrainingConfig()


def target_for_case(case: dict[str, Any]) -> int:
    """Construct the sole supervised target; never passed into event code."""

    answer = case["answer"]
    if answer not in VALUES:
        raise ValueError(f"unknown DMC answer: {answer}")
    return VALUES.index(answer)


def run_case_logits(controller: DMC01Controller, case: dict[str, Any]) -> torch.Tensor:
    """Process one complete case and return only its final-query logits.

    This function intentionally never reads the supervised label. The caller
    constructs that target separately with ``target_for_case``.
    """

    controller.reset_case()
    final_logits: torch.Tensor | None = None
    try:
        episodes = case["episodes"]
        for episode_position, episode in enumerate(episodes):
            if episode["index"] != episode_position:
                raise ValueError("case episodes must be contiguous and ordered")
            for event in episode["events"]:
                kind = event["kind"]
                if kind == "write":
                    if episode_position == len(episodes) - 1:
                        raise ValueError("write cannot occur in the final query episode")
                    controller.process_write(event, episode_position)
                elif kind == "noise":
                    if episode_position == len(episodes) - 1:
                        raise ValueError("noise cannot occur in the final query episode")
                    controller.process_noise(event)
                elif kind == "query":
                    if episode_position != len(episodes) - 1 or final_logits is not None:
                        raise ValueError("exactly one final query is required")
                    final_logits = controller.answer_query(event)
                else:
                    raise ValueError(f"unsupported DMC event kind: {kind}")
        if final_logits is None:
            raise ValueError("case has no final query")
        return final_logits
    finally:
        # This releases the ledger's case-local references after the returned
        # logits have captured the graph needed by the current batch loss.
        controller.reset_case()


def case_cross_entropy(logits: torch.Tensor, target: int) -> torch.Tensor:
    if logits.shape != (len(VALUES),):
        raise ValueError(f"expected {len(VALUES)} logits, got {tuple(logits.shape)}")
    target_tensor = torch.tensor(target, dtype=torch.long, device=logits.device)
    return F.cross_entropy(
        logits.unsqueeze(0),
        target_tensor.unsqueeze(0),
        reduction="mean",
    )


def complete_case_batch_loss(
    controller: DMC01Controller,
    cases: Sequence[dict[str, Any]],
) -> tuple[torch.Tensor, list[torch.Tensor]]:
    if not cases:
        raise ValueError("empty case batch")
    losses: list[torch.Tensor] = []
    logits: list[torch.Tensor] = []
    for case in cases:
        case_logits = run_case_logits(controller, case)
        logits.append(case_logits)
        losses.append(case_cross_entropy(case_logits, target_for_case(case)))
    return torch.stack(losses).mean(), logits


def train_complete_case_batch(
    controller: DMC01Controller,
    cases: Sequence[dict[str, Any]],
    optimizer: torch.optim.Optimizer,
    *,
    gradient_clip: float = FROZEN_TRAINING_CONFIG.gradient_clip,
) -> dict[str, float]:
    """Perform exactly one optimizer step for one complete-case batch."""

    controller.train()
    optimizer.zero_grad(set_to_none=True)
    batch_loss, _ = complete_case_batch_loss(controller, cases)
    batch_loss.backward()
    gradient_norm = clip_grad_norm_(controller.parameters(), max_norm=gradient_clip)
    optimizer.step()
    return {"batch_loss": float(batch_loss.detach().cpu()), "gradient_norm": float(gradient_norm.detach().cpu())}


def order_key(seed: int, epoch: int, case_id: str) -> bytes:
    payload = f"DMC01_ORDER|{seed}|{epoch}|{case_id}".encode("utf-8")
    return hashlib.sha256(payload).digest()


def ordered_cases(cases: Sequence[dict[str, Any]], *, seed: int, epoch: int) -> list[dict[str, Any]]:
    return sorted(cases, key=lambda case: order_key(seed, epoch, case["case_id"]))


def case_batches(
    cases: Sequence[dict[str, Any]],
    *,
    seed: int,
    epoch: int,
    batch_size: int = FROZEN_TRAINING_CONFIG.batch_size,
) -> Iterator[list[dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    ordered = ordered_cases(cases, seed=seed, epoch=epoch)
    for start in range(0, len(ordered), batch_size):
        yield ordered[start : start + batch_size]


def order_manifest(cases: Sequence[dict[str, Any]], seeds: Iterable[int]) -> dict[str, Any]:
    return {
        "algorithm": "SHA256('DMC01_ORDER|' + str(seed) + '|' + str(epoch) + '|' + case_id)",
        "sort": "ascending raw SHA-256 digest bytes",
        "epoch_numbers": [0, FROZEN_TRAINING_CONFIG.epochs - 1],
        "batch_size": FROZEN_TRAINING_CONFIG.batch_size,
        "seeds": {
            str(seed): {
                "epochs": [
                    {
                        "epoch": epoch,
                        "ordered_case_ids": [case["case_id"] for case in ordered_cases(cases, seed=seed, epoch=epoch)],
                        "batches": [[case["case_id"] for case in batch] for batch in case_batches(cases, seed=seed, epoch=epoch)],
                    }
                    for epoch in range(FROZEN_TRAINING_CONFIG.epochs)
                ]
            }
            for seed in seeds
        },
    }


def capture_rng_state() -> dict[str, Any]:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }


def restore_rng_state(state: dict[str, Any]) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])


def checkpoint_payload(
    controller: DMC01Controller,
    optimizer: torch.optim.Optimizer,
    *,
    seed: int,
    completed_epoch: int,
    next_batch_index: int,
    source_commit: str,
    dataset_identity: dict[str, Any],
    final_loss: float | None = None,
    metrics: dict[str, Any] | None = None,
    training_config: DMC01TrainingConfig = FROZEN_TRAINING_CONFIG,
) -> dict[str, Any]:
    """Build a post-step checkpoint payload; no checkpoint is written here."""

    if completed_epoch < 0 or next_batch_index < 0:
        raise ValueError("invalid checkpoint position")
    return {
        "model_state_dict": copy.deepcopy(controller.state_dict()),
        "optimizer_state": copy.deepcopy(optimizer.state_dict()),
        "seed": seed,
        "completed_epoch": completed_epoch,
        "next_batch_index": next_batch_index,
        "python_rng_state": capture_rng_state()["python"],
        "numpy_rng_state": capture_rng_state()["numpy"],
        "torch_rng_state": capture_rng_state()["torch"],
        "training_config": asdict(training_config),
        "source_commit": source_commit,
        "dmc00_dataset_identity": dataset_identity,
        "final_loss": final_loss,
        "metrics": metrics or {},
        "checkpoint_boundary": "immediately after one complete optimizer step",
    }


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def load_checkpoint(
    path: Path,
    controller: DMC01Controller,
    optimizer: torch.optim.Optimizer,
) -> dict[str, Any]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    controller.load_state_dict(payload["model_state_dict"])
    optimizer.load_state_dict(payload["optimizer_state"])
    restore_rng_state({"python": payload["python_rng_state"], "numpy": payload["numpy_rng_state"], "torch": payload["torch_rng_state"]})
    return payload


def json_training_config() -> dict[str, Any]:
    return asdict(FROZEN_TRAINING_CONFIG)
