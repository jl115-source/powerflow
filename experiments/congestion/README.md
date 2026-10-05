# Planned: congestion and redispatch

Before implementation, agree on:
- case30 as the working IEEE-30 variant and current versus MVA branch constraints;
- load-stress locations/ranges, P/Q scaling and power-factor treatment;
- slack/Q-limit policy and whether to retain the infeasible original operating point;
- controllable resources, cost interpretation, AC/DC OPF and curtailment representation;
- MATPOWER version and comparison tolerances.

Store each perturbation explicitly and retain the original baseline for comparison.
