"""Deterministic scenario transformations, always applied to a fresh copy."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from math import isfinite

from pandapower import pandapowerNet, reset_results


@dataclass(frozen=True)
class DemandScenario:
    """Scale all source P/Q demand at constant power factor; no random sampling."""

    name: str = "base_demand"
    demand_scale: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not isfinite(self.demand_scale) or self.demand_scale <= 0:
            raise ValueError("Scenario needs a name and a finite positive demand_scale")


def apply_scenario(net: pandapowerNet, scenario: DemandScenario) -> pandapowerNet:
    """Return an explicitly labelled single transformation, never compound scenarios."""
    if "gridstress_scenario" in net:
        raise ValueError("Apply each scenario to the original study network, not another scenario")
    study = deepcopy(net)
    study.load.loc[:, ["p_mw", "q_mvar"]] *= scenario.demand_scale
    reset_results(study)
    study.converged = False
    study.OPF_converged = False
    study.pop("gridstress_solution", None)
    study["gridstress_scenario"] = asdict(scenario)
    return study
