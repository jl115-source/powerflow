# MATPOWER validation plan

Validation is planned, not yet performed. pandapower's internal PYPOWER-based solver is
not an independent MATPOWER validation.

1. Freeze the pandapower input JSON and versions. Select MATPOWER `case30`, not `case_ieee30`.
2. Compare base MVA, original bus labels/types, demands, shunts, generator limits/setpoints,
   branches, charging, tap ratios, statuses, ratings and polynomial costs before solving.
3. Build explicit keyed bus/generator/branch mapping tables; never compare by row number.
   Original bus names are retained; pandapower indices are zero-based. Match parallel
   branches by endpoints plus circuit identity when present.
4. Match AC solver tolerance, initialization, slack, angle reference and Q-limit policy.
5. Compare bus voltage magnitudes/angles, both terminal P/Q, generator injections and losses.
   Initial acceptance targets: 1e-6 pu, 1e-4 degrees and 1e-4 MW/MVAr, subject to review
   after parameter parity. Include P/Q balance and separate absolute/relative errors.
6. Compare terminal MVA to MATPOWER RATE_A separately from pandapower current loading.
   At non-unit voltage these feasibility definitions differ. Do not compare percentages
   blindly. MATPOWER zero RATE_A means unconstrained, not zero capacity.
7. For OPF, align objective and feasibility conventions; compare cost, dispatch and residuals.
   An AC OPF can have local optima; document solver/version and compare feasibility first.

The result adapter is the only translation boundary for table schemas. Metrics and plots
consume pandas tables so a future MATPOWER adapter can produce the same contract.
