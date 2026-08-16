from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .relations import Relation


class TaskFamily(str, Enum):
    DIRECT = "W0-A"
    INVERSE = "W0-B"
    COMPOSITION = "W0-C"
    LONG_CHAIN = "W0-D"
    CONTRADICTION = "W0-X"


class SolveStatus(str, Enum):
    VALID = "valid"
    NO_ANSWER = "no_answer"
    AMBIGUOUS = "ambiguous"
    CONTRADICTION = "contradiction"


@dataclass(frozen=True, order=True)
class Fact:
    subject: int
    relation: Relation
    object: int

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "relation": self.relation.value, "object": self.object}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Fact":
        return cls(int(value["subject"]), Relation(value["relation"]), int(value["object"]))


@dataclass(frozen=True)
class Query:
    subject: int
    object: int

    def to_dict(self) -> dict[str, int]:
        return {"subject": self.subject, "object": self.object}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Query":
        return cls(int(value["subject"]), int(value["object"]))


@dataclass(frozen=True)
class SolveResult:
    status: SolveStatus
    relation: Relation | None = None


@dataclass(frozen=True)
class Sample:
    benchmark_version: str
    sample_id: str
    seed: int
    split: str
    task_family: TaskFamily
    chain_length: int
    entities: tuple[int, ...]
    facts: tuple[Fact, ...]
    query: Query
    answer: Relation | None
    contradiction_label: bool
    generation_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_version": self.benchmark_version,
            "sample_id": self.sample_id,
            "seed": self.seed,
            "split": self.split,
            "task_family": self.task_family.value,
            "chain_length": self.chain_length,
            "entities": list(self.entities),
            "facts": [fact.to_dict() for fact in self.facts],
            "query": self.query.to_dict(),
            "answer": self.answer.value if self.answer else None,
            "contradiction_label": self.contradiction_label,
            "generation_metadata": self.generation_metadata,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Sample":
        return cls(
            benchmark_version=str(value["benchmark_version"]),
            sample_id=str(value["sample_id"]),
            seed=int(value["seed"]),
            split=str(value["split"]),
            task_family=TaskFamily(value["task_family"]),
            chain_length=int(value["chain_length"]),
            entities=tuple(int(v) for v in value["entities"]),
            facts=tuple(Fact.from_dict(v) for v in value["facts"]),
            query=Query.from_dict(value["query"]),
            answer=Relation(value["answer"]) if value.get("answer") else None,
            contradiction_label=bool(value["contradiction_label"]),
            generation_metadata=dict(value.get("generation_metadata", {})),
        )
