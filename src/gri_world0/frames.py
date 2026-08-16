from __future__ import annotations

import hashlib

import numpy as np


def _derived_seed(sample_id: str, frame_seed: int, entity_id: int) -> int:
    payload = f"{sample_id}|{frame_seed}|{entity_id}|SO4".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def random_so4(sample_id: str, frame_seed: int, entity_id: int) -> np.ndarray:
    rng = np.random.default_rng(_derived_seed(sample_id, frame_seed, entity_id))
    matrix = rng.normal(size=(4, 4))
    q, r = np.linalg.qr(matrix)
    signs = np.sign(np.diag(r))
    signs[signs == 0] = 1
    q = q @ np.diag(signs)
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q.astype(np.float64)


def frames_for_entities(sample_id: str, frame_seed: int, entities: tuple[int, ...]) -> dict[int, np.ndarray]:
    return {entity: random_so4(sample_id, frame_seed, entity) for entity in entities}
