from gri_world0.relations import Relation, compose, inverse, is_transitive


def test_inverse_is_involution_for_every_relation():
    for relation in Relation:
        assert inverse(inverse(relation)) is relation


def test_expected_inverse_pairs():
    assert inverse(Relation.ABOVE) is Relation.BELOW
    assert inverse(Relation.LEFT) is Relation.RIGHT
    assert inverse(Relation.BEFORE) is Relation.AFTER
    assert inverse(Relation.INSIDE) is Relation.CONTAINS
    assert inverse(Relation.SAME) is Relation.SAME
    assert inverse(Relation.DIFFERENT) is Relation.DIFFERENT


def test_composition_is_deliberately_narrow():
    assert compose(Relation.ABOVE, Relation.ABOVE) is Relation.ABOVE
    assert compose(Relation.SAME, Relation.LEFT) is Relation.LEFT
    assert compose(Relation.RIGHT, Relation.SAME) is Relation.RIGHT
    assert compose(Relation.ABOVE, Relation.LEFT) is None
    assert compose(Relation.DIFFERENT, Relation.DIFFERENT) is None
    assert not is_transitive(Relation.DIFFERENT)
