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
