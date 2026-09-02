"""Operator-owned constitution. Plastic layers cannot rewrite it."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ConstitutionError(PermissionError):
    """Raised when a plastic layer tries to rewrite the constitution or violate it."""


class FrozenConstitution:
    """Costs, evidence preservation, reversibility, partitions. Hash-locked."""

    def __init__(
        self,
        *,
        mutation_ceiling: int = 80,
        query_ceiling: int = 8000,
        compute_ceiling: int = 80_000,
    ) -> None:
        payload = {
            "doctrine": {
                "need_initiates": True,
                "experience_tests": True,
                "evidence_retains": True,
                "operator_owns_the_boundary": True,
                "need_grants_compute_not_truth": True,
                "budget_is_not_truth_selector": True,
                "prior_body_is_lineage_regression": True,
                "world_witness_is_correspondence_outside_lineage": True,
                "both_prior_and_witness_required_for_write": True,
            },
            "evidence_preservation": True,
            "reversibility": True,
            "privacy_partitions": ["operator", "world", "lineage"],
            "resource_ceilings": {
                "mutations": int(mutation_ceiling),
                "queries": int(query_ceiling),
                "compute_units": int(compute_ceiling),
            },
            "outward_actions_forbidden": True,
            "failed_adaptations_retained": True,
            "immutable_experience_append_only": True,
        }
        frozen = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        object.__setattr__(self, "_frozen_json", frozen)
        object.__setattr__(self, "_digest", _digest(payload))

    def __setattr__(self, name: str, value: Any) -> None:  # noqa: ANN401
        raise ConstitutionError("constitution is not mutable by plastic layers")

    def __delattr__(self, name: str) -> None:
        raise ConstitutionError("constitution is not mutable by plastic layers")

    @property
    def digest(self) -> str:
        return self._digest

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._frozen_json)

    def verify(self) -> None:
        payload = json.loads(self._frozen_json)
        if _digest(payload) != self._digest:
            raise ConstitutionError("constitution digest mismatch")
        if not payload["evidence_preservation"] or not payload["reversibility"]:
            raise ConstitutionError("constitution core flags rewritten")
        if not payload["outward_actions_forbidden"]:
            raise ConstitutionError("outward-action ban rewritten")
        if not payload["doctrine"]["need_grants_compute_not_truth"]:
            raise ConstitutionError("doctrine rewritten")

    def ceiling(self, name: str) -> int:
        return int(json.loads(self._frozen_json)["resource_ceilings"][name])
