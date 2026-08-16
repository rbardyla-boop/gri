from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable

from .relations import Relation, inverse, is_strict, is_transitive
from .schema import Fact, Query, SolveResult, SolveStatus


def _adjacency(facts: Iterable[Fact]) -> dict[Relation, dict[int, set[int]]]:
    adj: dict[Relation, dict[int, set[int]]] = {
        r: defaultdict(set) for r in Relation
    }
    for fact in facts:
        adj[fact.relation][fact.subject].add(fact.object)
        # Every explicit fact also implies its inverse.
        adj[inverse(fact.relation)][fact.object].add(fact.subject)
    return adj


def _reachable(graph: dict[int, set[int]], start: int, target: int) -> bool:
    if start == target:
        return True
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nxt in graph.get(node, set()):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def detect_contradiction(facts: Iterable[Fact]) -> bool:
    facts = tuple(facts)
    adj = _adjacency(facts)

    # Strict order/containment relations cannot contain directed cycles.
    for relation in Relation:
        if not is_strict(relation):
            continue
        graph = adj[relation]
        nodes = set(graph)
        nodes.update(x for targets in graph.values() for x in targets)
        for node in nodes:
            # Search from each direct successor back to node, avoiding the
            # trivial start==target behavior in _reachable.
            for nxt in graph.get(node, set()):
                if nxt == node or _reachable(graph, nxt, node):
                    return True

    # SAME and DIFFERENT cannot both be asserted/entailed for a pair.
    same = adj[Relation.SAME]
    different = adj[Relation.DIFFERENT]
    pairs = {(a, b) for a, bs in same.items() for b in bs}
    if any(b in different.get(a, set()) for a, b in pairs):
        return True
    return False


def solve(facts: Iterable[Fact], query: Query) -> SolveResult:
    facts = tuple(facts)
    if detect_contradiction(facts):
        return SolveResult(SolveStatus.CONTRADICTION)

    adj = _adjacency(facts)
    candidates: set[Relation] = set()

    if query.subject == query.object:
        candidates.add(Relation.SAME)

    for relation in Relation:
        if relation is Relation.SAME:
            if _reachable(adj[Relation.SAME], query.subject, query.object):
                candidates.add(Relation.SAME)
            continue
        if relation is Relation.DIFFERENT:
            if query.object in adj[relation].get(query.subject, set()):
                candidates.add(relation)
            continue
        if is_transitive(relation):
            if _reachable(adj[relation], query.subject, query.object):
                candidates.add(relation)
        elif query.object in adj[relation].get(query.subject, set()):
            candidates.add(relation)

    if not candidates:
        return SolveResult(SolveStatus.NO_ANSWER)
    if len(candidates) > 1:
        return SolveResult(SolveStatus.AMBIGUOUS)
    return SolveResult(SolveStatus.VALID, next(iter(candidates)))
