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
6. For like-for-like AC current limits, select MATPOWER `opf.flow_lim='I'` and
   pandapower `OPF_FLOW_LIM=2`. MATPOWER interprets RATE_A as current expressed in MVA
   at 1 pu voltage: match RATE_A/baseMVA and both terminal current bases. The case30
   equal nominal line-terminal voltage bases are checked by the adapter. Compare
   both terminal currents plus constraint residuals, not just reported percentages.
   Separately compare fixed-MVA `opf.flow_lim='S'` against `OPF_FLOW_LIM=0`.
   DC OPF uses |P| <= RATE_A. Zero RATE_A means unconstrained, not zero capacity.
7. For OPF, align objective and feasibility conventions; compare cost, dispatch and residuals.
   An AC OPF can have local optima; document solver/version and compare feasibility first.

The result adapter is the only translation boundary for table schemas. Metrics and plots
consume pandas tables so a future MATPOWER adapter can produce the same contract.

Reference: [MATPOWER mpoption](https://matpower.org/documentation/ref-manual/legacy/functions/mpoption.html).
In installed pandapower 3.2.1, `optimal_powerflow.py` defaults OPF_FLOW_LIM to 2;
`pypower/opf_consfcn.py` evaluates squared terminal-current bounds for mode 2 and
squared terminal-MVA bounds for mode 0. `build_branch.py` converts line ratings to
RATE_A using sqrt(3) × nominal kV × allowable kA. The adapter passes modes explicitly.
No external MATPOWER execution or cross-backend validation is claimed in this milestone.
