# LCB Failure Map v0 — 2026-08-23

## Status

```text
TRACK:                       LCB / flux-maintained attractor memory
PURPOSE:                     FAILURE DISCOVERY, NOT CLAIM RESCUE
ORIGINAL LCB PRIMITIVE:      NOT ESTABLISHED
PARAMETRON CONTROL:          OPERATIONAL PASS / PRIOR ART
THERMODYNAMIC ADVANTAGE:     NOT ESTABLISHED
NEW BREAKTHROUGH:            NONE
```

This unit attacks the surviving LCB/flux-maintained-memory idea using the recovered positive-control model rather than trying to preserve the February 2026 paper's ontology.

The recovered package already retired the original repressilator memory demonstration, thermodynamic crossover, and Ghost Key as an LCB. This unit asks what additional failures can be extracted from the parametron control itself.

## F1 — Noise/hold failure follows ordinary barrier escape

The recovered positive control uses the zero-detuning degenerate-parametric-oscillator normal form

```text
dz/dt = -gamma*z + pump*conj(z) - g*|z|^2*z + h(t) + noise
```

At the canonical point `gamma=1`, `pump=1.4`, `g=1`, the rotating-frame x-axis dynamics reduce to

```text
dx/dt = mu*x - g*x^3 + h(t),  mu = pump-gamma = 0.4
```

with minima at `x=+-sqrt(mu/g)` and a barrier of `Delta U = mu^2/(4g) = 0.04`.

Monte Carlo retention loss matches the ordinary overdamped Kramers escape estimate

```text
k ~= mu/(sqrt(2)*pi) * exp(-Delta U / D),   D=sigma^2/2
```

closely:

| sigma | DeltaU/D | empirical k | Kramers k | empirical/predicted |
|---:|---:|---:|---:|---:|
| 0.10 | 8.000 | 2.39122e-05 | 3.02022e-05 | 0.792 |
| 0.12 | 5.556 | 0.000332411 | 0.000348055 | 0.955 |
| 0.15 | 3.556 | 0.00261085 | 0.0025718 | 1.015 |
| 0.18 | 2.469 | 0.00748954 | 0.0076219 | 0.983 |

At `sigma=0.15`, canonical 80-time-unit retention falls below 0.90 (observed about 0.84). At `sigma=0.18`, 20-time-unit retention is already below 0.90. This is a normal noise/barrier/retention frontier, not evidence of a new persistence law.

**Failure knowledge:** the parametron's robustness is largely explainable by conventional bistable barrier crossing in rotating coordinates.

## F2 — The Energy Withdrawal Test is not sufficient

A powered *static* bistable latch was simulated as

```text
power ON:  dx = (mu*x - g*x^3 + h)dt + sigma dW
power OFF: dx = (-gamma_off*x - g*x^3)dt + sigma dW
```

It has two fixed-point attractors under one powered operating point, accepts finite write pulses, self-restores after bounded perturbations, retains a state while powered, and loses the state after power removal.

Its canonical noise sweep is nearly the same as the parametron control. For example:

```text
sigma=0.12  latch accuracy ~0.979
sigma=0.15  latch accuracy ~0.851
sigma=0.18  latch accuracy ~0.670
```

After power removal, the absolute state amplitude falls below 0.2 for all simulated trials by about two model time units.

**Failure knowledge:** `power withdrawal erases state` is not sufficient to distinguish an LCB-specific primitive from ordinary volatile active memory. Intrinsic attractor recovery is also not unique; stable fixed-point latches possess it.

## F3 — "flow versus stasis" is frame-dependent for the parametron

The two parametron states are oscillations separated by pi in the laboratory signal, but in the rotating-frame variables used by the positive-control model they are fixed points

```text
z = +sqrt(mu/g)
z = -sqrt(mu/g)
```

with `dz/dt=0` at the stored states.

The same stored bit can therefore be described as a periodic lab-frame trajectory or a static rotating-frame fixed point.

**Failure knowledge:** `dx/dt != 0` versus `dx/dt = 0` is not by itself a coordinate/frame-invariant ontology for this driven control. This does not invalidate parametron memory; it invalidates using motion alone as the distinguishing informational primitive.

## F4 — Symmetry bias destroys one logical state

For the canonical double-well normal form, a constant bias tilts the landscape. The analytic saddle-node threshold is

```text
|b_crit| = 2*mu^(3/2)/(3*sqrt(3g)) ~= 0.09737
```

The stochastic sweep agrees: near `|bias|=0.10`, one directional write collapses to only a few percent success while the favored state remains effectively perfect.

**Failure knowledge:** the two-state memory requires tight control of symmetry-breaking bias; robustness must include bias/mismatch, not just additive noise.

## F5 — Write performance is an impulse/time tradeoff

At canonical pump and low noise, short weak pulses fail even though long pulses of the same sign succeed. Examples from the sweep:

```text
0.10 time x 0.40 force -> ~0.90 accuracy
0.10 time x 0.60 force -> ~0.97 accuracy
0.25 time x 0.20 force -> ~0.93 accuracy
0.50 time x 0.20 force -> ~1.00 accuracy
```

The smallest sampled pulse impulse producing >=0.95 mean directional accuracy was `0.06` (`0.1 x 0.6`), but impulse alone is not a complete write-cost metric because waveform and dynamics matter.

**Failure knowledge:** a fair benchmark needs an explicit write protocol and physical work accounting; merely demonstrating switchability is inadequate.

## F6 — Drive withdrawal has finite erase latency

The paper's prose used language implying immediate destruction after energy withdrawal. In the normal-form simulation, collapse is finite-rate:

```text
post-withdraw 0.0 -> mean amplitude ~0.632
0.5 -> ~0.341
1.0 -> ~0.199
2.0 -> ~0.073
```

With the chosen amplitude threshold 0.2, about half the trials remain above threshold at one time unit and none by two.

**Failure knowledge:** withdrawal should be measured as an erase-time distribution, not a binary instantaneous property.

## F7 — Nonequilibrium current alone does not buy memory

A controlled nonreversible Langevin experiment was added:

```text
U(x,y) = (x^2-1)^2/4 + y^2/2
dX = [-grad U + epsilon J grad U]dt + sqrt(2D)dW
```

where `J` is antisymmetric. For every `epsilon`, the stationary density remains exactly proportional to `exp(-U/D)`, but `epsilon>0` introduces a circulating probability current and positive entropy production.

At `D=0.10`, increasing irreversible circulation reduced finite-horizon retention:

| epsilon | no-flip survival | sign autocorr lag 10 | estimated EPR |
|---:|---:|---:|---:|
| 0.00 | 0.148 | 0.696 | 0.000 |
| 0.25 | 0.156 | 0.711 | 0.166 |
| 0.50 | 0.139 | 0.638 | 0.658 |
| 1.00 | 0.104 | 0.544 | 2.646 |
| 2.00 | 0.027 | 0.402 | 10.854 |
| 3.00 | 0.010 | 0.267 | 24.942 |
| 4.00 | 0.004 | 0.144 | 46.372 |

Deterministic perturbation-basin tests also show strong circulation can shrink the region around the + state that returns to the original memory. For perturbations sampled in a radius-1.5 disk around the + minimum, return probability falls from about 0.905 at `epsilon=0` to about 0.558 at `epsilon=4`.

**Failure knowledge:** positive entropy production / irreversible current is not sufficient for robust memory. Dissipation can increase state mixing and degrade retention. A successor must identify what *specific non-equilibrium mechanism* provides an advantage.

## Revised kill criteria

A future candidate should not receive LCB-specific credit merely for being powered, oscillatory, bistable, self-restoring, or erased by power loss.

Before novelty or advantage is considered, require all of:

1. **Common operating point:** at least two readable states coexist without storing the bit in an external control parameter.
2. **Finite write / post-write hold:** temporary input selects state and is fully removed during hold.
3. **Matched volatile-latch baseline:** compare against an ordinary powered fixed-point bistable memory, not just nonvolatile static storage.
4. **Matched parametron baseline:** compare against phase-bistable oscillator prior art.
5. **Flow-essentiality test:** demonstrate a capability or performance property that disappears when the dynamical circulation/current is removed while the static state landscape is otherwise matched.
6. **Physical energy accounting:** use calibrated electrical power or thermodynamically valid transition rates; no oscillation speed or noise proxy may be called entropy production.
7. **Retention frontier:** report error probability as a function of hold time, noise, drive margin, and static bias/mismatch.
8. **Write/read/reset accounting:** physical work/energy and latency for all operations.
9. **No hidden digital correction:** recovery must be native to the candidate substrate.
10. **Prior-art null:** failure to outperform or distinguish from parametrons, volatile latches, birhythmic oscillator memory, and reservoir/oscillator computing kills the new-primitive claim.

## New candidate question

The surviving research question is now:

> Can a physically realizable nonequilibrium memory demonstrate a measurable retention/recovery/write capability that depends essentially on irreversible dynamical flow and survives matched comparison with both a powered static latch and a parametron?

That is narrower than the February LCB claim, but it is experimentally meaningful.

## Nonclaims

This unit does not establish:

- a new computational primitive;
- a thermodynamic advantage;
- a biological or living ontology;
- a consciousness connection;
- a hardware implementation.

It records negative and narrowing evidence useful for designing the next test.
