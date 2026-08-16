from gri_world0.generator import generate_sample
from gri_world0.relations import Relation
from gri_world0.schema import SolveStatus, TaskFamily
from gri_world0.solver import solve


def test_all_normal_families_independently_solve():
    cases = [
        (TaskFamily.DIRECT, 1),
        (TaskFamily.INVERSE, 1),
        (TaskFamily.COMPOSITION, 3),
        (TaskFamily.LONG_CHAIN, 16),
    ]
    for i, (family, depth) in enumerate(cases):
        sample = generate_sample(seed=100 + i, split="x", task_family=family, chain_length=depth, relation=Relation.ABOVE)
        result = solve(sample.facts, sample.query)
        assert result.status is SolveStatus.VALID
        assert result.relation is sample.answer
        assert not sample.contradiction_label


def test_contradiction_generator_is_independently_detected():
    sample = generate_sample(seed=2026, split="contradiction", task_family=TaskFamily.CONTRADICTION, chain_length=5, relation=Relation.LEFT)
    assert sample.contradiction_label
    assert solve(sample.facts, sample.query).status is SolveStatus.CONTRADICTION
