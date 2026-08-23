from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def visible(fixture: dict[str, Any]) -> dict[str, Any]:
    return {k: fixture[k] for k in ("id", "kind", "prompt")}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def run_tool(tool: dict[str, Any], fixture: dict[str, Any], state: dict[str, Any], timeout: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    command = tool["command"]
    payload = {"fixture": visible(fixture), "state": state}
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "TE0_TOOL": tool["name"], "TE0_GOLD_VISIBLE": "0"},
        )
    except subprocess.TimeoutExpired:
        return None, {"failure": "timeout", "elapsed_seconds": time.monotonic() - t0}
    elapsed = time.monotonic() - t0
    meta = {"returncode": proc.returncode, "elapsed_seconds": elapsed, "stderr": proc.stderr, "stdout": proc.stdout}
    if proc.returncode != 0:
        meta["failure"] = "nonzero_exit"
        return None, meta
    try:
        value = json.loads(proc.stdout)
    except Exception as exc:
        meta["failure"] = "unparseable"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return None, meta
    if not isinstance(value, dict) or set(value) != {"state"} or not isinstance(value["state"], dict):
        meta["failure"] = "bad_tool_shape"
        return None, meta
    return value["state"], meta


def run_recipe(recipe: list[str], catalog: dict[str, Any], fixture: dict[str, Any], timeout: float) -> tuple[Any, list[dict[str, Any]], float, bool]:
    state: dict[str, Any] = {}
    trace = []
    total_latency = 0.0
    ok = True
    for name in recipe:
        tool = catalog[name]
        state2, meta = run_tool(tool, fixture, state, timeout)
        trace.append({"tool": name, "meta": meta})
        total_latency += float(meta.get("elapsed_seconds", 0.0))
        if state2 is None:
            ok = False
            break
        state = state2
    prediction = state.get("prediction") if ok else None
    if ok and "prediction" not in state:
        ok = False
    return prediction, trace, total_latency, ok


def evaluate(recipe: list[str], catalog: dict[str, Any], fixtures: list[dict[str, Any]], timeout: float,
             tool_penalty: float, latency_penalty: float, trace_path: Path) -> dict[str, Any]:
    exact = 0
    structural = 0
    latency = 0.0
    with trace_path.open("x", encoding="utf-8") as out:
        for ordinal, fixture in enumerate(fixtures):
            pred, trace, elapsed, ok = run_recipe(recipe, catalog, fixture, timeout)
            is_exact = ok and pred == fixture["target"]
            exact += int(is_exact)
            structural += int(not ok)
            latency += elapsed
            out.write(json.dumps({
                "ordinal": ordinal,
                "fixture_id": fixture["id"],
                "target_sha256": digest(fixture["target"]),
                "prediction_sha256": digest(pred) if ok else None,
                "exact": is_exact,
                "trace": trace,
            }, sort_keys=True) + "\n")
    n = len(fixtures)
    exact_rate = exact / n if n else 0.0
    mean_latency = latency / n if n else 0.0
    objective = exact_rate - tool_penalty * len(recipe) - latency_penalty * mean_latency - (structural / max(n, 1))
    return {
        "recipe": recipe,
        "recipe_sha256": digest(recipe),
        "n": n,
        "exact": exact,
        "exact_rate": exact_rate,
        "structural_failures": structural,
        "mean_latency_seconds": mean_latency,
        "tool_count": len(recipe),
        "objective": objective,
        "trace_path": str(trace_path),
    }


def load_catalog(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    tools = raw.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("catalog requires tools array")
    out = {}
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) < {"name", "command", "promotable", "requires", "provides"}:
            raise ValueError("invalid tool contract")
        if tool["name"] in out:
            raise ValueError("duplicate tool name")
        if type(tool["promotable"]) is not bool:
            raise ValueError("promotable must be boolean")
        if not isinstance(tool["requires"], list) or not all(isinstance(x, str) for x in tool["requires"]):
            raise ValueError("requires must be string array")
        if not isinstance(tool["provides"], list) or not all(isinstance(x, str) for x in tool["provides"]):
            raise ValueError("provides must be string array")
        out[tool["name"]] = tool
    return out


def available_after(recipe: tuple[str, ...] | list[str], catalog: dict[str, Any]) -> set[str] | None:
    available: set[str] = set()
    for name in recipe:
        tool = catalog[name]
        if not set(tool["requires"]).issubset(available):
            return None
        available.update(tool["provides"])
    return available


def extension_valid(prefix: tuple[str, ...], name: str, catalog: dict[str, Any]) -> bool:
    available = available_after(prefix, catalog)
    if available is None:
        return False
    return set(catalog[name]["requires"]).issubset(available)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--beam", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--tool-penalty", type=float, default=0.002)
    ap.add_argument("--latency-penalty", type=float, default=0.0001)
    args = ap.parse_args()

    fixtures = load_jsonl(args.fixtures)
    catalog = load_catalog(args.catalog)
    promotable_names = sorted(name for name, tool in catalog.items() if tool["promotable"])
    if not promotable_names:
        raise ValueError("no promotable tools")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    frontier: list[tuple[str, ...]] = [tuple()]
    seen = set()
    counter = 0
    for depth in range(1, args.max_depth + 1):
        scored_candidates = []
        expansion_candidates: list[tuple[str, ...]] = []
        for prefix in frontier:
            for name in promotable_names:
                if not extension_valid(prefix, name, catalog):
                    continue
                recipe = prefix + (name,)
                if recipe in seen:
                    continue
                seen.add(recipe)
                expansion_candidates.append(recipe)
                available = available_after(recipe, catalog)
                if available is None or "prediction" not in available:
                    continue
                trace_path = args.out_dir / f"recipe_{counter:06d}_{digest(recipe)[:12]}.jsonl"
                counter += 1
                result = evaluate(list(recipe), catalog, fixtures, args.timeout, args.tool_penalty, args.latency_penalty, trace_path)
                scored_candidates.append(result)
                all_results.append(result)
                print(json.dumps({k: result[k] for k in ("recipe", "exact_rate", "structural_failures", "objective")}, sort_keys=True))

        ranked = sorted(scored_candidates, key=lambda r: (-r["objective"], r["tool_count"], r["mean_latency_seconds"]))
        ranked_recipes = [tuple(row["recipe"]) for row in ranked[:args.beam]]
        incomplete = [r for r in expansion_candidates if "prediction" not in (available_after(r, catalog) or set())]
        frontier = ranked_recipes + incomplete[:args.beam]
        frontier = frontier[: max(args.beam, 1) * 2]
        if not frontier:
            break

    ranked_all = sorted(all_results, key=lambda r: (-r["objective"], r["tool_count"], r["mean_latency_seconds"]))
    report = {
        "status": "TE0_RECIPE_SEARCH_COMPLETE",
        "scientific_content": False,
        "gold_visible_to_tools": False,
        "fixtures_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
        "catalog_sha256": hashlib.sha256(args.catalog.read_bytes()).hexdigest(),
        "max_depth": args.max_depth,
        "beam": args.beam,
        "tool_penalty": args.tool_penalty,
        "latency_penalty": args.latency_penalty,
        "ranking": ranked_all,
    }
    report_path = args.out_dir / "TE0_RECIPE_SEARCH_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "winner": ranked_all[0] if ranked_all else None}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
