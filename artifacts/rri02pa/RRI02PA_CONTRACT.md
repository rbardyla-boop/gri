# RRI-02P-A — Parameter-Neutral Immutable Relation Anchor

Status: **PREREGISTERED; STRUCTURAL CHECKS ONLY; NO TRAINING AUTHORIZED**

## Claim under test

On WORLD-0, an immutable per-example relation anchor can improve long-depth
generalization over the frozen recurrent baseline when both models have
exactly 30,912 trainable parameters and are trained under the same frozen
protocol. This amendment tests one repair only: an immutable anchor, with no
new learned parameters.

## Frozen baseline

The reference model is the recurrent baseline at hidden width `H=49` and
message width `M=51`. Its update is:

```text
context = concat(h, aggregated_messages)
gate    = gate(context)
delta   = delta(context)
h_next  = LayerNorm(h + gate * delta)
```

Its readout receives only the mutable final state features
`[a, b, a-b, a*b]`.

## Sole candidate repair

For each current example, create a write-protected copy `a = h0`. At every
recurrent step, use the frozen interpolation:

```text
h_anchor = (h + a) / 2
context  = concat(h_anchor, aggregated_messages)
gate     = gate(context)
delta    = delta(context)
h_next   = LayerNorm(h + gate * delta)
```

The factor `1/2` is fixed. At step zero, `h=a=h0`, so the first recurrent
update must match the baseline exactly under identical weights and inputs.
The anchor is never updated, is not a trainable parameter, and is not passed
to the readout. No lambda sweep, learned coefficient, auxiliary loss,
attention, adaptive halting, persistent cross-example memory, or width change
is authorized.

## Capacity and implementation identity

The candidate inherits the baseline module topology and parameter shapes.
Therefore both models must have exactly 30,912 trainable parameters, with no
dummy, frozen, disconnected, or compensating parameters. The structural test
also requires identical state dictionaries under a paired non-evidence seed.

## Structural gates before evidence

All must pass before any evidence seed is run:

1. Exact trainable parameter equality: `30,912` vs `30,912`.
2. Paired initialization identity: identical state-dict keys and tensor values
   under the structural seed.
3. First-step identity: exact first recurrent state and one-step logits under
   identical weights and inputs.
4. Anchor immutability: the anchor remains byte-identical through depths
   `1,2,4,8,16,32,64,128`, with no aliasing or in-place mutation.
5. Readout firewall: the readout consumes mutable state only.

## Frozen future evidence protocol

Only after the structural gates pass: 80 epochs, training depth 4, batch size
16, AdamW with learning rate `3e-3`, weight decay `1e-4`, gradient clipping
`1.0`, CPU, one Torch thread, and deterministic seeds 1337–1341. Evaluate
`D5,D8,D16,D32,D64`; the primary metric is:

```text
P = mean(D8, D16, D32, D64)
```

The paired baseline is rerun unchanged in the same environment. No tuning is
permitted between runs.

## Advancement gates

The candidate advances only if every gate passes:

- mean train accuracy at least `.95`;
- mean IID validation accuracy at least `.95`;
- `P_anchor - P_baseline >= .05`;
- mean `D64_anchor - D64_baseline >= .10`;
- `P_anchor > P_baseline` on at least 4/5 paired seeds; ties are not wins.

If and only if those gates pass, rerun unchanged RRI-01 archaeology and apply
the CTI gate: mean CTI reduction at least 20% and lower CTI on at least 4/5
paired seeds. SEP remains diagnostic only and is not optimized.

## Stop rule

This preregistration stops after structural validation. No training,
performance evidence, or RRI-01 rerun is included in this commit.
