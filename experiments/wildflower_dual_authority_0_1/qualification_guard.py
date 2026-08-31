from __future__ import annotations

from pathlib import Path

from .design import DEVELOPMENT_SEEDS, MODEL_SEEDS, QUALIFICATION_SEEDS

AUTHORIZATION_PATH = Path(__file__).with_name("QUALIFICATION_AUTHORIZATION.json")


def assert_seed_is_registered(seed: int) -> None:
    if seed not in MODEL_SEEDS:
        raise ValueError(f"unregistered successor seed: {seed}")


def assert_qualification_locked(seed: int) -> None:
    assert_seed_is_registered(seed)
    if seed not in QUALIFICATION_SEEDS:
        return
    if not AUTHORIZATION_PATH.exists():
        raise RuntimeError(
            f"qualification seed {seed} is locked until local pre-lock review"
        )


def qualification_is_locked() -> bool:
    return not AUTHORIZATION_PATH.exists()


def development_seed_is_allowed(seed: int) -> bool:
    return seed in DEVELOPMENT_SEEDS and qualification_is_locked()
