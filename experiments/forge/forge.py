from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

Json = Any


def canonical_json(value: Json) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Json) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Tool:
    name: str
    input_kind: str
    output_kind: str
    cost: int
    fn: Callable[[Json], Json]

    def apply(self, value: Json) -> Json:
        return self.fn(value)


@dataclass(frozen=True)
class Chain:
    tools: tuple[str, ...]
    input_kind: str
    output_kind: str
    cost: int

    @property
    def chain_id(self) -> str:
        return sha256_json({
            "tools": self.tools,
            "input_kind": self.input_kind,
            "output_kind": self.output_kind,
            "cost": self.cost,
        })[:16]


@dataclass(frozen=True)
class Case:
    case_id: str
    input: Json
    expected: Json


@dataclass(frozen=True)
class ChainScore:
    chain: Chain
    correct: int
    total: int
    score: float
    failures: tuple[str, ...]


@dataclass(frozen=True)
class SearchConfig:
    input_kind: str
    output_kind: str
    max_depth: int = 4
    max_cost: int = 8
    max_candidates: int = 10000
    allow_repeated_tools: bool = False


@dataclass(frozen=True)
class HoldoutReceipt:
    champion_chain_id: str
    holdout_digest: str
    correct: int
    total: int
    score: float
    receipt_sha256: str


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        if tool.cost < 0:
            raise ValueError("tool cost must be nonnegative")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def compatible_from(self, kind: str) -> tuple[Tool, ...]:
        return tuple(sorted((t for t in self._tools.values() if t.input_kind == kind), key=lambda t: t.name))


class Toolsmith:
    """Builds candidate chains from registered primitives only.

    It does not generate Python, import modules, access files, or execute subprocesses.
    """

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def enumerate(self, config: SearchConfig) -> tuple[Chain, ...]:
        out: list[Chain] = []

        def walk(kind: str, names: tuple[str, ...], cost: int) -> None:
            if len(out) >= config.max_candidates:
                return
            if names and kind == config.output_kind:
                out.append(Chain(names, config.input_kind, kind, cost))
            if len(names) >= config.max_depth:
                return
            for tool in self.registry.compatible_from(kind):
                if not config.allow_repeated_tools and tool.name in names:
                    continue
                new_cost = cost + tool.cost
                if new_cost > config.max_cost:
                    continue
                walk(tool.output_kind, names + (tool.name,), new_cost)

        walk(config.input_kind, (), 0)
        dedup = {c.chain_id: c for c in out}
        return tuple(sorted(dedup.values(), key=lambda c: (len(c.tools), c.cost, c.tools)))


class Forge:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.toolsmith = Toolsmith(registry)
        self._holdout_consumed = False

    def run_chain(self, chain: Chain, value: Json) -> Json:
        kind = chain.input_kind
        current = value
        cost = 0
        for name in chain.tools:
            tool = self.registry.get(name)
            if tool.input_kind != kind:
                raise ValueError(f"type mismatch before {name}: have {kind}, need {tool.input_kind}")
            current = tool.apply(current)
            kind = tool.output_kind
            cost += tool.cost
        if kind != chain.output_kind or cost != chain.cost:
            raise ValueError("chain metadata mismatch")
        return current

    def score_chain(self, chain: Chain, cases: Sequence[Case]) -> ChainScore:
        failures: list[str] = []
        correct = 0
        for case in cases:
            try:
                observed = self.run_chain(chain, case.input)
            except Exception as exc:
                failures.append(f"{case.case_id}:EXCEPTION:{type(exc).__name__}")
                continue
            if observed == case.expected:
                correct += 1
            else:
                failures.append(case.case_id)
        total = len(cases)
        return ChainScore(chain, correct, total, correct / total if total else 0.0, tuple(failures))

    def search(self, config: SearchConfig, dev_cases: Sequence[Case]) -> tuple[ChainScore, ...]:
        """Search DEVELOPMENT cases only. There is intentionally no holdout argument."""
        candidates = self.toolsmith.enumerate(config)
        scored = [self.score_chain(chain, dev_cases) for chain in candidates]
        return tuple(sorted(scored, key=lambda s: (-s.score, s.chain.cost, len(s.chain.tools), s.chain.tools)))

    def evaluate_holdout_once(self, champion: Chain, holdout_cases: Sequence[Case], receipt_path: Path | None = None) -> HoldoutReceipt:
        if self._holdout_consumed:
            raise RuntimeError("FORGE_HOLDOUT_ALREADY_CONSUMED")
        self._holdout_consumed = True
        score = self.score_chain(champion, holdout_cases)
        holdout_digest = sha256_json([
            {"case_id": c.case_id, "input": c.input, "expected": c.expected}
            for c in holdout_cases
        ])
        body = {
            "champion_chain_id": champion.chain_id,
            "holdout_digest": holdout_digest,
            "correct": score.correct,
            "total": score.total,
            "score": score.score,
        }
        receipt = HoldoutReceipt(**body, receipt_sha256=sha256_json(body))
        if receipt_path is not None:
            if receipt_path.exists():
                raise FileExistsError(f"refusing to overwrite holdout receipt: {receipt_path}")
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt


@dataclass(frozen=True)
class Mutation:
    name: str
    fn: Callable[[Case], Iterable[Case]]


@dataclass(frozen=True)
class Failure:
    mutation: str
    source_case: str
    mutated_case: str
    observed: Json
    expected: Json


class Grinder:
    """Mines counterexamples against a fixed chain.

    Mutations are explicit and allow-listed. The grinder never changes the chain.
    """

    def __init__(self, forge: Forge, mutations: Sequence[Mutation]) -> None:
        self.forge = forge
        self.mutations = tuple(mutations)

    def grind(self, chain: Chain, cases: Sequence[Case], max_failures: int = 100) -> tuple[Failure, ...]:
        failures: list[Failure] = []
        for mutation in self.mutations:
            for source in cases:
                for mutated in mutation.fn(source):
                    try:
                        observed = self.forge.run_chain(chain, mutated.input)
                    except Exception as exc:
                        observed = {"exception": type(exc).__name__}
                    if observed != mutated.expected:
                        failures.append(Failure(mutation.name, source.case_id, mutated.case_id, observed, mutated.expected))
                        if len(failures) >= max_failures:
                            return tuple(failures)
        return tuple(failures)
