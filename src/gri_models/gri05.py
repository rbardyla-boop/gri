from __future__ import annotations

from .baseline import WeightTiedGraphReasoner
from .geometric import SO4GeometricReasoner
from .rri02pa import ImmutableRelationAnchorReasoner
from .train import set_seed

SEEDS = (1337, 1338, 1339, 1340, 1341)
DEPTHS = (5, 8, 16, 32, 64)
PRIMARY_DEPTHS = (8, 16, 32, 64)
PARAMETERS = 30_912


def build_model(kind: str, seed: int):
    set_seed(seed)
    if kind == "baseline":
        model = WeightTiedGraphReasoner(hidden_dim=49, message_dim=51)
    elif kind == "anchor":
        model = ImmutableRelationAnchorReasoner(hidden_dim=49, message_dim=51)
    elif kind == "so4":
        model = SO4GeometricReasoner(semantic_dim=39, channels=2, message_dim=44)
    else:
        raise ValueError(kind)
    count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if count != PARAMETERS:
        raise RuntimeError(f"parameter firewall failed for {kind}: {count} != {PARAMETERS}")
    return model


def primary_metric(extrapolation: dict[str, float]) -> float:
    return sum(extrapolation[str(d)] for d in PRIMARY_DEPTHS) / len(PRIMARY_DEPTHS)
