# MATPOWER validation results — Milestone 2b.1

**All five independent comparisons passed.** Evidence: [Octave validation run 37323760322](https://github.com/jl115-source/powerflow/actions/runs/37323760322),
validation implementation commit `5bb3d9a915ac0cea1cf954392b89355bea736fd6`, MATPOWER **8.1**,
GNU Octave **8.4.0**, Ubuntu 24.04, Python **3.11**. The downloadable `matpower-validation`
artifact includes native and converted input audits, raw Octave results, normalized
measurements, row-level differences, feasibility checks, branch utilization and hashes.
Later PR-head CI reruns the same gate; this table is a provenance-labelled evidence snapshot.

## Feasibility and limiting branches

All operative input-parity checks passed. Both implementations passed independently
reconstructed nodal balances, terminal-flow equations and OPF bounds before objectives
were compared. Raw PF's known overload remains an observation, not a PF validation failure.

| Matched OPF | Limiting branches in both implementations (original bus labels) |
|---|---|
| AC current | 6–8 |
| AC MVA | 6–8 and 25–27 |
| DC active flow | None |

The maximum objective discrepancy across OPF cases is **6.253e-12 source units/hour**.
The largest generator-dispatch discrepancy is **1.579e-8 MVAr** in AC-MVA OPF; active
dispatch differs by at most **8.795e-9 MW** there. These differences are far below the
reporting thresholds and consistent with floating-point / optimization termination
variation between implementations. There is no material economic or local-optimum
separation to explain in this case. This close match is plausible given shared
MIPS/PIPS ancestry; it is not evidence of globally optimal AC solutions.

## Maximum discrepancies

Absolute-error units follow the quantity names; cost is source units/hour. Relative
error uses MATPOWER as reference with a 1e-8 denominator floor, in that quantity's unit.
The maxima below may occur at different elements; full CSVs retain every element and
the worst absolute-error identity. DC V/Q are omitted here because they are unavailable,
not because their discrepancy is zero. The gate also compares reactive branch absorption
in its current schema; this original evidence snapshot predates that added summary row.

### ac_pf

| Quantity | Maximum absolute discrepancy | Maximum relative discrepancy |
|---|---:|---:|
| buses.vm_pu | 1.665e-15 | 1.718e-15 |
| buses.va_degree | 6.128e-14 | 1.895e-14 |
| generators.p_mw | 4.619e-14 | 1.778e-15 |
| generators.q_mvar | 9.805e-13 | 2.669e-13 |
| branches.p_from_mw | 5.906e-13 | 3.117e-13 |
| branches.q_from_mvar | 1.354e-12 | 2.660e-12 |
| branches.p_to_mw | 6.017e-13 | 2.642e-13 |
| branches.q_to_mvar | 1.377e-12 | 9.750e-13 |
| system.p_branch_loss_mw | 1.248e-13 | 5.106e-14 |
| system.cost_per_hour | 1.137e-13 | 1.916e-16 |

### dc_pf

| Quantity | Maximum absolute discrepancy | Maximum relative discrepancy |
|---|---:|---:|
| buses.va_degree | 4.885e-15 | 2.701e-15 |
| generators.p_mw | 0.000e+00 | 0.000e+00 |
| branches.p_from_mw | 8.882e-14 | 2.776e-07 |
| branches.p_to_mw | 8.882e-14 | 2.776e-07 |
| system.p_branch_loss_mw | 0.000e+00 | 0.000e+00 |
| system.cost_per_hour | 0.000e+00 | 0.000e+00 |

### ac_current_opf

| Quantity | Maximum absolute discrepancy | Maximum relative discrepancy |
|---|---:|---:|
| buses.vm_pu | 7.372e-14 | 7.031e-14 |
| buses.va_degree | 4.476e-12 | 2.086e-11 |
| generators.p_mw | 2.789e-11 | 8.652e-13 |
| generators.q_mvar | 1.702e-10 | 4.752e-11 |
| branches.p_from_mw | 1.660e-11 | 3.769e-12 |
| branches.q_from_mvar | 1.231e-10 | 2.122e-11 |
| branches.p_to_mw | 1.664e-11 | 3.791e-12 |
| branches.q_to_mvar | 1.230e-10 | 4.481e-11 |
| system.p_branch_loss_mw | 4.001e-13 | 1.562e-13 |
| system.cost_per_hour | 6.253e-12 | 1.084e-14 |

### ac_mva_opf

| Quantity | Maximum absolute discrepancy | Maximum relative discrepancy |
|---|---:|---:|
| buses.vm_pu | 5.070e-11 | 5.161e-11 |
| buses.va_degree | 2.457e-09 | 3.436e-09 |
| generators.p_mw | 8.795e-09 | 2.204e-10 |
| generators.q_mvar | 1.579e-08 | 5.236e-09 |
| branches.p_from_mw | 6.960e-09 | 1.103e-09 |
| branches.q_from_mvar | 9.079e-09 | 3.228e-09 |
| branches.p_to_mw | 6.960e-09 | 1.086e-09 |
| branches.q_to_mvar | 1.020e-08 | 5.212e-09 |
| system.p_branch_loss_mw | 4.365e-10 | 1.526e-10 |
| system.cost_per_hour | 1.478e-12 | 2.562e-15 |

### dc_opf

| Quantity | Maximum absolute discrepancy | Maximum relative discrepancy |
|---|---:|---:|
| buses.va_degree | 4.619e-14 | 3.126e-14 |
| generators.p_mw | 2.558e-13 | 7.913e-15 |
| branches.p_from_mw | 1.608e-13 | 6.699e-14 |
| branches.p_to_mw | 1.608e-13 | 6.699e-14 |
| system.p_branch_loss_mw | 0.000e+00 | 0.000e+00 |
| system.cost_per_hour | 1.137e-12 | 2.011e-15 |

## Interpretation and remaining scope

This cross-check supports the observed AC-current versus DC congestion disagreement:
it survives a separate native MATPOWER execution and matched operative inputs. The
current-versus-MVA distinction also survives validation, including the additional MVA
binding branch 25–27. The result concerns this source case and operating point; it does
not establish agreement over future stress scenarios or prove either AC solution globally optimal.

Next, within **Milestone 2b**: load/location stress sweeps, then critical-branch P/Q/V/I
decomposition, then nodal marginal prices. **Milestone 3 remains N-1/security analysis.**
This PR implements none of those later analyses.
