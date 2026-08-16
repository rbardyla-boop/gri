import numpy as np

from gri_world0.frames import frames_for_entities, random_so4
from gri_world0.generator import generate_sample
from gri_world0.schema import TaskFamily
from gri_world0.serialization import canonical_sample_line


def test_so4_is_orthogonal_and_proper():
    q = random_so4("abc", 1337, 17)
    assert np.allclose(q.T @ q, np.eye(4), atol=1e-12)
    assert np.isclose(np.linalg.det(q), 1.0, atol=1e-12)


def test_frame_generation_is_deterministic_and_seeded():
    a = random_so4("abc", 1337, 17)
    b = random_so4("abc", 1337, 17)
    c = random_so4("abc", 1338, 17)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_frame_seed_does_not_alter_semantic_sample():
    sample = generate_sample(seed=9, split="test", task_family=TaskFamily.LONG_CHAIN, chain_length=8)
    before = canonical_sample_line(sample)
    f1 = frames_for_entities(sample.sample_id, 1, sample.entities)
    f2 = frames_for_entities(sample.sample_id, 2, sample.entities)
    assert canonical_sample_line(sample) == before
    assert any(not np.array_equal(f1[k], f2[k]) for k in f1)
