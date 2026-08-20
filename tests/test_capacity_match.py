from gri_models.gri05 import PARAMETERS, PRIMARY_DEPTHS, build_model, primary_metric


def test_capacity_matched_models_are_exactly_equal_size():
    baseline = build_model("baseline", 2026)
    so4 = build_model("so4", 2026)
    b = sum(p.numel() for p in baseline.parameters() if p.requires_grad)
    g = sum(p.numel() for p in so4.parameters() if p.requires_grad)
    assert b == g == PARAMETERS == 30_912


def test_primary_metric_is_frozen_depth_mean():
    scores = {"5": 0.1, "8": 0.2, "16": 0.4, "32": 0.6, "64": 0.8}
    assert PRIMARY_DEPTHS == (8, 16, 32, 64)
    assert primary_metric(scores) == 0.5
