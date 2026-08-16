from pathlib import Path

from gri_models.data import NUM_RELATIONS, load_examples

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_train_encodes_without_model_specific_answer_leak():
    examples = load_examples(ROOT / "artifacts/frozen/world0_v0_1/train.jsonl")
    assert len(examples) == 128
    ex = examples[0]
    assert ex.node_features.shape[1] == 3
    assert ex.edges.shape[-1] == NUM_RELATIONS == 8
    assert ex.node_features[ex.query_subject, 1] == 1
    assert ex.node_features[ex.query_object, 2] == 1
