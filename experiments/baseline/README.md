# Baseline experiment

Run `gridstress-baseline --config experiments/baseline/config.toml --output outputs/baseline`
from the repository root. Parameters and classification thresholds are explicit in TOML.
Inspect `manifest.json` for completion and `tables/constraints.csv` for limit observations.
The unmodified case is allowed to have violations; do not tune it until the baseline is clean.
