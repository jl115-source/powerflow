"""Reproducible baseline experiment CLI and artifact export."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tomllib
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import pandapower as pp

from gridstress.metrics import DiagnosticOptions, constraint_diagnostics
from gridstress.networks import load_ieee30
from gridstress.powerflow import ACPowerFlowOptions, run_ac_power_flow
from gridstress.results import extract_results


def run_baseline(config_path: Path, output: Path) -> Path:
    """Run one deterministic case into a new directory; never overwrite a run.

    Failure propagates with a nonzero CLI exit; manifest.json is written last
    and therefore marks a completed run. Partial runs remain for debugging.
    """
    config_text = config_path.read_text()
    config = tomllib.loads(config_text)
    if set(config) != {"experiment", "powerflow", "diagnostics"}:
        raise ValueError("Expected exactly experiment, powerflow and diagnostics sections")
    if config["experiment"] != {"name": "ieee30_baseline", "network": "case30"}:
        raise ValueError("This milestone only supports the ieee30_baseline / case30 experiment")
    pf_options = ACPowerFlowOptions(**config["powerflow"])
    diagnostic_options = DiagnosticOptions(**config["diagnostics"])
    net = load_ieee30()
    network_json = pp.to_json(net)
    solved = run_ac_power_flow(net, pf_options)
    results = extract_results(solved)
    diagnostics = constraint_diagnostics(results, diagnostic_options)
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.toml").write_text(config_text)
    (output / "network_input.json").write_text(network_json)
    results.export_csv(output / "tables")
    diagnostics.to_csv(output / "tables" / "constraints.csv", index=False)
    # Backend selection belongs to this executable, never the plotting library.
    import matplotlib

    matplotlib.use("Agg")
    from gridstress.visualization import plot_baseline

    plot_baseline(results, output / "figures")
    repo = Path(__file__).resolve().parents[2]
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, text=True, capture_output=True, check=False
    )
    source_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    manifest = {
        "schema_version": 2,
        "experiment": config["experiment"],
        "solver": "AC Newton-Raphson",
        "powerflow": asdict(pf_options),
        "diagnostics": asdict(diagnostic_options),
        "fixed_solver_settings": {
            "init": "flat",
            "calculate_voltage_angles": True,
            "distributed_slack": False,
            "voltage_depend_loads": False,
            "trafo_model": "t",
            "trafo_loading": "current",
            "numba": False,
        },
        "network_sha256": hashlib.sha256(network_json.encode()).hexdigest(),
        "config_sha256": hashlib.sha256(config_text.encode()).hexdigest(),
        "source_sha256": source_hashes,
        "git_commit": git.stdout.strip() if git.returncode == 0 else None,
        "git_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "python": sys.version,
        "platform": platform.platform(),
        "versions": {
            name: version(name)
            for name in ("gridstress", "pandapower", "numpy", "scipy", "pandas", "matplotlib")
        },
        "random_seed": None,
        "converged": True,
        "optimal_dispatch": False,
        "constraint_status_counts": diagnostics.status.value_counts().to_dict(),
        "summary": results.summary.iloc[0].to_dict(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return output


def main() -> None:
    """Console entry point."""
    parser = argparse.ArgumentParser(description="Run the deterministic IEEE-30 AC baseline")
    parser.add_argument("--config", type=Path, default=Path("experiments/baseline/config.toml"))
    parser.add_argument("--output", type=Path, default=Path("outputs/baseline"))
    args = parser.parse_args()
    print(run_baseline(args.config, args.output).resolve())


if __name__ == "__main__":
    main()
