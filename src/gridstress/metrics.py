"""Backend-independent constraint diagnostics on tidy result tables."""

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

from gridstress.results import ResultTables


@dataclass(frozen=True)
class DiagnosticOptions:
    """Near thresholds use physical units, not percentages of generator range."""

    near_voltage_pu: float = 0.005
    near_loading_percentage_points: float = 5.0
    near_generator_mw: float = 1.0
    near_generator_mvar: float = 1.0
    tolerance: float = 1e-6

    def __post_init__(self) -> None:
        for value in vars(self).values():
            if not isfinite(value) or value < 0:
                raise ValueError("Diagnostic thresholds must be finite and nonnegative")
        if (
            min(
                self.near_voltage_pu,
                self.near_loading_percentage_points,
                self.near_generator_mw,
                self.near_generator_mvar,
            )
            < self.tolerance
        ):
            raise ValueError("Near thresholds must be at least the numerical tolerance")


def constraint_diagnostics(
    results: ResultTables,
    options: DiagnosticOptions | None = None,
) -> pd.DataFrame:
    """Return all evaluated bounds, including satisfied and unspecified bounds.

    Slack is value - lower or upper - value; negative means violation. 'at_limit'
    is a numerical observation, not an OPF binding-constraint/dual-price claim.
    Missing bounds produce 'unrated', never an invented limit. Tolerance is
    applied in each row's stated unit.
    """
    options = options or DiagnosticOptions()
    rows: list[dict[str, object]] = []

    def add(
        kind: str,
        idx: int,
        quantity: str,
        value: float,
        bound: str,
        limit: float,
        near: float,
        unit: str,
    ) -> None:
        if not np.isfinite(value):
            raise ValueError(f"Nonfinite {quantity} for {kind}:{idx}")
        slack = value - limit if bound == "lower" else limit - value
        if not np.isfinite(limit):
            status = "unrated"
        elif slack < -options.tolerance:
            status = "violated"
        elif abs(slack) <= options.tolerance:
            status = "at_limit"
        elif slack <= near:
            status = "near_limit"
        else:
            status = "ok"
        rows.append(
            dict(
                element_type=kind,
                element_id=idx,
                quantity=quantity,
                bound=bound,
                value=value,
                limit=limit,
                slack=slack,
                unit=unit,
                status=status,
            )
        )

    for row in results.buses.loc[results.buses.in_service].itertuples():
        for bound, limit in (("lower", row.min_vm_pu), ("upper", row.max_vm_pu)):
            add("bus", row.bus_id, "vm_pu", row.vm_pu, bound, limit, options.near_voltage_pu, "pu")
    for row in results.branches.loc[results.branches.in_service].itertuples():
        add(
            row.element_type,
            row.element_id,
            "loading_percent",
            row.loading_percent,
            "upper",
            row.max_loading_percent,
            options.near_loading_percentage_points,
            "percent",
        )
    for row in results.generators.loc[results.generators.in_service].itertuples():
        for quantity, near, unit in (
            ("p_mw", options.near_generator_mw, "MW"),
            ("q_mvar", options.near_generator_mvar, "MVAr"),
        ):
            for bound, prefix in (("lower", "min_"), ("upper", "max_")):
                add(
                    row.element_type,
                    row.element_id,
                    quantity,
                    getattr(row, quantity),
                    bound,
                    getattr(row, prefix + quantity),
                    near,
                    unit,
                )
    return pd.DataFrame(
        rows,
        columns=[
            "element_type",
            "element_id",
            "quantity",
            "bound",
            "value",
            "limit",
            "slack",
            "unit",
            "status",
        ],
    )
