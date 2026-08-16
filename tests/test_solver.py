from gri_world0.relations import Relation
from gri_world0.schema import Fact, Query, SolveStatus
from gri_world0.solver import detect_contradiction, solve


def test_direct_inverse_and_transitive_solution():
    facts = (
        Fact(1, Relation.ABOVE, 2),
        Fact(2, Relation.ABOVE, 3),
        Fact(3, Relation.ABOVE, 4),
    )
    assert solve(facts, Query(1, 4)).relation is Relation.ABOVE
    assert solve(facts, Query(4, 1)).relation is Relation.BELOW


def test_inside_has_formal_nested_set_transitivity():
    facts = (Fact(1, Relation.INSIDE, 2), Fact(2, Relation.INSIDE, 3))
    assert solve(facts, Query(1, 3)).relation is Relation.INSIDE
    assert solve(facts, Query(3, 1)).relation is Relation.CONTAINS


def test_different_is_not_transitive():
    facts = (Fact(1, Relation.DIFFERENT, 2), Fact(2, Relation.DIFFERENT, 3))
    assert solve(facts, Query(1, 3)).status is SolveStatus.NO_ANSWER


def test_strict_cycle_is_contradiction():
    facts = (
        Fact(1, Relation.ABOVE, 2),
        Fact(2, Relation.ABOVE, 3),
        Fact(3, Relation.ABOVE, 1),
    )
    assert detect_contradiction(facts)
    assert solve(facts, Query(1, 2)).status is SolveStatus.CONTRADICTION


def test_same_and_different_conflict():
    facts = (Fact(1, Relation.SAME, 2), Fact(1, Relation.DIFFERENT, 2))
    assert detect_contradiction(facts)
