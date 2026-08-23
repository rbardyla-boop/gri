from __future__ import annotations

from experiments.forge.controller import DiscoveryController, DiscoveryPolicy, DiscoveryStatus
from experiments.forge.forge import Case, Mutation


def build_fixture():
    build = [
        Case("B1", "PASS", "PASS"),
        Case("B2", "FAIL", "FAIL"),
        Case("B3", "INCONCLUSIVE", "INCONCLUSIVE"),
    ]
    dev = [
        Case("D1", " pass ", "PASS"),
        Case("D2", "FAIL ", "FAIL"),
        Case("D3", " InConClusive", "INCONCLUSIVE"),
    ]
    return build, dev


def test_controller_stops_resource_failure_before_tool_search() -> None:
    build, dev = build_fixture()
    report = DiscoveryController().run(
        build_cases=build,
        dev_cases=dev,
        signals={"oom": True},
        input_kind="text",
        output_kind="label",
    )
    assert report.status is DiscoveryStatus.STOP_WRONG_LAYER
    assert report.champion is None
    assert report.tool_names == ()


def test_controller_can_make_interface_repair_ready_for_freeze() -> None:
    build, dev = build_fixture()
    report = DiscoveryController().run(
        build_cases=build,
        dev_cases=dev,
        signals={"label_collision": True},
        input_kind="text",
        output_kind="label",
        policy=DiscoveryPolicy(
            dev_threshold=1.0,
            min_margin_over_null=0.5,
            max_grinder_failures=0,
            min_component_delta=0.0,
            max_depth=4,
            max_cost=4,
        ),
    )
    assert report.status is DiscoveryStatus.READY_FOR_FREEZE
    assert report.champion is not None
    assert report.champion.dev_score == 1.0
    assert "ts_build_lookup_canonical" in report.champion.chain.tools
    assert report.champion.chain.tools != ("ts_build_lookup",)


def test_controller_stops_if_simple_null_matches_candidate() -> None:
    build = [Case("B1", "YES", "YES"), Case("B2", "YES", "YES")]
    dev = [Case("D1", "YES", "YES"), Case("D2", "YES", "YES")]
    report = DiscoveryController().run(
        build_cases=build,
        dev_cases=dev,
        signals={"model_wrong_after_controls": True},
        input_kind="text",
        output_kind="text",
        policy=DiscoveryPolicy(min_margin_over_null=0.1),
    )
    assert report.status is DiscoveryStatus.STOP_NULL_MATCH
    assert report.best_null_score == 1.0


def test_controller_stops_on_grinder_counterexample() -> None:
    build, dev = build_fixture()

    def semantic_flip(case: Case):
        # Surface form remains normalizable, but the authoritative answer is
        # deliberately changed. A lookup/normalization recipe must fail.
        yield Case(case.case_id + "-flip", case.input, "DIFFERENT")

    report = DiscoveryController().run(
        build_cases=build,
        dev_cases=dev,
        signals={"label_collision": True},
        input_kind="text",
        output_kind="label",
        mutations=[Mutation("semantic_flip", semantic_flip)],
        policy=DiscoveryPolicy(
            dev_threshold=1.0,
            min_margin_over_null=0.5,
            max_grinder_failures=0,
            min_component_delta=0.0,
            max_depth=4,
            max_cost=4,
        ),
    )
    assert report.status is DiscoveryStatus.STOP_GRINDER_FAILURE
    assert report.grinder_failures == 1
