from copy import deepcopy

import numpy as np
import pandapower as pp
import pandas as pd
import pytest

from gridstress import (
    DemandScenario,
    OPFOptions,
    OPFPolicy,
    OptimalPowerFlowError,
    PowerFlowError,
    apply_scenario,
    build_study_case30,
    extract_results,
    load_ieee30,
    run_ac_opf,
    run_ac_power_flow,
    run_dc_opf,
    run_dc_power_flow,
)
from gridstress.metrics import DiagnosticOptions, compare_dispatch, constraint_diagnostics


@pytest.fixture(scope="module")
def solutions():
    return {
        "ac": run_ac_opf(build_study_case30()),
        "mva": run_ac_opf(build_study_case30(), flow_limit="apparent_power"),
        "dc": run_dc_opf(build_study_case30()),
        "relaxed": run_ac_opf(build_study_case30(OPFPolicy(thermal_limits=False))),
        "dc_relaxed": run_dc_opf(build_study_case30(OPFPolicy(thermal_limits=False))),
    }


def test_study_policy_retains_all_physical_parameters():
    source, study = load_ieee30(), build_study_case30()
    for key in ("bus", "line", "gen", "ext_grid", "load", "shunt", "poly_cost"):
        pd.testing.assert_frame_equal(
            source[key].drop(columns="controllable", errors="ignore"),
            study[key].drop(columns="controllable", errors="ignore"),
        )
    assert study.gen.controllable.all() and study.ext_grid.controllable.all()
    assert not study.load.controllable.any()
    assert "gridstress_policy" not in source


def test_scenario_is_explicit_and_does_not_compound():
    source = build_study_case30()
    before = deepcopy(source)
    scenario = apply_scenario(source, DemandScenario("ten_percent", 1.1))
    np.testing.assert_allclose(scenario.load.p_mw, source.load.p_mw * 1.1)
    np.testing.assert_allclose(scenario.load.q_mvar, source.load.q_mvar * 1.1)
    pd.testing.assert_frame_equal(source.load, before.load)
    pd.testing.assert_frame_equal(scenario.line, source.line)
    assert scenario.gridstress_scenario["demand_scale"] == 1.1
    with pytest.raises(ValueError, match="original study"):
        apply_scenario(scenario, DemandScenario())


def test_ac_opf_relieves_overload_and_checks_objective(solutions):
    raw = extract_results(run_ac_power_flow(load_ieee30()))
    result = extract_results(solutions["ac"])
    assert raw.branches.loading_percent.max() > 110
    assert result.branches.loading_percent.max() <= 100 + 1e-5
    assert (
        result.summary.iloc[0].dispatch_cost_per_hour < raw.summary.iloc[0].dispatch_cost_per_hour
    )
    assert result.summary.iloc[0].dispatch_cost_per_hour == pytest.approx(solutions["ac"].res_cost)
    diag = constraint_diagnostics(result, DiagnosticOptions(tolerance=1e-5))
    assert not (diag.status == "violated").any()
    assert abs(result.summary.iloc[0].q_balance_residual_mvar) < 1e-5


def test_current_vs_apparent_formulations_are_not_conflated(solutions):
    result = extract_results(solutions["mva"])
    assert result.branches.apparent_loading_percent.max() <= 100 + 1e-5
    assert result.branches.loading_percent.max() > 102
    diag = constraint_diagnostics(result, DiagnosticOptions(tolerance=1e-5))
    assert "apparent_loading_percent" in diag.quantity.values
    assert not (diag.status == "violated").any()
    # Verify the actual solver's converted RATE_A values, not just a metadata label.
    from pandapower.pypower.idx_brch import RATE_A

    np.testing.assert_allclose(
        solutions["mva"]._ppc["branch"][:, RATE_A], result.branches.rate_a_mva, atol=1e-8
    )


def test_thermal_counterfactual_and_cost_increment(solutions):
    constrained, relaxed = extract_results(solutions["ac"]), extract_results(solutions["relaxed"])
    assert relaxed.branches.loading_percent.max() > 103
    pd.testing.assert_series_equal(
        solutions["ac"].line.max_loading_percent, solutions["relaxed"].line.max_loading_percent
    )
    difference = (
        constrained.summary.iloc[0].dispatch_cost_per_hour
        - relaxed.summary.iloc[0].dispatch_cost_per_hour
    )
    assert difference == pytest.approx(2.37420877, abs=1e-4)
    assert solutions["dc"].res_cost == pytest.approx(solutions["dc_relaxed"].res_cost, abs=1e-5)


@pytest.mark.parametrize("solver", [run_dc_power_flow, run_dc_opf])
def test_dc_nodal_balance_and_unavailable_ac_quantities(solver):
    net = solver(build_study_case30())
    result = extract_results(net)
    assert result.buses.vm_pu.isna().all()
    assert result.generators.q_mvar.isna().all()
    assert result.branches.loading_percent.isna().all()
    assert result.branches.s_from_mva.isna().all()
    assert np.isnan(result.summary.iloc[0].q_balance_residual_mvar)
    assert abs(result.summary.iloc[0].p_branch_loss_mw) < 1e-9
    residual = pd.Series(0.0, index=net.bus.index)
    for row in result.generators.itertuples():
        residual.at[row.bus_id] += row.p_mw
    for table in (result.loads, result.shunts):
        for row in table.itertuples():
            residual.at[row.bus_id] -= row.p_mw
    for row in result.branches.itertuples():
        residual.at[row.from_bus] -= row.p_from_mw
        residual.at[row.to_bus] -= row.p_to_mw
    assert abs(residual).max() < 1e-6
    diag = constraint_diagnostics(result)
    assert not diag.quantity.isin(["vm_pu", "q_mvar", "loading_percent"]).any()
    assert "active_loading_percent" in diag.quantity.values


def test_opf_input_immutability_and_ac_pf_replay(solutions):
    net = build_study_case30()
    before = deepcopy(net)
    solved = run_ac_opf(net)
    for key, value in before.items():
        if isinstance(value, pd.DataFrame):
            pd.testing.assert_frame_equal(net[key], value)
    assert not net.OPF_converged and not net.converged
    replay = build_study_case30()
    replay.gen["p_mw"] = solved.res_gen.p_mw
    replay.gen["vm_pu"] = solved.res_bus.loc[replay.gen.bus, "vm_pu"].to_numpy()
    replay.ext_grid["vm_pu"] = solved.res_bus.loc[replay.ext_grid.bus, "vm_pu"].to_numpy()
    pf = run_ac_power_flow(replay)
    np.testing.assert_allclose(pf.res_bus.vm_pu, solved.res_bus.vm_pu, atol=1e-6)
    np.testing.assert_allclose(pf.res_line.p_from_mw, solved.res_line.p_from_mw, atol=1e-5)
    assert not extract_results(pf).summary.iloc[0].is_optimal_dispatch


def test_generator_redispatch_matches_by_identity(solutions):
    raw = extract_results(run_ac_power_flow(load_ieee30()))
    candidate = extract_results(solutions["ac"])
    delta = compare_dispatch(raw, candidate)
    assert len(delta) == 6
    assert (
        abs(
            delta.delta_p_mw.sum()
            - (candidate.summary.iloc[0].p_generation_mw - raw.summary.iloc[0].p_generation_mw)
        )
        < 1e-8
    )
    with pytest.raises(ValueError, match="same AC/DC"):
        compare_dispatch(raw, extract_results(solutions["dc"]))


def test_raw_network_requires_explicit_policy():
    with pytest.raises(ValueError, match="explicit policy"):
        run_ac_opf(load_ieee30())


def test_real_ac_opf_failure_is_loud():
    with pytest.raises(OptimalPowerFlowError, match="did not converge"):
        run_ac_opf(build_study_case30(), OPFOptions(max_iteration=1))


def test_infeasible_dc_capacity_has_no_shedding_fallback():
    net = apply_scenario(build_study_case30(), DemandScenario("exceeds_capacity", 10))
    with pytest.raises(OptimalPowerFlowError, match="did not converge"):
        run_dc_opf(net)
    assert not net.OPF_converged


@pytest.mark.parametrize(
    "solver,error",
    [
        (run_dc_power_flow, PowerFlowError),
        (run_dc_opf, OptimalPowerFlowError),
        (run_ac_opf, OptimalPowerFlowError),
    ],
)
def test_unsupplied_bus_rejected(solver, error):
    net = build_study_case30()
    bus = pp.create_bus(net, vn_kv=135, min_vm_pu=0.95, max_vm_pu=1.05)
    pp.create_load(net, bus, p_mw=1, q_mvar=0.2, controllable=False)
    with pytest.raises(error, match="unsupplied"):
        solver(net)


def test_missing_cost_is_not_an_implicit_zero():
    net = build_study_case30()
    net.poly_cost = net.poly_cost.iloc[1:]
    with pytest.raises(ValueError, match="Costs must cover"):
        run_ac_opf(net)


def test_dc_reactive_cost_is_rejected():
    net = build_study_case30()
    net.poly_cost.loc[0, "cq1_eur_per_mvar"] = 1
    with pytest.raises(ValueError, match="reactive-power costs"):
        run_dc_opf(net)


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf")])
def test_invalid_demand_scale(scale):
    with pytest.raises(ValueError):
        DemandScenario(demand_scale=scale)


def test_nonconvex_dc_cost_is_rejected():
    net = build_study_case30()
    net.poly_cost.loc[0, "cp2_eur_per_mw2"] = -1
    with pytest.raises(ValueError, match="convex"):
        run_dc_opf(net)


def test_nonfinite_ac_branch_reactive_flow_is_rejected(solutions):
    corrupted = deepcopy(solutions["ac"])
    corrupted.res_line.loc[0, "q_from_mvar"] = np.nan
    with pytest.raises(ValueError, match="Nonfinite"):
        extract_results(corrupted)
