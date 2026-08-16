from __future__ import annotations

from enum import Enum


class Relation(str, Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    INSIDE = "INSIDE"
    CONTAINS = "CONTAINS"
    SAME = "SAME"
    DIFFERENT = "DIFFERENT"


_INVERSE = {
    Relation.ABOVE: Relation.BELOW,
    Relation.BELOW: Relation.ABOVE,
    Relation.LEFT: Relation.RIGHT,
    Relation.RIGHT: Relation.LEFT,
    Relation.BEFORE: Relation.AFTER,
    Relation.AFTER: Relation.BEFORE,
    Relation.INSIDE: Relation.CONTAINS,
    Relation.CONTAINS: Relation.INSIDE,
    Relation.SAME: Relation.SAME,
    Relation.DIFFERENT: Relation.DIFFERENT,
}

# WORLD-0 gives INSIDE/CONTAINS a formal nested-set semantics: if A is inside B
# and B is inside C, then A is inside C. DIFFERENT is explicitly non-transitive.
_TRANSITIVE = {
    Relation.ABOVE,
    Relation.BELOW,
    Relation.LEFT,
    Relation.RIGHT,
    Relation.BEFORE,
    Relation.AFTER,
    Relation.INSIDE,
    Relation.CONTAINS,
    Relation.SAME,
}

_STRICT = {
    Relation.ABOVE,
    Relation.BELOW,
    Relation.LEFT,
    Relation.RIGHT,
    Relation.BEFORE,
    Relation.AFTER,
    Relation.INSIDE,
    Relation.CONTAINS,
}

PRIMARY_CHAIN_RELATIONS = (
    Relation.ABOVE,
    Relation.BELOW,
    Relation.LEFT,
    Relation.RIGHT,
    Relation.BEFORE,
    Relation.AFTER,
    Relation.INSIDE,
    Relation.CONTAINS,
)


def inverse(relation: Relation) -> Relation:
    return _INVERSE[relation]


def is_transitive(relation: Relation) -> bool:
    return relation in _TRANSITIVE


def is_strict(relation: Relation) -> bool:
    return relation in _STRICT


def compose(left: Relation, right: Relation) -> Relation | None:
    """Return the logically valid WORLD-0 composition, if uniquely defined.

    SAME acts as identity. A transitive relation composes with itself. Other
    mixed relation families are deliberately undefined in WORLD-0.
    """
    if left is Relation.SAME:
        return right
    if right is Relation.SAME:
        return left
    if left is right and is_transitive(left):
        return left
    return None
