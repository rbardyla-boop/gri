# SRI-1A-α.4.1 Recruitment Authorization Toolchain

This package is a fail-closed verifier. It never resolves human operational
fields and never treats the α.4 package identity as an α.2 parser or export
schema hash. `TRUST_ANCHORS.json` is independent of the operational config;
the production validator loads it relative to its own source. Run:

```sh
python3 validate_authorization.py --package ../SRI-1A-alpha.4_LIVE_PILOT_AUTHORIZATION_v0.1.0.zip
```

The command emits `SRI_ALPHA4_BLOCKERS.json` and exits 2 unless every
authoritative binding, invariant, and zero-human replay is verified. Parent
integrity, scientific invariants, replay, and ethics have distinct fail-closed
codes 3–6. Test fixtures are marked `NON-AUTHORITY`; they cannot create a
production receipt. `--test-mode` is the only path that may report a synthetic
success, and it prints `SRI_ALPHA4_TEST_VALIDATION_PASS`.
