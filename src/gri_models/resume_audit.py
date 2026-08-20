from __future__ import annotations

import hashlib
import io
import tempfile
from pathlib import Path

import numpy as np
import torch

from .data import load_examples
from .gri05 import build_model
from .resume import (
    begin_training,
    checkpoint_payload,
    load_checkpoint,
    make_optimizer,
    restore_checkpoint,
    save_checkpoint,
    train_epoch_range,
)

AUDIT_SEED = 9090


def tensor_state_hash(state: dict) -> str:
    buf = io.BytesIO()
    torch.save(state, buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def rng_equal(a, b) -> bool:
    if a["python"] != b["python"]:
        return False
    na, nb = a["numpy"], b["numpy"]
    if na[0] != nb[0] or not np.array_equal(na[1], nb[1]) or na[2:] != nb[2:]:
        return False
    return torch.equal(a["torch"], b["torch"])


def optimizer_equal(a, b) -> bool:
    if a.keys() != b.keys() or a["param_groups"] != b["param_groups"] or a["state"].keys() != b["state"].keys():
        return False
    for key in a["state"]:
        sa, sb = a["state"][key], b["state"][key]
        if sa.keys() != sb.keys():
            return False
        for field in sa:
            x, y = sa[field], sb[field]
            if isinstance(x, torch.Tensor):
                if not torch.equal(x, y):
                    return False
            elif x != y:
                return False
    return True


def audit(kind: str, artifact_dir: Path, *, total_epochs: int = 4, split_epoch: int = 2) -> dict:
    torch.set_num_threads(1)
    examples = load_examples(artifact_dir / "train.jsonl")[:16]

    full = build_model(kind, AUDIT_SEED)
    full_opt = make_optimizer(full)
    full_rng = begin_training(AUDIT_SEED)
    full_loss, full_rng = train_epoch_range(
        full, full_opt, examples, start_epoch=0, end_epoch=total_epochs,
        steps=4, batch_size=16, rng_state=full_rng,
    )

    part = build_model(kind, AUDIT_SEED)
    part_opt = make_optimizer(part)
    part_rng = begin_training(AUDIT_SEED)
    _, part_rng = train_epoch_range(
        part, part_opt, examples, start_epoch=0, end_epoch=split_epoch,
        steps=4, batch_size=16, rng_state=part_rng,
    )

    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "resume.pt"
        save_checkpoint(cp, checkpoint_payload(
            part, part_opt, epoch=split_epoch, rng_state=part_rng,
            model_kind=kind, seed=AUDIT_SEED,
        ))
        resumed = build_model(kind, AUDIT_SEED)
        resumed_opt = make_optimizer(resumed)
        epoch, resumed_rng = restore_checkpoint(load_checkpoint(cp), resumed, resumed_opt)
        resumed_loss, resumed_rng = train_epoch_range(
            resumed, resumed_opt, examples, start_epoch=epoch, end_epoch=total_epochs,
            steps=4, batch_size=16, rng_state=resumed_rng,
        )

    model_equal = all(torch.equal(a, b) for a, b in zip(full.state_dict().values(), resumed.state_dict().values()))
    opt_equal = optimizer_equal(full_opt.state_dict(), resumed_opt.state_dict())
    random_equal = rng_equal(full_rng, resumed_rng)
    return {
        "model": kind,
        "audit_seed": AUDIT_SEED,
        "examples": len(examples),
        "total_epochs": total_epochs,
        "split_epoch": split_epoch,
        "model_state_equal": model_equal,
        "optimizer_state_equal": opt_equal,
        "rng_state_equal": random_equal,
        "final_loss_equal": full_loss == resumed_loss,
        "uninterrupted_model_hash": tensor_state_hash(full.state_dict()),
        "resumed_model_hash": tensor_state_hash(resumed.state_dict()),
    }
