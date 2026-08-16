from pathlib import Path

from gri_world0.serialization import canonical_sample_line, file_sha256, write_jsonl
from gri_world0.splits import build_bundle


def test_same_seed_produces_byte_identical_dataset(tmp_path: Path):
    a = build_bundle(seed=1337, count_per_depth=8, contradiction_count=8)
    b = build_bundle(seed=1337, count_per_depth=8, contradiction_count=8)
    assert [canonical_sample_line(s) for s in a.train] == [canonical_sample_line(s) for s in b.train]
    pa, pb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_jsonl(pa, a.train)
    write_jsonl(pb, b.train)
    assert pa.read_bytes() == pb.read_bytes()
    assert file_sha256(pa) == file_sha256(pb)


def test_different_seed_changes_dataset():
    a = build_bundle(seed=1337, count_per_depth=4, contradiction_count=4)
    b = build_bundle(seed=1338, count_per_depth=4, contradiction_count=4)
    assert [s.sample_id for s in a.train] != [s.sample_id for s in b.train]
