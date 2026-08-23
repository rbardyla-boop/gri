from __future__ import annotations

import json
from typing import Any, Sequence

from experiments.forge.ecology import (
    DeclarativeToolFactory,
    FailureClass,
    FailureDiagnosis,
    ToolBlueprint,
    ToolSmith,
)
from experiments.forge.forge import Case, Tool


def extract_first_json_object(text: Any) -> str:
    """Extract the first balanced JSON object from surrounding text.

    This does not repair JSON syntax. It only removes non-JSON prefix/suffix
    while respecting quoted strings and escapes. If no complete object exists,
    it fails closed.
    """
    if not isinstance(text, str):
        raise TypeError("extract_first_json_object requires text")
    start = None
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = i
                depth = 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("NO_COMPLETE_JSON_OBJECT")


def parse_json_object(text: Any) -> dict[str, Any]:
    if not isinstance(text, str):
        raise TypeError("json_parse requires text")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def normalize_label_field(value: Any, *, key: str, allowed: Sequence[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("normalize_label requires object")
    if key not in value or not isinstance(value[key], str):
        raise ValueError("LABEL_FIELD_MISSING_OR_NOT_TEXT")
    canonical = {label.strip().lower(): label for label in allowed}
    raw = value[key].strip().lower()
    if raw not in canonical:
        raise ValueError("LABEL_NOT_RECOVERABLE")
    out = dict(value)
    out[key] = canonical[raw]
    return out


def dedupe_sort_list_field(value: Any, *, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("dedupe_sort_list requires object")
    raw = value.get(key)
    if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
        raise ValueError("LIST_FIELD_MISSING_OR_NONSTRING")
    out = dict(value)
    out[key] = sorted(set(raw))
    return out


def require_exact_keys(value: Any, *, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("require_exact_keys requires object")
    if set(value) != set(keys):
        raise ValueError("UNEXPECTED_OBJECT_KEYS")
    return dict(value)


class InterfaceRepairToolFactory(DeclarativeToolFactory):
    EXTRA_OPS = {
        "extract_json_object",
        "json_parse_object",
        "normalize_label_field",
        "dedupe_sort_list_field",
        "require_exact_keys",
    }

    def compile(self, blueprint: ToolBlueprint) -> Tool:
        if blueprint.op not in self.EXTRA_OPS:
            return super().compile(blueprint)
        p = dict(blueprint.params)
        if blueprint.op == "extract_json_object":
            fn = extract_first_json_object
        elif blueprint.op == "json_parse_object":
            fn = parse_json_object
        elif blueprint.op == "normalize_label_field":
            key = str(p["key"])
            allowed = tuple(str(x) for x in p["allowed"])
            if not allowed:
                raise ValueError("normalize_label_field requires allowed labels")
            fn = lambda x: normalize_label_field(x, key=key, allowed=allowed)
        elif blueprint.op == "dedupe_sort_list_field":
            key = str(p["key"])
            fn = lambda x: dedupe_sort_list_field(x, key=key)
        elif blueprint.op == "require_exact_keys":
            keys = tuple(str(x) for x in p["keys"])
            fn = lambda x: require_exact_keys(x, keys=keys)
        else:  # pragma: no cover
            raise AssertionError(blueprint.op)
        return Tool(blueprint.name, blueprint.input_kind, blueprint.output_kind, blueprint.cost, fn)


class InterfaceRepairToolSmith(ToolSmith):
    """TE0-E1 ToolSmith for semantics-preserving serialization repairs.

    It may normalize syntax/casing and set representation, but it cannot invent
    missing labels/evidence or consult the original prompt/target during use.
    """

    def __init__(self) -> None:
        super().__init__(InterfaceRepairToolFactory())

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
        if input_kind != "text" or output_kind != "json":
            return tuple(base)

        base.extend(
            [
                ToolBlueprint(
                    "ts_extract_json_object",
                    "extract_json_object",
                    "text",
                    "text",
                    1,
                    {},
                    diagnosis.failure_class,
                ),
                ToolBlueprint(
                    "ts_json_parse_object",
                    "json_parse_object",
                    "text",
                    "json",
                    1,
                    {},
                    diagnosis.failure_class,
                ),
            ]
        )

        expected_objects = [c.expected for c in build_cases if isinstance(c.expected, dict)]
        if expected_objects and len(expected_objects) == len(build_cases):
            key_sets = {tuple(sorted(obj.keys())) for obj in expected_objects}
            if len(key_sets) == 1:
                keys = key_sets.pop()
                base.append(
                    ToolBlueprint(
                        "ts_require_exact_keys",
                        "require_exact_keys",
                        "json",
                        "json",
                        1,
                        {"keys": list(keys)},
                        diagnosis.failure_class,
                    )
                )

                if "label" in keys and all(isinstance(obj.get("label"), str) for obj in expected_objects):
                    allowed = sorted({str(obj["label"]) for obj in expected_objects})
                    base.append(
                        ToolBlueprint(
                            "ts_normalize_label",
                            "normalize_label_field",
                            "json",
                            "json",
                            1,
                            {"key": "label", "allowed": allowed},
                            diagnosis.failure_class,
                        )
                    )

                if "evidence" in keys and all(
                    isinstance(obj.get("evidence"), list)
                    and all(isinstance(x, str) for x in obj["evidence"])
                    for obj in expected_objects
                ):
                    base.append(
                        ToolBlueprint(
                            "ts_dedupe_sort_evidence",
                            "dedupe_sort_list_field",
                            "json",
                            "json",
                            1,
                            {"key": "evidence"},
                            diagnosis.failure_class,
                        )
                    )
        return tuple(base)
