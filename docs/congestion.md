# First result: economic dispatch, thermal congestion and formulation choice

The default experiment keeps original case30 demand, ratings and costs. It makes the
six generators (including slack) controllable within their original bounds, with no
load shedding. AC OPF adjusts P, Q and generator voltage; DC OPF adjusts P only.

| Run | Cost units/hour | Max current loading (%) | Max MVA loading (%) | Active loss (MW) |
|---|---:|---:|---:|---:|
| raw_ac_pf | 593.4522 | 111.8314 | 108.8325 | 2.4438 |
| raw_dc_pf | 586.1451 | — | — | 0.0000 |
| ac_current | 576.8910 | 100.0000 | 102.5021 | 2.5609 |
| ac_thermal_relaxed | 574.5168 | 103.5686 | 106.1076 | 2.4194 |
| ac_mva | 576.8923 | 102.8461 | 100.0000 | 2.8605 |
| dc_opf | 565.2060 | — | — | 0.0000 |
| dc_thermal_relaxed | 565.2060 | — | — | 0.0000 |


Raw PF is a solved operating point, not an economic optimum. Current-constrained AC
OPF reduces cost by 16.5612 source units/hour and removes the original line-9 current
overload. Active losses rise slightly (2.4438 to 2.5609 MW): lower dispatch cost does
not imply minimum losses. See `redispatch.csv` for every generator's P/Q changes,
including the slack. Do not treat this raw-PF cost reduction as a congestion premium.

The paired thermal-relaxed AC OPF keeps all other constraints but removes line limits.
Its 574.5168 cost is 2.3742 lower than the current-constrained solve. That difference
estimates the incremental cost of thermal constraints **between the obtained local AC
solutions**; it is not a globally certified minimum congestion cost. DC OPF and its
thermal-relaxed pair both cost 565.2060, so DC identifies no active-flow congestion at
this demand. That result does not certify AC feasibility.

## Current is not fixed MVA

The AC-MVA optimum reaches 102.8461% current loading while satisfying its MVA limits.
Conversely, the current-constrained optimum exceeds the fixed-MVA bound while meeting
the current bound. At a terminal, |S| = sqrt(3) × |V| × |I|; voltage moves during AC
OPF, so these feasible sets differ. Both terminal magnitudes are checked. This is a
formulation comparison, not evidence that one solver failed to enforce its constraints.

`figures/current_vs_mva` isolates the original overloaded line (ID 9, zero-based buses
5–7). `dispatch_costs` compares all cases; `active_redispatch` shows AC-current minus
raw-PF dispatch. Each is exported as PDF and 300 dpi PNG. DC Q, current, MVA and voltage
magnitudes are unavailable and are deliberately left blank in CSV outputs.

## Reproduction and validation scope

Run `gridstress-congestion --output outputs/congestion` from the repository root.
The output contains source/study inputs, policies, options, hashes, per-run tables,
comparisons, a completion manifest and the figures. It never overwrites a run.
Tests verify source preservation, both terminal-rating conventions, independent cost
accounting, physical balance, a fresh AC PF replay of the optimized controls, missing
DC quantities, real solver failure and unsupplied-bus rejection. Failure is not a
load-shedding estimate or proof of physical infeasibility.

Reference software: pandapower 3.2.1, NumPy 2.2.6, SciPy 1.13.1, Python 3.11. The
SciPy pin is needed because the MVA OPF Hessian uses sparse `.H`, absent in newer
SciPy; no solver monkey patches were introduced. The original baseline regression
still passes. Python 3.13 is excluded because this SciPy pin has no supported wheel.

Independent MATPOWER validation is still planned: current limits with `opf.flow_lim='I'`,
then a separate fixed-MVA comparison with `'S'`. Nonlinear AC local optima and source
mapping must be checked before drawing cross-solver conclusions. Future congestion
work should examine targeted demand stress and Q/voltage sensitivity; Monte Carlo,
N-1, weather, curtailment and load shedding remain out of scope.
