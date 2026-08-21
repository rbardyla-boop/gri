from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, fields
from typing import Any, Iterable

import torch
from torch import nn

from dmc00.benchmark import VALUES
from gri_models.rri02pa import ImmutableRelationAnchorReasoner


VALUE_TO_INDEX = {value: index for index, value in enumerate(VALUES)}
HIDDEN_DIM = 49
MESSAGE_DIM = 51
TRAIN_DEPTH = 4
FIELD = "value"


@dataclass(frozen=True)
class DMCEventGraph:
    """The smallest fixed graph accepted by the frozen RRI processor.

    Node 0 is the source/query subject and node 1 is the object/query target.
    A write value is represented only as an input relation channel. Query and
    noise graphs have no relation channels, so they contain no answer value.
    """

    node_features: torch.Tensor
    edges: torch.Tensor
    query_subject: int = 0
    query_object: int = 1


def _role_graph(*, value_index: int | None) -> DMCEventGraph:
    node_features = torch.tensor(
        [[1.0, 1.0, 0.0], [1.0, 0.0, 1.0]], dtype=torch.float32
    )
    edges = torch.zeros((2, 2, len(VALUES)), dtype=torch.float32)
    if value_index is not None:
        edges[0, 1, value_index] = 1.0
    return DMCEventGraph(node_features=node_features, edges=edges)


def _require_keys(event: dict[str, Any], expected: set[str], kind: str) -> None:
    if set(event) != expected or event.get("kind") != kind:
        raise ValueError(f"malformed DMC {kind} event")


def encode_event(event: dict[str, Any]) -> DMCEventGraph:
    """Map one DMC event to the frozen RRI input shape.

    This adapter is deterministic and has no parameters. The existing RRI
    node encoder and message/update stack remain the only trainable encoder.
    Entity, field, query mode, memory id, and noise token are deliberately not
    placed in the neural event graph; entity/field are consumed only by the
    exact ledger address and query mode only selects a ledger record.
    """

    kind = event.get("kind")
    if kind == "write":
        _require_keys(event, {"kind", "memory_id", "entity", "field", "value"}, kind)
        if event["field"] != FIELD or event["value"] not in VALUE_TO_INDEX:
            raise ValueError("malformed DMC write payload")
        return _role_graph(value_index=VALUE_TO_INDEX[event["value"]])
    if kind == "query":
        _require_keys(event, {"kind", "entity", "field", "mode", "as_of_episode"}, kind)
        if event["field"] != FIELD or event["mode"] not in {"current", "history"}:
            raise ValueError("malformed DMC query payload")
        if event["mode"] == "current" and event["as_of_episode"] is not None:
            raise ValueError("current query cannot expose history index")
        if event["mode"] == "history" and not isinstance(event["as_of_episode"], int):
            raise ValueError("history query requires as_of_episode")
        return _role_graph(value_index=None)
    if kind == "noise":
        _require_keys(event, {"kind", "token"}, kind)
        return _role_graph(value_index=None)
    raise ValueError("unsupported DMC event kind")


@dataclass(frozen=True)
class MemoryRecord:
    """One append-only hidden representation; no symbolic answer is stored."""

    memory_id: str
    entity: str
    field: str
    creation_episode: int
    supersedes: str | None
    source_episode: int
    hidden_value: torch.Tensor


class ExactEpisodicLedger:
    """Zero-parameter append-only address store for DMC-01P."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], list[MemoryRecord]] = defaultdict(list)

    @property
    def trainable_parameter_count(self) -> int:
        return 0

    def reset(self) -> None:
        self._entries = defaultdict(list)

    def append(
        self,
        *,
        memory_id: str,
        entity: str,
        field: str,
        creation_episode: int,
        hidden_value: torch.Tensor,
    ) -> MemoryRecord:
        if not memory_id or not entity or field != FIELD or creation_episode < 0:
            raise ValueError("malformed memory metadata")
        if not isinstance(hidden_value, torch.Tensor) or hidden_value.ndim != 1:
            raise ValueError("hidden_value must be one hidden vector")
        key = (entity, field)
        previous = self._entries[key][-1] if self._entries[key] else None
        record = MemoryRecord(
            memory_id=memory_id,
            entity=entity,
            field=field,
            creation_episode=creation_episode,
            supersedes=previous.memory_id if previous else None,
            source_episode=creation_episode,
            hidden_value=hidden_value.clone(),
        )
        if any(existing.memory_id == memory_id for values in self._entries.values() for existing in values):
            raise ValueError("memory_id must be unique within a case")
        self._entries[key].append(record)
        return record

    def entries(self, entity: str, field: str = FIELD) -> tuple[MemoryRecord, ...]:
        return tuple(self._entries.get((entity, field), ()))

    def retrieve(
        self,
        *,
        entity: str,
        field: str = FIELD,
        mode: str,
        as_of_episode: int | None,
    ) -> MemoryRecord:
        if mode not in {"current", "history"}:
            raise ValueError("unknown retrieval mode")
        entries = list(self._entries.get((entity, field), ()))
        if mode == "history":
            if not isinstance(as_of_episode, int):
                raise ValueError("history retrieval requires as_of_episode")
            entries = [entry for entry in entries if entry.creation_episode <= as_of_episode]
        if not entries:
            raise LookupError("no exact memory record for query")
        return entries[-1]

    def all_entries(self) -> tuple[MemoryRecord, ...]:
        return tuple(entry for values in self._entries.values() for entry in values)


class DMC01Controller(nn.Module):
    """Shared RRI processor with an optional exact external ledger.

    ``retain_memory=False`` is the parameter-matched no-memory control. Both
    variants contain the same RRI module; the control simply discards write
    states and runs a query without an injected vector.
    """

    def __init__(self, processor: ImmutableRelationAnchorReasoner, *, retain_memory: bool):
        super().__init__()
        self.processor = processor
        self.retain_memory = retain_memory
        self.ledger: ExactEpisodicLedger | None = ExactEpisodicLedger() if retain_memory else None

    def reset_case(self) -> None:
        if self.ledger is not None:
            self.ledger.reset()

    def _run_graph(self, graph: DMCEventGraph, *, injected: torch.Tensor | None = None) -> torch.Tensor:
        h0 = self.processor.initialize(graph)
        anchor = self.processor.make_anchor(h0)
        h = h0
        if injected is not None:
            if injected.shape != (self.processor.hidden_dim,):
                raise ValueError("retrieved hidden vector has the wrong shape")
            h = h.clone()
            h[graph.query_object] = h[graph.query_object] + injected.to(h.device)
        edges = graph.edges.to(h.device)
        for _ in range(TRAIN_DEPTH):
            h = self.processor.recurrent_step(h, edges, anchor)
        return h

    def process_write(self, event: dict[str, Any], episode_index: int) -> MemoryRecord | None:
        _require_keys(event, {"kind", "memory_id", "entity", "field", "value"}, "write")
        graph = encode_event(event)
        state = self._run_graph(graph)
        if self.ledger is None:
            return None
        return self.ledger.append(
            memory_id=event["memory_id"],
            entity=event["entity"],
            field=event["field"],
            creation_episode=episode_index,
            hidden_value=state[graph.query_object],
        )

    def process_noise(self, event: dict[str, Any]) -> None:
        _require_keys(event, {"kind", "token"}, "noise")
        _ = self._run_graph(encode_event(event))

    def answer_query(self, event: dict[str, Any]) -> torch.Tensor:
        _require_keys(event, {"kind", "entity", "field", "mode", "as_of_episode"}, "query")
        graph = encode_event(event)
        injected = None
        if self.ledger is not None:
            record = self.ledger.retrieve(
                entity=event["entity"],
                field=event["field"],
                mode=event["mode"],
                as_of_episode=event["as_of_episode"],
            )
            injected = record.hidden_value
        state = self._run_graph(graph, injected=injected)
        return self.processor.readout_hidden(state, graph.query_subject, graph.query_object)

    def answer_query_with_hidden(self, event: dict[str, Any], hidden_value: torch.Tensor) -> torch.Tensor:
        """Evaluate the frozen query path with an externally selected vector.

        This is used only by the preregistered SHUFFLED_MEMORY evaluation. It
        bypasses symbolic address selection but preserves the same graph,
        anchor, injection point, recurrent steps, and mutable-only readout.
        """

        graph = encode_event(event)
        state = self._run_graph(graph, injected=hidden_value)
        return self.processor.readout_hidden(state, graph.query_subject, graph.query_object)


def build_paired_controllers(seed: int) -> tuple[DMC01Controller, DMC01Controller]:
    """Build exact/no-memory controllers with tensor-identical RRI weights."""

    torch.manual_seed(seed)
    exact = DMC01Controller(
        ImmutableRelationAnchorReasoner(hidden_dim=HIDDEN_DIM, message_dim=MESSAGE_DIM),
        retain_memory=True,
    )
    torch.manual_seed(seed)
    no_memory = DMC01Controller(
        ImmutableRelationAnchorReasoner(hidden_dim=HIDDEN_DIM, message_dim=MESSAGE_DIM),
        retain_memory=False,
    )
    return exact, no_memory


def trainable_parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def state_dict_equal(left: nn.Module, right: nn.Module) -> bool:
    left_state = left.state_dict()
    right_state = right.state_dict()
    return list(left_state) == list(right_state) and all(
        torch.equal(left_state[key], right_state[key]) for key in left_state
    )


def memory_record_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(MemoryRecord))


def build_shuffle_mapping(cases: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Freeze a deterministic same-condition cyclic peer mapping.

    Evaluation will replace a case's retrieved vector with the lexicographically
    next case in its own balanced family/condition group. No training uses this
    mapping, and the mapping never selects the case itself.
    """

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for case in cases:
        groups[(case["family"], case["condition"])].append(case["case_id"])
    mapping: dict[str, str] = {}
    for group, case_ids in groups.items():
        ordered = sorted(case_ids)
        if len(ordered) < 2:
            raise ValueError(f"shuffle group {group} needs at least two cases")
        for index, case_id in enumerate(ordered):
            mapping[case_id] = ordered[(index + 1) % len(ordered)]
    return mapping
