# Economic dispatch and congestion

Run `gridstress-congestion --config experiments/congestion/config.toml --output outputs/congestion`.
The default uses the original demand with explicit source-bound generator dispatch policy.

Seven cases: raw AC PF, raw DC PF, current-constrained AC OPF, thermal-relaxed AC OPF,
MVA-constrained AC OPF, constrained DC OPF, and thermal-relaxed DC OPF.

Inspect `comparison.csv`, `redispatch.csv`, `thermal_constraint_cost.csv`, each run's
`tables/constraints.csv`, and the three figures. `manifest.json` marks successful completion;
`failure.json` records an aborted solve, with no feasibility or load-shedding inference.
The experiment never overwrites a directory. Inputs, policies, settings and hashes are saved.

For later demand stress, copy the TOML and change the scenario name and demand_scale.
P/Q scale together; a failed OPF is surfaced, never hidden. The first study's result and
methodological cautions are in [docs/congestion.md](../../docs/congestion.md).
