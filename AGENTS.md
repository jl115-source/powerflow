# Engineering and scientific rules

- Keep reusable modelling code in `src/gridstress`, never in notebooks.
- Use typed functions and explicit configuration; no hidden RNG or mutable global state.
- Preserve source networks. Scenario changes must be named, recorded and applied to copies.
- Record case variant, software versions, input hashes, units and solver settings in each run.
- Fail on nonconvergence. Never silently switch solvers, drop unsupplied buses or invent ratings.
- Do not interpret failed PF as load shedding or PF constraint slack as an OPF dual price.
- Keep pandapower access in network/solver/result adapters. Metrics and plots consume tables.
- Extend device support only with complete P/Q accounting and tests; never silently omit losses.
- Use source IDs as keys. Do not assume DataFrame row order equals physical bus/branch order.
- For physics changes, test convergence, P/Q balance, sign conventions, limits and input immutability.
- Run `pytest`, `ruff check .`, `ruff format --check .` and a fresh baseline before publishing.
- DC PF, OPF, N-1, Monte Carlo and weather are planned; do not add them without an explicit task.
- Do not commit generated runs, virtual environments, credentials or downloaded third-party datasets.
