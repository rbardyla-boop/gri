from __future__ import annotations

from experiments.wildflower_dual_authority_0_3 import store as frozen_store


def test_frozen_epistemic_consumer_remains_available_without_reimplementation() -> None:
    assert hasattr(frozen_store, "ReferenceProvenanceStore")
    assert hasattr(frozen_store, "IncrementalProvenanceStore")
    reference = frozen_store.ReferenceProvenanceStore()
    packet = frozen_store.Packet(
        1,
        frozen_store.ACT_OBSERVE,
        1,
        frozen_store.REL_X,
        0,
        1,
    )
    reference.observe(packet)
    assert reference.status(1, 1) == frozen_store.STATUS_COMMITTED
