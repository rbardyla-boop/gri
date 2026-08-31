"""Frozen 0.3 selectors, model constants, and preregistered gates.

The predictive constants intentionally mirror 0.1 and 0.2.  The 0.3
challenge adds an explicit, deterministic alternate-evidence workload.
"""

MODEL_SEEDS = (340, 341, 342, 350, 351)
DEVELOPMENT_SEEDS = (340, 341, 342)
QUALIFICATION_SEEDS = (350, 351)
RESERVED_0_1_SEEDS = (311, 312, 313, 314, 315)
RESERVED_0_2_SEEDS = (320, 321, 322, 330, 331)

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
ALTERNATE_VALID_CASES_PER_EPISODE = 40
ALTERNATE_HOSTILE_CASES = 18

TRAIN_SELECTOR_ROOT_OFFSET = 3_000_000
ORDINARY_TEST_SELECTOR_ROOT_OFFSET = 3_050_000
CHALLENGE_SELECTOR_ROOT_OFFSET = 3_100_000
SELECTOR_SLOT_WIDTH = 200_000
SELECTOR_RANGE_WIDTH = 49_999


def selector_starts(model_seed: int) -> dict[str, int]:
    if model_seed not in MODEL_SEEDS:
        raise ValueError(f"unregistered model seed: {model_seed}")
    slot = MODEL_SEEDS.index(model_seed)
    base = TRAIN_SELECTOR_ROOT_OFFSET + slot * SELECTOR_SLOT_WIDTH
    return {
        "training": base,
        "ordinary_test": base + 50_000,
        "challenge": base + 100_000,
    }


def selector_ranges() -> dict[int, dict[str, tuple[int, int]]]:
    return {
        seed: {
            name: (start, start + SELECTOR_RANGE_WIDTH)
            for name, start in selector_starts(seed).items()
        }
        for seed in MODEL_SEEDS
    }


def selectors_are_disjoint_from_0_1() -> bool:
    return all(
        start > 2_200_000
        for ranges in selector_ranges().values()
        for start, _ in ranges.values()
    )


def qualification_gates() -> dict[str, object]:
    """Exact gates; minimum-opportunity checks prevent vacuous wins."""
    return {
        "alternate_support_opportunities_min": ALTERNATE_SUPPORT_MIN_OPPORTUNITIES,
        "alternate_support_preservation_rate": 1.0,
        "false_opportunity_classifications": 0,
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


def predictive_gates() -> dict[str, float]:
    """Unchanged predictive-authority gates copied from the 0.1 contract."""
    return {
        "h1_noninferior_all_max_ratio": 1.10,
        "h8_better_all_max_ratio": 1.00,
        "h8_mean_max_ratio": 0.90,
        "h32_better_all_max_ratio": 1.00,
        "h32_mean_max_ratio": 0.85,
        "event_h8_mean_max_ratio": 0.90,
    }
