from __future__ import annotations

from typing import Any, Sequence

from experiments.forge.ecology import FailureClass, FailureDiagnosis, ToolBlueprint, ToolSmith
from experiments.forge.forge import Case, Tool
from experiments.forge_e1.interface_tools import InterfaceRepairToolFactory, InterfaceRepairToolSmith


def canonicalize_label_evidence_schema(value: Any, *, allowed: Sequence[str]) -> dict[str, Any]:
    """Recover a narrow set of explicitly represented label/evidence schemas.

    No missing value is invented. Ambiguous/conflicting structures fail closed.
    Label spelling/case and evidence duplicates are deliberately left for
    separate tools so those mechanisms remain independently ablatable.
    """
    if not isinstance(value, dict):
        raise TypeError("schema canonicalizer requires object")

    allowed_lc = {str(x).strip().lower() for x in allowed}
    if not allowed_lc:
        raise ValueError("allowed labels required")

    # Direct canonical-shaped representation. Extra keys are not silently
    # discarded because that would make the transform semantically ambiguous.
    if set(value) == {"label", "evidence"}:
        label = value.get("label")
        evidence = value.get("evidence")
        if not isinstance(label, str) or not isinstance(evidence, list):
            raise ValueError("DIRECT_SCHEMA_TYPES_INVALID")
        if any(not isinstance(x, str) for x in evidence):
            raise ValueError("DIRECT_EVIDENCE_NONSTRING")
        return {"label": label, "evidence": list(evidence)}

    # Alternate model representation: one top-level label key whose value is an
    # object carrying one or more explicit evidence fields.
    if len(value) != 1:
        raise ValueError("SCHEMA_NOT_RECOVERABLE")
    raw_label, inner = next(iter(value.items()))
    if not isinstance(raw_label, str) or raw_label.strip().lower() not in allowed_lc:
        raise ValueError("TOP_LEVEL_LABEL_NOT_ALLOWED")
    if not isinstance(inner, dict):
        raise ValueError("NESTED_LABEL_VALUE_NOT_OBJECT")

    fields = [name for name in ("evidence", "evidenceArray", "evidenceMultiset") if name in inner]
    if not fields:
        raise ValueError("NESTED_EVIDENCE_MISSING")

    lists: list[list[str]] = []
    for name in fields:
        raw = inner[name]
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            raise ValueError(f"NESTED_{name}_INVALID")
        lists.append(list(raw))

    # Multiple explicit evidence representations are accepted only when they
    # encode the same set. This permits multiset+array redundancy without
    # choosing between conflicting claims.
    sets = {tuple(sorted(set(items))) for items in lists}
    if len(sets) != 1:
        raise ValueError("CONFLICTING_EVIDENCE_FIELDS")

    # Preserve an actually observed list; downstream set canonicalization owns
    # dedupe/sort behavior and therefore earns its own mechanism credit.
    return {"label": raw_label, "evidence": lists[0]}


class GateAwareInterfaceToolFactory(InterfaceRepairToolFactory):
    EXTRA_E2_OPS = {"canonicalize_label_evidence_schema"}

    def compile(self, blueprint: ToolBlueprint) -> Tool:
        if blueprint.op not in self.EXTRA_E2_OPS:
            return super().compile(blueprint)
        p = dict(blueprint.params)
        allowed = tuple(str(x) for x in p.get("allowed", ()))
        if not allowed:
            raise ValueError("canonicalize schema requires allowed labels")
        fn = lambda x: canonicalize_label_evidence_schema(x, allowed=allowed)
        return Tool(blueprint.name, blueprint.input_kind, blueprint.output_kind, blueprint.cost, fn)


class GateAwareInterfaceToolSmith(InterfaceRepairToolSmith):
    """E2 ToolSmith: E1 pure tools plus one recoverable-schema transform."""

    def __init__(self) -> None:
        ToolSmith.__init__(self, GateAwareInterfaceToolFactory())

    def propose(
        self,
        diagnosis: FailureDiagnosis,
        build_cases: Sequence[Case],
        input_kind: str,
        output_kind: str,
    ) -> tuple[ToolBlueprint, ...]:
        base = list(super().propose(diagnosis, build_cases, input_kind, output_kind))
        if diagnosis.failure_class is not FailureClass.INTERFACE:
            return tuple(base)
        expected = [c.expected for c in build_cases if isinstance(c.expected, dict)]
        if not expected or len(expected) != len(build_cases):
            return tuple(base)
        if not all(set(obj) == {"label", "evidence"} and isinstance(obj.get("label"), str) for obj in expected):
            return tuple(base)
        allowed = sorted({str(obj["label"]) for obj in expected})
        base.append(
            ToolBlueprint(
                "ts_canonicalize_schema",
                "canonicalize_label_evidence_schema",
                "json",
                "json",
                1,
                {"allowed": allowed},
                diagnosis.failure_class,
            )
        )
        return tuple(base)
