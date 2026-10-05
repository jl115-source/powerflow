"""Unit tests use synthetic converter fixtures; only Octave CI provides independent evidence."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pandapower.converter import to_ppc

from gridstress import (
    build_study_case30,
    extract_results,
    load_ieee30,
    run_ac_power_flow,
    run_dc_power_flow,
)
from gridstress.matpower import input_parity, normalize_matpower, normalize_pandapower
from gridstress.validation import run_validation
from gridstress.validation_metrics import Acceptance, audit_feasibility, compare_results


@pytest.fixture
def synthetic_native():
    # Deliberately derived from pandapower for unit testing, NOT an independent oracle.
    ppc = to_ppc(build_study_case30(), init="flat", mode="opf")
    native = {name: np.real(ppc[name]).copy() for name in ("bus", "gen", "branch", "gencost")}
    native["baseMVA"] = 100
    native["bus"][:, 0] += 1
    native["gen"][:, 0] += 1
    native["branch"][:, :2] += 1
    native["gen"][:, 6] = 100
    native["gen"][0, 1] = 23.54
    native["branch"][:, 8] = 0  # MATPOWER's identity-tap representation
    return native


def test_input_parity_and_mapping_do_not_depend_on_row_order(synthetic_native):
    case = synthetic_native
    case["bus"] = case["bus"][::-1]
    case["gen"], case["gencost"] = case["gen"][::-1], case["gencost"][::-1]
    case["branch"] = case["branch"][::-1]
    audit, maps = input_parity(case, 1e-9)
    assert not (audit.status == "fail").any()
    assert (audit.status == "documented_exception").any()
    assert len(maps["buses"]) == 30 and len(maps["branches"]) == 41
    assert maps["branches"].loc[9, "matpower_from_bus"] == 6
    assert maps["branches"].loc[9, "matpower_to_bus"] == 8


@pytest.mark.parametrize(
    "table,row,col",
    [("branch", 9, 5), ("branch", 0, 2), ("bus", 3, 3), ("gen", 1, 8), ("gencost", 0, 4)],
)
def test_operative_input_change_fails(synthetic_native, table, row, col):
    synthetic_native[table][row, col] += 0.1
    parity, _ = input_parity(synthetic_native, 1e-9)
    assert (parity.status == "fail").any()


def test_ambiguous_branch_identity_rejected(synthetic_native):
    synthetic_native["branch"][1, :2] = synthetic_native["branch"][0, :2]
    with pytest.raises(ValueError, match="ambiguous"):
        input_parity(synthetic_native, 1e-9)


@pytest.fixture
def canonical_ac():
    return normalize_pandapower(extract_results(run_ac_power_flow(load_ieee30())))


def test_discrepancies_are_keyed_and_maxima_are_explicit(canonical_ac):
    reference = deepcopy(canonical_ac)
    reference.buses = reference.buses.iloc[::-1]
    reference.generators = reference.generators.iloc[::-1]
    reference.branches = reference.branches.iloc[::-1]
    details, maxima = compare_results(canonical_ac, reference, "ac_pf", Acceptance())
    assert details.absolute_error.max() == 0
    assert maxima.status.eq("pass").all()
    reference.buses.loc[0, "vm_pu"] += 1e-3
    _, maxima = compare_results(canonical_ac, reference, "ac_pf", Acceptance())
    voltage = maxima.query("quantity == 'vm_pu'").iloc[0]
    assert voltage.max_absolute_error == pytest.approx(0.001)
    assert voltage.worst_absolute_entity == "1" and voltage.status == "fail"
    _, opf = compare_results(canonical_ac, reference, "ac_current_opf", Acceptance())
    assert opf.query("quantity == 'vm_pu'").iloc[0].status == "opf_solution_difference"


def test_relative_error_near_zero_uses_documented_floor(canonical_ac):
    reference = deepcopy(canonical_ac)
    reference.buses.loc[0, "va_degree"] = 0
    canonical_ac.buses.loc[0, "va_degree"] = 1e-9
    details, _ = compare_results(canonical_ac, reference, "ac_pf", Acceptance())
    angle = details.query("quantity == 'va_degree' and entity == '1'").iloc[0]
    assert angle.relative_error == pytest.approx(0.1)


def test_missing_result_identity_fails(canonical_ac):
    reference = replace(canonical_ac, generators=canonical_ac.generators.iloc[1:])
    with pytest.raises(ValueError, match="identities"):
        compare_results(canonical_ac, reference, "ac_pf", Acceptance())


def test_independent_equations_detect_bad_flows_and_injections(canonical_ac, synthetic_native):
    audit, branches = audit_feasibility(
        canonical_ac, synthetic_native, "ac_pf", "unit", Acceptance()
    )
    assert not audit.loc[audit.enforced, "status"].eq("fail").any()
    assert branches.query("from_bus == 6 and to_bus == 8").iloc[0].utilization_percent > 111
    canonical_ac.branches.loc[9, "q_from_mvar"] += 0.1
    audit, _ = audit_feasibility(canonical_ac, synthetic_native, "ac_pf", "unit", Acceptance())
    assert audit.query("metric == 'terminal_flow_equation_error'").iloc[0].status == "fail"
    canonical_ac.generators.loc[0, "p_mw"] += 1
    audit, _ = audit_feasibility(canonical_ac, synthetic_native, "ac_pf", "unit", Acceptance())
    assert audit.query("metric == 'nodal_p_residual_mw'").iloc[0].status == "fail"


def test_dc_adapter_and_comparison_never_invent_ac_measurements():
    net = run_dc_power_flow(load_ieee30())
    canonical = normalize_pandapower(extract_results(net))
    fixture = {name: np.real(net._ppc[name]).copy() for name in ("bus", "gen", "branch")}
    fixture["bus"][:, 0] += 1
    fixture["gen"][:, 0] += 1
    fixture["branch"][:, :2] += 1
    fixture.update(cost=canonical.cost, solver_objective=[])
    other = normalize_matpower(fixture, dc=True)
    details, maxima = compare_results(canonical, other, "dc_pf", Acceptance())
    assert other.buses.vm_pu.isna().all() and other.generators.q_mvar.isna().all()
    assert maxima.query("quantity == 'vm_pu'").iloc[0].status == "not_applicable"
    assert not maxima.status.eq("fail").any()
    assert details.query("quantity == 'q_from_mvar'").absolute_error.isna().all()


def test_missing_external_runtime_cannot_pass_gate(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise RuntimeError("GNU Octave is required")

    monkeypatch.setattr("gridstress.validation.run_matpower", missing)
    config = Path(__file__).resolve().parents[1] / "experiments/validation/config.toml"
    with pytest.raises(RuntimeError, match="Octave"):
        run_validation(config, tmp_path, "not-an-executable", tmp_path / "out")
    assert (tmp_path / "out/failure.json").exists()
    assert not (tmp_path / "out/manifest.json").exists()


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_validation_tolerance(value):
    with pytest.raises(ValueError):
        Acceptance(voltage_pu=value)
