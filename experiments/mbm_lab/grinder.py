from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def expand_candidates(spec: dict[str, Any]) -> list[dict[str, Any]]:
    axes = spec.get("axes", {})
    command_template = spec.get("command_template")
    if not isinstance(axes, dict) or not axes:
        raise ValueError("candidate spec requires non-empty axes")
    if not isinstance(command_template, list) or not command_template:
        raise ValueError("command_template must be a string array")
    names = list(axes)
    values = []
    for name in names:
        vals = axes[name]
        if not isinstance(vals, list) or not vals:
            raise ValueError(f"axis {name} must be non-empty list")
        values.append(vals)
    out = []
    for combo in itertools.product(*values):
        params = dict(zip(names, combo))
        command = [str(part).format(**params) for part in command_template]
        out.append({"params": params, "command": command, "id": sha(params)[:16]})
    return out


def run_one(command: list[str], fixture: dict[str, Any], timeout: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            input=json.dumps(fixture),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "MBM_LAB": "1"},
        )
        elapsed = time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        return None, {
            "class": "TIMEOUT",
            "elapsed_seconds": time.monotonic() - started,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }

    meta = {
        "class": "OK" if proc.returncode == 0 else "NONZERO_EXIT",
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.returncode != 0:
        return None, meta
    try:
        value = json.loads(proc.stdout)
    except Exception as exc:
        meta["class"] = "UNPARSEABLE"
        meta["parse_error"] = f"{type(exc).__name__}: {exc}"
        return None, meta
    if not isinstance(value, dict) or set(value) != {"prediction"}:
        meta["class"] = "BAD_ADAPTER_SHAPE"
        return None, meta
    return value["prediction"], meta


def evaluate_candidate(candidate: dict[str, Any], fixtures: list[dict[str, Any]], timeout: float, raw_path: Path) -> dict[str, Any]:
    exact = 0
    structural_failures = 0
    latencies = []
    by_kind: dict[str, dict[str, int]] = {}

    with raw_path.open("x", encoding="utf-8") as raw:
        for ordinal, fixture in enumerate(fixtures):
            prediction, meta = run_one(candidate["command"], fixture, timeout)
            target = fixture["target"]
            is_exact = prediction == target if prediction is not None else False
            exact += int(is_exact)
            structural_failures += int(prediction is None)
            latencies.append(meta["elapsed_seconds"])
            kind = fixture["kind"]
            stats = by_kind.setdefault(kind, {"n": 0, "exact": 0, "structural_failures": 0})
            stats["n"] += 1
            stats["exact"] += int(is_exact)
            stats["structural_failures"] += int(prediction is None)
            raw.write(json.dumps({
                "candidate_id": candidate["id"],
                "ordinal": ordinal,
                "fixture_id": fixture["id"],
                "kind": kind,
                "target_sha256": sha(target),
                "prediction_sha256": sha(prediction) if prediction is not None else None,
                "exact": is_exact,
                "meta": meta,
            }, sort_keys=True) + "\n")

    n = len(fixtures)
    return {
        "candidate_id": candidate["id"],
        "params": candidate["params"],
        "command": candidate["command"],
        "n": n,
        "exact": exact,
        "exact_rate": exact / n if n else 0.0,
        "structural_failures": structural_failures,
        "structural_failure_rate": structural_failures / n if n else 0.0,
        "mean_latency_seconds": sum(latencies) / len(latencies) if latencies else None,
        "by_kind": by_kind,
        "raw_log": str(raw_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--candidate-spec", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-candidates", type=int, default=0)
    args = ap.parse_args()

    fixtures = load_jsonl(args.fixtures)
    spec = json.loads(args.candidate_spec.read_text(encoding="utf-8"))
    candidates = expand_candidates(spec)
    if args.max_candidates > 0:
        candidates = candidates[:args.max_candidates]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, candidate in enumerate(candidates):
        raw_path = args.out_dir / f"candidate_{i:04d}_{candidate['id']}.jsonl"
        result = evaluate_candidate(candidate, fixtures, args.timeout, raw_path)
        results.append(result)
        print(json.dumps({
            "candidate": i,
            "id": result["candidate_id"],
            "exact_rate": result["exact_rate"],
            "structural_failures": result["structural_failures"],
            "params": result["params"],
        }, sort_keys=True))

    ranked = sorted(results, key=lambda r: (r["structural_failures"], -r["exact_rate"], r["mean_latency_seconds"] or 1e99))
    report = {
        "status": "MBM_GRINDER_COMPLETE",
        "scientific_content": False,
        "fixture_file": str(args.fixtures),
        "fixture_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
        "candidate_spec_sha256": hashlib.sha256(args.candidate_spec.read_bytes()).hexdigest(),
        "candidate_count": len(results),
        "ranking": ranked,
    }
    report_path = args.out_dir / "MBM_GRINDER_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "winner": ranked[0] if ranked else None}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
