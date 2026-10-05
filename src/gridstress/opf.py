"""AC/DC OPF adapters with explicit formulations and post-solve checks."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Literal

import numpy as np
import pandapower as pp
from pandapower import pandapowerNet
from pandapower.optimal_powerflow import OPFNotConverged

from gridstress.metrics import DiagnosticOptions, constraint_diagnostics
from gridstress.networks import OPFPolicy
from gridstress.results import extract_results


class OptimalPowerFlowError(RuntimeError):
    """Solver failure or failed feasibility check; not proof of infeasibility."""


@dataclass(frozen=True)
class OPFOptions:
    """PIPS tolerances are internal; post-checks use physical table units."""

    max_iteration: int = 150
    solver_tolerance: float = 1e-8
    check_tolerance: float = 1e-5

    def __post_init__(self) -> None:
        if type(self.max_iteration) is not int or self.max_iteration < 1:
            raise ValueError("max_iteration must be a positive integer")
        for value in (self.solver_tolerance, self.check_tolerance):
            if not isfinite(value) or value <= 0:
                raise ValueError("OPF tolerances must be finite and positive")
        if self.check_tolerance > 0.001:
            raise ValueError("check_tolerance must not exceed 0.001 in physical result units")


def _validate_study(net: pandapowerNet, dc: bool) -> None:
    if "gridstress_policy" not in net:
        raise ValueError("OPF requires build_study_case30() with an explicit policy")
    OPFPolicy(**net.gridstress_policy)
    if len(net.ext_grid) != 1 or not net.ext_grid.in_service.all():
        raise ValueError("Milestone 2 requires one in-service slack")
    for kind in ("gen", "ext_grid"):
        if not net[kind].controllable.all():
            raise ValueError(f"Study policy requires all {kind} elements controllable")
        for quantity in ("p_mw",) if dc else ("p_mw", "q_mvar"):
            bounds = net[kind][[f"min_{quantity}", f"max_{quantity}"]].to_numpy()
            if not np.isfinite(bounds).all() or (bounds[:, 0] > bounds[:, 1]).any():
                raise ValueError(f"Invalid {kind} {quantity} bounds")
    if net.load.controllable.any():
        raise ValueError("Demand must be fixed; load shedding is not implemented")
    for name in ("max_i_ka", "df", "parallel", "max_loading_percent"):
        if not np.isfinite(net.line[name]).all() or (net.line[name] <= 0).any():
            raise ValueError(f"Line {name} must be finite and positive")
    bounds = net.bus[["min_vm_pu", "max_vm_pu"]].to_numpy()
    if not np.isfinite(bounds).all() or (bounds[:, 0] > bounds[:, 1]).any():
        raise ValueError("Invalid bus voltage bounds")
    if not np.allclose(
        net.bus.loc[net.line.from_bus, "vn_kv"].to_numpy(),
        net.bus.loc[net.line.to_bus, "vn_kv"].to_numpy(),
    ):
        raise ValueError("Line terminal voltage bases differ; add a transformer adapter")
    if not net.pwl_cost.empty:
        raise NotImplementedError("Only complete polynomial generation costs are supported")
    costs = net.poly_cost.set_index(["et", "element"], verify_integrity=True)
    expected = {
        (kind, idx) for kind in ("gen", "ext_grid") for idx in net[kind].index[net[kind].in_service]
    }
    if set(costs.index) != expected or not np.isfinite(costs.to_numpy()).all():
        raise ValueError("Costs must cover exactly all sources with finite coefficients")
    if dc and (costs.cp2_eur_per_mw2 < 0).any():
        raise ValueError("DC OPF requires convex active-power costs")
    if dc and (costs[["cq0_eur", "cq1_eur_per_mvar", "cq2_eur_per_mvar2"]] != 0).any().any():
        raise ValueError("DC studies do not support reactive-power costs")


def _run_opf(net: pandapowerNet, model: str, flow_limit: str, options: OPFOptions) -> pandapowerNet:
    _validate_study(net, dc=model == "dc")
    solved = deepcopy(net)
    solved.converged = False
    solved.OPF_converged = False
    solved.pop("gridstress_solution", None)
    thermal = net.gridstress_policy["thermal_limits"]
    original_limits = solved.line.max_loading_percent.copy()
    if not thermal:
        # Missing column -> RATE_A=0 -> unlimited in pandapower's OPF conversion.
        solved.line = solved.line.drop(columns="max_loading_percent")
    kwargs = dict(
        OPF_FLOW_LIM=2 if flow_limit == "current" else 0,
        OPF_VIOLATION=options.solver_tolerance,
        PDIPM_FEASTOL=options.solver_tolerance,
        PDIPM_GRADTOL=options.solver_tolerance,
        PDIPM_COMPTOL=options.solver_tolerance,
        PDIPM_COSTTOL=options.solver_tolerance,
        PDIPM_MAX_IT=options.max_iteration,
        check_connectivity=True,
        suppress_warnings=False,
        delta=1e-10,
    )
    try:
        if model == "ac":
            pp.runopp(solved, init="flat", calculate_voltage_angles=True, numba=False, **kwargs)
        else:
            pp.rundcopp(solved, **kwargs)
    except OPFNotConverged as exc:
        raise OptimalPowerFlowError(
            f"{model.upper()} OPF did not converge ({flow_limit}, thermal_limits={thermal}); "
            "no fallback or load shedding attempted"
        ) from exc
    if not solved.OPF_converged:
        raise OptimalPowerFlowError("OPF returned without convergence")
    solved.line["max_loading_percent"] = original_limits
    solved["gridstress_solution"] = dict(
        model=model,
        optimal=True,
        flow_limit=flow_limit,
        thermal_limits=thermal,
        options=asdict(options),
    )
    values = solved.res_bus.loc[
        solved.bus.in_service, ["va_degree"] if model == "dc" else ["vm_pu", "va_degree"]
    ]
    if not np.isfinite(values.to_numpy()).all():
        raise OptimalPowerFlowError("OPF contains unsupplied in-service buses")
    result = extract_results(solved)
    summary = result.summary.iloc[0]
    for key in (
        ["p_balance_residual_mw"]
        if model == "dc"
        else ["p_balance_residual_mw", "q_balance_residual_mvar"]
    ):
        if not np.isfinite(summary[key]) or abs(summary[key]) > options.check_tolerance:
            raise OptimalPowerFlowError(f"Post-solve power balance failed: {key}={summary[key]}")
    diag = constraint_diagnostics(result, DiagnosticOptions(tolerance=options.check_tolerance))
    enforced = diag if thermal else diag.loc[diag.element_type != "line"]
    if (enforced.status == "violated").any():
        raise OptimalPowerFlowError("Post-solve enforced constraint check failed")
    if not np.isfinite(solved.res_cost) or not np.isclose(
        summary.dispatch_cost_per_hour, solved.res_cost, atol=options.check_tolerance, rtol=1e-8
    ):
        raise OptimalPowerFlowError("Independent dispatch cost does not match solver objective")
    return solved


def run_ac_opf(
    net: pandapowerNet,
    options: OPFOptions | None = None,
    *,
    flow_limit: Literal["current", "apparent_power"] = "current",
) -> pandapowerNet:
    """AC OPF on a copy: current (2) or fixed-MVA (0) limits; local optimum only."""
    if flow_limit not in ("current", "apparent_power"):
        raise ValueError("AC flow_limit must be current or apparent_power")
    return _run_opf(net, "ac", flow_limit, options or OPFOptions())


def run_dc_opf(net: pandapowerNet, options: OPFOptions | None = None) -> pandapowerNet:
    """Lossless DC OPF with |P| <= RATE_A; no Q/voltage feasibility claim."""
    return _run_opf(net, "dc", "active_power", options or OPFOptions())
