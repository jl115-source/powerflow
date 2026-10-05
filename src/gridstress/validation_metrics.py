"""Backend-neutral discrepancy tables and independent case30 feasibility equations."""

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

from gridstress.matpower import CanonicalResult, keyed


@dataclass(frozen=True)
class Acceptance:
    """Absolute tolerances use each column's stated physical units."""

    input_absolute: float = 1e-9
    voltage_pu: float = 1e-6
    angle_degree: float = 1e-4
    power_mw_mvar: float = 1e-4
    balance_mw_mvar: float = 1e-4
    limit_tolerance: float = 1e-5
    binding_percentage_points: float = 0.01
    relative_denominator_floor: float = 1e-8
    objective_absolute: float = 1e-4
    objective_relative: float = 1e-5

    def __post_init__(self) -> None:
        if any(not isfinite(x) or x <= 0 for x in vars(self).values()):
            raise ValueError("All validation tolerances must be finite and positive")


def compare_results(
    candidate: CanonicalResult, reference: CanonicalResult, case: str, acceptance: Acceptance
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Report absolute and floored relative errors; never enforce relative errors near zero.

    OPF solution discrepancies are reported, not forced to PF tolerances. Feasibility,
    objective agreement and matched limiting sets are gated separately.
    """
    rows = []
    dc = case.startswith("dc")
    for table, keys in (
        ("buses", ["bus_id"]),
        ("generators", ["bus_id"]),
        ("branches", ["from_bus", "to_bus"]),
    ):
        left, right = keyed(getattr(candidate, table), keys), keyed(getattr(reference, table), keys)
        if not left.index.equals(right.index) or not left.columns.equals(right.columns):
            raise ValueError(f"Mismatched {table} identities or quantities")
        for quantity in left.columns:
            unavailable = dc and (quantity == "vm_pu" or quantity.startswith("q_"))
            tol = (
                acceptance.voltage_pu
                if quantity == "vm_pu"
                else (
                    acceptance.angle_degree if quantity == "va_degree" else acceptance.power_mw_mvar
                )
            )
            for idx in left.index:
                a, b = float(left.at[idx, quantity]), float(right.at[idx, quantity])
                if unavailable:
                    if not (np.isnan(a) and np.isnan(b)):
                        raise ValueError("DC AC-only quantities must be unavailable on both sides")
                    absolute = relative = np.nan
                else:
                    if not np.isfinite([a, b]).all():
                        raise ValueError(f"Nonfinite {table} {quantity} at {idx}")
                    absolute = abs(a - b)
                    relative = absolute / max(abs(b), acceptance.relative_denominator_floor)
                rows.append(
                    dict(
                        case=case,
                        table=table,
                        entity=str(idx),
                        quantity=quantity,
                        pandapower=a,
                        matpower=b,
                        absolute_error=absolute,
                        relative_error=relative,
                        absolute_tolerance=tol,
                        applicability="unavailable_dc" if unavailable else "available",
                    )
                )
    for quantity, a, b in (
        (
            "p_branch_loss_mw",
            float((candidate.branches.p_from_mw + candidate.branches.p_to_mw).sum()),
            float((reference.branches.p_from_mw + reference.branches.p_to_mw).sum()),
        ),
        ("cost_per_hour", candidate.cost, reference.cost),
    ):
        if not np.isfinite([a, b]).all():
            raise ValueError("Nonfinite system metric")
        tol = (
            acceptance.objective_absolute
            if quantity == "cost_per_hour"
            else acceptance.power_mw_mvar
        )
        rows.append(
            dict(
                case=case,
                table="system",
                entity="system",
                quantity=quantity,
                pandapower=a,
                matpower=b,
                absolute_error=abs(a - b),
                relative_error=abs(a - b) / max(abs(b), acceptance.relative_denominator_floor),
                absolute_tolerance=tol,
                applicability="available",
            )
        )
    details = pd.DataFrame(rows)
    summaries = []
    for (table, quantity), group in details.groupby(["table", "quantity"], sort=False):
        available = group.applicability.eq("available")
        if not available.any():
            summaries.append(
                dict(
                    case=case,
                    table=table,
                    quantity=quantity,
                    max_absolute_error=np.nan,
                    max_relative_error=np.nan,
                    worst_absolute_entity=None,
                    absolute_tolerance=group.absolute_tolerance.iloc[0],
                    status="not_applicable",
                )
            )
            continue
        worst = group.loc[group.absolute_error.idxmax()]
        within = bool((group.absolute_error <= group.absolute_tolerance).all())
        summaries.append(
            dict(
                case=case,
                table=table,
                quantity=quantity,
                max_absolute_error=float(group.absolute_error.max()),
                max_relative_error=float(group.relative_error.max()),
                worst_absolute_entity=worst.entity,
                absolute_tolerance=float(worst.absolute_tolerance),
                status=("pass" if within else "fail")
                if case.endswith("_pf")
                else ("within_pf_tolerance" if within else "opf_solution_difference"),
            )
        )
    return details, pd.DataFrame(summaries)


def audit_feasibility(
    result: CanonicalResult, native: dict, case: str, backend: str, acceptance: Acceptance
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct pi-branch equations and nodal KCL without either solver's routines.

    Scope is the audited case30: one source per generation bus, no parallel branch
    identities. Each endpoint is checked and source shunts enter nodal accounting.
    PF constraint violations are observations; OPF constraints are acceptance checks.
    """
    dc, opf = case.startswith("dc"), case.endswith("opf")
    bus = np.asarray(native["bus"], dtype=float)
    gen = np.asarray(native["gen"], dtype=float)
    line = np.asarray(native["branch"], dtype=float)
    base = float(native["baseMVA"])
    ids = bus[:, 0].astype(int)
    position = {idx: i for i, idx in enumerate(ids)}
    bus_values = keyed(result.buses, ["bus_id"]).loc[ids]
    gen_values = keyed(result.generators, ["bus_id"]).loc[gen[:, 0].astype(int)]
    line_keys = pd.MultiIndex.from_arrays(
        [line[:, 0].astype(int), line[:, 1].astype(int)], names=["from_bus", "to_bus"]
    )
    flow = keyed(result.branches, ["from_bus", "to_bus"]).loc[line_keys]
    f = np.array([position[int(i)] for i in line[:, 0]])
    t = np.array([position[int(i)] for i in line[:, 1]])
    angle = np.deg2rad(bus_values.va_degree.to_numpy())
    vm = np.ones(len(bus)) if dc else bus_values.vm_pu.to_numpy()
    tap = np.where(line[:, 8] == 0, 1, line[:, 8])
    shift = np.deg2rad(line[:, 9])
    if dc:
        p_from = (angle[f] - angle[t] - shift) / (line[:, 3] * tap) * base
        p_to = -p_from
        q_from = q_to = np.zeros(len(line))
    else:
        voltage = vm * np.exp(1j * angle)
        series = 1 / (line[:, 2] + 1j * line[:, 3])
        complex_tap = tap * np.exp(1j * shift)
        ytt = series + 0.5j * line[:, 4]
        yff = ytt / abs(complex_tap) ** 2
        yft = -series / np.conj(complex_tap)
        ytf = -series / complex_tap
        sf = voltage[f] * np.conj(yff * voltage[f] + yft * voltage[t]) * base
        st = voltage[t] * np.conj(ytf * voltage[f] + ytt * voltage[t]) * base
        p_from, p_to, q_from, q_to = sf.real, st.real, sf.imag, st.imag
    residual_p = bus[:, 2] + bus[:, 4] * vm**2
    residual_q = bus[:, 3] - bus[:, 5] * vm**2
    np.add.at(residual_p, f, p_from)
    np.add.at(residual_p, t, p_to)
    np.add.at(residual_q, f, q_from)
    np.add.at(residual_q, t, q_to)
    gp = np.array([position[int(i)] for i in gen[:, 0]])
    np.add.at(residual_p, gp, -gen_values.p_mw.to_numpy())
    if not dc:
        np.add.at(residual_q, gp, -gen_values.q_mvar.to_numpy())
    flow_error = max(
        np.max(abs(flow.p_from_mw.to_numpy() - p_from)), np.max(abs(flow.p_to_mw.to_numpy() - p_to))
    )
    if not dc:
        flow_error = max(
            flow_error,
            np.max(abs(flow.q_from_mvar.to_numpy() - q_from)),
            np.max(abs(flow.q_to_mvar.to_numpy() - q_to)),
        )
    rate = line[:, 5]
    if not (rate > 0).all():
        raise ValueError("case30 validation requires finite positive RATE_A")
    if dc:
        utilization = np.maximum(abs(p_from), abs(p_to)) / rate * 100
    elif case == "ac_mva_opf":
        utilization = np.maximum(np.hypot(p_from, q_from), np.hypot(p_to, q_to)) / rate * 100
    else:
        utilization = (
            np.maximum(np.hypot(p_from, q_from) / vm[f], np.hypot(p_to, q_to) / vm[t]) / rate * 100
        )
    checks = []

    def check(metric: str, value: float, tolerance: float, enforced: bool = True) -> None:
        passed = bool(np.isfinite(value) and value <= tolerance)
        checks.append(
            dict(
                case=case,
                backend=backend,
                metric=metric,
                value=float(value),
                tolerance=tolerance,
                enforced=enforced,
                status=("pass" if passed else "fail") if enforced else "observation",
            )
        )

    check("nodal_p_residual_mw", float(max(abs(residual_p))), acceptance.balance_mw_mvar)
    check("terminal_flow_equation_error", float(flow_error), acceptance.power_mw_mvar)
    check(
        "p_bound_violation_mw",
        float(max(0, np.max(gen[:, 9] - gen_values.p_mw), np.max(gen_values.p_mw - gen[:, 8]))),
        acceptance.limit_tolerance,
        opf,
    )
    if not dc:
        check("nodal_q_residual_mvar", float(max(abs(residual_q))), acceptance.balance_mw_mvar)
        check(
            "q_bound_violation_mvar",
            float(
                max(0, np.max(gen[:, 4] - gen_values.q_mvar), np.max(gen_values.q_mvar - gen[:, 3]))
            ),
            acceptance.limit_tolerance,
            opf,
        )
        check(
            "voltage_bound_violation_pu",
            float(max(0, np.max(bus[:, 12] - vm), np.max(vm - bus[:, 11]))),
            acceptance.limit_tolerance,
            opf,
        )
    check(
        "thermal_violation_percentage_points",
        float(max(0, max(utilization) - 100)),
        acceptance.limit_tolerance,
        opf,
    )
    costs = np.asarray(native["gencost"], dtype=float)
    independent_cost = float(
        np.sum(costs[:, 4] * gen_values.p_mw**2 + costs[:, 5] * gen_values.p_mw + costs[:, 6])
    )
    check(
        "cost_evaluation_error", abs(independent_cost - result.cost), acceptance.objective_absolute
    )
    if opf:
        if result.objective is None:
            raise ValueError("Missing OPF objective")
        check(
            "objective_evaluation_error",
            abs(independent_cost - result.objective),
            acceptance.objective_absolute,
        )
    branch_report = pd.DataFrame(
        {
            "case": case,
            "backend": backend,
            "from_bus": line[:, 0].astype(int),
            "to_bus": line[:, 1].astype(int),
            "utilization_percent": utilization,
            "limiting": utilization >= 100 - acceptance.binding_percentage_points,
        }
    )
    return pd.DataFrame(checks), branch_report
