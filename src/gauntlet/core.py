from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_spec(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".toml":
        return tomllib.loads(path.read_text(encoding="utf-8"))
    if suffix == ".json":
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError("Gauntlet JSON spec must be an object")
        return value
    raise ValueError("Gauntlet spec must be .toml or .json")


def _find_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _git(root: Path, *args: str) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _git_head(root: Path) -> str | None:
    return _git(root, "rev-parse", "HEAD")


def _git_dirty(root: Path) -> bool | None:
    status = _git(root, "status", "--porcelain")
    return None if status is None else bool(status)


def _safe_path(root: Path, raw: str) -> Path:
    path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes experiment root: {raw}") from exc
    return path


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _ignored_component(path: Path) -> bool:
    ignored = {".git", ".gauntlet", ".venv", "__pycache__", ".pytest_cache"}
    return any(part in ignored for part in path.parts)


def _expand_declared(root: Path, values: Iterable[str]) -> list[Path]:
    resolved: dict[str, Path] = {}
    for raw in values:
        path = _safe_path(root, raw)
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_file():
            resolved[_relative(root, path)] = path
            continue
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = child.relative_to(root)
            if not _ignored_component(rel):
                resolved[str(rel)] = child
    return [resolved[key] for key in sorted(resolved)]


def _file_manifest(root: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": _relative(root, path),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in paths
    ]


def _output_manifest(root: Path, declared: Sequence[str]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw in declared:
        path = _safe_path(root, raw)
        if not path.exists():
            missing.append(raw)
            continue
        if path.is_file():
            rows.extend(_file_manifest(root, [path]))
        else:
            rows.extend(_file_manifest(root, _expand_declared(root, [raw])))
    deduped = {row["path"]: row for row in rows}
    return [deduped[key] for key in sorted(deduped)], sorted(missing)


def _validate_spec(spec: dict[str, Any]) -> None:
    experiment = spec.get("experiment")
    freeze = spec.get("freeze")
    run = spec.get("run")
    if not isinstance(experiment, dict) or not isinstance(experiment.get("id"), str):
        raise ValueError("spec requires [experiment] id")
    if not isinstance(freeze, dict) or not isinstance(freeze.get("inputs", []), list):
        raise ValueError("spec requires [freeze] inputs = [...] (possibly empty)")
    if not isinstance(run, dict):
        raise ValueError("spec requires [run]")
    mode = run.get("mode", "subprocess")
    if mode not in {"subprocess", "python"}:
        raise ValueError("run.mode must be 'subprocess' or 'python'")
    if mode == "subprocess":
        command = run.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError("subprocess run requires command = [..]")
    else:
        if not isinstance(run.get("entry"), str):
            raise ValueError("python run requires entry = 'script.py'")
        args = run.get("args", [])
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            raise ValueError("python run args must be strings")
    outputs = run.get("outputs", [])
    if not isinstance(outputs, list) or not all(isinstance(x, str) for x in outputs):
        raise ValueError("run.outputs must be a list of paths")
    protected = freeze.get("protected", [])
    if not isinstance(protected, list) or not all(isinstance(x, str) for x in protected):
        raise ValueError("freeze.protected must be a list of paths")
    if protected and mode != "python":
        raise ValueError(
            "protected roots require run.mode='python' in Gauntlet v0; arbitrary subprocess isolation is not claimed"
        )
    gates = spec.get("gates", [])
    if not isinstance(gates, list):
        raise ValueError("[[gates]] entries must form a list")
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("name"), str) or not isinstance(gate.get("path"), str):
            raise ValueError("each gate requires name and path")
        if gate.get("op", ">=") not in {">=", ">", "<=", "<", "==", "!="}:
            raise ValueError(f"unsupported gate operator: {gate.get('op')}")
        if "value" not in gate:
            raise ValueError(f"gate {gate['name']} requires value")


def create_freeze(spec_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    spec_path = Path(spec_path).resolve()
    spec = load_spec(spec_path)
    _validate_spec(spec)
    root = _find_root(spec_path.parent)
    experiment = spec["experiment"]
    freeze_cfg = spec.get("freeze", {})
    require_clean = bool(experiment.get("require_clean_repo", False))
    require_same_commit = bool(experiment.get("require_same_commit", True))
    dirty = _git_dirty(root)
    if require_clean and dirty:
        raise RuntimeError("repository is dirty; freeze refused")

    inputs = _expand_declared(root, [str(x) for x in freeze_cfg.get("inputs", [])])
    protected = [_relative(root, _safe_path(root, str(x))) for x in freeze_cfg.get("protected", [])]
    run_cfg = spec["run"]
    if run_cfg.get("mode", "subprocess") == "python":
        entry = _safe_path(root, str(run_cfg["entry"]))
        if not entry.is_file():
            raise FileNotFoundError(entry)

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "spec": {
            "path": _relative(root, spec_path),
            "sha256": file_sha256(spec_path),
        },
        "inputs": _file_manifest(root, inputs),
        "protected_roots": protected,
        "run": run_cfg,
        "repo": {
            "head": _git_head(root),
            "dirty": dirty,
            "require_clean": require_clean,
            "require_same_commit": require_same_commit,
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
        },
    }
    body = dict(manifest)
    manifest["manifest_sha256"] = digest(body)
    target = Path(output_path).resolve() if output_path else root / ".gauntlet" / "freeze.json"
    write_json(target, manifest)
    return {**manifest, "manifest_path": str(target)}


def verify_freeze(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    root = Path(manifest["root"]).resolve()
    failures: list[str] = []
    checks: dict[str, bool] = {}

    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    checks["manifest_digest"] = digest(body) == manifest.get("manifest_sha256")
    if not checks["manifest_digest"]:
        failures.append("manifest_digest")

    spec_path = root / manifest["spec"]["path"]
    checks["spec_exists"] = spec_path.is_file()
    checks["spec_hash"] = checks["spec_exists"] and file_sha256(spec_path) == manifest["spec"]["sha256"]
    if not checks["spec_exists"]:
        failures.append("spec_missing")
    elif not checks["spec_hash"]:
        failures.append("spec_hash")

    input_ok = True
    for row in manifest.get("inputs", []):
        item = root / row["path"]
        if not item.is_file() or item.stat().st_size != row["bytes"] or file_sha256(item) != row["sha256"]:
            input_ok = False
            failures.append(f"input:{row['path']}")
    checks["inputs"] = input_ok

    current_head = _git_head(root)
    require_same = bool(manifest.get("repo", {}).get("require_same_commit", True))
    frozen_head = manifest.get("repo", {}).get("head")
    checks["repo_head"] = not require_same or frozen_head is None or current_head == frozen_head
    if not checks["repo_head"]:
        failures.append("repo_head")

    require_clean = bool(manifest.get("repo", {}).get("require_clean", False))
    dirty = _git_dirty(root)
    checks["repo_clean"] = not require_clean or dirty is False
    if not checks["repo_clean"]:
        failures.append("repo_dirty")

    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "manifest_path": str(path),
    }


def _run_environment(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    src = root / "src"
    existing = env.get("PYTHONPATH", "")
    pieces = [str(src)] if src.is_dir() else []
    if existing:
        pieces.append(existing)
    if pieces:
        env["PYTHONPATH"] = os.pathsep.join(pieces)
    return env


def _execute_manifest(manifest_path: Path) -> subprocess.CompletedProcess[str]:
    manifest = read_json(manifest_path)
    root = Path(manifest["root"]).resolve()
    run_cfg = manifest["run"]
    mode = run_cfg.get("mode", "subprocess")
    if mode == "python":
        # Load the installed Gauntlet guard in isolated mode before exposing any
        # target-project import paths. This prevents a foreign src/gauntlet
        # package or PYTHONPATH entry from shadowing the integrity guard.
        command = [sys.executable, "-I", "-m", "gauntlet._guard_exec", str(manifest_path)]
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
    else:
        command = [str(x) for x in run_cfg["command"]]
        env = _run_environment(root)
    timeout = float(run_cfg.get("timeout_seconds", 3600))
    return subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _stream_fingerprint(value: str) -> dict[str, Any]:
    encoded = value.encode("utf-8")
    return {"bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}


def run_frozen(manifest_path: str | Path, run_id: str | None = None) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    verification = verify_freeze(manifest_path)
    if not verification["pass"]:
        raise RuntimeError(f"freeze verification failed: {verification['failures']}")
    manifest = read_json(manifest_path)
    root = Path(manifest["root"]).resolve()
    run_cfg = manifest["run"]
    run_id = run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S.%fZ")

    started = time.perf_counter()
    completed = _execute_manifest(manifest_path)
    wall = time.perf_counter() - started
    outputs, missing = _output_manifest(root, [str(x) for x in run_cfg.get("outputs", [])])
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "freeze_manifest_sha256": manifest["manifest_sha256"],
        "mode": run_cfg.get("mode", "subprocess"),
        "command": run_cfg.get("command") if run_cfg.get("mode", "subprocess") == "subprocess" else [
            sys.executable,
            str(run_cfg["entry"]),
            *[str(x) for x in run_cfg.get("args", [])],
        ],
        "exit_code": completed.returncode,
        "wall_time_seconds": wall,
        "stdout": _stream_fingerprint(completed.stdout),
        "stderr": _stream_fingerprint(completed.stderr),
        "outputs": outputs,
        "missing_outputs": missing,
        "run_status": "PASS" if completed.returncode == 0 and not missing else "FAIL",
    }
    receipt["receipt_sha256"] = digest(receipt)
    target = root / ".gauntlet" / "runs" / f"{run_id}.json"
    write_json(target, receipt)
    return {**receipt, "receipt_path": str(target)}


def _verify_receipt(path: Path) -> tuple[dict[str, Any], bool]:
    receipt = read_json(path)
    observed = receipt.get("receipt_sha256")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    return receipt, observed == digest(body)


def replay_run(
    manifest_path: str | Path,
    original_receipt_path: str | Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    original_path = Path(original_receipt_path).resolve()
    original, original_digest_ok = _verify_receipt(original_path)
    if not original_digest_ok:
        raise RuntimeError("original run receipt digest mismatch")
    manifest = read_json(manifest_path)
    if original.get("freeze_manifest_sha256") != manifest.get("manifest_sha256"):
        raise RuntimeError("receipt is bound to a different freeze manifest")
    replay_id = run_id or datetime.now(timezone.utc).strftime("replay-%Y%m%dT%H%M%S.%fZ")
    replay_receipt = run_frozen(manifest_path, replay_id)
    compare_stdout = bool(manifest.get("run", {}).get("replay_compare_stdout", False))
    checks = {
        "exit_code": replay_receipt["exit_code"] == original["exit_code"],
        "outputs": replay_receipt["outputs"] == original["outputs"],
        "missing_outputs": replay_receipt["missing_outputs"] == original["missing_outputs"],
        "stdout": (not compare_stdout) or replay_receipt["stdout"] == original["stdout"],
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "replay_id": replay_id,
        "source_receipt_sha256": original["receipt_sha256"],
        "replay_receipt_sha256": replay_receipt["receipt_sha256"],
        "checks": checks,
        "pass": all(checks.values()),
    }
    result["replay_sha256"] = digest(result)
    root = Path(manifest["root"]).resolve()
    target = root / ".gauntlet" / "replays" / f"{replay_id}.json"
    write_json(target, result)
    return {**result, "replay_path": str(target)}


def lookup(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(dotted_path)
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise KeyError(dotted_path)
    return current


def _compare(observed: Any, op: str, expected: Any) -> bool:
    if op == "==":
        return observed == expected
    if op == "!=":
        return observed != expected
    if not isinstance(observed, (int, float)) or isinstance(observed, bool):
        raise TypeError(f"operator {op} requires numeric observed value, got {type(observed).__name__}")
    if not isinstance(expected, (int, float)) or isinstance(expected, bool):
        raise TypeError(f"operator {op} requires numeric expected value")
    if op == ">=":
        return observed >= expected
    if op == ">":
        return observed > expected
    if op == "<=":
        return observed <= expected
    if op == "<":
        return observed < expected
    raise ValueError(op)


def audit_result(
    spec_path: str | Path,
    result_path: str | Path,
    *,
    evidence_class: str = "RETROSPECTIVE_AUDIT",
) -> dict[str, Any]:
    spec_path = Path(spec_path).resolve()
    result_path = Path(result_path).resolve()
    spec = load_spec(spec_path)
    _validate_spec(spec)
    result = read_json(result_path)
    gate_rows: list[dict[str, Any]] = []
    required_pass = True
    for gate in spec.get("gates", []):
        observed = lookup(result, str(gate["path"]))
        passed = _compare(observed, str(gate.get("op", ">=")), gate["value"])
        required = bool(gate.get("required", True))
        if required and not passed:
            required_pass = False
        gate_rows.append(
            {
                "name": gate["name"],
                "path": gate["path"],
                "observed": observed,
                "op": gate.get("op", ">="),
                "expected": gate["value"],
                "required": required,
                "pass": passed,
            }
        )

    comparison_cfg = spec.get("comparison")
    comparison: dict[str, Any] | None = None
    comparison_pass = True
    reverse_dominates = False
    if comparison_cfg is not None:
        if not isinstance(comparison_cfg, dict):
            raise ValueError("[comparison] must be a table")
        candidate = float(lookup(result, str(comparison_cfg["candidate_path"])))
        baseline = float(lookup(result, str(comparison_cfg["baseline_path"])))
        minimum_delta = float(comparison_cfg.get("minimum_delta", 0.0))
        direction = str(comparison_cfg.get("direction", "greater"))
        if direction == "greater":
            delta = candidate - baseline
        elif direction == "less":
            delta = baseline - candidate
        else:
            raise ValueError("comparison.direction must be greater or less")
        comparison_pass = delta >= minimum_delta
        reverse_dominates = delta <= -minimum_delta if minimum_delta > 0 else delta < 0
        comparison = {
            "candidate": candidate,
            "baseline": baseline,
            "direction": direction,
            "minimum_delta": minimum_delta,
            "effective_delta": delta,
            "pass": comparison_pass,
        }

    if required_pass and comparison_pass:
        state = "ADVANCE"
    elif reverse_dominates:
        state = "BASELINE_DOMINATES"
    else:
        state = "NO_ESTABLISHED_ADVANTAGE"

    audit: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": evidence_class,
        "spec_sha256": file_sha256(spec_path),
        "result_sha256": file_sha256(result_path),
        "gates": gate_rows,
        "required_gates_pass": required_pass,
        "comparison": comparison,
        "state": state,
    }
    audit["audit_sha256"] = digest(audit)
    return audit


def verdict_frozen(
    manifest_path: str | Path,
    receipt_path: str | Path,
    replay_path: str | Path | None = None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    receipt_path = Path(receipt_path).resolve()
    manifest = read_json(manifest_path)
    root = Path(manifest["root"]).resolve()
    freeze_verification = verify_freeze(manifest_path)
    receipt, receipt_digest_ok = _verify_receipt(receipt_path)
    receipt_binding = receipt.get("freeze_manifest_sha256") == manifest.get("manifest_sha256")
    run_pass = receipt.get("run_status") == "PASS"

    spec_path = root / manifest["spec"]["path"]
    spec = load_spec(spec_path)
    verdict_cfg = spec.get("verdict", {})
    result_raw = verdict_cfg.get("result_file")
    if not isinstance(result_raw, str):
        raise ValueError("frozen verdict requires [verdict] result_file")
    result_path = _safe_path(root, result_raw)
    output_hashes = {row["path"]: row["sha256"] for row in receipt.get("outputs", [])}
    result_rel = _relative(root, result_path)
    result_bound = result_path.is_file() and output_hashes.get(result_rel) == file_sha256(result_path)

    replay_ok = True
    replay_binding = True
    if replay_path is not None:
        replay_value = read_json(Path(replay_path).resolve())
        replay_body = {key: value for key, value in replay_value.items() if key != "replay_sha256"}
        replay_digest_ok = replay_value.get("replay_sha256") == digest(replay_body)
        replay_binding = replay_value.get("source_receipt_sha256") == receipt.get("receipt_sha256")
        replay_ok = bool(replay_value.get("pass")) and replay_digest_ok and replay_binding
    elif bool(verdict_cfg.get("require_replay", False)):
        replay_ok = False

    integrity = {
        "freeze": freeze_verification["pass"],
        "receipt_digest": receipt_digest_ok,
        "receipt_binding": receipt_binding,
        "run": run_pass,
        "result_binding": result_bound,
        "replay": replay_ok,
        "replay_binding": replay_binding,
    }
    audit = audit_result(spec_path, result_path, evidence_class="PREREGISTERED_RUN") if result_path.is_file() else None
    if all(integrity.values()) and audit is not None:
        state = audit["state"]
    else:
        state = "INTEGRITY_FAIL"
    verdict: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "PREREGISTERED_RUN",
        "integrity": integrity,
        "audit": audit,
        "state": state,
    }
    verdict["verdict_sha256"] = digest(verdict)
    return verdict
