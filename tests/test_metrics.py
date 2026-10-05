from dataclasses import replace

import numpy as np
import pytest

from gridstress.metrics import DiagnosticOptions, constraint_diagnostics


@pytest.mark.parametrize(
    "value,status", [(94, "ok"), (95, "near_limit"), (100, "at_limit"), (101, "violated")]
)
def test_loading_thresholds(results, value, status):
    branches = results.branches.copy()
    branches.loc[0, ["loading_percent", "max_loading_percent"]] = [value, 100]
    result = constraint_diagnostics(replace(results, branches=branches))
    row = result.query("element_type == 'line' and element_id == 0").iloc[0]
    assert row.status == status
    assert row.slack == pytest.approx(100 - value)


def test_lower_voltage_upper_generator_and_missing_rating(results):
    buses, generators, branches = (
        results.buses.copy(),
        results.generators.copy(),
        results.branches.copy(),
    )
    buses.loc[0, "vm_pu"] = buses.loc[0, "min_vm_pu"] - 0.01
    generators.loc[0, "p_mw"] = generators.loc[0, "max_p_mw"]
    branches.loc[0, "max_loading_percent"] = np.nan
    diag = constraint_diagnostics(
        replace(results, buses=buses, generators=generators, branches=branches)
    )
    assert (
        diag.query("element_type == 'bus' and element_id == 0 and bound == 'lower'").iloc[0].status
        == "violated"
    )
    assert (
        diag.query("element_type == 'ext_grid' and quantity == 'p_mw' and bound == 'upper'")
        .iloc[0]
        .status
        == "at_limit"
    )
    assert diag.query("element_type == 'line' and element_id == 0").iloc[0].status == "unrated"


def test_out_of_service_elements_excluded(results):
    branches = results.branches.copy()
    branches.loc[0, "in_service"] = False
    diag = constraint_diagnostics(replace(results, branches=branches))
    assert diag.query("element_type == 'line' and element_id == 0").empty


def test_nonfinite_result_fails(results):
    buses = results.buses.copy()
    buses.loc[0, "vm_pu"] = np.nan
    with pytest.raises(ValueError, match="Nonfinite"):
        constraint_diagnostics(replace(results, buses=buses))


def test_negative_threshold_rejected():
    with pytest.raises(ValueError):
        DiagnosticOptions(near_voltage_pu=-1)
