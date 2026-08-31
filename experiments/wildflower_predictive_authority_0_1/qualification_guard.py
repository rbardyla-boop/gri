"""Fail-closed execution guard for the design-only successor."""

from __future__ import annotations

import json
from pathlib import Path

from . import design

AUTHORIZATION_PATH = Path(__file__).with_name("EXECUTION_AUTHORIZATION.json")


def assert_seed_is_registered(seed: int) -> None:
    if design.reserved_seed(seed):
        raise ValueError(f"historical seed is not reusable in successor: {seed}")
    if seed not in design.MODEL_SEEDS:
        raise ValueError(f"unregistered predictive-authority seed: {seed}")


def assert_seed_authorized(seed: int) -> None:
    assert_seed_is_registered(seed)
    if not AUTHORIZATION_PATH.exists():
        raise RuntimeError(
            f"scientific execution is locked during design-only pass: seed {seed}"
        )
    try:
        payload = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("execution authorization is unreadable") from exc
    if payload.get("status") != "AUTHORIZED":
        raise RuntimeError("scientific execution is locked: authorization is not active")
    if seed not in payload.get("authorized_seeds", ()):
        raise RuntimeError(f"seed {seed} is not explicitly authorized")


def qualification_is_locked() -> bool:
    if not AUTHORIZATION_PATH.exists():
        return True

    try:
        payload = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    return payload.get("status") != "AUTHORIZED"
