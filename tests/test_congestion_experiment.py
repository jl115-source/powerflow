import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from gridstress.congestion import run_congestion
from gridstress.opf import OptimalPowerFlowError


def test_complete_comparison_and_failure_record(tmp_path):
    config = Path(__file__).resolve().parents[1] / "experiments/congestion/config.toml"
    output = run_congestion(config, tmp_path / "comparison")
    summary = pd.read_csv(output / "comparison.csv")
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "complete" and len(manifest["runs"]) == 7
    assert len(summary) == 7 and set(summary.model) == {"ac", "dc"}
    assert not (output / "failure.json").exists()
    assert len(list((output / "figures").glob("*.png"))) == 3
    for name, run in manifest["runs"].items():
        data = (output / "runs" / name / "network_input.json").read_bytes()
        assert hashlib.sha256(data).hexdigest() == run["input_sha256"]
    dc = summary.query("model == 'dc'")
    assert dc.min_vm_pu.isna().all() and dc.q_generation_mvar.isna().all()
    redispatch = pd.read_csv(output / "redispatch.csv")
    assert len(redispatch) == 30
    costs = pd.read_csv(output / "thermal_constraint_cost.csv").set_index("model")
    assert costs.loc["ac", "incremental_cost_per_hour"] > 2
    assert abs(costs.loc["dc", "incremental_cost_per_hour"]) < 1e-5
    with pytest.raises(FileExistsError):
        run_congestion(config, output)
    failed_config = tmp_path / "fails.toml"
    failed_config.write_text(config.read_text().replace("max_iteration = 150", "max_iteration = 1"))
    with pytest.raises(OptimalPowerFlowError):
        run_congestion(failed_config, tmp_path / "failed")
    failure = json.loads((tmp_path / "failed/failure.json").read_text())
    assert failure["variant"] == "ac_current"
    assert not (tmp_path / "failed/manifest.json").exists()
