from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch

from gri_world0.relations import PRIMARY_CHAIN_RELATIONS
from gri_world0.schema import Sample
from gri_world0.serialization import read_jsonl

RELATIONS = tuple(PRIMARY_CHAIN_RELATIONS)
RELATION_TO_INDEX = {r: i for i, r in enumerate(RELATIONS)}
NUM_RELATIONS = len(RELATIONS)


@dataclass
class GraphExample:
    node_features: torch.Tensor  # [N, 3]
    edges: torch.Tensor          # [N, N, R], asserted direction only
    query_subject: int
    query_object: int
    label: int
    sample_id: str
    chain_length: int


def encode_sample(sample: Sample, *, dtype: torch.dtype = torch.float32) -> GraphExample:
    if sample.answer not in RELATION_TO_INDEX:
        raise ValueError(f"sample answer is not a scored directional label: {sample.answer}")
    entities = tuple(sorted(sample.entities))
    local = {entity: i for i, entity in enumerate(entities)}
    n = len(entities)
    node_features = torch.zeros((n, 3), dtype=dtype)
    node_features[:, 0] = 1.0
    qs = local[sample.query.subject]
    qo = local[sample.query.object]
    node_features[qs, 1] = 1.0
    node_features[qo, 2] = 1.0

    edges = torch.zeros((n, n, NUM_RELATIONS), dtype=dtype)
    for fact in sample.facts:
        if fact.relation not in RELATION_TO_INDEX:
            continue
        edges[local[fact.subject], local[fact.object], RELATION_TO_INDEX[fact.relation]] = 1.0

    return GraphExample(
        node_features=node_features,
        edges=edges,
        query_subject=qs,
        query_object=qo,
        label=RELATION_TO_INDEX[sample.answer],
        sample_id=sample.sample_id,
        chain_length=sample.chain_length,
    )


def load_examples(path: Path) -> list[GraphExample]:
    return [encode_sample(s) for s in read_jsonl(path) if not s.contradiction_label]
