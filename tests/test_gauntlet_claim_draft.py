from __future__ import annotations

import json
from pathlib import Path

import pytest

from gauntlet.autopsy import autopsy_claim
from gauntlet.claim_draft import materialize_approved_markdown_claim, scan_markdown


MARKDOWN = """# External result

### Controlled memory ablation

All variants use the same model and evaluation protocol. Each block changes only the named component.

| Block | Variant | R2R SR | RxR SR |
| --- | --- | ---: | ---: |
| Memory | Full history | 61.9 | 61.1 |
|  | Full AT-Mem | 66.2 | 65.7 |

## Limitations

The baseline is a floor, not a meaningful semantic comparison.
"""


def _approval(draft: dict) -> dict:
    return {
        "approved": True,
        "reviewer_statement": "I checked the selected rows, metrics, direction, and control sentence against the source.",
        "source_git_blob_sha1": draft["source"]["git_blob_sha1"],
        "source_revision": "deadbeef",
        "table_heading_contains": "Controlled memory ablation",
        "row_label_column": 1,
        "candidate_label": "Full AT-Mem",
        "baseline_label": "Full history",
        "required_source_phrases": [
            "All variants use the same model and evaluation protocol. Each block changes only the named component."
        ],
        "metrics": [
            {"name": "r2r_sr", "column": 2, "value_index": 0, "direction": "greater", "minimum_improvement": 0.0},
            {"name": "rxr_sr", "column": 3, "value_index": 0, "direction": "greater", "minimum_improvement": 0.0},
        ],
        "autopsy_id": "synthetic-approved-markdown",
        "credit_target": "selected memory component",
        "claim_if_advance": "selected memory component retains provisional conditional credit",
        "claim_if_not_advance": "selected memory component does not retain credit",
    }


def test_scan_markdown_catalogs_tables_without_credit_authority(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(source, source_uri="https://example.invalid/source", source_revision="deadbeef")

    assert draft["evidence_class"] == "UNAPPROVED_MARKDOWN_CLAIM_DRAFT"
    assert draft["authority_status"] == "HUMAN_APPROVAL_REQUIRED"
    assert draft["table_count"] == 1
    assert draft["tables"][0]["heading"] == "Controlled memory ablation"
    assert draft["boundary"]["candidate_not_inferred"] is True
    assert draft["boundary"]["baseline_not_inferred"] is True
    assert draft["boundary"]["negative_signal_not_inferred"] is True
    assert draft["boundary"]["credit_decision_not_run"] is True
    assert draft["evidence_requests"]["baseline_strength"]["status"] == "UNRESOLVED"
    assert draft["evidence_requests"]["source_lineage"]["status"] == "UNRESOLVED"
    assert "Full AT-Mem" in [row["clean_cells"][1] for row in draft["tables"][0]["rows"]]


def test_human_approval_materializes_evidence_then_unchanged_engine_can_advance(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    output_dir = tmp_path / "generated"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(
        source,
        output=draft_path,
        source_uri="https://example.invalid/source",
        source_revision="deadbeef",
    )
    approval_path.write_text(json.dumps(_approval(draft), indent=2) + "\n", encoding="utf-8")

    receipt = materialize_approved_markdown_claim(draft_path, approval_path, output_dir=output_dir)
    evidence = json.loads((output_dir / "evidence.json").read_text(encoding="utf-8"))
    verdict = autopsy_claim(output_dir / "autopsy.toml")

    assert receipt["authority_status"] == "READY_FOR_UNCHANGED_AUTOPSY_ENGINE"
    assert evidence["evidence_class"] == "HUMAN_APPROVED_MARKDOWN_EXTRACTION"
    assert evidence["comparison"]["metrics"]["r2r_sr"]["improvement"] == pytest.approx(4.3)
    assert evidence["comparison"]["metrics"]["rxr_sr"]["improvement"] == pytest.approx(4.6)
    assert evidence["controls"]["source_phrases_verified"] is True
    assert verdict["outcome"] == "ADVANCE"
    assert verdict["credit_disposition"] == "PROVISIONAL"
    assert verdict["boundary"]["prospective_credit"] is False


def test_human_approved_source_fact_can_override_raw_advance_with_generic_negative_signal(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    output_dir = tmp_path / "generated"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(source, output=draft_path, source_revision="deadbeef")
    approval = _approval(draft)
    approval["approved_facts"] = [
        {
            "name": "baseline_is_floor",
            "value": True,
            "source_phrase": "The baseline is a floor, not a meaningful semantic comparison.",
        },
        {
            "name": "baseline_is_meaningful_semantic_comparison",
            "value": False,
            "source_phrase": "The baseline is a floor, not a meaningful semantic comparison.",
        },
    ]
    approval["signals"] = [
        {
            "id": "weak-baseline",
            "kind": "strong_baseline_missing",
            "mode": "all",
            "predicates": [
                {"fact": "baseline_is_floor", "equals": True},
                {"fact": "baseline_is_meaningful_semantic_comparison", "equals": False},
            ],
        }
    ]
    approval["claim_if_not_advance"] = "score lead survives, but requested superiority credit is withheld because the approved source calls the comparator a floor"
    approval_path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")

    receipt = materialize_approved_markdown_claim(draft_path, approval_path, output_dir=output_dir)
    evidence = json.loads((output_dir / "evidence.json").read_text(encoding="utf-8"))
    verdict = autopsy_claim(output_dir / "autopsy.toml")

    assert receipt["approved_fact_count"] == 2
    assert receipt["approved_signal_count"] == 1
    assert evidence["facts"]["baseline_is_floor"]["source_phrase_verified"] is True
    assert "ADVANCE" in verdict["triggered_outcomes"]
    assert "STRONG_BASELINE_MISSING" in verdict["triggered_outcomes"]
    assert verdict["outcome"] == "STRONG_BASELINE_MISSING"
    assert verdict["credit_disposition"] == "WITHHELD"


def test_materialization_fails_without_explicit_approval(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(source, output=draft_path, source_revision="deadbeef")
    approval = _approval(draft)
    approval["approved"] = False
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ValueError, match="approved=true"):
        materialize_approved_markdown_claim(draft_path, approval_path, output_dir=tmp_path / "out")


def test_materialization_fails_if_human_approval_is_bound_to_wrong_source(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(source, output=draft_path, source_revision="deadbeef")
    approval = _approval(draft)
    approval["source_git_blob_sha1"] = "0" * 40
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ValueError, match="does not bind"):
        materialize_approved_markdown_claim(draft_path, approval_path, output_dir=tmp_path / "out")


def test_materialization_fails_if_approved_source_text_is_absent(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(source, output=draft_path, source_revision="deadbeef")
    approval = _approval(draft)
    approval["required_source_phrases"] = ["This sentence does not exist in the source."]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ValueError, match="approved source phrase missing"):
        materialize_approved_markdown_claim(draft_path, approval_path, output_dir=tmp_path / "out")


def test_materialization_fails_if_approved_fact_phrase_is_absent(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    draft_path = tmp_path / "draft.json"
    approval_path = tmp_path / "approval.json"
    source.write_text(MARKDOWN, encoding="utf-8")
    draft = scan_markdown(source, output=draft_path, source_revision="deadbeef")
    approval = _approval(draft)
    approval["approved_facts"] = [
        {"name": "made_up_fact", "value": True, "source_phrase": "This fact is not in the source."}
    ]
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ValueError, match="approved fact source phrase missing"):
        materialize_approved_markdown_claim(draft_path, approval_path, output_dir=tmp_path / "out")
