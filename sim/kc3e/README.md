# KC-3E-D — Finite-Horizon Population Dynamics

KC-3E-D is a development-only characterization harness over frozen KC-3D.
It executes exactly four explicit `population_tick(population)` calls and
records complete population snapshots at `t0` through `t4`.

The harness compares single-packet chain positions, branching seeds,
non-colliding packets, same-slot competitors in both placements, empty and
dead-intermediate controls, observed fixed/repeated states, and serialization
restart at each boundary. Total work is bounded at 32 activations and 448
slot-contact attempts.

There is no reusable horizon runner or automatic execution mechanism. The only
allowed terminal results are `KC_3E_DEV_COMPLETE` and `KC_3E_DEV_INVALID`;
scientific thresholds and scientific verdicts remain forbidden.

