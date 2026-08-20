# RRI-02P — Immutable Relation Anchor Preregistration

Status: **CAPACITY MATCH UNRESOLVED; NO TRAINING AUTHORIZED**

## Frozen baseline

The reference model is the GRI-05/RRI-01 recurrent baseline at hidden width
49 and message width 51, with 30,912 trainable parameters. Its update is:

```text
context = concat(h, aggregated_messages)
gate    = gate(context)
delta   = delta(context)
h_next  = LayerNorm(h + gate * delta)
```

## Candidate repair

The sole preregistered candidate would preserve `a = h0` for the current
example and expose it to both learned update networks:

```text
context = concat(h, a, aggregated_messages)
gate    = gate(context)
delta   = delta(context)
h_next  = LayerNorm(h + gate * delta)
```

The anchor would never be updated and would not enter the final readout. No
second processing stack, auxiliary loss, attention, or persistent memory is
allowed.

## Capacity result

For hidden width `H`, message width `M`, and eight relation channels, the
baseline parameter equation is:

```text
P_base(H,M) = 9H^2 + 19H + (3H + 17)M + 8
```

Adding the immutable anchor to both gate and delta contexts adds `2H^2`:

```text
P_anchor(H,M) = 11H^2 + 19H + (3H + 17)M + 8
```

The exhaustive positive-width search found zero solutions to
`P_anchor(H,M) = 30,912` in `H=1..100`, `M=1..1000`. Since positive `M`
already bounds useful `H` below 54, this covers the natural width domain.

No width was selected, no implementation was created, and no performance
experiment is authorized.

## Conditional protocol and gates

If a future authorized amendment supplies a legitimate exact match, the
frozen protocol would be 80 epochs, recurrent training depth 4, batch size 16,
AdamW (`3e-3`, weight decay `1e-4`), gradient clip `1.0`, CPU/one Torch thread,
and seeds 1337–1341. The primary metric would remain
`mean(D8,D16,D32,D64)`.

Advancement would require mean train and IID accuracy at least `.95`, primary
improvement at least `.05`, mean D64 improvement at least `.10`, and paired
primary wins on at least 4/5 seeds. If those pass, the unchanged RRI-01
archaeology would additionally require mean CTI reduction of at least 20% and
lower CTI in at least 4/5 paired seeds.
