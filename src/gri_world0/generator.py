from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import BENCHMARK_VERSION
from .relations import PRIMARY_CHAIN_RELATIONS, Relation, inverse
from .schema import Fact, Query, Sample, SolveStatus, TaskFamily
from .serialization import sample_semantic_id
from .solver import solve

MAX_ENTITIES = 128


def _sample_entities(rng: np.random.Generator, count: int) -> tuple[int, ...]:
    if count > MAX_ENTITIES:
        raise ValueError(f"requested {count} entities > MAX_ENTITIES={MAX_ENTITIES}")
    return tuple(int(x) for x in rng.choice(MAX_ENTITIES, size=count, replace=False))


def _finalize(sample: Sample) -> Sample:
    sid = sample_semantic_id(sample)
    return replace(sample, sample_id=sid)


def generate_sample(
    *, seed: int, split: str, task_family: TaskFamily, chain_length: int,
    relation: Relation | None = None,
) -> Sample:
    rng = np.random.default_rng(seed)
    relation = relation or PRIMARY_CHAIN_RELATIONS[int(rng.integers(0, len(PRIMARY_CHAIN_RELATIONS)))]

    if task_family is TaskFamily.DIRECT:
        chain_length = 1
        a, b = _sample_entities(rng, 2)
        facts = (Fact(a, relation, b),)
        query = Query(a, b)
        answer = relation
    elif task_family is TaskFamily.INVERSE:
        chain_length = 1
        a, b = _sample_entities(rng, 2)
        facts = (Fact(a, relation, b),)
        query = Query(b, a)
        answer = inverse(relation)
    elif task_family in (TaskFamily.COMPOSITION, TaskFamily.LONG_CHAIN):
        if chain_length < 2:
            raise ValueError("composition/long-chain samples require chain_length >= 2")
        nodes = _sample_entities(rng, chain_length + 1)
        facts = tuple(Fact(nodes[i], relation, nodes[i + 1]) for i in range(chain_length))
        query = Query(nodes[0], nodes[-1])
        answer = relation
    elif task_family is TaskFamily.CONTRADICTION:
        if chain_length < 3:
            chain_length = 3
        # Build an explicit strict cycle. Use a forward-only base relation so
        # the intended cycle is visually and semantically direct.
        cycle_relation = relation
        nodes = _sample_entities(rng, chain_length)
        facts = tuple(
            Fact(nodes[i], cycle_relation, nodes[(i + 1) % chain_length])
            for i in range(chain_length)
        )
        query = Query(nodes[0], nodes[1])
        answer = None
    else:
        raise ValueError(task_family)

    entities = tuple(sorted({x for f in facts for x in (f.subject, f.object)}))
    sample = Sample(
        benchmark_version=BENCHMARK_VERSION,
        sample_id="",
        seed=seed,
        split=split,
        task_family=task_family,
        chain_length=chain_length,
        entities=entities,
        facts=facts,
        query=query,
        answer=answer,
        contradiction_label=task_family is TaskFamily.CONTRADICTION,
        generation_metadata={"relation_family": relation.value},
    )
    sample = _finalize(sample)

    result = solve(sample.facts, sample.query)
    if sample.contradiction_label:
        if result.status is not SolveStatus.CONTRADICTION:
            raise AssertionError("generator produced non-contradictory contradiction sample")
    elif result.status is not SolveStatus.VALID or result.relation is not sample.answer:
        raise AssertionError(f"generator/solver disagreement: {result} != {sample.answer}")
    return sample
