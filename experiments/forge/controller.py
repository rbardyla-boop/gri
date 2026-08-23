from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence

from experiments.forge.ecology import (
    Ablator,
    Composer,
    FailureClass,
    FailureDiagnosis,
    NullSmith,
    RecipeCandidate,
    ToolSmith,
    classify_failure,
)
from experiments.forge.forge import Case, Forge, Grinder, Mutation, Registry, SearchConfig


class DiscoveryStatus(str, Enum):
    READY_FOR_FREEZE = "READY_FOR_FREEZE"
    STOP_WRONG_LAYER = "STOP_WRONG_LAYER"
    STOP_NO_TOOLS = "STOP_NO_TOOLS"
    STOP_NO_RECIPE = "STOP_NO_RECIPE"
    STOP_NULL_MATCH = "STOP_NULL_MATCH"
    STOP_GRINDER_FAILURE = "STOP_GRINDER_FAILURE"
    STOP_COMPONENT_UNNECESSARY = "STOP_COMPONENT_UNNECESSARY"
    STOP_DEV_GATE = "STOP_DEV_GATE"


@dataclass(frozen=True)
class DiscoveryPolicy:
    dev_threshold: float = 0.90
    min_margin_over_null: float = 0.10
    max_grinder_failures: int = 0
    min_component_delta: float = 0.0
    max_depth: int = 4
    max_cost: int = 8
    max_candidates: int = 10000
    complexity_penalty: float = 0.01
    cost_penalty: float = 0.005


@dataclass(frozen=True)
class DiscoveryReport:
    status: DiscoveryStatus
    diagnosis: FailureDiagnosis
    champion: RecipeCandidate | None
    best_null_score: float
    grinder_failures: int
    ablation_min_delta: float | None
    tool_names: tuple[str, ...]
    reason: str

    def to_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["diagnosis"]["failure_class"] = self.diagnosis.failure_class.value
        if self.champion is not None:
            value["champion"]["chain"] = {
                "tools": list(self.champion.chain.tools),
                "input_kind": self.champion.chain.input_kind,
                "output_kind": self.champion.chain.output_kind,
                "cost": self.champion.chain.cost,
                "chain_id": self.champion.chain.chain_id,
            }
        return value


# These failures must be repaired at their own layer before tool search can earn
# scientific credit. This prevents a clever recipe from papering over a broken
# experiment, host, or benchmark.
NON_TOOL_SEARCH_CLASSES = {
    FailureClass.INTEGRITY,
    FailureClass.RESOURCE,
    FailureClass.TASK_DEFINITION,
}


class DiscoveryController:
    """Bounded BUILD/DEV discovery loop.

    This controller has no Vault argument and cannot call Judge. It decides only
    whether a development champion is ready to be frozen for a later independent
    one-shot verification.
    """

    def __init__(self, smith: ToolSmith | None = None) -> None:
        self.smith = smith or ToolSmith()

    def run(
        self,
        *,
        build_cases: Sequence[Case],
        dev_cases: Sequence[Case],
        signals: dict[str, Any],
        input_kind: str,
        output_kind: str,
        mutations: Sequence[Mutation] = (),
        policy: DiscoveryPolicy | None = None,
    ) -> DiscoveryReport:
        policy = policy or DiscoveryPolicy()
        diagnosis = classify_failure(signals)
        if diagnosis.failure_class in NON_TOOL_SEARCH_CLASSES:
            return DiscoveryReport(
                DiscoveryStatus.STOP_WRONG_LAYER,
                diagnosis,
                None,
                0.0,
                0,
                None,
                (),
                "failure must be repaired outside the tool ecology before search",
            )

        registry = Registry()
        blueprints = self.smith.propose(diagnosis, build_cases, input_kind, output_kind)
        if not blueprints:
            return DiscoveryReport(
                DiscoveryStatus.STOP_NO_TOOLS,
                diagnosis,
                None,
                0.0,
                0,
                None,
                (),
                "ToolSmith has no allow-listed proposal for this failure class",
            )
        self.smith.register(registry, blueprints)
        forge = Forge(registry)

        config = SearchConfig(
            input_kind,
            output_kind,
            max_depth=policy.max_depth,
            max_cost=policy.max_cost,
            max_candidates=policy.max_candidates,
        )
        ranked = Composer(forge).search(
            dev_cases,
            config,
            complexity_penalty=policy.complexity_penalty,
            cost_penalty=policy.cost_penalty,
        )
        if not ranked:
            return DiscoveryReport(
                DiscoveryStatus.STOP_NO_RECIPE,
                diagnosis,
                None,
                0.0,
                0,
                None,
                registry.names(),
                "no type-compatible recipe reached the requested output type",
            )

        champion = ranked[0]
        nulls = list(NullSmith.constant_null(dev_cases)) + [NullSmith.identity_null(dev_cases)]
        best_null = max((row.score for row in nulls), default=0.0)
        if champion.dev_score - best_null < policy.min_margin_over_null:
            return DiscoveryReport(
                DiscoveryStatus.STOP_NULL_MATCH,
                diagnosis,
                champion,
                best_null,
                0,
                None,
                registry.names(),
                "candidate does not beat the strongest transparent null by the frozen margin",
            )

        grinder_failures = 0
        if mutations:
            grinder_failures = len(Grinder(forge, mutations).grind(champion.chain, dev_cases, max_failures=policy.max_grinder_failures + 1))
            if grinder_failures > policy.max_grinder_failures:
                return DiscoveryReport(
                    DiscoveryStatus.STOP_GRINDER_FAILURE,
                    diagnosis,
                    champion,
                    best_null,
                    grinder_failures,
                    None,
                    registry.names(),
                    "fixed champion failed the allowed adversarial mutation budget",
                )

        ablations = Ablator(forge).single_tool_ablations(champion.chain, dev_cases, champion.dev_score)
        valid_deltas = [row.delta_from_full for row in ablations if row.valid and row.delta_from_full is not None]
        min_delta = min(valid_deltas) if valid_deltas else None
        if valid_deltas and min_delta is not None and min_delta <= policy.min_component_delta:
            return DiscoveryReport(
                DiscoveryStatus.STOP_COMPONENT_UNNECESSARY,
                diagnosis,
                champion,
                best_null,
                grinder_failures,
                min_delta,
                registry.names(),
                "at least one removable tool does not earn the required component credit",
            )

        if champion.dev_score < policy.dev_threshold:
            return DiscoveryReport(
                DiscoveryStatus.STOP_DEV_GATE,
                diagnosis,
                champion,
                best_null,
                grinder_failures,
                min_delta,
                registry.names(),
                "development score is below the frozen readiness threshold",
            )

        return DiscoveryReport(
            DiscoveryStatus.READY_FOR_FREEZE,
            diagnosis,
            champion,
            best_null,
            grinder_failures,
            min_delta,
            registry.names(),
            "development-only gates passed; freeze champion before any Vault exposure",
        )
