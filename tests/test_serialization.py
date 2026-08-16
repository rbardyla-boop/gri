import json
from pathlib import Path

from gri_world0.generator import generate_sample
from gri_world0.schema import TaskFamily
from gri_world0.serialization import canonical_sample_line, read_jsonl, sample_semantic_id, write_jsonl


def test_sample_hash_is_stable_and_self_consistent():
    sample = generate_sample(seed=42, split="train", task_family=TaskFamily.COMPOSITION, chain_length=3)
    assert sample.sample_id == sample_semantic_id(sample)
    assert canonical_sample_line(sample) == canonical_sample_line(sample)


def test_round_trip_jsonl(tmp_path: Path):
    sample = generate_sample(seed=43, split="train", task_family=TaskFamily.COMPOSITION, chain_length=4)
    path = tmp_path / "x.jsonl"
    write_jsonl(path, [sample])
    loaded = read_jsonl(path)
    assert loaded == [sample]


def test_malformed_jsonl_fails_closed(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"bad":true}\n', encoding="utf-8")
    try:
        read_jsonl(path)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed artifact did not fail")
