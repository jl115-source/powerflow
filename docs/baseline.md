# Baseline findings

Reference run: pandapower 3.2.1, default configuration, AC Newton-Raphson.
These values are regression evidence, not independent MATPOWER validation.

| Metric | Value |
|---|---:|
| Demand | 189.200000 MW |
| Generation including slack | 191.643803 MW |
| Active network loss | 2.443803 MW |
| Minimum bus voltage | 0.960624 pu |
| Maximum branch current loading | 111.831406% |
| Evaluated dispatch cost | 593.452242 source cost units/hour |
| Absolute active balance residual | < 1e-6 MW |
| Absolute reactive balance residual | < 1e-6 MVAr |

The unchanged operating point converges but has a thermal overload on line 9
(pandapower buses 5–7, source bus labels 6–8). See `constraints.csv` for all
violations and proximity classifications, including generator reactive limits.
Do not silently repair the original network to eliminate baseline violations.

The tests also identified a stale `converged=True` flag in the bundled case JSON
with empty result tables. The loader explicitly clears solver results/flags while
preserving every source parameter table. A fresh solve is always required.

Before congestion experiments, agree on the case variant, current versus MVA ratings,
load scaling/power factor, generator flexibility/Q enforcement and OPF cost conventions.
