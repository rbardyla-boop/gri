# KC-1A — Isolated Knowledge Cell

## Status

```text
KC-1A LIFECYCLE: PASS
VERDICT: KC_1A_LIFECYCLE_PASS
SCIENTIFIC VERDICT: FORBIDDEN
```

KC-1A is a deterministic lifecycle candidate only. It has eight integer value
slots and eight occupancy bits, no step counter, no history buffer, no RNG,
and no population or replication logic.

The lifecycle gate checks cold start, deterministic stepping, canonical
serialization/restoration, restart at every active-token boundary, static
source containment/accounting, and mounting all 24 KC-0 sequences. It does
not test knowledge retention, learning, generalization, superiority,
replication, or population behavior.

## Anchors

```text
candidate source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

candidate manifest SHA-256:
157b7a4629bfa82720e95185cf5fcbbccadcc5e78f6416a1bb70b8f255d8ec51

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

lifecycle receipt SHA-256:
34cd1bdf709ede024607f981954957a9b17ec40b77b674368b78e0144797e01b
```

The next question, if separately authorized, is single-cell knowledge
retention. No replication or population engine is authorized by KC-1A.
