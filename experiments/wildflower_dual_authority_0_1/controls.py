from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlSpec:
    name: str
    witnessing: bool
    dependency_tracking: bool
    grounded_recomputation: bool
    purpose: str


CONTROLS = (
    ControlSpec(
        "DUAL_AUTHORITY",
        witnessing=True,
        dependency_tracking=True,
        grounded_recomputation=True,
        purpose="World witnessing, provenance tracking, and grounded recomputation.",
    ),
    ControlSpec(
        "DIRECT_COMMIT",
        witnessing=False,
        dependency_tracking=False,
        grounded_recomputation=False,
        purpose="Prediction-derived claims become durable immediately.",
    ),
    ControlSpec(
        "CONFIDENCE_COMMIT",
        witnessing=False,
        dependency_tracking=False,
        grounded_recomputation=False,
        purpose="Predictions commit when predictive authority reaches 0.50.",
    ),
    ControlSpec(
        "DAG_NO_WITNESS",
        witnessing=False,
        dependency_tracking=True,
        grounded_recomputation=False,
        purpose="Dependencies exist but no independent world roots are admitted.",
    ),
    ControlSpec(
        "WITNESS_NO_DAG",
        witnessing=True,
        dependency_tracking=False,
        grounded_recomputation=False,
        purpose="World coordinates arrive without descendant provenance links.",
    ),
    ControlSpec(
        "WITNESS_PLUS_RECOMPUTE_NO_DAG",
        witnessing=True,
        dependency_tracking=False,
        grounded_recomputation=True,
        purpose="Separates world evidence and recomputation from DAG provenance.",
    ),
    ControlSpec(
        "DAG_PLUS_WITNESS_NO_RECOMPUTE",
        witnessing=True,
        dependency_tracking=True,
        grounded_recomputation=False,
        purpose="Measures rollback and preservation without grounded rebuilding.",
    ),
)
