"""Pandapower network adapter. Source parameters are never rewritten."""

from copy import deepcopy
from dataclasses import asdict, dataclass

import numpy as np
from pandapower import pandapowerNet, reset_results
from pandapower.networks import case30


def load_ieee30() -> pandapowerNet:
    """Return a fresh PYPOWER-derived case30, distinct from case_ieee30.

    Preserve source IDs, ratings, setpoints, limits, shunts and cost coefficients.
    Pandapower bus indices are zero-based; source bus names remain available.
    """
    net = case30()
    # The bundled JSON carries a stale convergence flag; clear solver state only.
    reset_results(net)
    net.converged = False
    net.OPF_converged = False
    return net


@dataclass(frozen=True)
class OPFPolicy:
    """Explicit case30 study decisions; numerical limits and costs stay original.

    All six sources dispatch within source P/Q and bus voltage bounds. Demand
    cannot participate in dispatch. Disabling thermal limits creates a labelled
    network-constrained economic-dispatch counterfactual (not copper-plate ED).
    """

    name: str = "source_bounds_dispatch"
    thermal_limits: bool = True

    def __post_init__(self) -> None:
        if self.name != "source_bounds_dispatch" or type(self.thermal_limits) is not bool:
            raise ValueError("Unsupported OPF policy")


def build_study_case30(policy: OPFPolicy | None = None) -> pandapowerNet:
    """Construct source_case30 + explicit OPF policy, without altering source data.

    Source loading limits remain in the study network even for the thermal-relaxed
    counterfactual, so result diagnostics can measure violations against them.
    Only the OPF solver's private copy removes them when the policy requests it.
    """
    policy = policy or OPFPolicy()
    net = deepcopy(load_ieee30())
    for kind in ("gen", "ext_grid"):
        net[kind]["controllable"] = True
        for quantity in ("p_mw", "q_mvar"):
            limits = net[kind][[f"min_{quantity}", f"max_{quantity}"]]
            if not np.isfinite(limits.to_numpy()).all():
                raise ValueError(f"Missing {kind} {quantity} bounds")
            if (limits.iloc[:, 0] > limits.iloc[:, 1]).any():
                raise ValueError(f"Inverted {kind} {quantity} bounds")
    net.load["controllable"] = False
    net["gridstress_policy"] = asdict(policy)
    return net
