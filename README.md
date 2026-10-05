# Probabilistic Power-System Stress Testing
## Congestion, Contingencies and Grid Uncertainty

A research framework for tracing uncertain demand, wind, solar, generator availability,
and transmission availability through network physics and optimal dispatch into congestion,
redispatch, operating cost, curtailment, voltage/thermal violations, contingency severity,
and eventually load-shedding risk. Weather may later provide correlated inputs; it is not
this project's organizing model.

**Milestone 1: deterministic IEEE-30 AC baseline.** Implemented: unmodified network loading,
copy-on-solve AC power flow, tidy results, constraint diagnostics, reproducible exports,
and publication-oriented PDF/PNG figures. DC PF, OPF, renewable curtailment, Monte Carlo,
N-1 analysis and weather models are deliberately not implemented yet.

### Run

Python 3.11 is the tested reference environment; package metadata permits 3.11–3.13.
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
```

The dependency snapshot was tested on macOS ARM64 / Python 3.11; CI also checks Ubuntu
Python 3.11. Alternatively, `pip install -e '.[dev]'` resolves the bounded dependencies.
Use a new output directory for each run; existing runs are never overwritten. No network
access or external data is needed after dependencies are installed.

The run produces six result CSVs plus `constraints.csv`, three diagnostic figures in both
PDF and 300 dpi PNG, the exact input network, configuration, and a completion manifest
with versions, input/source hashes and Git revision. A missing manifest means an incomplete
run. There is no random seed because the baseline is deterministic.

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

### Research stages

1. **Baseline (implemented):** verify AC physics, accounting, source limits and repeatability.
2. **Congestion:** deterministic stress scenarios, DC PF, AC/DC OPF, redispatch and cost;
   align branch ratings and validate selected cases against MATPOWER.
3. **Contingencies:** explicit N-1 outages, island handling and severity metrics.
4. **Probabilistic analysis:** seeded correlated demand/renewables and availability models;
   distributions of congestion, cost and violations, followed by a defined load-shedding model.
5. **Final case study:** RTS-GMLC with documented data provenance and temporal assumptions.

### Repository

```text
src/gridstress/      reusable adapters, result schema, metrics, plotting and experiment CLI
experiments/        baseline configuration; congestion/contingencies/probabilistic plans
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
Current-based line loading is not interchangeable with MATPOWER apparent-power limits.
See [assumptions and units](docs/assumptions.md), [result schema](docs/results.md),
[baseline findings](docs/baseline.md), and [validation plan](docs/matpower-validation.md).

Upstream references: [pandapower case documentation](https://pandapower.readthedocs.io/en/v3.2.1/networks/power_system_test_cases.html),
[AC power flow](https://pandapower.readthedocs.io/en/v3.2.1/powerflow/ac.html),
[MATPOWER case30](https://github.com/MATPOWER/matpower/blob/master/data/case30.m).
