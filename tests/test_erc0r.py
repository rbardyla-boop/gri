from experiments.erc0.run_erc0 import GraphIndex, extract_features, generate_case
from experiments.erc0r.run_erc0r import (
    FRESH_SEED_PREFIX,
    REGISTERED_CASES_PER_SIZE,
    compact_report,
    frontier_terms,
    rank_frontier,
    rank_quiet_parent,
    run_benchmark,
)


def test_fresh_seed_namespace_differs_from_erc0():
    assert FRESH_SEED_PREFIX != 2026082300
    assert REGISTERED_CASES_PER_SIZE == 32


def test_frontier_and_quiet_parent_are_deterministic_full_rankings():
    case, _ = generate_case(64, FRESH_SEED_PREFIX + 64000)
    features = extract_features(case)
    graph = GraphIndex(case)
    for method in (rank_quiet_parent, rank_frontier):
        left = method(case, features, graph)
        right = method(case, features, graph)
        assert left == right
        assert len(left) == len(case.node_ids)
        assert set(left) == set(case.node_ids)


def test_frontier_terms_do_not_require_truth():
    case, _ = generate_case(64, FRESH_SEED_PREFIX + 64001)
    features = extract_features(case)
    graph = GraphIndex(case)
    node = rank_frontier(case, features, graph)[0]
    terms = frontier_terms(node, features, graph)
    assert len(terms) == 3
    assert not hasattr(case, "root_id")


def test_small_fresh_benchmark_replays_exactly():
    left = compact_report(run_benchmark(sizes=(32, 128), cases_per_size=3))
    right = compact_report(run_benchmark(sizes=(32, 128), cases_per_size=3))
    assert left == right


def test_no_model_calls():
    report = compact_report(run_benchmark(sizes=(32,), cases_per_size=2))
    assert report["scientific_model_calls"] == 0
    assert report["parent_terminal_status"] == "ERC0_SYNTHETIC_FAIL"
