import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from gridstress.baseline import run_baseline


def test_reproducible_complete_experiment_and_no_overwrite(tmp_path):
    config = Path(__file__).resolve().parents[1] / "experiments/baseline/config.toml"
    first = run_baseline(config, tmp_path / "first")
    second = run_baseline(config, tmp_path / "second")
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["converged"] and not manifest["optimal_dispatch"]
    assert (
        manifest["network_sha256"]
        == hashlib.sha256((first / "network_input.json").read_bytes()).hexdigest()
    )
    assert (
        manifest["network_sha256"]
        == json.loads((second / "manifest.json").read_text())["network_sha256"]
    )
    assert len(list((first / "tables").glob("*.csv"))) == 7
    assert len(list((first / "figures").glob("*.pdf"))) == 3
    assert len(list((first / "figures").glob("*.png"))) == 3
    for path in (first / "tables").glob("*.csv"):
        pd.testing.assert_frame_equal(pd.read_csv(path), pd.read_csv(second / "tables" / path.name))
    with pytest.raises(FileExistsError):
        run_baseline(config, first)


def test_unknown_config_key_fails(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[experiment]\nname="wrong"\n')
    with pytest.raises(ValueError, match="sections"):
        run_baseline(path, tmp_path / "bad-output")
    assert not (tmp_path / "bad-output").exists()
