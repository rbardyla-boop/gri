from collections import Counter

from gri_world0.splits import EXTRAPOLATION_DEPTHS, build_bundle


def test_training_never_contains_depth_over_four():
    bundle = build_bundle(count_per_depth=8, contradiction_count=8)
    assert max(s.chain_length for s in bundle.train) <= 4


def test_depth_specific_splits_are_exact():
    bundle = build_bundle(count_per_depth=8, contradiction_count=8)
    for depth in EXTRAPOLATION_DEPTHS:
        assert {s.chain_length for s in bundle.extrapolation[depth]} == {depth}


def test_all_split_ids_are_disjoint():
    bundle = build_bundle(count_per_depth=8, contradiction_count=8)
    groups = [bundle.train, bundle.validation, bundle.test_iid, bundle.contradiction, *bundle.extrapolation.values()]
    all_ids = [s.sample_id for group in groups for s in group]
    assert len(all_ids) == len(set(all_ids))


def test_train_answer_distribution_has_all_directional_labels():
    bundle = build_bundle(count_per_depth=32, contradiction_count=8)
    counts = Counter(s.answer.value for s in bundle.train if s.answer)
    for label in ["ABOVE", "BELOW", "LEFT", "RIGHT", "BEFORE", "AFTER", "INSIDE", "CONTAINS"]:
        assert counts[label] > 0
