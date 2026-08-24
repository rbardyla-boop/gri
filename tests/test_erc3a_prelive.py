from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.erc3a.channel_schema import CHANNEL_SCHEMA, CURRENT_CHANNELS_BY_RELAY, LINE_ENDPOINTS
from experiments.erc3a.locator import (
    BASELINE_WINDOW_SAMPLES,
    POST_WINDOW_SAMPLES,
    RMS_WINDOW_SAMPLES,
    causal_rms,
    locate,
)
from experiments.erc3a.producer_boundary import assert_clean
from experiments.erc3a.scoring import score_after_prediction_seals, verify_prediction_seals

ERC3A_ROOT = Path(__file__).parents[1] / "experiments" / "erc3a"
SELECTED_IDS_SHA256 = "aef9418b6ee352f0c2ab96ac6ecb7e097aa834662a646453495905a1c6dcf6db"


def _fixture() -> dict:
    event_index = 1600
    length = event_index + POST_WINDOW_SAMPLES
    waveform = {channel: [1.0] * length for channel in CHANNEL_SCHEMA}
    for channel in CHANNEL_SCHEMA:
        if "_vol_" in channel:
            waveform[channel] = [0.0] * length

    def step(relay: str, start_delta: int, amplitude: float) -> None:
        for channel in CURRENT_CHANNELS_BY_RELAY[relay]:
            waveform[channel][event_index + start_delta :] = [amplitude] * (length - event_index - start_delta)

    # Both endpoints of Line_2_3_a respond, with the receiving end later.
    step("Bus_2_Line_02_03A", 40, 2.0)
    step("Bus_3_Line_02_03A", 90, 2.0)
    # A one-ended, high-magnitude distractor has no receiving-end support.
    step("Bus_1_Line_01_02B", 5, 100.0)
    # A valid but later two-ended line checks the primary later-of rule.
    step("Bus_1_Line_01_02A", 20, 1.5)
    step("Bus_2_Line_01_02A", 110, 1.5)
    return {
        "opaque_id": "P90-SYNTHETIC-01",
        "t_evnt_start": event_index / 6400,
        "waveform_sha256": "synthetic-fixture-sha256",
        "channel_schema": list(CHANNEL_SCHEMA),
        "waveform": waveform,
    }


def test_selected_sample_ids_are_frozen_and_public_files_are_opaque_only() -> None:
    acquisition = json.loads((ERC3A_ROOT / "ERC3A_ACQUISITION_MAP.json").read_text())
    ids = [row["sample_id"] for row in acquisition]
    digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
    assert digest == SELECTED_IDS_SHA256
    assert len(ids) == 64
    assert len({row["opaque_id"] for row in acquisition}) == 64

    assert_clean(
        [
            ERC3A_ROOT / "ERC3A_PUBLIC_SELECTION.json",
            ERC3A_ROOT / "ERC3A_PRODUCER_MANIFEST.json",
        ]
    )
    public = json.loads((ERC3A_ROOT / "ERC3A_PUBLIC_SELECTION.json").read_text())
    assert all(set(row) == {"opaque_id", "t_evnt_start"} for row in public)


def test_producer_identity_regression_fails_on_any_forbidden_key(tmp_path: Path) -> None:
    leaked = tmp_path / "leaked.json"
    leaked.write_text(json.dumps({"opaque_id": "x", "sample_id": 1}))
    with pytest.raises(AssertionError, match="identity leakage"):
        assert_clean([leaked])


def test_causal_rms_does_not_use_future_samples() -> None:
    prefix = [1.0] * 130
    assert causal_rms(prefix) == causal_rms(prefix + [100.0])[: len(prefix)]


def test_locator_uses_registered_windows_and_later_endpoint() -> None:
    prediction = locate(_fixture())
    assert prediction["protocol"]["rms_window_samples"] == RMS_WINDOW_SAMPLES == 128
    assert prediction["protocol"]["baseline_window_samples"] == BASELINE_WINDOW_SAMPLES == 640
    assert prediction["protocol"]["post_window_samples"] == POST_WINDOW_SAMPLES == 640
    assert prediction["protocol"]["onset_threshold"] == 5.0
    assert prediction["protocol"]["persistence_samples"] == 32

    assert prediction["primary"][0]["line_id"] == "Line_2_3_a"
    primary_by_line = {row["line_id"]: row for row in prediction["primary"]}
    single_by_line = {row["line_id"]: row for row in prediction["single_ended"]}
    assert primary_by_line["Line_2_3_a"]["onset_sample"] is not None
    assert primary_by_line["Line_2_3_a"]["onset_sample"] > single_by_line["Line_2_3_a"]["onset_sample"]
    assert primary_by_line["Line_1_2_b"]["onset_sample"] is None
    assert prediction["magnitude_only"][0]["line_id"] == "Line_1_2_b"


def test_locator_rejects_truth_or_acquisition_identity() -> None:
    leaked = _fixture()
    leaked["sample_id"] = 118
    with pytest.raises(ValueError, match="forbidden producer fields"):
        locate(leaked)


def test_live_replay_serialization_is_exact_and_scoring_waits_for_it() -> None:
    prediction = locate(_fixture())
    live = [prediction]
    replay = json.loads(json.dumps(live, sort_keys=True))
    assert verify_prediction_seals(live, replay)
    scorer = [{"opaque_id": prediction["opaque_id"], "truth": {"fault_target": "Line_2_3_a", "sc_type": 0}}]
    scored = score_after_prediction_seals(live_predictions=live, replay_predictions=replay, scorer_map=scorer)
    assert scored["status"] == "ERC3A_SCORED_AFTER_SEALS"
    assert scored["same_set_rescue_authorized"] is False

    replay[0]["primary"][0]["line_id"] = "Line_1_2_a"
    with pytest.raises(ValueError, match="serialization mismatch"):
        score_after_prediction_seals(live_predictions=live, replay_predictions=replay, scorer_map=scorer)


def test_manifest_has_64_bindings_and_no_payload_was_opened() -> None:
    index = json.loads((ERC3A_ROOT / "ERC3A_ACQUISITION_INDEX.json").read_text())
    manifest = json.loads((ERC3A_ROOT / "ERC3A_PRODUCER_MANIFEST.json").read_text())
    assert index["zip_entry_count"] == 9022
    assert index["pkl_member_count"] == 9022
    assert index["selected_member_count"] == 64
    assert index["selected_member_payload_bytes_read"] == 0
    assert index["selected_member_payload_ranges_requested"] == 0
    assert index["waveform_members_opened"] == 0
    assert index["scientific_predictions"] == 0
    assert len(manifest) == 64
    assert all(row["waveform_binding"]["payload_sha256"] is None for row in manifest)
    assert all("sample_id" not in json.dumps(row) for row in manifest)


def test_all_fixed_line_endpoints_are_registered() -> None:
    assert len(LINE_ENDPOINTS) == 4
    assert len({relay for endpoints in LINE_ENDPOINTS.values() for relay in endpoints}) == 8

