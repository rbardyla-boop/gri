# LCB Prior-Art Collision — 2026-08-23

## Terminal purpose

This record asks which surviving LCB claims are already occupied by established work. It is a kill gate for novelty, not a literature section designed to make the project look connected to known research.

## Collision 1 — nonequilibrium electronic memory reliability

Freitas, Proesmans, and Esposito, *Physical Review E* 105, 034107 (2022), **Reliability and entropy production in nonequilibrium electronic memories**, studies a realistic low-power MOS SRAM model in which logical values are metastable nonequilibrium states. It derives a bistable quasipotential and an explicit relation/bound for the memory error rate in connection with entropy production, validated by stochastic simulation.

DOI: https://doi.org/10.1103/PhysRevE.105.034107

Therefore the following is **not** available as an LCB novelty claim:

> nonequilibrium dissipation can support bistable memory whose reliability is related to entropy production.

That territory is already explicit in the literature.

## Collision 2 — general nonequilibrium cost of accurate storage

Chiribella, Meng, Renner et al., *Nature Communications* 13, 7155 (2022), **The nonequilibrium cost of accurate information processing**, derives general accuracy-versus-nonequilibrium-resource limits for storing, transmitting, cloning, and erasing information.

DOI: https://doi.org/10.1038/s41467-022-34541-w

Therefore a generic statement such as

> persistence/accuracy trades against nonequilibrium resources

is not a new LCB principle.

## Collision 3 — thermodynamically explicit bistable chemistry

Vellela and Qian, *Journal of the Royal Society Interface* 6, 925–940 (2009), **Stochastic dynamics and non-equilibrium thermodynamics of a bistable chemical system: the Schlögl model revisited**, treats the Schlögl reaction network as a canonical open, bistable chemical system. It explicitly analyzes flux, chemical potential, entropy production, stochastic switching, and the separation between fast intrabasin relaxation and slow interbasin switching.

DOI: https://doi.org/10.1098/rsif.2008.0476

Nguyen and Seifert, *Physical Review E* 102, 022101 (2020), further study entropy-current fluctuations at the bistable first-order transition in chemical reaction networks using the Schlögl model, relating the exponential prefactor to the effective barrier between fixed points.

DOI: https://doi.org/10.1103/PhysRevE.102.022101

Remlein and Seifert, *Journal of Chemical Physics* 160, 134103 (2024), study nonequilibrium flux and entropy-production fluctuations in the Schlögl model at criticality.

DOI: https://doi.org/10.1063/5.0203659

Therefore the following is not novel:

> a chemically fueled nonequilibrium system can maintain two metastable information-bearing states with stochastic switching and a defined entropy-production rate.

## Collision 4 — thermodynamics of chemical reaction networks is mature enough to police our accounting

Schmiedl and Seifert, *Journal of Chemical Physics* 126, 044101 (2007), define trajectory-level energy, work, heat, and entropy production for stochastic chemical reaction networks.

DOI: https://doi.org/10.1063/1.2428297

Rao and Esposito, *Physical Review X* 6, 041064 (2016), develop a rigorous thermodynamic framework for open chemical reaction networks with chemostats and separate steady-state dissipation from transient relaxation/driving contributions.

DOI: https://doi.org/10.1103/PhysRevX.6.041064

This reinforces the recovery audit's rejection of proxies such as oscillation speed or noise amplitude being labelled entropy production without a thermodynamically specified model.

## Collision 5 — multiple stable dynamical attractors / birhythmicity

Birhythmic systems explicitly contain two stable limit cycles, often with different amplitudes and frequencies, separated by an unstable cycle. Such systems are established in nonlinear dynamics and have been studied in biochemical, biological, electrical, and electromechanical settings. Contemporary work still studies stochastic switching between the two stable cycles.

Representative sources:

- Zhang et al., *Chaos* 34, 123105 (2024), **Most probable trajectories of a birhythmic oscillator under random perturbations**, describing two stable limit cycles separated by an unstable cycle and noise-induced escape between them. DOI: https://doi.org/10.1063/5.0229131
- García López, *Chaos, Solitons & Fractals* 170, 113412 (2023), reports multistable domains with two well-resolved coexisting stable limit cycles. DOI: https://doi.org/10.1016/j.chaos.2023.113412
- Birhythmic analog circuits have also been physically implemented as testbeds, so two persistent oscillatory attractors are not merely an abstract possibility.

Therefore the following is not enough for novelty:

> use two different stable limit cycles as two logical states.

## Collision 6 — parametric oscillator storage is old prior art

The recovered positive control is intentionally a parametron / degenerate parametric oscillator. Phase-bistable parametric oscillators have long been used as state-storage and switching systems. The recovery package already classifies this control as PASS / PRIOR ART.

Thus 0/pi phase memory under a sustaining pump is a null, not a candidate breakthrough.

## Surviving novelty space

After these collisions, the project cannot defensibly claim novelty from any of the following alone:

```text
powered memory
nonequilibrium memory
flux-erased memory
metastable nonequilibrium states
entropy-production / reliability trade-offs
two fixed-point attractors
two phase states
two stable limit cycles
intrinsic attractor relaxation
noise-induced switching
chemical bistability
```

The only scientifically interesting opening we currently see is narrower:

> **Does an explicitly irreversible dynamical flow produce a measurable memory capability or a matched cost/robustness advantage that cannot be reproduced by changing the static quasipotential/barrier, an ordinary powered bistable latch, a Schlögl-type active chemical latch, or a parametric/birhythmic oscillator control?**

This claim is **NOT ESTABLISHED**.

## Consequence for next experiments

The next candidate must pass a **Flow-Essentiality Test** rather than merely an Energy Withdrawal Test.

If removing the irreversible current while preserving the relevant stationary state landscape leaves the claimed capability intact, then the flow does not deserve mechanism credit.

If a static/quasipotential adjustment at matched power, error, latency, and write protocol can reproduce the result, the LCB-specific mechanism claim fails.

## Terminal novelty verdict

```text
GENERIC NONEQUILIBRIUM MEMORY:            PRIOR ART
ENTROPY-PRODUCTION / RELIABILITY LINK:    PRIOR ART
BISTABLE CHEMICAL NESS MEMORY:            PRIOR ART
PARAMETRON PHASE MEMORY:                  PRIOR ART
TWO STABLE LIMIT-CYCLE STATES:            PRIOR ART
FLOW-ESSENTIAL MEMORY ADVANTAGE:          OPEN / NOT ESTABLISHED
NEW COMPUTATIONAL PRIMITIVE:              NOT ESTABLISHED
```
