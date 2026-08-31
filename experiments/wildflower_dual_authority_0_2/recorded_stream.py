"""Canonical serialization for replayable control-transition streams."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from . import store
from .controls import RecordedTransition, StreamClaim


def _packet_to_dict(packet: store.Packet) -> dict[str, int]:
    return {
        "stable_reference": packet.stable_reference,
        "act": packet.act,
        "subject": packet.subject,
        "relation": packet.relation,
        "object": packet.object,
        "value": packet.value,
    }


def _packet_from_dict(data: dict[str, int]) -> store.Packet:
    packet = store.Packet(**data)
    packet.validate()
    return packet


def _claim_to_dict(claim: StreamClaim) -> dict[str, object]:
    return {
        "packet": _packet_to_dict(claim.packet),
        "semantic_parents": [list(parent) for parent in claim.semantic_parents],
    }


def _claim_from_dict(data: dict[str, object]) -> StreamClaim:
    parents = tuple(tuple(int(value) for value in parent) for parent in data["semantic_parents"])
    return StreamClaim(_packet_from_dict(data["packet"]), parents)


def transition_to_dict(frame: RecordedTransition) -> dict[str, object]:
    if not math.isfinite(frame.authority):
        raise ValueError("authority must be finite")
    return {
        "tick": frame.tick,
        "predictions": [_claim_to_dict(claim) for claim in frame.predictions],
        "witnesses": [_packet_to_dict(packet) for packet in frame.witnesses],
        "recomputed": [_claim_to_dict(claim) for claim in frame.recomputed],
        "authority": frame.authority,
        "truth_packets": [_packet_to_dict(packet) for packet in frame.truth_packets],
        "preservation_targets": [
            _claim_to_dict(claim) for claim in frame.preservation_targets
        ],
        "recomputation_targets": [
            _claim_to_dict(claim) for claim in frame.recomputation_targets
        ],
    }


def transition_from_dict(data: dict[str, object]) -> RecordedTransition:
    authority = float(data["authority"])
    if not math.isfinite(authority):
        raise ValueError("authority must be finite")
    return RecordedTransition(
        tick=int(data["tick"]),
        predictions=tuple(_claim_from_dict(item) for item in data["predictions"]),
        witnesses=tuple(_packet_from_dict(item) for item in data["witnesses"]),
        recomputed=tuple(_claim_from_dict(item) for item in data["recomputed"]),
        authority=authority,
        truth_packets=tuple(
            _packet_from_dict(item) for item in data["truth_packets"]
        ),
        preservation_targets=tuple(
            _claim_from_dict(item) for item in data.get("preservation_targets", ())
        ),
        recomputation_targets=tuple(
            _claim_from_dict(item) for item in data.get("recomputation_targets", ())
        ),
    )


def canonical_stream_bytes(frames: Iterable[RecordedTransition]) -> bytes:
    payload = [transition_to_dict(frame) for frame in frames]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def write_stream(path: Path, frames: Iterable[RecordedTransition]) -> str:
    payload = canonical_stream_bytes(frames)
    path.write_bytes(payload + b"\n")
    return hashlib.sha256(payload).hexdigest()


def read_stream(path: Path) -> tuple[RecordedTransition, ...]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError("recorded stream must be a JSON list")
    return tuple(transition_from_dict(item) for item in payload)
