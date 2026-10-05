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
- AC/DC PF and OPF are implemented. N-1, Monte Carlo and weather remain out of scope.
- Preserve source/study/scenario separation. Never label DC voltages or Q as AC results.
- Keep current, fixed-MVA and DC active-flow constraints explicit in results and comparisons.
- Before publishing solver changes, run both baseline and congestion experiments.
- Do not commit generated runs, virtual environments, credentials or downloaded third-party datasets.
