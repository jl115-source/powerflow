# Milestone 2b.1 — Independent MATPOWER validation

This gate runs native MATPOWER 8.1 in a separate GNU Octave process and compares it
with pandapower 3.2.1/PYPOWER. These are separate MATLAB/Octave and Python executions,
with separate source cases and result extraction; they share algorithmic ancestry
(MIPS/PIPS). This is not a comparison of unrelated optimization algorithms or a
certificate of globally optimal AC dispatch.

## Five matched formulations

| Case | pandapower | MATPOWER | Comparison |
|---|---|---|---|
| AC PF | Newton-Raphson, flat, Q limits off | NR power mismatch/polar, native unity start, Q limits off | Strict V/angle/P/Q agreement |
| DC PF | rundcpp | rundcpf | Active quantities and angles; Q/V unavailable |
| AC-current OPF | OPF_FLOW_LIM=2 | opf.flow_lim='I', MIPS | Feasibility, current-limiting branch set, objective |
| AC-MVA OPF | OPF_FLOW_LIM=0 | opf.flow_lim='S', MIPS | Feasibility, MVA-limiting branch set, objective |
| DC OPF | rundcopp / PIPS | rundcopf / MIPS | Lossless active equations, bounds, limiting set, objective |

MATPOWER uses its legacy core explicitly (`exp.use_legacy_core=1`) to make solver
selection unambiguous. AC OPF uses bound-based interior initialization (`opf.start=1`),
matching the purpose of pandapower `init='flat'`; numerical iterates need not coincide.
All PF tolerances are 1e-8, max 30 iterations; OPF feasibility/gradient/complementarity/
objective tolerances are 1e-8, max 150. Solver options are exported, not inferred from
library defaults. Both systems use bus 1 as angle reference; no fitted angle offset
or output rescaling is applied. No retries, warm-start tuning or source repairs are used.

## Input parity is required before result comparison

MATPOWER loads its own `case30.m`. Pandapower's source and explicit study policy retain
all physical numbers. An OPF-mode conversion exposes P/Q/voltage limits for auditing;
it is **not** fed into MATPOWER. Source bus names map converter IDs to original bus
numbers, generators map by their unique source bus, and branches map by oriented
original endpoints. Duplicate or missing identities fail; parallel-circuit generalization
is intentionally outside this case30 gate. Tables can be reordered without changing results.

System base MVA, P/Q loads, shunts, R/X/charging, RATE_A, statuses, P/Q/voltage bounds,
angle limits, nonslack active setpoints, generator voltage setpoints and cost coefficients
must agree within 1e-9. The converter's 1e-10 bound expansion is visible in the audit.
Unity tap encodings 0 and 1 are normalized only for semantic comparison. The source
network and the actual MATPOWER case are never modified by this audit.

Documented exceptions appear as rows, not suppressed differences:
- Area/zone annotations: not used by these five formulations.
- Generator mBase: unused nameplate annotation; equations use common system baseMVA.
- Initial slack Pg: not retained as a setpoint by pandapower; PF solves it, and OPF
  ignores initial dispatch in favor of an interior starting point.
- RATE_B/C: unused emergency ratings; all operative RATE_A values must match.

## Feasibility first

A NumPy checker reconstructs each pi-branch's terminal powers from V/angle and original
R/X/B/tap data, then checks nodal P/Q balances including source shunts. It uses neither
pandapower nor MATPOWER equation-building routines. DC checks reconstruct the lossless
angle-flow equations and active nodal balance. Generator P/Q, bus-voltage, branch-angle and both
terminal thermal bounds are checked for OPF. PF limit violations remain observations:
the raw case is known to overload branch 6–8, so convergence is not feasibility.

For AC-current limits, utilization is max(|S_from|/V_from_pu, |S_to|/V_to_pu)/RATE_A.
For fixed MVA it is max(|S_from|, |S_to|)/RATE_A; for DC it is max(|P_from|, |P_to|)/RATE_A.
Multiply by 100 for percent. This handles MATPOWER current limits expressed as MVA
at nominal voltage. Loading at or above 99.99% is flagged as limiting (including overloads in PF
observations); feasible OPF results must also satisfy the upper bound. OPF requires the same limiting set for each matched formulation, including an
empty set for uncongested DC. A set mismatch requests review rather than inventing parity.

Both objectives are independently recomputed from the native cost curves. Only after
feasibility passes does the gate evaluate objective agreement. AC dispatch or reactive
support differences are reported, not forced to PF equality: different local solutions
are possible. Material objective differences (beyond 1e-4 absolute plus 1e-5 relative)
request review and block the automatic gate; they are not declared solver invalidity.

## Discrepancies and acceptance

All quantities have row-level and maximum absolute/relative discrepancies. Relative
error is |pandapower − MATPOWER| / max(|MATPOWER|, 1e-8), with the floor in each quantity's
unit. It is diagnostic only; near-zero values can have large relative errors. The CSV
reports the largest relative discrepancy separately from the largest absolute one.

Active branch losses and reactive branch absorption are both compared (the latter is
unavailable for DC). In case30 the active shunts consume zero MW, so active branch
loss equals total active network loss.

Strict PF acceptance: 1e-6 pu voltage, 1e-4 degrees angle, 1e-4 MW/MVAr flows, dispatch
and losses. PF evaluated cost uses 1e-4 source units/hour. Independent nodal/terminal
checks use 1e-4 MW/MVAr, enforced bound residuals 1e-5 in the row's physical unit.
DC voltage magnitudes, Q and apparent/current magnitudes are unavailable, never zeros.
No pointwise OPF dispatch-equality threshold is imposed; every difference is retained.

See [measured results](matpower-validation-results.md), [run instructions](../experiments/validation/README.md) and the CI artifact for the
executed results. Unit tests use synthetic fixtures and are not independent evidence.

## Reproducibility and scope

The official release zip is pinned to SHA-256
`7f13b1441669a64e312d14a60e564cd91977ff1676ff77d25538e94ff313dd56`.
Extracted files are individually hashed and checked before execution. Manifests record
runtime versions, code revision/hashes, options, raw outputs and artifact hashes.
The process is bounded by a timeout; no Python substitute is accepted if Octave is absent.

The remaining Milestone 2b sequence is validation → load/location stress sweeps →
critical-branch P/Q/V/I decomposition → nodal marginal prices. Milestone 3 remains
N-1/security analysis. None of those later features are implemented in this PR.

Primary references: [MATPOWER 8.1 release](https://github.com/MATPOWER/matpower/releases/tag/8.1),
[mpoption](https://matpower.org/documentation/ref-manual/legacy/functions/mpoption.html),
[native case30](https://github.com/MATPOWER/matpower/blob/8.1/data/case30.m).
