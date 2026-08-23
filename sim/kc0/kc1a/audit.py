"""Static and runtime audit for the KC-1A lifecycle candidate."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .cell import KC1ACell
except ImportError:  # pragma: no cover - exercised by direct lifecycle CLI.
    from cell import KC1ACell


FORBIDDEN_NAMES = {
    "fixture_id", "sequence_length", "query_id", "target_answer",
    "held_out_status", "trial_name", "future_tokens", "simulator_counter",
    "verdict_state", "step_count", "history_buffer", "population",
    "replicate", "divide", "share", "random", "time", "os", "socket",
    "subprocess", "pathlib", "environ",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_source(source: Path, manifest_path: Path) -> dict[str, Any]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    names: set[str] = set()
    imports: set[str] = set()
    step_signatures: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "step":
            step_signatures.append(len(node.args.args))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_source_hash = sha256(source)
    declared_source_hash = manifest.get("source_sha256")
    runtime_manifest = KC1ACell().resource_manifest()
    declared_resource = {
        "candidate_id": manifest.get("candidate_id"),
        "candidate_version": manifest.get("candidate_version"),
        "state_bytes_max": manifest.get("state", {}).get("state_bytes_max"),
        "persistent_scalar_count": manifest.get("state", {}).get("persistent_scalar_count"),
        "value_slots": manifest.get("state", {}).get("value_slots"),
        "occupancy_bits": manifest.get("state", {}).get("occupancy_bits"),
        "step_operation_budget": manifest.get("operations", {}).get("step_operation_budget"),
        "readout_operation_budget": manifest.get("operations", {}).get("readout_operation_budget"),
        "uses_rng": manifest.get("containment", {}).get("uses_rng"),
        "uses_wall_clock": manifest.get("containment", {}).get("uses_wall_clock"),
        "uses_filesystem": manifest.get("containment", {}).get("uses_filesystem"),
        "uses_network": manifest.get("containment", {}).get("uses_network"),
        "uses_environment": manifest.get("containment", {}).get("uses_environment"),
        "uses_optimizer": manifest.get("containment", {}).get("uses_optimizer"),
        "uses_external_model": manifest.get("containment", {}).get("uses_external_model"),
        "has_step_counter": manifest.get("state", {}).get("has_step_counter"),
        "has_history_buffer": manifest.get("state", {}).get("has_history_buffer"),
        "has_population_logic": manifest.get("state", {}).get("has_population_logic"),
    }
    forbidden = sorted((names | imports) & FORBIDDEN_NAMES)
    return {
        "status": "PASS" if (
            declared_source_hash == actual_source_hash
            and not forbidden
            and step_signatures == [3]
            and declared_resource == runtime_manifest
            and manifest.get("scientific_execution") == "FORBIDDEN"
            and manifest.get("scientific_verdict") == "FORBIDDEN"
        ) else "FAIL",
        "source_sha256": actual_source_hash,
        "declared_source_sha256": declared_source_hash,
        "forbidden_names": forbidden,
        "imports": sorted(imports),
        "step_signatures": step_signatures,
        "declared_resource": declared_resource,
        "runtime_resource": runtime_manifest,
    }
