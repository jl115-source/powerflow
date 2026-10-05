# Probabilistic Power-System Stress Testing
## Congestion, Contingencies and Grid Uncertainty

A research framework for tracing uncertain demand, wind, solar, generator availability,
and transmission availability through network physics and optimal dispatch into congestion,
redispatch, operating cost, curtailment, voltage/thermal violations, contingency severity,
and eventually load-shedding risk. Weather may later provide correlated inputs; it is not
this project's organizing model.

**Milestone 2: economic dispatch and congestion.** AC/DC power flow, current- and
MVA-constrained AC OPF, DC OPF, explicit study policies and demand scenarios, tidy
results, physical feasibility checks, and reproducible comparison experiments.
The unmodified AC baseline is preserved. Monte Carlo, N-1, renewables, load shedding
and weather models remain future work.

The first comparison removes the raw PF overload through AC redispatch. Current-constrained
AC OPF costs **576.89** source units/hour versus **593.45** for raw PF. A paired AC solve
without thermal constraints costs **574.52**; the **2.37** difference estimates the incremental
cost of thermal constraints for these local solutions. Fixed-MVA AC OPF remains within its
MVA limits while reaching **102.85% current loading**. DC OPF reports no active-flow congestion at the same demand; it does not certify AC feasibility.
See [experiment findings](docs/congestion.md) for the full comparison and limitations.

**Milestone 2b.1 adds an independent MATPOWER validation gate** for AC/DC PF,
AC-current/MVA OPF and DC OPF. It audits native input parity and produces feasibility,
absolute/relative discrepancy and limiting-branch comparison tables. An actual Octave
execution is required; missing runtime or failed acceptance blocks the gate. See
[validation methods](docs/matpower-validation.md), [measured results](docs/matpower-validation-results.md),
and [run instructions](experiments/validation/README.md).

### Run

Python 3.11 is the tested reference environment; package metadata permits 3.11–3.12.
From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
pytest
ruff check .
ruff format --check .
gridstress-baseline --config experiments/baseline/config.toml --output outputs/baseline
gridstress-congestion --config experiments/congestion/config.toml --output outputs/congestion
```

The dependency snapshot was tested on macOS ARM64 / Python 3.11; CI also checks Ubuntu
Python 3.11. Alternatively, `pip install -e '.[dev]'` resolves the bounded dependencies.
Use a new output directory for each run; existing runs are never overwritten. No network
access or external data is needed after dependencies are installed.

The baseline run produces six result CSVs plus `constraints.csv`, three diagnostic figures in both
PDF and 300 dpi PNG, the exact input network, configuration, and a completion manifest
with versions, input/source hashes and Git revision. A missing manifest means an incomplete
run. There is no random seed because the baseline is deterministic.

The congestion run compares seven cases, exports per-run inputs/tables plus cost and
redispatch comparisons, and produces three PDF/PNG figures. A failure aborts the run and
writes `failure.json`; it does not silently drop a case or infer load shedding.

### API

```python
from gridstress import load_ieee30, run_ac_power_flow, extract_results
from gridstress.metrics import constraint_diagnostics

network = load_ieee30()
solved = run_ac_power_flow(network)  # original network remains untouched
results = extract_results(solved)
constraints = constraint_diagnostics(results)
violations = constraints.query("status == 'violated'")
print(results.summary)
```

- `load_ieee30()`: a fresh pandapower `case30` with original limits and coefficients.
- `run_ac_power_flow(net, options)`: explicit Newton-Raphson settings; raises on failure
  or unsupplied in-service buses. Results belong to this solved snapshot; re-solve after edits.
- `extract_results(net)`: `ResultTables` containing buses, generators (including slack),
  branches, loads, shunts, and system summary.
- `constraint_diagnostics(results, options)`: tidy lower/upper bound evaluations and slack.
- `plot_baseline(results, directory)`: voltage, ranked branch-loading and P/Q dispatch figures.
- `run_baseline(config_path, output)`: complete reproducible experiment.

```python
from gridstress import build_study_case30, run_ac_opf, run_dc_opf, extract_results

study = build_study_case30()  # explicit source-bound dispatch policy
ac = extract_results(run_ac_opf(study))  # current magnitude constraints
mva = extract_results(run_ac_opf(study, flow_limit="apparent_power"))
dc = extract_results(run_dc_opf(study))  # active-flow constraints; Q/V unavailable
```

`OPFPolicy`, `DemandScenario` and `apply_scenario()` separate the original source case
from declared modelling decisions and demand scaling. `run_dc_power_flow()` retains fixed
active dispatch; `compare_dispatch()` joins generator identities to calculate redispatch.
No reusable modelling code lives in notebooks.

### Research stages

1. **Baseline (implemented):** verify AC physics, accounting, source limits and repeatability.
2. **Economic dispatch/congestion (implemented):** DC PF, AC/DC OPF, explicit policies,
   deterministic demand scaling, redispatch, and current-versus-MVA comparison. Next: targeted
   stress sweeps after the Milestone 2b.1 MATPOWER validation gate.
3. **Contingencies:** explicit N-1 outages, island handling and severity metrics.
4. **Probabilistic analysis:** seeded correlated demand/renewables and availability models;
   distributions of congestion, cost and violations, followed by a defined load-shedding model.
5. **Final case study:** RTS-GMLC with documented data provenance and temporal assumptions.

### Repository

```text
src/gridstress/      reusable adapters, result schema, metrics, plotting and experiment CLI
experiments/        baseline + congestion configurations; later-stage plans
notebooks/          presentation only; no reusable modelling code
tests/              physics, accounting, transformations, failures and experiment tests
docs/               assumptions, schema, MATPOWER validation plan and baseline findings
data/               data provenance policy; IEEE-30 is bundled with pandapower
AGENTS.md           modelling and engineering rules
requirements-lock.txt  exact tested dependency snapshot
```

### Scientific scope

The source is **pandapower `case30` (PYPOWER-derived)**, not the distinct `case_ieee30`.
Source network parameters are retained, including the single slack and polynomial costs.
Default PF does **not** enforce generator P/Q or thermal/voltage limits: these are measured
and reported. The original baseline can therefore converge while violating constraints.
Cost is an evaluated source-cost-unit/hour quantity, not a currency conversion or optimum.
Current-based line loading is not interchangeable with fixed-MVA limits. MATPOWER also
supports current limits (`opf.flow_lim='I'`), which will be used for like-for-like validation.
See [assumptions and units](docs/assumptions.md), [result schema](docs/results.md),
[baseline findings](docs/baseline.md), and [validation plan](docs/matpower-validation.md).

Upstream references: [pandapower case documentation](https://pandapower.readthedocs.io/en/v3.2.1/networks/power_system_test_cases.html),
[AC power flow](https://pandapower.readthedocs.io/en/v3.2.1/powerflow/ac.html),
[MATPOWER case30](https://github.com/MATPOWER/matpower/blob/master/data/case30.m).

The solver dependency snapshot now pins SciPy 1.13.1 and NumPy 2.2.6: pandapower 3.2.1's
MVA OPF Hessian uses sparse-matrix `.H`, removed in newer SciPy. This is a compatibility pin,
not a monkey patch or a network-data change. Both formulations are tested in CI.
