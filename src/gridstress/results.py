"""Pandapower-to-tidy-table adapter with explicit physical sign conventions."""

from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd
from pandapower import pandapowerNet


@dataclass(frozen=True)
class ResultTables:
    """Tables are independent copies, keyed by source element type and index."""

    buses: pd.DataFrame
    generators: pd.DataFrame
    branches: pd.DataFrame
    loads: pd.DataFrame
    shunts: pd.DataFrame
    summary: pd.DataFrame

    def export_csv(self, directory: Path) -> None:
        """Write one tidy CSV per table; IDs are explicit columns, never row indices."""
        directory.mkdir(parents=True, exist_ok=True)
        for field in fields(self):
            getattr(self, field.name).to_csv(directory / f"{field.name}.csv", index=False)


def evaluate_dispatch_cost(net: pandapowerNet) -> float:
    """Evaluate complete polynomial P/Q costs at solved dispatch.

    Units are source cost units/hour, not asserted to be current EUR or USD.
    Reject unsupported or incomplete cost data rather than assume zero cost.
    """
    if not net.converged:
        raise ValueError("A converged power flow is required")
    if not net.pwl_cost.empty:
        raise NotImplementedError("Piecewise-linear costs are outside baseline scope")
    costs = net.poly_cost.set_index(["et", "element"], verify_integrity=True)
    expected = {
        (kind, idx)
        for kind in ("gen", "ext_grid", "sgen")
        for idx in net[kind].index[net[kind].in_service]
    }
    if set(costs.index) != expected:
        raise ValueError("Polynomial costs must cover exactly the in-service generators")
    total = 0.0
    for (kind, idx), cost in costs.iterrows():
        p, q = net[f"res_{kind}"].loc[idx, ["p_mw", "q_mvar"]]
        total += (
            cost.cp0_eur
            + cost.cp1_eur_per_mw * p
            + cost.cp2_eur_per_mw2 * p**2
            + cost.cq0_eur
            + cost.cq1_eur_per_mvar * q
            + cost.cq2_eur_per_mvar2 * q**2
        )
    if not np.isfinite(total):
        raise ValueError("Dispatch cost contains nonfinite inputs")
    return float(total)


def _element_results(net: pandapowerNet, kind: str, columns: list[str]) -> pd.DataFrame:
    source = net[kind]
    frame = source.loc[:, columns].copy()
    frame.insert(0, "element_id", source.index)
    frame.insert(0, "element_type", kind)
    return frame.join(net[f"res_{kind}"][["p_mw", "q_mvar"]]).reset_index(drop=True)


def extract_results(net: pandapowerNet) -> ResultTables:
    """Extract the AC baseline schema; reject unsupported devices or invalid results.

    Generation is positive injection. Loads/shunts are positive consumption.
    Branch terminal powers are positive INTO the branch at each terminal, hence
    p_loss_mw = p_from_mw + p_to_mw. Reactive branch absorption may be negative.
    This adapter supports the case30 device set (lines, gen, ext_grid, loads,
    shunts); extensions must add loss accounting before enabling other devices.
    """
    if not net.converged:
        raise ValueError("Cannot extract results from an unconverged network")
    for kind in (
        "trafo",
        "trafo3w",
        "impedance",
        "dcline",
        "storage",
        "sgen",
        "ward",
        "xward",
        "motor",
        "asymmetric_load",
        "asymmetric_sgen",
        "svc",
        "ssc",
        "tcsc",
        "vsc",
        "line_dc",
        "bus_dc",
    ):
        if kind in net and not net[kind].empty:
            raise NotImplementedError(f"Baseline extraction does not support {kind}")
    buses = net.bus[["name", "vn_kv", "in_service", "min_vm_pu", "max_vm_pu"]].copy()
    buses.insert(0, "bus_id", buses.index)
    buses = buses.join(net.res_bus[["vm_pu", "va_degree", "p_mw", "q_mvar"]])
    buses = buses.reset_index(drop=True)
    generators = pd.concat(
        [
            _element_results(
                net, kind, ["bus", "in_service", "min_p_mw", "max_p_mw", "min_q_mvar", "max_q_mvar"]
            )
            for kind in ("ext_grid", "gen")
        ],
        ignore_index=True,
    ).rename(columns={"bus": "bus_id"})
    branches = net.line[
        ["from_bus", "to_bus", "in_service", "max_loading_percent", "max_i_ka", "df", "parallel"]
    ].copy()
    branches.insert(0, "element_id", branches.index)
    branches.insert(0, "element_type", "line")
    branches = branches.join(
        net.res_line[
            [
                "p_from_mw",
                "q_from_mvar",
                "p_to_mw",
                "q_to_mvar",
                "i_from_ka",
                "i_to_ka",
                "loading_percent",
            ]
        ]
    ).reset_index(drop=True)
    branches["s_from_mva"] = np.hypot(branches.p_from_mw, branches.q_from_mvar)
    branches["s_to_mva"] = np.hypot(branches.p_to_mw, branches.q_to_mvar)
    branches["p_loss_mw"] = branches.p_from_mw + branches.p_to_mw
    branches["q_absorption_mvar"] = branches.q_from_mvar + branches.q_to_mvar
    branches["loading_basis"] = "current"
    loads = _element_results(net, "load", ["bus", "in_service"])
    shunts = _element_results(net, "shunt", ["bus", "in_service"])
    loads = loads.rename(columns={"bus": "bus_id"})
    shunts = shunts.rename(columns={"bus": "bus_id"})
    for frame, cols in (
        (buses, ["vm_pu", "va_degree"]),
        (generators, ["p_mw", "q_mvar"]),
        (branches, ["p_from_mw", "p_to_mw", "loading_percent"]),
        (loads, ["p_mw", "q_mvar"]),
        (shunts, ["p_mw", "q_mvar"]),
    ):
        if not np.isfinite(frame.loc[frame.in_service, cols].to_numpy()).all():
            raise ValueError("Nonfinite results on in-service elements")
    p_gen, q_gen = generators[["p_mw", "q_mvar"]].sum()
    p_load, q_load = loads[["p_mw", "q_mvar"]].sum()
    p_shunt, q_shunt = shunts[["p_mw", "q_mvar"]].sum()
    p_loss = branches.p_loss_mw.sum()
    q_absorption = branches.q_absorption_mvar.sum()
    summary = pd.DataFrame(
        [
            {
                "p_generation_mw": p_gen,
                "q_generation_mvar": q_gen,
                "p_load_mw": p_load,
                "q_load_mvar": q_load,
                "p_shunt_mw": p_shunt,
                "q_shunt_mvar": q_shunt,
                "p_branch_loss_mw": p_loss,
                "q_branch_absorption_mvar": q_absorption,
                "p_network_loss_mw": p_loss + p_shunt,
                "p_balance_residual_mw": p_gen - p_load - p_shunt - p_loss,
                "q_balance_residual_mvar": q_gen - q_load - q_shunt - q_absorption,
                "dispatch_cost_per_hour": evaluate_dispatch_cost(net),
                "cost_unit": "source_cost_unit/hour",
                "is_optimal_dispatch": False,
            }
        ]
    )
    return ResultTables(buses, generators, branches, loads, shunts, summary)
