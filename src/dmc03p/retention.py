from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch
from torch import nn

from dmc00.benchmark import VALUES
from dmc01.memory import FIELD, HIDDEN_DIM, MESSAGE_DIM, TRAIN_DEPTH, encode_event
from dmc02p.controller import MemoryRecord, RetentionMetadata
from gri_models.rri02pa import ImmutableRelationAnchorReasoner


CAPACITY = 16
FEATURE_DIM = 2
AFFINE_PARAMETER_COUNT = FEATURE_DIM + 1
EVIDENCE_SEEDS = (1337, 1338, 1339, 1340, 1341)
NON_EVIDENCE_SEED = 9090
RANDOM_CONTROL_SEED = 20260202
FAMILIES = frozenset({"mission_set", "salience", "supersession", "utility_change", "distractor_flood"})
MISSION_FAMILIES = frozenset({"mission_set", "supersession", "utility_change"})
SHUFFLE_SEED = 20260303

FORBIDDEN_RETENTION_NAMES = frozenset(
    {
        "answer",
        "answer_value",
        "case_id",
        "correctness",
        "future_event",
        "future_events",
        "hidden_answer",
        "hidden_value",
        "oracle_action",
        "oracle_answer",
        "query",
        "query_key",
        "query_entity",
        "query_field",
        "target",
        "value",
    }
)


def trainable_parameter_count(module: nn.Module) -> int:
    return sum(parameter.numel() for parameter in module.parameters() if parameter.requires_grad)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def model_state_hash(module: nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in module.state_dict().items():
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(tuple(tensor.shape)).encode("ascii"))
        digest.update(b"\0")
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def _stable_digest(*parts: object) -> str:
    return sha256_bytes("|".join(str(part) for part in parts).encode("utf-8"))


def _validate_metadata(metadata: RetentionMetadata) -> None:
    if metadata.family not in FAMILIES or metadata.field != FIELD:
        raise ValueError("retention metadata is outside the DMC-02A family contract")
    if metadata.salience not in {None, "HIGH", "LOW"}:
        raise ValueError("invalid salience metadata")
    if not isinstance(metadata.entity, str) or not metadata.entity:
        raise ValueError("invalid exact-key metadata")
    if not isinstance(metadata.creation_episode, int) or metadata.creation_episode < 0:
        raise ValueError("invalid creation episode")


@dataclass(frozen=True)
class RetentionFeatureEncoder:
    """The frozen two-feature map for DMC-03P.

    The encoder accepts only RetentionMetadata plus the currently active
    mission scope.  It never accepts a MemoryRecord, hidden vector, answer, or
    query.  The two features exactly express the DMC-02A admission predicate:
    mission-family records are useful iff they are in scope; salience-family
    records are useful iff they are HIGH salience.
    """

    feature_names: tuple[str, str] = ("mission_membership", "high_salience")

    def encode(self, metadata: RetentionMetadata, active_entities: Iterable[str] | None) -> torch.Tensor:
        _validate_metadata(metadata)
        active = frozenset(active_entities or ())
        in_mission = float(metadata.family in MISSION_FAMILIES and metadata.entity in active)
        high_salience = float(metadata.salience == "HIGH")
        return torch.tensor((in_mission, high_salience), dtype=torch.float32)

    def as_json(self) -> dict[str, Any]:
        return {
            "feature_dim": FEATURE_DIM,
            "features": [
                {
                    "name": "mission_membership",
                    "source_field": "active_entities + RetentionMetadata.entity",
                    "encoding": "1 iff family is mission_set, supersession, or utility_change and entity is in the current active mission scope; otherwise 0",
                    "numeric_range": [0, 1],
                    "type": "boolean",
                    "available_before_final_query": True,
                    "why_authorized": "DMC-02A mission membership is an explicit retention utility signal.",
                },
                {
                    "name": "high_salience",
                    "source_field": "RetentionMetadata.salience",
                    "encoding": "1 for HIGH and 0 for LOW or absent",
                    "numeric_range": [0, 1],
                    "type": "boolean",
                    "available_before_final_query": True,
                    "why_authorized": "DMC-02A salience and distractor-flood retention uses explicit HIGH/LOW salience.",
                },
            ],
            "excluded_authorized_fields": [
                {
                    "field": "RetentionMetadata.supersedes",
                    "reason": "not needed because supersession records are already selected by current mission membership",
                },
                {
                    "field": "RetentionMetadata.creation_episode",
                    "reason": "not needed by the frozen DMC-02A bounded admission rule",
                },
            ],
            "forbidden_inputs": sorted(FORBIDDEN_RETENTION_NAMES),
            "affine_sufficiency": "oracle_retain = 1 iff mission_membership == 1 or high_salience == 1; w=(1,1), b=-0.5 separates the two classes",
        }


FEATURE_ENCODER = RetentionFeatureEncoder()


def retention_features(metadata: RetentionMetadata, active_entities: Iterable[str] | None) -> torch.Tensor:
    return FEATURE_ENCODER.encode(metadata, active_entities)


def authorized_oracle_target(metadata: RetentionMetadata, active_entities: Iterable[str] | None) -> int:
    features = retention_features(metadata, active_entities)
    return int(bool(features[0].item() or features[1].item()))


class AffineRetentionScorer(nn.Module):
    """Smallest preregistered learned priority model: x -> w dot x + b."""

    def __init__(self, feature_dim: int = FEATURE_DIM) -> None:
        super().__init__()
        if feature_dim != FEATURE_DIM:
            raise ValueError("DMC-03P feature dimension is frozen at two")
        self.linear = nn.Linear(feature_dim, 1, bias=True)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        if features.shape[-1] != FEATURE_DIM:
            raise ValueError("retention feature shape changed")
        return self.linear(features).squeeze(-1)

    @property
    def parameter_count(self) -> int:
        return trainable_parameter_count(self)


def initialize_scorer(seed: int) -> AffineRetentionScorer:
    """Initialize without mutating the caller's global RNG stream."""

    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        scorer = AffineRetentionScorer()
    return scorer


def freeze_processor(processor: nn.Module) -> nn.Module:
    processor.eval()
    for parameter in processor.parameters():
        parameter.requires_grad_(False)
    return processor


def assert_processor_frozen(processor: nn.Module) -> None:
    if any(parameter.requires_grad for parameter in processor.parameters()):
        raise AssertionError("DMC-03P processor is not frozen")


def build_retention_optimizer(scorer: AffineRetentionScorer) -> torch.optim.Optimizer:
    """Build the future optimizer while proving it can see scorer only."""

    parameters = list(scorer.parameters())
    if len(parameters) != 2 or trainable_parameter_count(scorer) != AFFINE_PARAMETER_COUNT:
        raise AssertionError("unexpected affine scorer parameterization")
    return torch.optim.AdamW(parameters, lr=1e-2, weight_decay=0.0)


def load_frozen_processor(path: str | Path) -> tuple[ImmutableRelationAnchorReasoner, dict[str, Any]]:
    payload = torch.load(Path(path), map_location="cpu", weights_only=False)
    processor = ImmutableRelationAnchorReasoner(hidden_dim=HIDDEN_DIM, message_dim=MESSAGE_DIM)
    state = {
        name.removeprefix("processor."): tensor
        for name, tensor in payload["model_state_dict"].items()
        if name.startswith("processor.")
    }
    if len(state) != len(processor.state_dict()):
        raise AssertionError("DMC-01 checkpoint processor state is incomplete")
    processor.load_state_dict(state, strict=True)
    freeze_processor(processor)
    assert_processor_frozen(processor)
    if sum(parameter.numel() for parameter in processor.parameters()) != 30_912:
        raise AssertionError("frozen DMC-01 processor parameter count changed")
    return processor, payload


def _validate_write_event(event: dict[str, Any]) -> None:
    required = {"kind", "memory_id", "entity", "field", "value"}
    if event.get("kind") != "write" or not required.issubset(event):
        raise ValueError("malformed DMC-03P write event")
    if event["field"] != FIELD or event["value"] not in VALUES:
        raise ValueError("malformed DMC-03P write core")
    if not isinstance(event["memory_id"], str) or not event["memory_id"]:
        raise ValueError("missing memory identity")


def encode_hidden(processor: ImmutableRelationAnchorReasoner, event: dict[str, Any]) -> torch.Tensor:
    _validate_write_event(event)
    core = {key: event[key] for key in ("kind", "memory_id", "entity", "field", "value")}
    graph = encode_event(core)
    h0 = processor.initialize(graph)
    anchor = processor.make_anchor(h0)
    h = h0
    for _ in range(TRAIN_DEPTH):
        h = processor.recurrent_step(h, graph.edges.to(h.device), anchor)
    hidden = h[graph.query_object]
    if hidden.shape != (HIDDEN_DIM,):
        raise ValueError("DMC-03P hidden representation shape changed")
    return hidden


def record_metadata(record: MemoryRecord, family: str) -> RetentionMetadata:
    return RetentionMetadata(
        family=family,
        entity=record.entity,
        field=record.field,
        creation_episode=record.creation_episode,
        salience=record.salience,
        supersedes=record.supersedes,
    )


class LearnedRetention16Ledger:
    """Hard-cap learned top-16 retention with exact deterministic retrieval."""

    def __init__(self, scorer: AffineRetentionScorer, *, family: str) -> None:
        if family not in FAMILIES:
            raise ValueError(f"unknown DMC-02A family: {family}")
        self.scorer = scorer
        self.family = family
        self.active_entities: frozenset[str] | None = None
        self._records: list[MemoryRecord] = []

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> tuple[MemoryRecord, ...]:
        return tuple(self._records)

    def clear(self) -> None:
        self._records.clear()
        self.active_entities = None

    @staticmethod
    def tie_key(memory_id: str) -> str:
        return hashlib.sha256(memory_id.encode("utf-8")).hexdigest()

    def _score(self, record: MemoryRecord) -> float:
        metadata = record_metadata(record, self.family)
        features = retention_features(metadata, self.active_entities)
        with torch.no_grad():
            return float(self.scorer(features).item())

    def _rerank(self, candidates: Sequence[MemoryRecord]) -> None:
        if len(candidates) <= CAPACITY:
            self._records = list(candidates)
            self._assert_capacity()
            return
        ranked = sorted(candidates, key=lambda record: (-self._score(record), self.tie_key(record.memory_id)))
        self._records = ranked[:CAPACITY]
        self._assert_capacity()

    def consider(self, record: MemoryRecord) -> bool:
        if any(old.memory_id == record.memory_id for old in self._records):
            raise ValueError("memory_id must be unique within a case")
        candidates = list(self._records)
        if self.family == "utility_change":
            candidates = [old for old in candidates if old.entity != record.entity]
        candidates.append(record)
        self._rerank(candidates)
        return any(old.memory_id == record.memory_id for old in self._records)

    def process_scope(self, event: dict[str, Any]) -> None:
        if event.get("kind") not in {"mission_set", "mission_update"}:
            raise ValueError("unsupported DMC-03P scope event")
        entities = event.get("entities")
        if not isinstance(entities, list) or not entities or len(set(entities)) != len(entities):
            raise ValueError("invalid mission scope")
        self.active_entities = frozenset(entities)
        self._rerank(self._records)

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
            raise AssertionError("DMC-03P physical memory exceeded 16 records")


class DMC03PController(nn.Module):
    """Frozen RRI processor plus the only trainable DMC-03P scorer."""

    def __init__(self, processor: ImmutableRelationAnchorReasoner, scorer: AffineRetentionScorer, *, family: str) -> None:
        super().__init__()
        if family not in FAMILIES:
            raise ValueError(f"unknown DMC-02A family: {family}")
        self.processor = freeze_processor(processor)
        self.scorer = scorer
        self.family = family
        self.ledger = LearnedRetention16Ledger(self.scorer, family=family)

    @property
    def capacity(self) -> int:
        return CAPACITY

    @property
    def trainable_retention_parameter_count(self) -> int:
        return trainable_parameter_count(self.scorer)

    def optimizer_parameters(self) -> list[nn.Parameter]:
        return list(self.scorer.parameters())

    def reset_case(self) -> None:
        self.ledger.clear()

    def process_scope_event(self, event: dict[str, Any]) -> None:
        self.ledger.process_scope(event)

    def make_record(self, event: dict[str, Any], episode_index: int, hidden_value: torch.Tensor | None = None) -> MemoryRecord:
        _validate_write_event(event)
        if episode_index < 0:
            raise ValueError("invalid episode index")
        hidden = encode_hidden(self.processor, event) if hidden_value is None else hidden_value
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

    def process_write(self, event: dict[str, Any], episode_index: int) -> MemoryRecord:
        record = self.make_record(event, episode_index)
        self.ledger.consider(record)
        if len(self.ledger) > CAPACITY:
            raise AssertionError("DMC-03P memory invariant violated")
        return record

    def retrieve(self, query: dict[str, Any]) -> MemoryRecord:
        required = {"kind", "entity", "field", "mode", "as_of_episode"}
        if set(query) != required or query["kind"] != "query":
            raise ValueError("malformed exact query")
        return self.ledger.retrieve(entity=query["entity"], field=query["field"], mode=query["mode"], as_of_episode=query["as_of_episode"])


def stateless_order(example_ids: Iterable[str], *, seed: int, epoch: int) -> list[str]:
    return sorted(example_ids, key=lambda example_id: (_stable_digest("DMC03P-order", seed, epoch, example_id), example_id))


def shuffled_order_batches(example_ids: Sequence[str], *, seed: int, epoch: int, batch_size: int = 256) -> list[list[str]]:
    if batch_size <= 0:
        raise ValueError("batch size must be positive")
    ordered = stateless_order(example_ids, seed=seed, epoch=epoch)
    return [ordered[start : start + batch_size] for start in range(0, len(ordered), batch_size)]


def shuffle_metadata_permutation(family: str, condition: str, width: int = 16) -> tuple[int, ...]:
    if family not in FAMILIES or width <= 0:
        raise ValueError("invalid metadata shuffle specification")
    ranked = sorted(
        range(width),
        key=lambda slot: (_stable_digest("DMC03P-shuffle", SHUFFLE_SEED, family, condition, slot), slot),
    )
    return tuple(ranked)


def retention_loss(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
    if logits.shape != targets.shape:
        raise ValueError("retention logits/targets shape mismatch")
    return nn.functional.binary_cross_entropy_with_logits(logits, targets, reduction="mean")


def training_protocol() -> dict[str, Any]:
    return {
        "epochs": 40,
        "batch_size": 256,
        "optimizer": "AdamW",
        "learning_rate": 1e-2,
        "weight_decay": 0.0,
        "gradient_clip": 1.0,
        "device": "cpu",
        "torch_threads": 1,
        "ordering": "ascending SHA256(DMC03P-order|seed|epoch|training_example_id), then example_id",
        "early_stopping": False,
        "scheduler": False,
        "hyperparameter_search": False,
        "evidence_training_executed_in_DMC03P": False,
    }

