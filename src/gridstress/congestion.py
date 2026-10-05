"""First economic-dispatch and congestion comparison; deterministic, no outages."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tomllib
from dataclasses import asdict, replace
from importlib.metadata import version
from pathlib import Path

import pandapower as pp
import pandas as pd

from gridstress.metrics import DiagnosticOptions, compare_dispatch, constraint_diagnostics
from gridstress.networks import OPFPolicy, build_study_case30, load_ieee30
from gridstress.opf import OPFOptions, run_ac_opf, run_dc_opf
from gridstress.powerflow import ACPowerFlowOptions, run_ac_power_flow, run_dc_power_flow
from gridstress.results import ResultTables, extract_results
from gridstress.scenarios import DemandScenario, apply_scenario


def run_congestion(config_path: Path, output: Path) -> Path:
    """Export seven paired solves; fail loudly with a failure record, never omit a case."""
    text = config_path.read_text()
    config = tomllib.loads(text)
    if set(config) != {"experiment", "scenario", "policy", "opf", "powerflow", "diagnostics"}:
        raise ValueError("Unexpected or missing congestion configuration sections")
    if config["experiment"] != {"name": "case30_redispatch"}:
        raise ValueError("Unsupported congestion experiment")
    scenario = DemandScenario(**config["scenario"])
    policy = OPFPolicy(**config["policy"])
    if not policy.thermal_limits:
        raise ValueError("The comparison needs a constrained policy; relaxed pairs are explicit")
    options = OPFOptions(**config["opf"])
    pf = ACPowerFlowOptions(**config["powerflow"])
    diagnostic = DiagnosticOptions(**config["diagnostics"])
    if diagnostic.tolerance < options.check_tolerance:
        raise ValueError("Diagnostic tolerance must cover the OPF post-check tolerance")
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.toml").write_text(text)
    source_json = pp.to_json(load_ieee30())
    (output / "source_case30.json").write_text(source_json)
    variants = (
        ("raw_ac_pf", "ac_pf", "current", True),
        ("raw_dc_pf", "dc_pf", "active_power", True),
        ("ac_current", "ac_opf", "current", True),
        ("ac_thermal_relaxed", "ac_opf", "current", False),
        ("ac_mva", "ac_opf", "apparent_power", True),
        ("dc_opf", "dc_opf", "active_power", True),
        ("dc_thermal_relaxed", "dc_opf", "active_power", False),
    )
    tables: dict[str, ResultTables] = {}
    rows = []
    run_metadata = {}
    for name, solver, flow, thermal in variants:
        inputs = (
            load_ieee30()
            if solver in ("ac_pf", "dc_pf")
            else (build_study_case30(replace(policy, thermal_limits=thermal)))
        )
        inputs = apply_scenario(inputs, scenario)
        run_dir = output / "runs" / name
        run_dir.mkdir(parents=True)
        input_json = pp.to_json(inputs)
        (run_dir / "network_input.json").write_text(input_json)
        try:
            if solver == "ac_pf":
                solved = run_ac_power_flow(inputs, pf)
            elif solver == "dc_pf":
                solved = run_dc_power_flow(inputs)
            elif solver == "ac_opf":
                solved = run_ac_opf(inputs, options, flow_limit=flow)
            else:
                solved = run_dc_opf(inputs, options)
            result = extract_results(solved)
            diagnostics = constraint_diagnostics(result, diagnostic)
        except Exception as exc:
            (output / "failure.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "variant": name,
                        "exception_type": type(exc).__name__,
                        "message": str(exc),
                        "not_an_infeasibility_certificate": True,
                    },
                    indent=2,
                )
            )
            raise
        result.export_csv(run_dir / "tables")
        diagnostics.to_csv(run_dir / "tables" / "constraints.csv", index=False)
        tables[name] = result
        summary = result.summary.iloc[0].to_dict()
        summary.update(
            run_id=name,
            max_current_loading_percent=result.branches.loading_percent.max(),
            max_apparent_loading_percent=result.branches.apparent_loading_percent.max(),
            max_active_loading_percent=result.branches.active_loading_percent.max(),
            min_vm_pu=result.buses.vm_pu.min(),
            violations_under_formulation=int((diagnostics.status == "violated").sum()),
        )
        rows.append(summary)
        run_metadata[name] = {
            "solver": solver,
            "solution": solved.gridstress_solution,
            "policy": inputs.get("gridstress_policy"),
            "scenario": asdict(scenario),
            "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(),
        }
    comparisons = (
        ("ac_current", "raw_ac_pf"),
        ("ac_mva", "raw_ac_pf"),
        ("dc_opf", "raw_dc_pf"),
        ("ac_current", "ac_thermal_relaxed"),
        ("dc_opf", "dc_thermal_relaxed"),
    )
    dispatch = []
    for candidate, reference in comparisons:
        delta = compare_dispatch(tables[reference], tables[candidate])
        delta.insert(0, "reference", reference)
        delta.insert(0, "candidate", candidate)
        dispatch.append(delta)
    dispatch_table = pd.concat(dispatch, ignore_index=True)
    summary_table = pd.DataFrame(rows)
    summary_table.to_csv(output / "comparison.csv", index=False)
    dispatch_table.to_csv(output / "redispatch.csv", index=False)
    costs = summary_table.set_index("run_id").dispatch_cost_per_hour
    congestion_cost = pd.DataFrame(
        [
            {
                "model": model,
                "constrained": name,
                "thermal_relaxed": relaxed,
                "incremental_cost_per_hour": costs[name] - costs[relaxed],
                "interpretation": "local AC solution difference"
                if model == "ac"
                else "DC optimum difference",
            }
            for model, name, relaxed in (
                ("ac", "ac_current", "ac_thermal_relaxed"),
                ("dc", "dc_opf", "dc_thermal_relaxed"),
            )
        ]
    )
    congestion_cost.to_csv(output / "thermal_constraint_cost.csv", index=False)
    import matplotlib

    matplotlib.use("Agg")
    from gridstress.visualization import plot_congestion

    plot_congestion(summary_table, dispatch_table, tables, output / "figures")
    repo = Path(__file__).resolve().parents[2]
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, text=True, capture_output=True, check=False
    )
    manifest = {
        "schema_version": 2,
        "status": "complete",
        "experiment": config["experiment"],
        "configuration": config,
        "runs": run_metadata,
        "source_sha256": hashlib.sha256(source_json.encode()).hexdigest(),
        "config_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "code_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
        "git_commit": git.stdout.strip() if git.returncode == 0 else None,
        "git_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "python": sys.version,
        "platform": platform.platform(),
        "random_seed": None,
        "versions": {
            name: version(name)
            for name in ("gridstress", "pandapower", "numpy", "scipy", "pandas", "matplotlib")
        },
        "solver_settings": {
            "ac_opf_init": "flat",
            "ac_pf_init": "flat",
            "ac_numba": False,
            "dc_pf_numba": "auto-detected; resolved flag saved in run solution metadata",
            "check_connectivity": True,
            "opf_delta": 1e-10,
            "current_OPF_FLOW_LIM": 2,
            "apparent_OPF_FLOW_LIM": 0,
            "dc_branch_limit": "abs(P) <= RATE_A",
            "pf_distributed_slack": False,
            "pf_voltage_depend_loads": False,
            "pf_calculate_voltage_angles": True,
            "pf_trafo_model": "t",
            "pf_trafo_loading": "current",
            "opf_suppress_warnings": False,
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return output


def main() -> None:
    """Run the explicitly configured comparison into a new output directory."""
    parser = argparse.ArgumentParser(description="IEEE-30 economic dispatch and congestion")
    parser.add_argument("--config", type=Path, default=Path("experiments/congestion/config.toml"))
    parser.add_argument("--output", type=Path, default=Path("outputs/congestion"))
    args = parser.parse_args()
    print(run_congestion(args.config, args.output).resolve())


if __name__ == "__main__":
    main()
