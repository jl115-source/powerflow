"""Pandapower network adapter. Source parameters are never rewritten."""

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
