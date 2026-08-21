from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Iterable

import torch
from torch import nn

from dmc00.benchmark import VALUES
from dmc01.memory import FIELD, HIDDEN_DIM, MESSAGE_DIM, TRAIN_DEPTH, encode_event
from gri_models.rri02pa import ImmutableRelationAnchorReasoner


CAPACITY = 16
RANDOM_CONTROL_SEED = 20260202
FAMILIES = {"mission_set", "salience", "supersession", "utility_change", "distractor_flood"}


@dataclass(frozen=True)
class RetentionMetadata:
    """The only input accepted by a retention decision.

    It intentionally contains no write value, hidden vector, answer, case ID,
    final query, or future event.  The neural path consumes the value before
    this metadata-only policy is called.
    """

    family: str
    entity: str
    field: str
    creation_episode: int
    salience: str | None
    supersedes: str | None


@dataclass(frozen=True)
class MemoryRecord:
    """One physical neural record; no symbolic answer value is stored."""

    memory_id: str
    entity: str
    field: str
    creation_episode: int
    supersedes: str | None
    source_episode: int
    hidden_value: torch.Tensor
    salience: str | None


def trainable_parameter_count(module: nn.Module) -> int:
    return sum(parameter.numel() for parameter in module.parameters() if parameter.requires_grad)


def stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _core_write_event(event: dict[str, Any]) -> dict[str, Any]:
    required = {"kind", "memory_id", "entity", "field", "value"}
    if event.get("kind") != "write" or not required.issubset(event) or event["field"] != FIELD or event["value"] not in VALUES:
        raise ValueError("malformed DMC-02 write event")
    return {key: event[key] for key in required}


class ExactRetentionPolicy:
    """Zero-parameter, benchmark-authorized retention policy."""

    def __init__(self, family: str) -> None:
        if family not in FAMILIES:
            raise ValueError(f"unknown DMC-02A family: {family}")
        self.family = family
        self.active_entities: frozenset[str] | None = None

    def mission_set(self, entities: Iterable[str]) -> None:
        values = tuple(entities)
        if not values or len(values) not in {8, 16} or len(set(values)) != len(values):
            raise ValueError("invalid mission scope")
        self.active_entities = frozenset(values)

    def mission_update(self, entities: Iterable[str]) -> None:
        if self.family != "utility_change":
            raise ValueError("mission update is only valid for utility_change")
        self.mission_set(entities)

    def admits(self, metadata: RetentionMetadata) -> bool:
        """Decide from authorized metadata only; no answer/query access exists."""

        if metadata.family != self.family or metadata.field != FIELD:
            raise ValueError("retention metadata family/field mismatch")
        if self.family in {"mission_set", "supersession", "utility_change"}:
            return self.active_entities is not None and metadata.entity in self.active_entities
        if self.family in {"salience", "distractor_flood"}:
            return metadata.salience == "HIGH"
        raise AssertionError("unreachable family")


class ExactRetention16Ledger:
    """Exactly bounded physical storage for benchmark-authorized retention."""

    def __init__(self, policy: ExactRetentionPolicy) -> None:
        self.policy = policy
        self._records: list[MemoryRecord] = []

    @property
    def capacity(self) -> int:
        return CAPACITY

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> tuple[MemoryRecord, ...]:
        return tuple(self._records)

    def clear(self) -> None:
        self._records.clear()

    def evict_not_in(self, entities: frozenset[str]) -> None:
        self._records = [record for record in self._records if record.entity in entities]
        self._assert_capacity()

    def consider(self, record: MemoryRecord) -> bool:
        metadata = RetentionMetadata(
            family=self.policy.family,
            entity=record.entity,
            field=record.field,
            creation_episode=record.creation_episode,
            salience=record.salience,
            supersedes=record.supersedes,
        )
        if not self.policy.admits(metadata):
            self._assert_capacity()
            return False
        if self.policy.family == "utility_change":
            # The explicit mission update made the old value obsolete for the
            # current-only utility-shift task. Supersession history never uses
            # this path, so its old records remain intact.
            self._records = [old for old in self._records if old.entity != record.entity]
        if any(old.memory_id == record.memory_id for old in self._records):
            raise ValueError("memory_id must be unique within a case")
        self._records.append(record)
        self._assert_capacity()
        return True

    def retrieve(self, *, entity: str, field: str, mode: str, as_of_episode: int | None) -> MemoryRecord:
        if mode not in {"current", "history"} or field != FIELD:
            raise ValueError("invalid exact retrieval request")
        matches = [record for record in self._records if record.entity == entity and record.field == field]
        if mode == "history":
            if not isinstance(as_of_episode, int):
                raise ValueError("history retrieval requires as_of_episode")
            matches = [record for record in matches if record.creation_episode <= as_of_episode]
        if not matches:
            raise LookupError("no retained exact record")
        return max(matches, key=lambda record: record.creation_episode)

    def _assert_capacity(self) -> None:
        if len(self._records) > CAPACITY:
            raise AssertionError("DMC-02P physical memory exceeded 16 records")


class FIFO16Ledger:
    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> tuple[MemoryRecord, ...]:
        return tuple(self._records)

    def clear(self) -> None:
        self._records.clear()

    def consider(self, record: MemoryRecord) -> bool:
        self._records.append(record)
        if len(self._records) > CAPACITY:
            self._records.pop(0)
        return True

    def retrieve(self, *, entity: str, field: str, mode: str, as_of_episode: int | None) -> MemoryRecord:
        if mode == "history":
            records = [record for record in self._records if record.creation_episode <= (as_of_episode if isinstance(as_of_episode, int) else -1)]
        else:
            records = list(self._records)
        matches = [record for record in records if record.entity == entity and record.field == field]
        if not matches:
            raise LookupError("no FIFO record")
        return max(matches, key=lambda record: record.creation_episode)


class Random16Ledger:
    """The exact deterministic reservoir rule frozen by DMC-02A."""

    def __init__(self, *, seed: int = RANDOM_CONTROL_SEED, case_id: str = "") -> None:
        self.seed = seed
        self.case_id = case_id
        self._records: list[MemoryRecord] = []
        self._seen = 0

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> tuple[MemoryRecord, ...]:
        return tuple(self._records)

    def clear(self) -> None:
        self._records.clear()
        self._seen = 0

    def consider(self, record: MemoryRecord) -> bool:
        self._seen += 1
        if len(self._records) < CAPACITY:
            self._records.append(record)
            return True
        draw = stable_int("DMC02A-random-reservoir", self.seed, self.case_id, self._seen, record.memory_id)
        if draw % self._seen < CAPACITY:
            slot = stable_int("DMC02A-random-slot", self.seed, self.case_id, self._seen, record.memory_id) % CAPACITY
            self._records[slot] = record
            return True
        return False

    def retrieve(self, *, entity: str, field: str, mode: str, as_of_episode: int | None) -> MemoryRecord:
        if mode == "history":
            records = [record for record in self._records if record.creation_episode <= (as_of_episode if isinstance(as_of_episode, int) else -1)]
        else:
            records = list(self._records)
        matches = [record for record in records if record.entity == entity and record.field == field]
        if not matches:
            raise LookupError("no random-retention record")
        return max(matches, key=lambda record: record.creation_episode)


class DMC02PController(nn.Module):
    """Frozen DMC-01 processor plus one of three zero-parameter ledgers."""

    def __init__(self, processor: ImmutableRelationAnchorReasoner, *, family: str, mode: str, case_id: str = "", random_seed: int = RANDOM_CONTROL_SEED) -> None:
        super().__init__()
        if family not in FAMILIES:
            raise ValueError(f"unknown family: {family}")
        if mode not in {"exact16", "fifo16", "random16"}:
            raise ValueError(f"unknown memory mode: {mode}")
        self.processor = processor
        self.family = family
        self.mode = mode
        self.case_id = case_id
        if mode == "exact16":
            self.ledger: Any = ExactRetention16Ledger(ExactRetentionPolicy(family))
        elif mode == "fifo16":
            self.ledger = FIFO16Ledger()
        else:
            self.ledger = Random16Ledger(seed=random_seed, case_id=case_id)

    @property
    def capacity(self) -> int:
        return CAPACITY

    @property
    def trainable_memory_parameter_count(self) -> int:
        return 0

    def reset_case(self) -> None:
        self.ledger.clear()
        if self.mode == "exact16":
            self.ledger.policy.active_entities = None

    def process_scope_event(self, event: dict[str, Any]) -> None:
        if self.mode != "exact16":
            self._assert_capacity()
            return
        if event.get("kind") == "mission_set":
            self.ledger.policy.mission_set(event["entities"])
        elif event.get("kind") == "mission_update":
            self.ledger.policy.mission_update(event["entities"])
            self.ledger.evict_not_in(self.ledger.policy.active_entities or frozenset())
        else:
            raise ValueError("unsupported scope event")
        self._assert_capacity()

    def encode_hidden(self, event: dict[str, Any]) -> torch.Tensor:
        core = _core_write_event(event)
        graph = encode_event(core)
        h0 = self.processor.initialize(graph)
        anchor = self.processor.make_anchor(h0)
        h = h0
        for _ in range(TRAIN_DEPTH):
            h = self.processor.recurrent_step(h, graph.edges.to(h.device), anchor)
        hidden = h[graph.query_object]
        if hidden.shape != (HIDDEN_DIM,):
            raise ValueError("DMC-01 hidden representation shape changed")
        return hidden

    def make_record(self, event: dict[str, Any], episode_index: int, hidden_value: torch.Tensor | None = None) -> MemoryRecord:
        core = _core_write_event(event)
        if episode_index < 0 or not isinstance(event.get("memory_id"), str) or not event["memory_id"]:
            raise ValueError("malformed record metadata")
        hidden = self.encode_hidden(core) if hidden_value is None else hidden_value
        if not isinstance(hidden, torch.Tensor) or hidden.ndim != 1 or hidden.shape != (HIDDEN_DIM,):
            raise ValueError("hidden_value must be one 49-dimensional tensor")
        return MemoryRecord(
            memory_id=event["memory_id"],
            entity=event["entity"],
            field=event["field"],
            creation_episode=episode_index,
            supersedes=event.get("supersedes"),
            source_episode=episode_index,
            hidden_value=hidden,
            salience=event.get("salience"),
        )

    def retain_record(self, record: MemoryRecord) -> bool:
        retained = self.ledger.consider(record)
        self._assert_capacity()
        return retained

    def process_write(self, event: dict[str, Any], episode_index: int) -> MemoryRecord:
        # Hidden generation happens even when the zero-parameter policy drops
        # the record, matching the DMC-02P event ordering contract.
        record = self.make_record(event, episode_index)
        self.retain_record(record)
        return record

    def retrieve(self, query: dict[str, Any]) -> MemoryRecord:
        required = {"kind", "entity", "field", "mode", "as_of_episode"}
        if set(query) != required or query["kind"] != "query":
            raise ValueError("malformed exact query")
        return self.ledger.retrieve(entity=query["entity"], field=query["field"], mode=query["mode"], as_of_episode=query["as_of_episode"])

    def _assert_capacity(self) -> None:
        if len(self.ledger) > CAPACITY:
            raise AssertionError("DMC-02P memory invariant violated")


class ExactRetention16Controller(DMC02PController):
    def __init__(self, processor: ImmutableRelationAnchorReasoner, *, family: str, case_id: str = "") -> None:
        super().__init__(processor, family=family, mode="exact16", case_id=case_id)


class FIFO16Controller(DMC02PController):
    def __init__(self, processor: ImmutableRelationAnchorReasoner, *, family: str, case_id: str = "") -> None:
        super().__init__(processor, family=family, mode="fifo16", case_id=case_id)


class Random16Controller(DMC02PController):
    def __init__(self, processor: ImmutableRelationAnchorReasoner, *, family: str, case_id: str = "", seed: int = RANDOM_CONTROL_SEED) -> None:
        super().__init__(processor, family=family, mode="random16", case_id=case_id, random_seed=seed)


def build_processor() -> ImmutableRelationAnchorReasoner:
    return ImmutableRelationAnchorReasoner(hidden_dim=HIDDEN_DIM, message_dim=MESSAGE_DIM)


def load_dmc01_checkpoint(path: str | Path, *, family: str, mode: str = "exact16", case_id: str = "") -> tuple[DMC02PController, dict[str, Any]]:
    """Load a frozen DMC-01 controller state without optimizer or training state."""

    payload = torch.load(Path(path), map_location="cpu", weights_only=False)
    processor = build_processor()
    controller = DMC02PController(processor, family=family, mode=mode, case_id=case_id)
    controller.load_state_dict(payload["model_state_dict"], strict=True)
    controller.eval()
    return controller, payload


def memory_record_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(MemoryRecord))


def retention_metadata_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(RetentionMetadata))
