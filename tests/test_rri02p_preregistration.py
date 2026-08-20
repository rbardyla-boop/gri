import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts/rri02p"


def baseline_parameters(hidden: int, message: int) -> int:
    return 9 * hidden * hidden + 19 * hidden + (3 * hidden + 17) * message + 8


def anchor_parameters(hidden: int, message: int) -> int:
    return 11 * hidden * hidden + 19 * hidden + (3 * hidden + 17) * message + 8


def test_capacity_equations_and_unresolved_search_are_consistent():
    search = json.loads((ARTIFACTS / "capacity_search.json").read_text())
    assert baseline_parameters(49, 51) == 30912
    assert search["exact_solution_count"] == 0
    assert search["exact_solutions"] == []
    for hidden in range(1, 101):
        for message in range(1, 1001):
            assert anchor_parameters(hidden, message) != 30912


def test_preregistration_forbids_training_and_candidate_evidence():
    receipt = json.loads((ARTIFACTS / "RRI02P_RECEIPT.json").read_text())
    assert receipt["training_performed"] is False
    assert receipt["candidate_model_implemented"] is False
    assert receipt["performance_evidence_generated"] is False
    assert receipt["terminal_state"] == "RRI_02P_CAPACITY_MATCH_UNRESOLVED"
