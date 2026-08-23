# KC-1B-D — Single-Cell Retention Characterization

## Status

```text
KC-1B-D: COMPLETE
VERDICT: KC_1B_DEV_COMPLETE
SCIENTIFIC VERDICT: FORBIDDEN
THRESHOLD: UNDEFINED_IN_DEVELOPMENT
```

The characterization uses the frozen KC-1A source and KC-0 development bank.
It runs 36 rows: three packet conditions (`correct_packet`, `no_packet`, and
`wrong_packet`), two distractor sets (`standard` and `altered`), and six fixed
delays (`0, 1, 2, 4, 8, 16`). It records state differentiation, query
recoverability, specificity, raw state/readout values, full/value-only/
occupancy-only probes, and serialization interruption at a fixed delay split.

Replay and restart comparisons passed for every row. This does not establish
retention, learning, generalization, superiority, or any scientific result;
it only completes the development characterization harness.

## Anchors

```text
KC-1A source SHA-256:
2ec7c17fdfd384fd110367a74f912752bb7289a98829a0e64cf1453aef9c4173

KC-1B-D config SHA-256:
bf116743a8a568e41efbd3dc81d051affac5ddeceec989d0c1ff40d184705309

KC-0 bank SHA-256:
0eff453e68c0c38f9f85e040f42ad87b8de0c5ec03557ecba1dbc077135caef5

Characterization receipt file SHA-256:
45a45ef56da4b28107f8f010a9e1e8c6c79f3d1c802308b5576cba1c5febbb3e

The receipt also carries a separate `canonical_receipt_sha256` field; it is
not the hash of the serialized receipt file itself.
```

The next possible unit is a separately frozen blind retention qualification;
the KC-1A cell itself remains unchanged.
