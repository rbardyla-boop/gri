The adversarial matrix is executable in `test_toolchain.py`: arbitrary
non-SHA text, self-consistent fake authority, missing/wrong parser or schema,
changed stimulus/scoring/randomization, unresolved REB/target/compensation,
consent placeholders, mutated ingestion, fake boolean replay/invariant claims,
and non-authority fixtures all fail closed. The live package test verifies the
untouched current package remains locked and skips cleanly when the external
parent is absent from a standalone archive.
