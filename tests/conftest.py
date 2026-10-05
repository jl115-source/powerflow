import pytest

from gridstress import extract_results, load_ieee30, run_ac_power_flow


@pytest.fixture
def net():
    return load_ieee30()


@pytest.fixture
def solved(net):
    return run_ac_power_flow(net)


@pytest.fixture
def results(solved):
    return extract_results(solved)
