from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from recipe_search import digest, load_catalog, load_jsonl, run_recipe


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trace(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                raise ValueError(f"invalid checkpoint JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"invalid checkpoint row at {path}:{line_no}")
            rows.append(row)
    return rows


def validate_prefix(rows: list[dict[str, Any]], fixtures: list[dict[str, Any]], replays: int) -> None:
    planned = len(fixtures) * replays
    if len(rows) > planned:
        raise ValueError(f"checkpoint has {len(rows)} rows but only {planned} are planned")
    for index, row in enumerate(rows):
        replay = index // len(fixtures)
        ordinal = index % len(fixtures)
        fixture = fixtures[ordinal]
        expected = (replay, ordinal, fixture["id"])
        actual = (row.get("replay"), row.get("ordinal"), row.get("fixture_id"))
        if actual != expected:
            raise ValueError(
                f"checkpoint is not an exact execution prefix at row {index}: expected {expected}, got {actual}"
            )


def summarize_trace(
    recipe: list[str],
    rows: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    replays: int,
    trace_path: Path,
) -> dict[str, Any]:
    expected_n = len(fixtures) * replays
    if len(rows) != expected_n:
        raise ValueError(f"cannot summarize incomplete trace: {len(rows)}/{expected_n}")

    exact = 0
    structural = 0
    total_latency = 0.0
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "exact": 0, "structural_failures": 0})
    replay_preds: dict[str, list[str | None]] = defaultdict(list)

    for row in rows:
        is_exact = bool(row.get("exact"))
        ok = bool(row.get("ok", row.get("prediction_sha256") is not None))
        exact += int(is_exact)
        structural += int(not ok)
        total_latency += float(row.get("elapsed_seconds", 0.0))
        replay_preds[str(row["fixture_id"])].append(row.get("prediction_sha256") if ok else None)
        key = f"{row.get('attack','unknown')}|{row.get('size','unknown')}|{row['kind']}"
        group = grouped[key]
        group["n"] += 1
        group["exact"] += int(is_exact)
        group["structural_failures"] += int(not ok)

    inconsistent = sum(1 for values in replay_preds.values() if len(set(values)) > 1)
    by_group = {
        key: {**value, "exact_rate": value["exact"] / value["n"] if value["n"] else 0.0}
        for key, value in sorted(grouped.items())
    }
    n = len(rows)
    return {
        "recipe": recipe,
        "recipe_sha256": digest(recipe),
        "n": n,
        "exact": exact,
        "exact_rate": exact / n if n else 0.0,
        "structural_failures": structural,
        "replay_inconsistent_fixtures": inconsistent,
        "mean_latency_seconds": total_latency / n if n else 0.0,
        "by_group": by_group,
        "trace_path": str(trace_path),
    }


def checkpoint_recipe(result: dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--recipes", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--replays", type=int, default=2)
    ap.add_argument("--no-resume", action="store_true", help="fail if any prior grinder trace/checkpoint exists")
    args = ap.parse_args()

    fixtures = load_jsonl(args.fixtures)
    catalog = load_catalog(args.catalog)
    spec = json.loads(args.recipes.read_text(encoding="utf-8"))
    recipes = spec.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        raise ValueError("recipes file requires non-empty recipes array")
    if args.replays < 1:
        raise ValueError("replays must be >= 1")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    expected_per_recipe = len(fixtures) * args.replays

    for recipe_index, recipe in enumerate(recipes):
        if not isinstance(recipe, list) or not recipe or not all(isinstance(x, str) and x for x in recipe):
            raise ValueError("recipe must be a non-empty string array")

        recipe_id = digest(recipe)[:12]
        trace_path = args.out_dir / f"recipe_{recipe_index:03d}_{recipe_id}.jsonl"
        checkpoint_path = args.out_dir / f"recipe_{recipe_index:03d}_{recipe_id}.result.json"

        if args.no_resume and (trace_path.exists() or checkpoint_path.exists()):
            raise FileExistsError(f"prior grinder artifact exists for recipe {recipe_index}")

        rows = load_trace(trace_path)
        validate_prefix(rows, fixtures, args.replays)

        if checkpoint_path.exists():
            if len(rows) != expected_per_recipe:
                raise ValueError(f"result checkpoint exists but trace is incomplete for recipe {recipe_index}")
            result = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if result.get("recipe_sha256") != digest(recipe):
                raise ValueError(f"recipe checkpoint hash mismatch for recipe {recipe_index}")
            results.append(result)
            print(json.dumps({
                "recipe_index": recipe_index,
                "status": "TE0_GRINDER_RECIPE_REUSED",
                "completed": len(rows),
                "planned": expected_per_recipe,
                "recipe": recipe,
            }, sort_keys=True), flush=True)
            continue

        start_index = len(rows)
        print(json.dumps({
            "recipe_index": recipe_index,
            "status": "TE0_GRINDER_RECIPE_RESUME" if start_index else "TE0_GRINDER_RECIPE_START",
            "completed": start_index,
            "planned": expected_per_recipe,
            "recipe": recipe,
        }, sort_keys=True), flush=True)

        mode = "a" if trace_path.exists() else "x"
        with trace_path.open(mode, encoding="utf-8") as out:
            for flat_index in range(start_index, expected_per_recipe):
                replay = flat_index // len(fixtures)
                ordinal = flat_index % len(fixtures)
                fixture = fixtures[ordinal]
                pred, trace, elapsed, ok = run_recipe(recipe, catalog, fixture, args.timeout)
                is_exact = ok and pred == fixture["target"]
                row = {
                    "replay": replay,
                    "ordinal": ordinal,
                    "fixture_id": fixture["id"],
                    "attack": fixture.get("attack"),
                    "size": fixture.get("size"),
                    "kind": fixture["kind"],
                    "target_sha256": digest(fixture["target"]),
                    "prediction_sha256": digest(pred) if ok else None,
                    "exact": is_exact,
                    "ok": ok,
                    "elapsed_seconds": elapsed,
                    "trace": trace,
                }
                out.write(json.dumps(row, sort_keys=True) + "\n")
                out.flush()
                os.fsync(out.fileno())

        rows = load_trace(trace_path)
        validate_prefix(rows, fixtures, args.replays)
        result = summarize_trace(recipe, rows, fixtures, args.replays, trace_path)
        checkpoint_recipe(result, checkpoint_path)
        results.append(result)
        print(json.dumps({
            "recipe_index": recipe_index,
            "status": "TE0_GRINDER_RECIPE_COMPLETE",
            "exact_rate": result["exact_rate"],
            "structural_failures": result["structural_failures"],
            "mean_latency_seconds": result["mean_latency_seconds"],
            "recipe": recipe,
        }, sort_keys=True), flush=True)

    ranked = sorted(
        results,
        key=lambda row: (
            row["structural_failures"],
            row["replay_inconsistent_fixtures"],
            -row["exact_rate"],
            len(row["recipe"]),
            row["mean_latency_seconds"],
        ),
    )
    report = {
        "status": "TE0_RECIPE_GRINDER_COMPLETE",
        "scientific_content": False,
        "vault_used": False,
        "gold_visible_to_tools": False,
        "fixtures_sha256": file_sha(args.fixtures),
        "catalog_sha256": file_sha(args.catalog),
        "recipes_sha256": file_sha(args.recipes),
        "replays": args.replays,
        "resumable_checkpoints": True,
        "ranking": ranked,
    }
    report_path = args.out_dir / "TE0_RECIPE_GRINDER_REPORT.json"
    tmp = report_path.with_suffix(report_path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, report_path)
    print(json.dumps({"report": str(report_path), "winner": ranked[0] if ranked else None}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
