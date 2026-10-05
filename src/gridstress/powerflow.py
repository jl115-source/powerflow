"""Explicit AC solver boundary; the caller's network is never mutated."""

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandapower as pp
from pandapower import pandapowerNet
from pandapower.powerflow import LoadflowNotConverged


class PowerFlowError(RuntimeError):
    """Power flow failed, or an energized bus has no finite solution."""


@dataclass(frozen=True)
class ACPowerFlowOptions:
    """Newton-Raphson options; tolerance_mva is a power-mismatch tolerance."""

    tolerance_mva: float = 1e-8
    max_iteration: int = 30
    enforce_q_lims: bool = False

    def __post_init__(self) -> None:
        if not isfinite(self.tolerance_mva) or self.tolerance_mva <= 0:
            raise ValueError("tolerance_mva must be finite and positive")
        if type(self.max_iteration) is not int or self.max_iteration < 1:
            raise ValueError("max_iteration must be a positive integer")
        if type(self.enforce_q_lims) is not bool:
            raise ValueError("enforce_q_lims must be boolean")


def run_ac_power_flow(
    net: pandapowerNet,
    options: ACPowerFlowOptions | None = None,
) -> pandapowerNet:
    """Solve a deep copy with flat initialization and a single source slack.

    Fail on nonconvergence and unsupplied in-service buses. No load shedding,
    dispatch correction, rating adjustment or fallback solver is attempted.
    """
    options = options or ACPowerFlowOptions()
    solved = deepcopy(net)
    solved.OPF_converged = False
    solved.pop("gridstress_solution", None)
    try:
        pp.runpp(
            solved,
            algorithm="nr",
            init="flat",
            calculate_voltage_angles=True,
            tolerance_mva=options.tolerance_mva,
            max_iteration=options.max_iteration,
            enforce_q_lims=options.enforce_q_lims,
            check_connectivity=True,
            distributed_slack=False,
            voltage_depend_loads=False,
            trafo_model="t",
            trafo_loading="current",
            numba=False,
        )
    except LoadflowNotConverged as exc:
        raise PowerFlowError(f"AC power flow did not converge: {options}") from exc
    if not solved.converged:
        raise PowerFlowError("AC power flow returned without convergence")
    values = solved.res_bus.loc[solved.bus.in_service, ["vm_pu", "va_degree"]]
    if not np.isfinite(values.to_numpy()).all():
        raise PowerFlowError("In-service buses contain nonfinite results (possibly unsupplied)")
    solved["gridstress_solution"] = {
        "model": "ac",
        "optimal": False,
        "flow_limit": "current",
        "thermal_limits": False,
    }
    return solved


def run_dc_power_flow(net: pandapowerNet) -> pandapowerNet:
    """Lossless linear DC PF; Q, voltage magnitudes and AC feasibility are unavailable."""
    solved = deepcopy(net)
    solved.OPF_converged = False
    solved.pop("gridstress_solution", None)
    try:
        pp.rundcpp(solved, check_connectivity=True, trafo_model="t", trafo_loading="current")
    except LoadflowNotConverged as exc:
        raise PowerFlowError("DC power flow did not converge") from exc
    angles = solved.res_bus.loc[solved.bus.in_service, "va_degree"]
    if not solved.converged or not np.isfinite(angles).all():
        raise PowerFlowError("DC power flow failed or contains unsupplied in-service buses")
    solved["gridstress_solution"] = {
        "model": "dc",
        "optimal": False,
        "flow_limit": "active_power",
        "thermal_limits": False,
        "numba": bool(solved["_options"]["numba"]),
    }
    return solved
