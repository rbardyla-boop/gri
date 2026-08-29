from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

import run_dual_authority0


ROOT = Path(__file__).resolve().parents[1]
FROZEN_AUTHORITY_HASHES = {
    "probe_innovation_model.py": "97925c78ac50cf54b96cca05c4794b5b78465cf44e63d53dc7ed45673afedab1",
    "qualify_authority190.py": "13a39e6579d9e17c061e9cbaaa3d3635c723c897695f8f87c61634f191e1590e",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dual_authority_reuses_byte_locked_predictive_authority_sources() -> None:
    for name, expected in FROZEN_AUTHORITY_HASHES.items():
        assert _sha256(ROOT / name) == expected


def test_dual_authority_predictive_constants_are_unchanged() -> None:
    assert run_dual_authority0.THRESHOLD == 0.30
    assert run_dual_authority0.WIDTH == 0.30
    assert run_dual_authority0.DECAY == 0.998
    assert run_dual_authority0.BURN == 12


def test_developmental_cognitive_loop_cannot_read_evaluator_metadata() -> None:
    source = inspect.getsource(run_dual_authority0.run_developmental_episode)
    lowered = source.lower()
    for forbidden in (
        ".mode",
        ".rule_event",
        ".collision",
        ".boundary",
        "mode_evaluator_only",
        "episode_seed_evaluator_only",
    ):
        assert forbidden not in lowered


def test_developmental_loop_uses_both_authority_boundaries() -> None:
    source = inspect.getsource(run_dual_authority0.run_developmental_episode)
    assert "_predictive_authority_one" in source
    assert "materialize_prediction" in source
    assert "materialize_world_witness" in source
    assert "derive_from_committed_coordinates" in source


def test_scored_run_is_blocked_without_separate_authorization(monkeypatch) -> None:
    monkeypatch.setattr(
        run_dual_authority0,
        "AUTHORIZATION_PATH",
        ROOT / "definitely-not-authorized.json",
    )
    with pytest.raises(RuntimeError, match="blocked"):
        run_dual_authority0._load_authorization()


def test_runner_has_no_forbidden_language_model_dependencies() -> None:
    source = inspect.getsource(run_dual_authority0).lower()
    for forbidden in (
        "import transformers",
        "from transformers",
        "import whisper",
        "from whisper",
        "import clip",
        "from clip",
        "tokenizer(",
        "transcript",
    ):
        assert forbidden not in source
