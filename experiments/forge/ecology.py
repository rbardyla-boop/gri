from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from experiments.forge.forge import Case, Chain, Forge, Registry, SearchConfig, Tool, sha256_json

Json = Any


class FailureClass(str, Enum):
    MODEL = "MODEL_FAILURE"
    MEASUREMENT = "MEASUREMENT_FAILURE"
    TOOL = "TOOL_FAILURE"
    RETRIEVAL = "RETRIEVAL_FAILURE"
    STATE = "STATE_FAILURE"
    INTERFACE = "INTERFACE_FAILURE"
    RESOURCE = "RESOURCE_FAILURE"
    TASK_DEFINITION = "TASK_DEFINITION_FAILURE"
    INTEGRITY = "INTEGRITY_FAILURE"
    UNKNOWN = "UNKNOWN_FAILURE"


@dataclass(frozen=True)
class FailureDiagnosis:
    failure_class: FailureClass
    evidence: tuple[str, ...]
    recommended_action: str


def classify_failure(signals: dict[str, Any]) -> FailureDiagnosis:
    """Conservative rule-based failure classification.

    Multiple severe signals resolve by precedence: integrity -> resource ->
    measurement -> interface -> task definition -> retrieval -> state -> tool ->
    model -> unknown.
    """
    rules = [
        (FailureClass.INTEGRITY, ("hash_mismatch", "holdout_leak", "replay_mismatch", "unauthorized_retry"), "stop; invalidate the run"),
        (FailureClass.RESOURCE, ("oom", "timeout_host", "gpu_unavailable", "disk_full"), "repair host/resources; do not interpret as science"),
        (FailureClass.MEASUREMENT, ("instrument_unqualified", "semantic_readout_unreliable", "metric_collision"), "repair or replace the instrument before science"),
        (FailureClass.INTERFACE, ("schema_mismatch", "label_collision", "parse_failure", "tool_protocol_error"), "repair the boundary without changing the underlying model"),
        (FailureClass.TASK_DEFINITION, ("ambiguous_gold", "underspecified_task", "shortcut_leak"), "repair task definition or benchmark before model comparison"),
        (FailureClass.RETRIEVAL, ("wrong_retrieval", "missing_retrieval", "retrieval_dominates_error"), "test retrieval/null controls before model changes"),
        (FailureClass.STATE, ("state_loss", "state_corruption", "stale_state"), "test state representation and persistence controls"),
        (FailureClass.TOOL, ("tool_wrong", "tool_timeout", "tool_unavailable"), "repair/delete/substitute the tool and rerun development only"),
        (FailureClass.MODEL, ("model_wrong_after_controls", "model_invariant_to_required_change"), "record model-limited failure; tools may not be the missing mechanism"),
    ]
    true_keys = {k for k, v in signals.items() if bool(v)}
    for cls, keys, action in rules:
        hits = tuple(k for k in keys if k in true_keys)
        if hits:
            return FailureDiagnosis(cls, hits, action)
    return FailureDiagnosis(FailureClass.UNKNOWN, tuple(sorted(true_keys)), "collect a smaller discriminating test before generating tools")


@dataclass(frozen=True)
class ToolBlueprint:
    name: str
    op: str
    input_kind: str
    output_kind: str
    cost: int
    params: dict[str, Any]
    source_failure: FailureClass

    @property
    def blueprint_id(self) -> str:
        return sha256_json(asdict(self))[:16]


class DeclarativeToolFactory:
    """Compiles a tiny allow-listed DSL into pure tools.

    No eval/exec/import/subprocess/file/network operations exist in this DSL.
    """

    ALLOWED_OPS = {"identity", "strip", "lower", "normalize_space", "lookup", "threshold", "json_pick"}

    def compile(self, blueprint: ToolBlueprint) -> Tool:
        if blueprint.op not in self.ALLOWED_OPS:
            raise ValueError(f"FORGE_TOOL_OP_FORBIDDEN:{blueprint.op}")
        p = dict(blueprint.params)

        if blueprint.op == "identity":
            fn = lambda x: x
        elif blueprint.op == "strip":
            fn = lambda x: str(x).strip()
        elif blueprint.op == "lower":
            fn = lambda x: str(x).lower()
        elif blueprint.op == "normalize_space":
            fn = lambda x: " ".join(str(x).split())
        elif blueprint.op == "lookup":
            mapping = dict(p.get("mapping", {}))
            default_present = "default" in p
            default = p.get("default")

            def fn(x: Any) -> Any:
                key = str(x)
                if key in mapping:
                    return mapping[key]
                if default_present:
                    return default
                raise KeyError(key)
        elif blueprint.op == "threshold":
            threshold = float(p["threshold"])
            low = p["low"]
            high = p["high"]
            fn = lambda x: high if float(x) >= threshold else low
        elif blueprint.op == "json_pick":
            key = str(p["key"])
            fn = lambda x: x[key]
        else:  # pragma: no cover
            raise AssertionError(blueprint.op)

        return Tool(blueprint.name, blueprint.input_kind, blueprint.output_kind, blueprint.cost, fn)


class ToolSmith:
    """Proposes small transparent tools from BUILD evidence only."""

    def __init__(self, factory: DeclarativeToolFactory | None = None) -> None:
        self.factory = factory or DeclarativeToolFactory()

    def propose(self, diagnosis: FailureDiagnosis, build_cases: Sequence[Case], input_kind: str, output_kind: str) -> tuple[ToolBlueprint, ...]:
        out: list[ToolBlueprint] = []

        if diagnosis.failure_class in {FailureClass.INTERFACE, FailureClass.MEASUREMENT, FailureClass.TOOL} and input_kind == "text":
            for op in ("strip", "lower", "normalize_space"):
                out.append(ToolBlueprint(f"ts_{op}", op, "text", "text", 1, {}, diagnosis.failure_class))

        # Exact BUILD lookup is intentionally embarrassing. DEV/Vault decide whether
        # it generalizes; no hidden evidence is used here.
        mapping: dict[str, Any] = {}
        consistent = True
        for case in build_cases:
            key = str(case.input)
            if key in mapping and mapping[key] != case.expected:
                consistent = False
                break
            mapping[key] = case.expected
        if build_cases and consistent:
            out.append(ToolBlueprint("ts_build_lookup", "lookup", input_kind, output_kind, 1, {"mapping": mapping}, diagnosis.failure_class))

        # For interface-like text failures, ToolSmith may also infer a canonical
        # BUILD dictionary. The canonicalization itself remains separate tools, so
        # Composer must discover the needed recipe and DEV/Vault can kill it.
        if build_cases and input_kind == "text" and diagnosis.failure_class in {FailureClass.INTERFACE, FailureClass.MEASUREMENT, FailureClass.TOOL}:
            canonical: dict[str, Any] = {}
            canonical_ok = True
            for case in build_cases:
                key = " ".join(str(case.input).split()).lower()
                if key in canonical and canonical[key] != case.expected:
                    canonical_ok = False
                    break
                canonical[key] = case.expected
            if canonical_ok:
                out.append(ToolBlueprint("ts_build_lookup_canonical", "lookup", "text", output_kind, 1, {"mapping": canonical}, diagnosis.failure_class))

        return tuple(out)

    def register(self, registry: Registry, blueprints: Sequence[ToolBlueprint]) -> tuple[str, ...]:
        names: list[str] = []
        for blueprint in blueprints:
            registry.register(self.factory.compile(blueprint))
            names.append(blueprint.name)
        return tuple(names)


@dataclass(frozen=True)
class NullResult:
    name: str
    score: float
    failures: tuple[str, ...]


class NullSmith:
    """Scores deliberately simple transparent nulls before complex recipes receive credit."""

    @staticmethod
    def constant_null(cases: Sequence[Case]) -> tuple[NullResult, ...]:
        if not cases:
            return ()
        values = sorted({json.dumps(c.expected, sort_keys=True) for c in cases})
        out: list[NullResult] = []
        for encoded in values:
            value = json.loads(encoded)
            failures = tuple(c.case_id for c in cases if c.expected != value)
            score = 1.0 - len(failures) / len(cases)
            out.append(NullResult(f"constant:{encoded}", score, failures))
        return tuple(sorted(out, key=lambda r: (-r.score, r.name)))

    @staticmethod
    def identity_null(cases: Sequence[Case]) -> NullResult:
        failures = tuple(c.case_id for c in cases if c.input != c.expected)
        return NullResult("identity", 1.0 - len(failures) / len(cases) if cases else 0.0, failures)


@dataclass(frozen=True)
class AblationResult:
    removed_tool: str
    valid: bool
    score: float | None
    delta_from_full: float | None
    reason: str | None


class Ablator:
    def __init__(self, forge: Forge) -> None:
        self.forge = forge

    def single_tool_ablations(self, chain: Chain, cases: Sequence[Case], full_score: float | None = None) -> tuple[AblationResult, ...]:
        if full_score is None:
            full_score = self.forge.score_chain(chain, cases).score
        out: list[AblationResult] = []
        for i, removed in enumerate(chain.tools):
            names = chain.tools[:i] + chain.tools[i + 1 :]
            if not names:
                out.append(AblationResult(removed, False, None, None, "empty_chain"))
                continue
            try:
                kind = chain.input_kind
                cost = 0
                for name in names:
                    tool = self.forge.registry.get(name)
                    if tool.input_kind != kind:
                        raise ValueError(f"type break at {name}")
                    kind = tool.output_kind
                    cost += tool.cost
                if kind != chain.output_kind:
                    raise ValueError("output type changed")
                ablated = Chain(names, chain.input_kind, chain.output_kind, cost)
                score = self.forge.score_chain(ablated, cases).score
                out.append(AblationResult(removed, True, score, full_score - score, None))
            except Exception as exc:
                out.append(AblationResult(removed, False, None, None, str(exc)))
        return tuple(out)


@dataclass(frozen=True)
class RecipeCandidate:
    chain: Chain
    dev_score: float
    objective: float
    null_margin: float
    failures: tuple[str, ...]


class Composer:
    """Bounded recipe search over DEV only, with simplicity/resource penalties."""

    def __init__(self, forge: Forge) -> None:
        self.forge = forge

    def search(self, dev_cases: Sequence[Case], config: SearchConfig, *, complexity_penalty: float = 0.01, cost_penalty: float = 0.005) -> tuple[RecipeCandidate, ...]:
        nulls = list(NullSmith.constant_null(dev_cases)) + [NullSmith.identity_null(dev_cases)]
        best_null = max((n.score for n in nulls), default=0.0)
        scored = self.forge.search(config, dev_cases)
        candidates = [
            RecipeCandidate(
                s.chain,
                s.score,
                s.score - complexity_penalty * len(s.chain.tools) - cost_penalty * s.chain.cost,
                s.score - best_null,
                s.failures,
            )
            for s in scored
        ]
        return tuple(sorted(candidates, key=lambda c: (-c.objective, -c.dev_score, c.chain.cost, c.chain.tools)))


class JudgeVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class JudgeReceipt:
    verdict: JudgeVerdict
    chain_id: str
    vault_digest: str
    score: float
    threshold: float
    min_margin_over_null: float
    best_null_score: float
    receipt_sha256: str


class Judge:
    """One-shot vault verifier. It cannot optimize or mutate candidates."""

    def __init__(self, forge: Forge) -> None:
        self.forge = forge

    def evaluate_once(
        self,
        champion: Chain,
        vault_cases: Sequence[Case],
        *,
        threshold: float,
        min_margin_over_null: float = 0.0,
        receipt_path: Path | None = None,
        consumption_path: Path | None = None,
    ) -> JudgeReceipt:
        # Persistent burn-before-score option. A crash still consumes the Vault run.
        if consumption_path is not None:
            consumption_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with consumption_path.open("x", encoding="utf-8") as handle:
                    handle.write(json.dumps({"status": "VAULT_CONSUMED", "chain_id": champion.chain_id}, sort_keys=True) + "\n")
            except FileExistsError as exc:
                raise RuntimeError("FORGE_VAULT_ALREADY_CONSUMED") from exc
        if receipt_path is not None and receipt_path.exists():
            raise RuntimeError("FORGE_VAULT_RECEIPT_ALREADY_EXISTS")

        nulls = list(NullSmith.constant_null(vault_cases)) + [NullSmith.identity_null(vault_cases)]
        best_null = max((n.score for n in nulls), default=0.0)
        holdout = self.forge.evaluate_holdout_once(champion, vault_cases)
        margin = holdout.score - best_null
        if holdout.total == 0:
            verdict = JudgeVerdict.INCONCLUSIVE
        elif holdout.score >= threshold and margin >= min_margin_over_null:
            verdict = JudgeVerdict.PASS
        else:
            verdict = JudgeVerdict.FAIL
        body = {
            "verdict": verdict.value,
            "chain_id": champion.chain_id,
            "vault_digest": holdout.holdout_digest,
            "score": holdout.score,
            "threshold": threshold,
            "min_margin_over_null": min_margin_over_null,
            "best_null_score": best_null,
        }
        receipt = JudgeReceipt(verdict, champion.chain_id, holdout.holdout_digest, holdout.score, threshold, min_margin_over_null, best_null, sha256_json(body))
        if receipt_path is not None:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps({**body, "receipt_sha256": receipt.receipt_sha256}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt


class Ledger:
    """Append-only hash-chained experiment ledger."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "GENESIS"
        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return "GENESIS"
        return json.loads(lines[-1])["record_sha256"]

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        body = {"prev_sha256": self._last_hash(), **record}
        wrapped = {**body, "record_sha256": sha256_json(body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(wrapped, sort_keys=True) + "\n")
        return wrapped

    def verify(self) -> bool:
        prev = "GENESIS"
        if not self.path.exists():
            return True
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            observed = row.pop("record_sha256")
            if row.get("prev_sha256") != prev or sha256_json(row) != observed:
                return False
            prev = observed
        return True


@dataclass(frozen=True)
class SkillPacket:
    chain_id: str
    tools: tuple[str, ...]
    input_kind: str
    output_kind: str
    cost: int
    judge_receipt_sha256: str
    authority: bool = True

    @property
    def packet_sha256(self) -> str:
        return sha256_json(asdict(self))


def promote_skill(chain: Chain, receipt: JudgeReceipt) -> SkillPacket:
    if receipt.verdict is not JudgeVerdict.PASS:
        raise ValueError("FORGE_PROMOTION_REQUIRES_JUDGE_PASS")
    if receipt.chain_id != chain.chain_id:
        raise ValueError("FORGE_PROMOTION_CHAIN_MISMATCH")
    return SkillPacket(chain.chain_id, chain.tools, chain.input_kind, chain.output_kind, chain.cost, receipt.receipt_sha256)
