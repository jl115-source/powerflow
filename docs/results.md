# Tidy result contract (schema version 1)

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
`is_optimal_dispatch` is false. Curtailment, redispatch, unserved energy and contingency
severity are unavailable in this milestone and are not fabricated as zeros.
