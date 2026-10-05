# Tidy result contract (schema version 2)

CSV files have no implicit row index. Physical units appear in column names. Element identity
is `(element_type, element_id)` and bus identity is `bus_id`; names are display metadata.
All tables correspond to one run, whose directory and manifest carry experiment identity.
Concatenating runs requires adding a run ID. The extractor does not trust positional joins.

| Table | Row granularity | Principal values |
|---|---|---|
| buses | bus | source name, nominal kV, status, voltage bounds, vm_pu, va_degree, net P/Q consumption |
| generators | ext_grid/gen element | bus, status, solved P/Q injections, source min/max P/Q |
| branches | line | from/to bus, status, current rating/derating/parallel count, terminal P/Q/S/current, loading, active loss, reactive absorption |
| loads | load | bus, status, actual P/Q consumption |
| shunts | shunt | bus, status, actual voltage-dependent P/Q consumption |
| summary | system | generation, demand, shunts, branch/network losses, P/Q balance residuals, evaluated cost |
| constraints | element + quantity + bound | value, limit, signed slack, unit, status |

Generation − load − shunt − branch absorption must be approximately zero for both P and Q.
`p_network_loss_mw` includes active shunt consumption; do not subtract shunts twice.
`is_optimal_dispatch` distinguishes PF from successful OPF (AC optimality is local).
`model`, `flow_limit`, `thermal_limits_enforced`, and `objective_cost_per_hour` identify
what was solved. The objective is null for PF. OPF checks cost against an independently
evaluated polynomial total, P/Q balance, and enforced constraint bounds.

Branch tables retain current, apparent-power and active-power loading separately:
`loading_percent`, `apparent_loading_percent`, `active_loading_percent`. All use the
source nominal rating basis; compare each to `max_loading_percent`. `rate_a_mva` is
sqrt(3) × nominal kV × max_i_ka × df × parallel × max_loading_percent / 100.
For the DC model that RATE_A number is used as an MW bound, not a solved MVA flow.

DC outputs leave voltage magnitudes, Q, terminal current and MVA blank/NaN; zero DC
loss is a model assumption, not an AC loss estimate. Diagnostics omit Q and voltage
and assess active loading. The AC-MVA solve assesses apparent loading, while current
loading remains separately available to show the formulation difference.

Thermal-relaxed outputs retain original source ratings for comparison; a source-bound
violation in those runs is not a violation of an enforced OPF constraint. Curtailment, redispatch, unserved energy and contingency
severity are unavailable in this milestone and are not fabricated as zeros.
