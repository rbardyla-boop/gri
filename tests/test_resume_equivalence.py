from pathlib import Path

from gri_models.resume_audit import AUDIT_SEED, audit

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/frozen/world0_v0_1"


def _assert_pass(report):
    assert report["audit_seed"] == AUDIT_SEED == 9090
    assert report["model_state_equal"]
    assert report["optimizer_state_equal"]
    assert report["rng_state_equal"]
    assert report["final_loss_equal"]
    assert report["uninterrupted_model_hash"] == report["resumed_model_hash"]


def test_baseline_resume_is_exactly_equivalent():
    _assert_pass(audit("baseline", ART, total_epochs=3, split_epoch=1))


def test_so4_resume_is_exactly_equivalent():
    _assert_pass(audit("so4", ART, total_epochs=3, split_epoch=1))
