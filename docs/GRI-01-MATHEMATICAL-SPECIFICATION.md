# GRI-01 — Mathematical Specification

Status: PROVISIONAL

Let a directed graph be G=(V,E). At recurrent step t, node i has invariant semantic state s_i^t and geometric state V_i^t in R^(d_g x c_g).

The first geometric group is SO(4), deliberately independent of the later E8 hypothesis.

Each node has a local frame Q_i in SO(4). For canonical geometric state Z_i, local coordinates are V_i=Q_i Z_i.

For directed edge j->i, the base exact transport is

U_ij = Q_i Q_j^{-1}.

Under independent local frame changes G_i and G_j,

V_i' = G_i V_i,
U_ij' = G_i U_ij G_j^{-1}.

Therefore U_ij' V_j' = G_i U_ij V_j.

Messages may use invariant Gram quantities V_i^T V_i, V_j_to_i^T V_j_to_i, and V_i^T V_j_to_i. Geometric outputs are generated only as invariant scalar/channel coefficients multiplying equivariant vectors.

One learned transition F_theta is reused across all recurrent steps. Readout consumes invariant quantities only.

Dimensional memory, learned connection dynamics, curvature/holonomy, and E8 relation codebooks remain downstream ablations.
