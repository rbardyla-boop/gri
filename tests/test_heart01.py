"""HEART01 execution. The contract is preregistered; these tests are the run."""

from __future__ import annotations

import json

import pytest

from experiments.heart01.constitution import ConstitutionError, FrozenConstitution
from experiments.heart01.organism import STATE_KEYS, Organism
from experiments.heart01.scoring import CRITERIA, format_scoreboard, run_heart
from experiments.heart01.systems import run_system
from experiments.heart01.world import Event


@pytest.fixture(scope="module")
def heart():
    return run_heart()


def test_f_passes_all_six(heart):
    board = heart["board"]["F"]
    assert list(board) == list(CRITERIA)
    assert all(board.values()), board


def test_ablations_a_through_e_fail_at_least_one_that_f_passes(heart):
    f = heart["board"]["F"]
    f_pass = {k for k, v in f.items() if v}
    assert f_pass == set(CRITERIA)
    for name in "ABCDE":
        row = heart["board"][name]
        failed = [k for k, v in row.items() if not v]
        assert failed, f"{name} unexpectedly passed all six"
        assert set(failed) & f_pass, f"{name} failed only criteria F also failed: {failed}"


def test_f_is_unique_perfect_score(heart):
    perfect = [n for n, row in heart["board"].items() if all(row.values())]
    assert perfect == ["F"], perfect


def test_constitution_cannot_be_rewritten_by_plastic_layers():
    c = FrozenConstitution()
    digest = c.digest
    with pytest.raises(ConstitutionError):
        c.evidence_preservation = False  # type: ignore[attr-defined]
    with pytest.raises(ConstitutionError):
        del c.digest
    leaked = c.as_dict()
    leaked["evidence_preservation"] = False
    leaked["doctrine"]["need_grants_compute_not_truth"] = False
    c.verify()
    assert c.digest == digest
    assert c.as_dict()["evidence_preservation"] is True


def test_organism_state_schema(heart):
    state = heart["summaries"]["F"]["state"]
    assert tuple(state) == STATE_KEYS
    assert state["core_specific_residues"] == {}
    assert state["constitution"]["outward_actions_forbidden"] is True
    assert isinstance(state["immutable_experience"], list)
    assert state["failed_adaptations"]
    assert state["prior_stable_bodies"]
    assert "rebuild_beliefs_from_portable_life" == state["reconstruction_recipe"]["method"]
    json.dumps(state)


def test_experience_is_append_only(heart):
    org = heart["orgs"]["F"]
    n = len(org.immutable_experience)
    prefix = [dict(tr) for tr in org.immutable_experience[:10]]
    org.append_experience({"t": 999, "name": "seal", "payload": {}, "poison": False})
    assert len(org.immutable_experience) == n + 1
    assert org.immutable_experience[:10] == prefix
    assert org.immutable_experience[n]["metabolism"] == "Experienced"
    assert org.emitted_traces == n


def test_failed_adaptations_stored_on_f(heart):
    kinds = {a["kind"] for a in heart["orgs"]["F"].failed_adaptations}
    assert "skill" in kinds or "clock_maintainer" in str(heart["orgs"]["F"].failed_adaptations)
    assert any("poison" in str(a) or a.get("name") == "clock_maintainer" for a in heart["orgs"]["F"].failed_adaptations)


def test_outward_actions_forbidden():
    org = Organism(system="F", constitution=FrozenConstitution())
    with pytest.raises(ConstitutionError):
        org.reject_outward({"kind": "http"})
    with pytest.raises(ConstitutionError):
        org.reject_outward({"type": "post"})


def test_metabolism_labels(heart):
    org = heart["orgs"]["F"]
    assert all(tr.get("metabolism") == "Experienced" for tr in org.immutable_experience)
    skill = org.portable_skills.get("vault_opener")
    assert skill and skill["metabolism"] == "Integrated"
    assert any(tn.get("metabolism") == "Believed" for tn in org.tensions)


def test_f_keeps_contradiction_and_does_not_hide_family(heart):
    s = heart["summaries"]["F"]
    assert s["town_rel"] == "sibling"
    assert s["family_rel"] == "cousin"
    assert not s["flat_rel"]
    assert s["family_traces"] >= 3
    assert "family" not in s["hidden_contexts"]
    assert s["tensions"]


def test_f_reverses_only_with_witness_e_does_not(heart):
    assert heart["summaries"]["F"]["mid_mara_market"] == "greenhouse"
    assert heart["summaries"]["F"]["end_mara_market"] == "river"
    assert heart["summaries"]["E"]["mid_mara_market"] == "greenhouse"
    assert heart["summaries"]["E"]["end_mara_market"] != "river"


def test_f_ignores_poison_d_does_not(heart):
    assert heart["board"]["F"]["ignores_isolated_poison"]
    assert not heart["summaries"]["F"]["has_clock_skill"]
    assert heart["summaries"]["D"]["has_clock_skill"]
    assert not heart["board"]["D"]["ignores_isolated_poison"]


def test_a_is_the_cost_ceiling(heart):
    costs = {n: heart["summaries"][n]["lifetime_cost"] for n in "ABCDEF"}
    assert costs["F"] < costs["A"]
    assert not heart["board"]["A"]["lowers_lifetime_cost_vs_A"]
    assert not heart["board"]["A"]["moves_on_persistent_wounds"]


def test_deterministic():
    a = run_heart()
    b = run_heart()
    assert a["board"] == b["board"]
    for name in "ABCDEF":
        assert a["summaries"][name]["lifetime_cost"] == b["summaries"][name]["lifetime_cost"]
        assert a["summaries"][name]["constitution_digest"] == b["summaries"][name]["constitution_digest"]


def test_scoreboard_prints_and_mentions_f(heart):
    text = format_scoreboard(heart)
    assert "HEART F: PASS" in text


def test_world_query_event_roundtrip():
    org = run_system("A")
    e = Event("query", 0, "where", {"person": "Mara", "day_type": "Market"})
    assert org.predict(e) == "market"
