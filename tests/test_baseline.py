from copy import deepcopy

import numpy as np
import pandapower as pp
import pandas as pd
import pytest

from gridstress import ACPowerFlowOptions, PowerFlowError, extract_results, run_ac_power_flow
from gridstress.metrics import constraint_diagnostics
from gridstress.results import evaluate_dispatch_cost


def test_network_provenance_and_fresh_copy(net):
    from pandapower.networks import case30

    from gridstress import load_ieee30

    source = case30()
    for name in ("bus", "line", "gen", "ext_grid", "load", "shunt", "poly_cost"):
        pd.testing.assert_frame_equal(net[name], source[name])
    assert (len(net.bus), len(net.line), len(net.gen), len(net.ext_grid)) == (30, 41, 5, 1)
    net.load.loc[0, "p_mw"] = 999
    assert load_ieee30().load.loc[0, "p_mw"] != 999


def test_solver_preserves_all_input_tables(net):
    before = deepcopy(net)
    solved = run_ac_power_flow(net)
    assert solved.converged
    assert not net.converged
    for key, value in before.items():
        if isinstance(value, pd.DataFrame):
            pd.testing.assert_frame_equal(net[key], value)
    assert np.isfinite(solved.res_bus[["vm_pu", "va_degree"]]).all().all()


def test_physical_accounting_and_source_dispatch(solved, results):
    row = results.summary.iloc[0]
    assert abs(row.p_balance_residual_mw) < 1e-6
    assert abs(row.q_balance_residual_mvar) < 1e-6
    assert row.p_branch_loss_mw > 0
    np.testing.assert_allclose(results.branches.p_loss_mw, solved.res_line.pl_mw, atol=1e-10)
    np.testing.assert_allclose(solved.res_gen.p_mw, solved.gen.p_mw, atol=1e-8)
    np.testing.assert_allclose(
        results.branches.loading_percent,
        100
        * np.maximum(results.branches.i_from_ka, results.branches.i_to_ka)
        / (results.branches.max_i_ka * results.branches.df * results.branches.parallel),
    )
    assert results.generators.element_type.tolist().count("ext_grid") == 1
    assert not row.is_optimal_dispatch


def test_nonzero_active_shunt_accounting(net):
    net.shunt.loc[net.shunt.index[0], "p_mw"] = 1.0  # explicit synthetic test perturbation
    result = extract_results(run_ac_power_flow(net)).summary.iloc[0]
    assert result.p_shunt_mw > 0
    assert result.p_network_loss_mw == pytest.approx(result.p_branch_loss_mw + result.p_shunt_mw)
    assert abs(result.p_balance_residual_mw) < 1e-6


def test_baseline_regression_is_not_an_independent_validation(results):
    assert results.buses.vm_pu.min() == pytest.approx(0.9606237084, abs=1e-7)
    assert results.branches.loading_percent.max() == pytest.approx(111.8314056, abs=1e-4)
    assert results.summary.iloc[0].p_branch_loss_mw == pytest.approx(2.44380313, abs=1e-6)
    violations = constraint_diagnostics(results).query("status == 'violated'")
    assert not violations.query("quantity == 'loading_percent'").empty


def test_polynomial_cost_includes_slack_and_reactive_terms(solved):
    # Independent hand expression for the bundled six active-power polynomials.
    p0 = solved.res_ext_grid.at[0, "p_mw"]
    p1, p2, p3, p4, p5 = solved.res_gen.p_mw
    expected = (
        2 * p0
        + 0.02 * p0**2
        + 1.75 * p1
        + 0.0175 * p1**2
        + p2
        + 0.0625 * p2**2
        + 3.25 * p3
        + 0.00834 * p3**2
        + 3 * p4
        + 0.025 * p4**2
        + 3 * p5
        + 0.025 * p5**2
    )
    assert evaluate_dispatch_cost(solved) == pytest.approx(expected)
    solved.poly_cost.loc[0, ["cq0_eur", "cq1_eur_per_mvar", "cq2_eur_per_mvar2"]] = [3, 2, 4]
    q0 = solved.res_ext_grid.at[0, "q_mvar"]
    assert evaluate_dispatch_cost(solved) == pytest.approx(expected + 3 + 2 * q0 + 4 * q0**2)


def test_missing_cost_fails(solved):
    solved.poly_cost = solved.poly_cost.iloc[1:]
    with pytest.raises(ValueError, match="cover exactly"):
        extract_results(solved)


def test_unconverged_extraction_fails(net):
    with pytest.raises(ValueError, match="unconverged"):
        extract_results(net)


def test_real_solver_nonconvergence_fails(net):
    with pytest.raises(PowerFlowError, match="did not converge"):
        run_ac_power_flow(net, ACPowerFlowOptions(max_iteration=1))
    assert not net.converged


def test_unsupplied_bus_is_not_silently_discarded(net):
    bus = pp.create_bus(net, vn_kv=135, name="isolated test bus")
    pp.create_load(net, bus, p_mw=1, q_mvar=0.2)
    with pytest.raises(PowerFlowError, match="unsupplied"):
        run_ac_power_flow(net)


def test_unsupported_device_fails_instead_of_omitting_accounting(solved):
    pp.create_sgen(solved, bus=0, p_mw=0, q_mvar=0)
    with pytest.raises(NotImplementedError, match="sgen"):
        extract_results(solved)


def test_result_alignment_uses_ids(solved):
    reference = extract_results(solved)
    solved.bus = solved.bus.iloc[::-1]
    solved.line = solved.line.iloc[::-1]
    solved.res_gen = solved.res_gen.iloc[::-1]
    reordered = extract_results(solved)
    for name, keys in (
        ("buses", ["bus_id"]),
        ("branches", ["element_id"]),
        ("generators", ["element_type", "element_id"]),
    ):
        pd.testing.assert_frame_equal(
            getattr(reference, name).sort_values(keys).reset_index(drop=True),
            getattr(reordered, name).sort_values(keys).reset_index(drop=True),
        )


def test_explicit_q_limit_enforcement(net):
    solved = run_ac_power_flow(net, ACPowerFlowOptions(enforce_q_lims=True))
    assert (solved.res_gen.q_mvar <= solved.gen.max_q_mvar + 1e-6).all()
    assert (solved.res_gen.q_mvar >= solved.gen.min_q_mvar - 1e-6).all()


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(tolerance_mva=0),
        dict(tolerance_mva=float("nan")),
        dict(max_iteration=0),
        dict(max_iteration=1.5),
        dict(enforce_q_lims="false"),
    ],
)
def test_invalid_solver_options(kwargs):
    with pytest.raises(ValueError):
        ACPowerFlowOptions(**kwargs)
