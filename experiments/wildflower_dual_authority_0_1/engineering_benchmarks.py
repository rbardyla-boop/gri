"""Engineering-only store benchmark; never imports or runs Nursery episodes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from typing import Callable, Type

import numpy as np

from . import store as d


SIZES = (100, 500, 1_000, 2_000, 5_000, 10_000)
BENCHMARK_NAME = "STORE_REFRESH_BENCH_0"


def _proposal(reference: int, value: int = 1) -> d.Packet:
    return d.Packet(reference, d.ACT_PROPOSE, reference, d.REL_X, 0, value)


def _derived(reference: int, value: int, parent: d.ClaimKey) -> d.Packet:
    return d.Packet(reference, d.ACT_DERIVE, reference, d.REL_LEFT_OF, 0, value)


def _build_graph(store_type: Type[d.ReferenceEpistemicStore], size: int) -> d.ReferenceEpistemicStore:
    store = store_type(max_claims=size + 64)
    root_packet = _proposal(1)
    store.propose(root_packet)
    root_key = store.claim_key(root_packet)
    for index in range(1, size):
        packet = _derived(100_000 + index, index, root_key)
        store.derive(packet, (root_key,))
    return store


def _descendant_walk(store: d.ReferenceEpistemicStore, root: d.ClaimKey) -> int:
    pending = [root]
    visited: set[d.ClaimKey] = set()
    supports = 0
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        for support_id in sorted(store.children.get(key, ())):
            supports += 1
            child_key = store.support_to_claim[support_id] if hasattr(store, "support_to_claim") else (
                store.supports[support_id].packet.stable_reference,
                store.supports[support_id].packet.value,
            )
            pending.append(child_key)
    return supports


def _measure(
    store: d.ReferenceEpistemicStore,
    name: str,
    operation: Callable[[], object],
) -> dict[str, object]:
    store.reset_engineering_metrics()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    value = operation()
    wall = time.perf_counter() - wall_start
    cpu = time.process_time() - cpu_start
    counters = store.engineering_metrics()
    return {
        "operation": name,
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "claims_visited": counters.get("claims_visited", 0),
        "supports_visited": counters.get("supports_visited", 0),
        "recursive_calls": counters.get("recursive_calls", 0),
        "cache_hits": counters.get("cache_hits", 0),
        "cache_misses": counters.get("cache_misses", 0),
        "dirty_claims_processed": counters.get("dirty_claims_processed", 0),
        "dirty_supports_processed": counters.get("dirty_supports_processed", 0),
        "descendant_claims_visited": counters.get("descendant_claims_visited", 0),
        "descendant_traversals": counters.get("descendant_traversals", 0),
        "result_size": len(value) if isinstance(value, (dict, tuple, list, set)) else None,
    }


def _worker(implementation: str, size: int) -> dict[str, object]:
    store_type: Type[d.ReferenceEpistemicStore]
    if implementation == "reference":
        store_type = d.ReferenceEpistemicStore
    elif implementation == "incremental":
        store_type = d.IncrementalEpistemicStore
    else:
        raise ValueError(f"unknown implementation: {implementation}")

    build_wall_start = time.perf_counter()
    build_cpu_start = time.process_time()
    store = _build_graph(store_type, size)
    build = {
        "wall_seconds": time.perf_counter() - build_wall_start,
        "cpu_seconds": time.process_time() - build_cpu_start,
        "claims_visited": store.engineering_metrics().get("claims_visited", 0),
        "supports_visited": store.engineering_metrics().get("supports_visited", 0),
        "recursive_calls": store.engineering_metrics().get("recursive_calls", 0),
    }
    root_key = (1, 1)
    isolated_reference = 2 * size + 1
    insertion_result = _measure(
        store,
        "support_insertion",
        lambda: store.propose(_proposal(isolated_reference)),
    )
    witness_reference = isolated_reference + 1
    store.propose(_proposal(witness_reference))
    witness_result = _measure(
        store,
        "witness_insertion",
        lambda: store.observe(
            d.Packet(
                witness_reference,
                d.ACT_OBSERVE,
                witness_reference,
                d.REL_X,
                0,
                2,
            )
        ),
    )
    revoke_reference = witness_reference + 1
    revoke_support = store.propose(_proposal(revoke_reference))
    revoke_result = _measure(
        store,
        "support_revocation",
        lambda: store.revoke_support(revoke_support),
    )
    refresh_result = _measure(
        store,
        "status_refresh",
        lambda: store._refresh_all_statuses(),
    )
    effective_result = _measure(
        store,
        "effective_support_calculation",
        lambda: store._effective_map(),
    )
    grounded_result = _measure(
        store,
        "grounded_support_calculation",
        lambda: store._claim_grounded(root_key),
    )
    descendant_result = _measure(
        store,
        "descendant_traversal",
        lambda: _descendant_walk(store, root_key),
    )
    before_after_result = _measure(
        store,
        "before_after_map_construction",
        lambda: (store._effective_map(), store._effective_map()),
    )
    recomputation_state = np.array(
        [-0.4, -0.2, 0.3, 0.5, -0.1, 0.2], dtype=np.float32
    )
    d.materialize_world_witness(store, recomputation_state, 0, 1)
    recomputation_result = _measure(
        store,
        "recomputation",
        lambda: d.derive_from_committed_coordinates(
            store, recomputation_state, 0, 1
        ),
    )
    ledger_result = _measure(
        store,
        "ledger_write",
        lambda: store.ledger.append(99, size),
    )
    return {
        "benchmark": BENCHMARK_NAME,
        "implementation": implementation,
        "graph_size_supports": size,
        "graph_claims": len(store.claims),
        "graph_supports": len(store.supports),
        "build": build,
        "operations": [
            insertion_result,
            witness_result,
            revoke_result,
            refresh_result,
            effective_result,
            grounded_result,
            descendant_result,
            before_after_result,
            recomputation_result,
            ledger_result,
        ],
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "deterministic_replay": store.ledger.head_sha256 == store.ledger.replay_head(),
    }


def _run_worker(implementation: str, size: int) -> None:
    result = _worker(implementation, size)
    print(json.dumps(result, sort_keys=True))


def _run_parent(timeout_seconds: float) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for implementation in ("reference", "incremental"):
        for size in SIZES:
            command = [
                sys.executable,
                "-m",
                "experiments.wildflower_dual_authority_0_1.engineering_benchmarks",
                "--worker",
                "--implementation",
                implementation,
                "--size",
                str(size),
            ]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env={**os.environ, "PYTHONHASHSEED": "0"},
                )
                row = json.loads(completed.stdout)
            except subprocess.TimeoutExpired:
                row = {
                    "benchmark": BENCHMARK_NAME,
                    "implementation": implementation,
                    "graph_size_supports": size,
                    "status": "timeout",
                    "timeout_seconds": timeout_seconds,
                }
            except subprocess.CalledProcessError as exc:
                row = {
                    "benchmark": BENCHMARK_NAME,
                    "implementation": implementation,
                    "graph_size_supports": size,
                    "status": "error",
                    "stderr": exc.stderr[-2_000:],
                }
            row["harness_wall_seconds"] = time.perf_counter() - started
            rows.append(row)
    return {
        "benchmark": BENCHMARK_NAME,
        "synthetic_only": True,
        "sizes": list(SIZES),
        "timeout_seconds_per_trial": timeout_seconds,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--implementation", choices=("reference", "incremental"))
    parser.add_argument("--size", type=int)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.implementation is None or args.size is None:
            raise SystemExit("--worker requires --implementation and --size")
        _run_worker(args.implementation, args.size)
        return
    result = _run_parent(args.timeout)
    output = args.output or Path(__file__).with_name("artifacts") / "STORE_REFRESH_BENCH_0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
