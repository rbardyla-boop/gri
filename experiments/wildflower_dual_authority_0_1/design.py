from __future__ import annotations

MODEL_SEEDS = (311, 312, 313, 314, 315)
DEVELOPMENT_SEEDS = (311, 312, 313)
QUALIFICATION_SEEDS = (314, 315)
SPENT_SEEDS = (0, 1, 2, 3, 10, 12, 20, 21, 22, 40, 41, 42, 60, 61, 62, 130, 160, 190, 230, 310)

TRAIN_SELECTOR_ROOT_OFFSET = 9_000
ORDINARY_TEST_SELECTOR_ROOT_OFFSET = 19_000
CHALLENGE_SELECTOR_ROOT_OFFSET = 29_000

TRAIN_PER_MODE = 2
ORDINARY_TEST_PER_MODE = 2
CHALLENGE_PER_MODE = 1
TRAINING_EPISODE_LENGTH = 420
ORDINARY_EVALUATION_LENGTH = 520
CHALLENGE_EPISODE_LENGTH = 260
TRAINING_STEPS_PER_EPISODE = 80
MAX_ACTIVE_CLAIMS = 8_192
CONFIDENCE_CONTROL_THRESHOLD = 0.50

ALTERNATE_SUPPORT_MIN_OPPORTUNITIES = 30
RECOMPUTATION_MIN_OPPORTUNITIES = 30


def selector_starts(model_seed: int) -> dict[str, int]:
    if model_seed not in MODEL_SEEDS:
        raise ValueError(f"unregistered model seed: {model_seed}")
    slot = MODEL_SEEDS.index(model_seed)
    base = 800_000 + slot * 200_000
    return {
        "training": base,
        "ordinary_test": base + 50_000,
        "challenge": base + 100_000,
    }


def selector_ranges() -> dict[int, dict[str, tuple[int, int]]]:
    return {
        seed: {
            name: (start, start + 49_999)
            for name, start in selector_starts(seed).items()
        }
        for seed in MODEL_SEEDS
    }


def qualification_gates() -> dict[str, object]:
    return {
        "alternate_support_opportunities_min": ALTERNATE_SUPPORT_MIN_OPPORTUNITIES,
        "alternate_support_preservation_rate": 1.0,
        "recomputation_opportunities_min": RECOMPUTATION_MIN_OPPORTUNITIES,
        "recomputation_precision": 1.0,
        "recomputation_recall": 1.0,
        "stale_support_survival_rate": 0.0,
        "false_durable_claim_rate": 0.0,
        "rollback_recall": 1.0,
        "duplicate_support_rate": 0.0,
        "orphan_support_rate": 0.0,
        "support_DAG_integrity": True,
        "active_store_bound": True,
        "deterministic_replay": True,
    }
