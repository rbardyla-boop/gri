from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .generator import generate_sample
from .relations import PRIMARY_CHAIN_RELATIONS, inverse
from .schema import Sample, TaskFamily

TRAIN_DEPTHS = (1, 2, 3, 4)
EXTRAPOLATION_DEPTHS = (5, 8, 16, 32, 64)


@dataclass(frozen=True)
class SplitBundle:
    train: tuple[Sample, ...]
    validation: tuple[Sample, ...]
    test_iid: tuple[Sample, ...]
    extrapolation: dict[int, tuple[Sample, ...]]
    contradiction: tuple[Sample, ...]


def _family_for_depth(depth: int, index: int) -> TaskFamily:
    if depth == 1:
        return TaskFamily.DIRECT if index % 2 == 0 else TaskFamily.INVERSE
    if depth <= 4:
        return TaskFamily.COMPOSITION
    return TaskFamily.LONG_CHAIN


def _build_split(name: str, base_seed: int, count_per_depth: int, depths: tuple[int, ...]) -> tuple[Sample, ...]:
    samples: list[Sample] = []
    cursor = 0
    for depth in depths:
        for i in range(count_per_depth):
            family = _family_for_depth(depth, i)
            # Balance the *answer* labels exactly when count_per_depth is a
            # multiple of the eight directional relation labels. For inverse
            # tasks choose the asserted relation so its inverse is the target.
            target_answer = PRIMARY_CHAIN_RELATIONS[i % len(PRIMARY_CHAIN_RELATIONS)]
            relation = inverse(target_answer) if family is TaskFamily.INVERSE else target_answer
            # Split-specific seed bands eliminate accidental identical RNG streams.
            seed = base_seed + cursor * 1009 + depth * 9176 + i
            samples.append(generate_sample(seed=seed, split=name, task_family=family, chain_length=depth, relation=relation))
            cursor += 1
    return tuple(samples)


def _assert_disjoint(groups: dict[str, tuple[Sample, ...]]) -> None:
    seen: dict[str, str] = {}
    for name, samples in groups.items():
        for sample in samples:
            prior = seen.get(sample.sample_id)
            if prior is not None:
                raise AssertionError(f"sample_id collision between {prior} and {name}: {sample.sample_id}")
            seen[sample.sample_id] = name


def build_bundle(seed: int = 1337, count_per_depth: int = 32, contradiction_count: int = 64) -> SplitBundle:
    train = _build_split("train", seed + 1_000_000, count_per_depth, TRAIN_DEPTHS)
    validation = _build_split("validation", seed + 2_000_000, max(4, count_per_depth // 4), TRAIN_DEPTHS)
    test_iid = _build_split("test_iid", seed + 3_000_000, max(4, count_per_depth // 4), TRAIN_DEPTHS)
    extrapolation = {
        depth: _build_split(f"test_depth_{depth}", seed + 4_000_000 + depth * 100_000, max(4, count_per_depth // 4), (depth,))
        for depth in EXTRAPOLATION_DEPTHS
    }
    contradiction = tuple(
        generate_sample(
            seed=seed + 9_000_000 + i * 1013,
            split="contradiction",
            task_family=TaskFamily.CONTRADICTION,
            chain_length=3 + (i % 4),
            relation=PRIMARY_CHAIN_RELATIONS[i % len(PRIMARY_CHAIN_RELATIONS)],
        )
        for i in range(contradiction_count)
    )
    groups = {"train": train, "validation": validation, "test_iid": test_iid, "contradiction": contradiction}
    groups.update({f"test_depth_{d}": s for d, s in extrapolation.items()})
    _assert_disjoint(groups)
    return SplitBundle(train, validation, test_iid, extrapolation, contradiction)


def answer_distribution(samples: tuple[Sample, ...]) -> dict[str, int]:
    counts = Counter(sample.answer.value if sample.answer else "NONE" for sample in samples)
    return dict(sorted(counts.items()))
