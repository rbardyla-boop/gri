from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.forge.ecology import FailureClass, ToolBlueprint
from experiments.forge.forge import Case


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_cases(path: Path) -> tuple[Case, ...]:
    out: list[Case] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        case_id = str(row["case_id"])
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        out.append(Case(case_id, row["input"], row["expected"]))
    if not out:
        raise ValueError(f"empty case file: {path}")
    return tuple(out)


def blueprint_to_json(bp: ToolBlueprint) -> dict[str, Any]:
    return {
        "name": bp.name,
        "op": bp.op,
        "input_kind": bp.input_kind,
        "output_kind": bp.output_kind,
        "cost": bp.cost,
        "params": bp.params,
        "source_failure": bp.source_failure.value,
        "blueprint_id": bp.blueprint_id,
    }


def blueprint_from_json(row: dict[str, Any]) -> ToolBlueprint:
    bp = ToolBlueprint(
        str(row["name"]),
        str(row["op"]),
        str(row["input_kind"]),
        str(row["output_kind"]),
        int(row["cost"]),
        dict(row.get("params", {})),
        FailureClass(str(row["source_failure"])),
    )
    expected = row.get("blueprint_id")
    if expected is not None and expected != bp.blueprint_id:
        raise ValueError(f"blueprint digest mismatch: {bp.name}")
    return bp
