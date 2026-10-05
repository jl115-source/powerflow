# Baseline assumptions and units

- `pandapower==3.2.1`, `pandapower.networks.case30()`: 30 buses, 41 lines, five PV
  generators and one external-grid slack. No parameter normalization or repairs.
  Only cached result tables and stale convergence flags are cleared by the loader.
  This PYPOWER-derived economic-study variant differs from `case_ieee30`.
- Balanced, steady-state AC network. Constant P/Q demand; source shunts retain voltage
  dependence. No stochastic inputs, time evolution, outages, renewables or load shedding.
- Newton-Raphson, flat start, voltage angles enabled, 30 iterations, mismatch tolerance
  1e-8 MVA, single slack, connectivity checking, no numba acceleration. Input is deep-copied.
- The single slack balances active losses; PV generators hold active setpoints and regulate
  voltage through reactive output. Active bounds are not enforced. Q enforcement defaults
  off to expose source-case violations; enabling it is an explicit saved option. The slack's
  limits still require diagnostics. PF convergence is not operational feasibility.
- Thermal and voltage limits are source data, not imposed by the PF solver. Branch loading
  is max terminal current relative to `max_i_ka * df * parallel`, expressed in percent;
  compare against each source `max_loading_percent`, not an assumed universal threshold.
- P is MW, Q is MVAr, S is MVA, current is kA, voltage is per-unit (base `vn_kv`), angles
  are degrees relative to the slack. Branch powers enter the branch at each terminal.
  Generator P/Q are injections; load, shunt and bus-result P/Q use consumption convention.
- Active network loss includes branch loss plus active shunt consumption. Reactive branch
  absorption includes charging and can be negative; it is not a dissipative energy loss.
- Polynomial P/Q cost is evaluated at the solved dispatch including slack. Although
  pandapower names coefficient columns `eur`, no currency conversion is performed. Interpret
  as source cost units/hour, not modern euros. No startup, commitment or time weighting.
  Missing/duplicate/unsupported costs fail instead of silently returning a partial total.
- Diagnostic defaults: near voltage 0.005 pu, near branch loading 5 percentage points,
  near generator P/Q 1 MW / 1 MVAr. Classification tolerance is 1e-6 in the row's unit.
  Slack < -tolerance is violated; abs(slack) <= tolerance is at_limit; otherwise slack
  <= the near threshold is near_limit. These are proximity observations, not OPF duals.
- Extraction intentionally supports only the case30 device set. Other device classes
  raise before totals are calculated. Future transformer/storage/renewable work must add
  explicit schema and accounting tests. Ratings that are NaN/inf are labeled unrated.


## Milestone 2 study policy

`load_ieee30()` is the source benchmark. `build_study_case30(OPFPolicy(...))` produces
an independent network with all six generation sources explicitly controllable and all
loads explicitly fixed. Numerical generator P/Q limits, voltage bounds, ratings, shunts
and cost coefficients remain source values. Generator/slack voltage magnitudes can be
optimized within bus bounds; their raw-PF setpoints are not fixed OPF targets. Q-limit
constraints are part of AC OPF regardless of the PF `enforce_q_lims` diagnostic option.

`apply_scenario()` scales all demand P and Q together, preserves power factor, resets
solver state, and records name/factor. It rejects composition on an existing scenario.
The published first experiment uses factor 1.0; no load/generation adjustments repair
its raw baseline. Generator and network availability are not changed.

The native AC formulation is selected explicitly with `OPF_FLOW_LIM=2` (current).
A separate AC comparator uses `OPF_FLOW_LIM=0` (fixed apparent power). Both enforce
both terminal magnitudes; reporting always distinguishes physical current from MVA.
DC OPF uses lossless linear active-power balance and |P| <= RATE_A, with no Q or
voltage feasibility claim. Source case30 has no reactive costs; DC rejects such costs.

The paired thermal-relaxed study removes `max_loading_percent` only from the solver's
private copy (pandapower converts its absence to RATE_A=0, meaning unconstrained), then
restores source ratings for diagnostics. Every other policy and physical parameter is
identical. This retains network power balance, voltages and generator bounds; it is
not copper-plate dispatch. AC objective differences are between local solutions and
are not a global optimality certificate. Raw-PF to OPF cost change combines several
effects and must not be called a congestion premium.

PIPS tolerances: feasibility, gradient, complementarity, objective and OPF violation
1e-8; at most 150 iterations; AC OPF `init="flat"` uses pandapower's bound-based start
(this differs from flat-voltage AC PF initialization). No retry/fallback is attempted.
Post-check tolerance: 1e-5 in each physical result unit. In-service buses must have
finite solved states; P/Q totals and all enforced table bounds are independently checked.
A solver failure is not proof of physical infeasibility or unserved demand.

Pandapower 3.2.1 DC PF auto-detects numba even when its keyword is supplied; the
adapter records the resolved flag rather than claiming to override it. The locked
environment omits numba, so its informational speed warning is expected.
