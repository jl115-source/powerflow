"""Milestone 2b.1: independent five-formulation MATPOWER validation gate."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandapower as pp
import pandas as pd

from gridstress import (
    ACPowerFlowOptions,
    OPFOptions,
    build_study_case30,
    extract_results,
    load_ieee30,
    run_ac_opf,
    run_ac_power_flow,
    run_dc_opf,
    run_dc_power_flow,
)
from gridstress.matpower import (
    ARCHIVE_SHA256,
    RUNS,
    input_parity,
    normalize_matpower,
    normalize_pandapower,
    run_matpower,
)
from gridstress.validation_metrics import Acceptance, audit_feasibility, compare_results


class ValidationError(RuntimeError):
    """The independent validation gate failed or requires review."""


def _validate(config: dict, root: Path, octave: str, output: Path) -> dict:
    if set(config) != {"solver", "acceptance"}:
        raise ValueError("Expected exactly solver and acceptance configuration sections")
    settings = config["solver"]
    if set(settings) != {"pf_tolerance", "pf_max_iteration", "opf_tolerance", "opf_max_iteration"}:
        raise ValueError("Unknown or missing solver settings")
    acceptance = Acceptance(**config["acceptance"])
    pf_options = ACPowerFlowOptions(
        tolerance_mva=settings["pf_tolerance"],
        max_iteration=settings["pf_max_iteration"],
        enforce_q_lims=False,
    )
    opf_options = OPFOptions(
        solver_tolerance=settings["opf_tolerance"], max_iteration=settings["opf_max_iteration"]
    )
    source = load_ieee30()
    (output / "pandapower_source.json").write_text(pp.to_json(source))
    (output / "pandapower_study.json").write_text(pp.to_json(build_study_case30()))
    independent = run_matpower(root, octave, settings, output)
    native = independent["native_case"]
    parity, mappings = input_parity(native, acceptance.input_absolute)
    parity.to_csv(output / "input_parity.csv", index=False)
    for name, frame in mappings.items():
        frame.to_csv(output / f"mapping_{name}.csv", index=False)
    if (parity.status == "fail").any():
        raise ValidationError("Physical input parity failed; result comparison is not admissible")
    detail_tables, summaries, audits, branches = [], [], [], []
    canonical = {}
    for case in RUNS:
        if case == "ac_pf":
            solved = run_ac_power_flow(source, pf_options)
        elif case == "dc_pf":
            solved = run_dc_power_flow(source)
        elif case == "ac_current_opf":
            solved = run_ac_opf(build_study_case30(), opf_options)
        elif case == "ac_mva_opf":
            solved = run_ac_opf(build_study_case30(), opf_options, flow_limit="apparent_power")
        else:
            solved = run_dc_opf(build_study_case30(), opf_options)
        left = normalize_pandapower(extract_results(solved))
        right = normalize_matpower(independent["runs"][case], dc=case.startswith("dc"))
        canonical[case] = (left, right)
        # Feasibility comes before inspecting objective / solution agreement.
        for backend, result in (("pandapower", left), ("matpower", right)):
            result.export(output / "results" / case / backend)
            audit, branch = audit_feasibility(result, native, case, backend, acceptance)
            audits.append(audit)
            branches.append(branch)
        details, summary = compare_results(left, right, case, acceptance)
        detail_tables.append(details)
        summaries.append(summary)
    details = pd.concat(detail_tables, ignore_index=True)
    summary = pd.concat(summaries, ignore_index=True)
    feasibility = pd.concat(audits, ignore_index=True)
    loading = pd.concat(branches, ignore_index=True)
    details.to_csv(output / "discrepancies.csv", index=False)
    summary.to_csv(output / "maximum_discrepancies.csv", index=False)
    feasibility.to_csv(output / "feasibility.csv", index=False)
    loading.to_csv(output / "branch_utilization.csv", index=False)
    gate = [
        {
            "stage": "input_parity",
            "case": "all",
            "status": "pass",
            "explanation": "All operative physical parameters match; see documented exceptions",
        }
    ]
    for case in RUNS:
        checks = feasibility[feasibility.case == case]
        physics_pass = not (checks.loc[checks.enforced, "status"] == "fail").any()
        gate.append(
            dict(
                stage="feasibility",
                case=case,
                status="pass" if physics_pass else "fail",
                explanation="PF checks equations; OPF also checks all enforced bounds",
            )
        )
        if case.endswith("_pf"):
            errors = summary[summary.case == case]
            gate.append(
                dict(
                    stage="pf_discrepancies",
                    case=case,
                    status="pass" if not (errors.status == "fail").any() else "fail",
                    explanation="Absolute voltage, angle, P/Q, loss and evaluated-cost tolerances",
                )
            )
        else:
            selected = loading[(loading.case == case) & loading.limiting]
            sets = {
                backend: set(
                    zip(
                        selected.loc[selected.backend == backend, "from_bus"],
                        selected.loc[selected.backend == backend, "to_bus"],
                        strict=True,
                    )
                )
                for backend in ("pandapower", "matpower")
            }
            gate.append(
                dict(
                    stage="limiting_branches",
                    case=case,
                    status="pass" if sets["pandapower"] == sets["matpower"] else "review_required",
                    explanation=(f"pandapower={sorted(sets['pandapower'])}; "
                                 f"MATPOWER={sorted(sets['matpower'])}"),
                )
            )
            left, right = canonical[case]
            objective_close = np.isclose(
                left.cost,
                right.cost,
                atol=acceptance.objective_absolute,
                rtol=acceptance.objective_relative,
            )
            gate.append(
                dict(
                    stage="objective_after_feasibility",
                    case=case,
                    status=("pass" if objective_close else "review_required")
                    if physics_pass
                    else "not_admissible",
                    explanation=(
                        f"Cost delta={left.cost - right.cost:.12g}; no dispatch equality imposed. "
                        "AC comparison is between local optima, not a global certificate."
                    ),
                )
            )
    gate_table = pd.DataFrame(gate)
    gate_table.to_csv(output / "gate.csv", index=False)
    passed = bool(gate_table.status.eq("pass").all())
    return {
        "status": "pass" if passed else "review_required_or_failed",
        "gate_passed": passed,
        "matpower_version": independent["matpower_version"],
        "octave_version": independent["runtime_version"],
        "archive_sha256": ARCHIVE_SHA256,
        "formulations": list(RUNS),
        "configuration": config,
        "independence": ("MATPOWER 8.1 MATLAB/Octave vs pandapower/PYPOWER Python; "
                         "shared algorithmic ancestry"),
        "native_case_sha256": hashlib.sha256(
            json.dumps(native, sort_keys=True).encode()
        ).hexdigest(),
    }


def run_validation(config_path: Path, root: Path, octave: str, output: Path) -> Path:
    """Run an independent gate into a new directory; failures preserve evidence and exit nonzero."""
    config_text = config_path.read_text()
    config = tomllib.loads(config_text)
    output.mkdir(parents=True, exist_ok=False)
    (output / "config.toml").write_text(config_text)
    try:
        manifest = _validate(config, root, octave, output)
    except Exception as exc:
        (output / "failure.json").write_text(
            json.dumps(
                {"status": "failed", "exception": type(exc).__name__, "message": str(exc)}, indent=2
            )
        )
        raise
    repo = Path(__file__).resolve().parents[2]
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=False
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, text=True, capture_output=True, check=False
    )
    manifest.update(
        schema_version=1,
        git_commit=revision.stdout.strip(),
        git_dirty=bool(dirty.stdout.strip()),
        python=sys.version,
        platform=platform.platform(),
        versions={
            name: version(name) for name in ("gridstress", "pandapower", "numpy", "scipy", "pandas")
        },
        code_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.iterdir())
            if p.suffix in (".py", ".m")
        },
        artifact_sha256={
            str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    if not manifest["gate_passed"]:
        raise ValidationError(
            "MATPOWER validation gate did not pass; inspect gate.csv and discrepancies"
        )
    return output


def main() -> None:
    """CLI requiring an actual external Octave/MATPOWER installation."""
    parser = argparse.ArgumentParser(description="Independent MATPOWER case30 validation gate")
    parser.add_argument("--config", type=Path, default=Path("experiments/validation/config.toml"))
    parser.add_argument("--matpower-root", type=Path, required=True)
    parser.add_argument("--octave", default="octave-cli")
    parser.add_argument("--output", type=Path, default=Path("outputs/matpower-validation"))
    args = parser.parse_args()
    print(run_validation(args.config, args.matpower_root, args.octave, args.output).resolve())


if __name__ == "__main__":
    main()
