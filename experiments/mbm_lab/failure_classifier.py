from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLASSES = (
    "MODEL_FAILURE",
    "MEASUREMENT_FAILURE",
    "TOOL_FAILURE",
    "RETRIEVAL_FAILURE",
    "STATE_FAILURE",
    "INTERFACE_FAILURE",
    "RESOURCE_FAILURE",
    "TASK_DEFINITION_FAILURE",
    "UNKNOWN_FAILURE",
)


@dataclass(frozen=True)
class Failure:
    klass: str
    reason: str
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"class": self.klass, "reason": self.reason, "evidence": self.evidence}


def classify(event: dict[str, Any]) -> Failure:
    """Conservative rule-based first pass. Never upgrades a model failure from guesswork."""
    if event.get("timeout") or event.get("oom") or event.get("gpu_unavailable") or event.get("resource_exhausted"):
        return Failure("RESOURCE_FAILURE", "host/resource constraint prevented valid execution", event)
    if event.get("unparseable") or event.get("schema_error") or event.get("serialization_error") or event.get("protocol_error"):
        return Failure("INTERFACE_FAILURE", "execution interface contract failed", event)
    if event.get("tool_nonzero_exit") or event.get("tool_exception") or event.get("tool_unavailable"):
        return Failure("TOOL_FAILURE", "external tool failed independently of task answer", event)
    if event.get("retrieval_wrong") or event.get("retrieval_missing"):
        return Failure("RETRIEVAL_FAILURE", "retrieval supplied missing or incorrect evidence", event)
    if event.get("state_corruption") or event.get("state_loss") or event.get("state_stale"):
        return Failure("STATE_FAILURE", "task state was lost, corrupted, or stale", event)
    if event.get("measurement_disagreement") or event.get("readout_invalid") or event.get("label_collision"):
        return Failure("MEASUREMENT_FAILURE", "measurement/readout does not validly represent the target construct", event)
    if event.get("ambiguous_gold") or event.get("underspecified_task") or event.get("contradictory_task"):
        return Failure("TASK_DEFINITION_FAILURE", "task or gold definition is not sufficiently determinate", event)
    if event.get("valid_execution") is True and event.get("valid_measurement") is True and event.get("answer_wrong") is True:
        return Failure("MODEL_FAILURE", "valid execution and measurement produced an incorrect answer", event)
    return Failure("UNKNOWN_FAILURE", "insufficient evidence to localize failure", event)
