# KC-3F-D — Scheduler Counterfactual

KC-3F-D is a development-only counterfactual harness beside frozen KC-3D.
It keeps the same four-tick horizon, initial populations, KC-3C activation,
restart checks, and resource bounds while comparing four fixed start-of-tick
orders: ascending, descending, even/odd, and odd/even numeric cell IDs.

The harness records complete trajectories for chain, branching, multi-packet,
same-slot, empty, and dead-intermediate scenarios. The canonical ascending
condition must reproduce frozen KC-3D. Other orders are counterfactual
observations, not adaptive policies. No random source, fitness, selection,
learning, spawning, background execution, or scientific verdict is present.

