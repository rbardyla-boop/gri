from experiments.erc0.run_erc0 import (
    PACKET_CAPACITY,
    GraphIndex,
    build_packet,
    extract_features,
    generate_case,
    rank_relay,
    report_without_rows,
    run_benchmark,
    verify_packet,
    verify_source_hashes,
)


def test_truth_is_not_present_in_visible_case():
    case, truth = generate_case(32, 2026082301)
    assert truth.root_id in case.node_ids
    assert not hasattr(case, "root_id")
    assert not hasattr(case, "affected_ids")


def test_case_generation_is_deterministic():
    left = generate_case(64, 12345)
    right = generate_case(64, 12345)
    assert left == right


def test_signal_provenance_recomputes():
    case, _ = generate_case(64, 22222)
    assert verify_source_hashes(case)


def test_relay_packet_is_bounded_and_source_bound():
    case, _ = generate_case(128, 33333)
    features = extract_features(case)
    graph = GraphIndex(case)
    ranking = rank_relay(case, features, graph)
    packet, digest = build_packet(case, ranking, features, graph)
    assert 1 <= len(packet) <= PACKET_CAPACITY
    assert verify_packet(case, packet, digest)


def test_small_benchmark_replays_exactly():
    left = report_without_rows(run_benchmark(sizes=(32, 128), cases_per_size=3))
    right = report_without_rows(run_benchmark(sizes=(32, 128), cases_per_size=3))
    assert left == right


def test_registered_benchmark_has_no_model_calls():
    report = report_without_rows(run_benchmark(sizes=(32,), cases_per_size=2))
    assert report["scientific_model_calls"] == 0
    assert report["claim_scope"] == "synthetic transparent fault-localization mechanics only"
