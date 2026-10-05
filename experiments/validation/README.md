# Milestone 2b.1: independent MATPOWER validation gate

Scope: case30 AC PF, DC PF, AC-current OPF, AC-MVA OPF, and DC OPF only.
No stress sweeps, price extraction or contingency studies are introduced.

Install GNU Octave (the CI runtime is Ubuntu 24.04), then from the repository root:

```bash
python scripts/fetch_matpower.py --destination .cache/matpower
gridstress-validate-matpower --matpower-root .cache/matpower/matpower8.1 \
  --octave octave-cli --config experiments/validation/config.toml \
  --output outputs/matpower-validation
```

Use a fresh destination for download and a fresh output directory for every run.
MATPOWER is downloaded from its official 8.1 GitHub release and checksum-verified.
It is never copied into this repository. The MATLAB-language bridge runs in an
external Octave process and independently loads MATPOWER's native case30; it does
not receive pandapower solution vectors or converted network matrices.

An actual passing run is mandatory: missing Octave, source-integrity failure,
nonconvergence, failed physical parity or gate review/failure returns nonzero.
`manifest.json` records completion and `gate_passed`; a completed comparison is not
necessarily a passing validation. Exceptions write `failure.json` and preserve logs.

Outputs:
- `input_parity.csv` and `mapping_*.csv`: operative input comparisons and source IDs.
- `matpower_raw.json`, solver settings, Octave logs, and pandapower source/study JSON.
- `results/<formulation>/<backend>/`: normalized bus, generator and branch values.
- `feasibility.csv`: independently reconstructed network equations and bound checks.
- `branch_utilization.csv`: matched formulation loading and limiting-branch identities.
- `discrepancies.csv`: every individual absolute/relative difference.
- `maximum_discrepancies.csv`: per-quantity maxima and worst absolute-error identity.
- `gate.csv` and manifest: staged acceptance, runtime versions and artifact hashes.

GitHub's **MATPOWER validation / independent-validation** check runs the gate on
pushes and pull requests and uploads evidence even when validation fails. Protecting
`main` with a required check is a separate repository setting; this workflow does not
silently alter branch protection.
