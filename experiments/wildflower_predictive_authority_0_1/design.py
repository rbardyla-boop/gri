"""Prelocked design constants for the predictive-authority successor.

The selector ranges and scientific gates are new design declarations.  The
historical predictor, Nursery world, and old predictive gates are carried for
comparability only; no scientific seed is authorized by this module.
"""

from __future__ import annotations

MODEL_SEEDS = (360, 361, 362, 370, 371)
DEVELOPMENT_SEEDS = (360, 361, 362)
QUALIFICATION_SEEDS = (370, 371)

RESERVED_0_1_SEEDS = (311, 312, 313, 314, 315)
RESERVED_0_2_SEEDS = (320, 321, 322, 330, 331)
RESERVED_0_3_SEEDS = (340, 341, 342, 350, 351)

TRAIN_PER_MODE = 2
ORDINARY_TEST_PER_MODE = 2
TRAINING_EPISODE_LENGTH = 420
ORDINARY_EVALUATION_LENGTH = 520
TRAINING_STEPS_PER_EPISODE = 80
BURN = 12
HORIZONS = (1, 8, 32)

# Historical 0.3 numeric predictor constants.  These are carried forward,
# not tuned by this design pass.
AUTHORITY_THRESHOLD = 0.30
AUTHORITY_WIDTH = 0.30
AUTHORITY_DECAY = 0.998

# New selectors are separated from every earlier WILDFLOWER selector block.
SELECTOR_ROOT = 3_600_000
SELECTOR_SLOT_WIDTH = 200_000
SELECTOR_RANGE_WIDTH = 49_999
TRAINING_OFFSET = 0
ORDINARY_TEST_OFFSET = 50_000
DIAGNOSTIC_OFFSET = 100_000

# Diagnostic-only policy constants.  They are fixed structural probes, not
# scientific thresholds.  No policy using them is execution-authorized yet.
CAPPED_AUTHORITY_CAP = 0.65
HORIZON_8_FACTOR = 0.55
HORIZON_32_FACTOR = 0.35
DISAGREEMENT_FLOOR = 0.05

SUCCESSOR_CANDIDATES = (
    "HORIZON_CONDITIONED",
)
PRIMARY_CANDIDATE = "HORIZON_CONDITIONED"
DIAGNOSTIC_COMPARATORS = (
    "P0_NULL_ONLY",
    "P1_LEARNED_ONLY",
    "P2_CURRENT_POLICY",
    "P3_DELAYED_AUTHORITY",
    "P4_CAPPED_AUTHORITY",
    "P5_HORIZON_AWARE_DIAGNOSTIC",
    "DISAGREEMENT_GATED",
    "P6_ORACLE_UPPER_BOUND",
)

# Exact successor gate choices. These are frozen before any fresh scientific
# seed and were not selected by inspecting a fresh successor result.
H8_WORSE_SUBSET_MAX_RATIO = 1.05
H8_USEFUL_CAPTURE_MIN_FRACTION = 0.50
H1_GLOBAL_MAX_RATIO = 1.05
H32_GLOBAL_MAX_RATIO = 1.05
NONTRIVIAL_MIN_FRACTION = 0.05
NONTRIVIAL_MIN_MEAN_AUTHORITY = 0.05
MIN_SUBSET_ORIGINS = 30

OLD_PREDICTIVE_GATES = {
    "h1_noninferior_all_max_ratio": 1.10,
    "h8_better_all_max_ratio": 1.00,
    "h8_mean_max_ratio": 0.90,
    "h32_better_all_max_ratio": 1.00,
    "h32_mean_max_ratio": 0.85,
    "event_h8_mean_max_ratio": 0.90,
}

# Machine-readable mirror of the frozen scientific gate table.  Every
# executable comparator must route through ``gate_passes`` below so that a
# polarity change cannot be introduced by a generic <= helper.
GATE_CONTRACT: dict[str, dict[str, float | str]] = {
    "old_h1_max": {
        "operator": "<=",
        "threshold": OLD_PREDICTIVE_GATES["h1_noninferior_all_max_ratio"],
    },
    "old_h8_max": {
        "operator": "<=",
        "threshold": OLD_PREDICTIVE_GATES["h8_better_all_max_ratio"],
    },
    "old_h8_mean": {
        "operator": "<=",
        "threshold": OLD_PREDICTIVE_GATES["h8_mean_max_ratio"],
    },
    "old_h32_max": {
        "operator": "<=",
        "threshold": OLD_PREDICTIVE_GATES["h32_better_all_max_ratio"],
    },
    "old_h32_mean": {
        "operator": "<=",
        "threshold": OLD_PREDICTIVE_GATES["h32_mean_max_ratio"],
    },
    "old_event_h8_mean": {
        "operator": "<=",
        "threshold": OLD_PREDICTIVE_GATES["event_h8_mean_max_ratio"],
    },
    "h8_worse_learned_protection": {
        "operator": "<=",
        "threshold": H8_WORSE_SUBSET_MAX_RATIO,
    },
    "h8_useful_learner_capture": {
        "operator": ">=",
        "threshold": H8_USEFUL_CAPTURE_MIN_FRACTION,
    },
    "h1_global_regression": {
        "operator": "<=",
        "threshold": H1_GLOBAL_MAX_RATIO,
    },
    "h32_global_noninferiority": {
        "operator": "<=",
        "threshold": H32_GLOBAL_MAX_RATIO,
    },
    "h8_nontrivial_fraction": {
        "operator": ">=",
        "threshold": NONTRIVIAL_MIN_FRACTION,
    },
    "h8_nontrivial_mean": {
        "operator": ">=",
        "threshold": NONTRIVIAL_MIN_MEAN_AUTHORITY,
    },
}


def gate_passes(name: str, value: float) -> bool:
    """Apply the frozen operator and threshold for one named gate."""

    try:
        contract = GATE_CONTRACT[name]
    except KeyError as exc:
        raise ValueError(f"unknown scientific gate: {name}") from exc
    operator = contract["operator"]
    threshold = float(contract["threshold"])
    if operator == "<=":
        return value <= threshold
    if operator == ">=":
        return value >= threshold
    raise ValueError(f"unsupported gate operator for {name}: {operator!r}")

SUCCESSOR_MECHANISM_CRITERIA = {
    "learned_improvement_captured": "sum(null - gated) / sum(null - learned) >= 0.50 on H8 useful origins",
    "worse_than_null_avoided": "sum(gated) / sum(null) <= 1.05 on H8 worse-than-null origins",
    "h1_non_regression": "sum(gated H1) / sum(null H1) <= 1.05",
    "h8_non_inferiority": "old H8 max and mean gates pass",
    "h8_helpful_case": "covered by the H8 useful-learner capture gate",
    "h32_preserved": "sum(gated H32) / sum(null H32) <= 1.05",
    "authority_nontrivial": "5% of origins exceed 0.10 and mean H8 authority across all origins >= 0.05",
}


def selector_starts(model_seed: int) -> dict[str, int]:
    """Return disjoint selector starts in the new successor namespace."""

    if model_seed not in MODEL_SEEDS:
        raise ValueError(f"unregistered predictive-authority seed: {model_seed}")
    slot = MODEL_SEEDS.index(model_seed)
    base = SELECTOR_ROOT + slot * SELECTOR_SLOT_WIDTH
    return {
        "training": base + TRAINING_OFFSET,
        "ordinary_test": base + ORDINARY_TEST_OFFSET,
        "diagnostic": base + DIAGNOSTIC_OFFSET,
    }


def selector_ranges() -> dict[int, dict[str, tuple[int, int]]]:
    return {
        seed: {
            name: (start, start + SELECTOR_RANGE_WIDTH)
            for name, start in selector_starts(seed).items()
        }
        for seed in MODEL_SEEDS
    }


def selectors_are_fresh() -> bool:
    """Check namespace separation from all historical selector roots."""

    starts = [
        start
        for ranges in selector_ranges().values()
        for start, _ in ranges.values()
    ]
    return len(starts) == len(set(starts)) and min(starts) >= SELECTOR_ROOT


def reserved_seed(seed: int) -> bool:
    return seed in (
        *RESERVED_0_1_SEEDS,
        *RESERVED_0_2_SEEDS,
        *RESERVED_0_3_SEEDS,
    )
