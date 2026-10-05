"""Independent MATPOWER process boundary, input audit and keyed case30 adapters."""

import hashlib
import json
import shutil
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pandapower.converter import to_ppc

from gridstress.networks import build_study_case30, load_ieee30
from gridstress.results import ResultTables

ARCHIVE_SHA256 = "7f13b1441669a64e312d14a60e564cd91977ff1676ff77d25538e94ff313dd56"
RUNS = ("ac_pf", "dc_pf", "ac_current_opf", "ac_mva_opf", "dc_opf")


@dataclass
class CanonicalResult:
    """Original MATPOWER bus numbers and oriented endpoint keys; no row-order matching."""

    buses: pd.DataFrame
    generators: pd.DataFrame
    branches: pd.DataFrame
    cost: float
    objective: float | None

    def export(self, directory: Path) -> None:
        """Write raw canonical measurements; unavailable DC fields remain NaN."""
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("buses", "generators", "branches"):
            getattr(self, name).to_csv(directory / f"{name}.csv", index=False)


def keyed(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Require complete, unique identities before any alignment."""
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"Missing or ambiguous identity: {keys}")
    return frame.set_index(keys).sort_index()


def normalize_pandapower(result: ResultTables) -> CanonicalResult:
    """Translate source IDs using retained bus names, including the slack generator."""
    source = load_ieee30()
    mapping = source.bus.name.astype(int).to_dict()
    bus = result.buses[["bus_id", "vm_pu", "va_degree"]].copy()
    bus.bus_id = bus.bus_id.map(mapping)
    gen = result.generators[["bus_id", "p_mw", "q_mvar"]].copy()
    gen.bus_id = gen.bus_id.map(mapping)
    branch = result.branches[
        ["from_bus", "to_bus", "p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"]
    ].copy()
    for col in ("from_bus", "to_bus"):
        branch[col] = branch[col].map(mapping)
    for frame, keys in ((bus, ["bus_id"]), (gen, ["bus_id"]), (branch, ["from_bus", "to_bus"])):
        keyed(frame, keys)
    summary = result.summary.iloc[0]
    return CanonicalResult(
        bus, gen, branch, float(summary.dispatch_cost_per_hour), summary.objective_cost_per_hour
    )


def normalize_matpower(record: dict, dc: bool) -> CanonicalResult:
    """Read actual MATPOWER result matrices, discarding artificial DC Q/V values."""
    bus, gen, branch = (np.asarray(record[name], dtype=float) for name in ("bus", "gen", "branch"))
    b = pd.DataFrame({"bus_id": bus[:, 0].astype(int), "vm_pu": bus[:, 7], "va_degree": bus[:, 8]})
    g = pd.DataFrame({"bus_id": gen[:, 0].astype(int), "p_mw": gen[:, 1], "q_mvar": gen[:, 2]})
    lines = pd.DataFrame(
        {
            "from_bus": branch[:, 0].astype(int),
            "to_bus": branch[:, 1].astype(int),
            "p_from_mw": branch[:, 13],
            "q_from_mvar": branch[:, 14],
            "p_to_mw": branch[:, 15],
            "q_to_mvar": branch[:, 16],
        }
    )
    if dc:
        b["vm_pu"] = np.nan
        g["q_mvar"] = np.nan
        lines[["q_from_mvar", "q_to_mvar"]] = np.nan
    for frame, keys in ((b, ["bus_id"]), (g, ["bus_id"]), (lines, ["from_bus", "to_bus"])):
        keyed(frame, keys)
    objective = record["solver_objective"]
    return CanonicalResult(
        b, g, lines, float(record["cost"]), None if isinstance(objective, list) else float(objective)
    )


def input_parity(native: dict, tolerance: float) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Compare effective case30 inputs, explicitly classifying representation differences.

    The OPF conversion retains all source physical bounds. PF shares these physical
    data but ignores the bounds. Native MATPOWER case30 is never overwritten.
    """
    net = build_study_case30()
    converted = deepcopy(net)
    ppc = to_ppc(converted, init="flat", mode="opf")
    labels = net.bus.name.astype(int).to_dict()
    # Explicit map from pandapower's converter bus IDs to original source labels.
    converter_bus = {
        int(converted["_pd2ppc_lookups"]["bus"][idx]): label for idx, label in labels.items()
    }
    ppc["bus"][:, 0] = [converter_bus[int(i)] for i in ppc["bus"][:, 0]]
    ppc["gen"][:, 0] = [converter_bus[int(i)] for i in ppc["gen"][:, 0]]
    for col in (0, 1):
        ppc["branch"][:, col] = [converter_bus[int(i)] for i in ppc["branch"][:, col]]
    names = {
        "bus": [
            "bus_id",
            "type",
            "pd",
            "qd",
            "gs",
            "bs",
            "area",
            "vm",
            "va",
            "base_kv",
            "zone",
            "vmax",
            "vmin",
        ],
        "gen": ["bus_id", "pg", "qg", "qmax", "qmin", "vg", "mbase", "status", "pmax", "pmin"],
        "branch": [
            "from_bus",
            "to_bus",
            "r",
            "x",
            "b",
            "rate_a",
            "rate_b",
            "rate_c",
            "tap",
            "shift",
            "status",
            "angmin",
            "angmax",
        ],
    }
    rows = []

    def add(table: str, entity: str, field: str, a: float, b: float, note: str = "") -> None:
        both_finite = bool(np.isfinite(a) and np.isfinite(b))
        difference = abs(a - b) if both_finite else np.nan
        status = (
            "documented_exception"
            if note
            else ("pass" if both_finite and difference <= tolerance else "fail")
        )
        rows.append(
            dict(
                table=table,
                entity=entity,
                field=field,
                pandapower=a,
                matpower=b,
                absolute_difference=difference,
                status=status,
                explanation=note,
            )
        )

    add("system", "system", "base_mva", float(ppc["baseMVA"]), float(native["baseMVA"]))
    for table, columns in names.items():
        keys = ["from_bus", "to_bus"] if table == "branch" else ["bus_id"]
        left = keyed(pd.DataFrame(np.real(ppc[table][:, : len(columns)]), columns=columns), keys)
        right = keyed(
            pd.DataFrame(np.asarray(native[table])[:, : len(columns)], columns=columns), keys
        )
        if not left.index.equals(right.index):
            raise ValueError(
                f"Input {table} identities do not match (parallel circuits unsupported)"
            )
        for idx in left.index:
            for field in left.columns:
                a, b = float(left.at[idx, field]), float(right.at[idx, field])
                note = ""
                if table == "bus" and field in ("area", "zone"):
                    note = "Metadata only; no area/zone constraints in these five formulations"
                elif table == "gen" and field == "mbase":
                    note = "Unused generator nameplate base; network equations use system baseMVA"
                elif table == "gen" and field == "pg" and idx == 1:
                    note = ("Initial slack PG is solved by PF; "
                            "OPF ignores initial dispatch (interior start)")
                elif table == "branch" and field in ("rate_b", "rate_c"):
                    note = "Emergency ratings unused; RATE_A is the matched operative limit"
                elif table == "branch" and field == "tap":
                    a, b = (1.0 if a == 0 else a), (1.0 if b == 0 else b)
                add(table, str(idx), field, a, b, note)
    # Costs are keyed to each generator's original bus, not native/converter row order.
    for case, key in ((ppc, "pp"), (native, "mp")):
        matrix = np.asarray(case["gencost"], dtype=float)
        gens = np.asarray(case["gen"], dtype=float)
        if matrix.shape != (len(gens), 7):
            raise ValueError("Validation requires six quadratic active-power costs, no Q costs")
        frame = pd.DataFrame(
            matrix, columns=["model", "startup", "shutdown", "n", "c2", "c1", "c0"]
        )
        frame.insert(0, "bus_id", gens[:, 0].astype(int))
        if key == "pp":
            costs = keyed(frame, ["bus_id"])
        else:
            reference = keyed(frame, ["bus_id"])
    if not costs.index.equals(reference.index):
        raise ValueError("Cost identities do not match")
    for idx in costs.index:
        for field in costs.columns:
            add(
                "gencost",
                str(idx),
                field,
                float(costs.at[idx, field]),
                float(reference.at[idx, field]),
            )
    mappings = {
        "buses": pd.DataFrame(
            {"pandapower_bus_id": list(labels), "matpower_bus_id": list(labels.values())}
        ),
        "generators": pd.concat(
            [
                pd.DataFrame(
                    {
                        "element_type": kind,
                        "element_id": net[kind].index,
                        "matpower_bus_id": net[kind].bus.map(labels),
                    }
                )
                for kind in ("ext_grid", "gen")
            ],
            ignore_index=True,
        ),
        "branches": pd.DataFrame(
            {
                "pandapower_line_id": net.line.index,
                "matpower_from_bus": net.line.from_bus.map(labels),
                "matpower_to_bus": net.line.to_bus.map(labels),
            }
        ),
    }
    return pd.DataFrame(rows), mappings


def run_matpower(root: Path, octave: str, settings: dict, output: Path) -> dict:
    """Run a separate Octave process against verified official sources; timeout is fatal."""
    root = root.resolve()
    provenance = json.loads((root.parent / "provenance.json").read_text())
    if provenance["archive_sha256"] != ARCHIVE_SHA256:
        raise ValueError("Unrecognized MATPOWER archive")
    for name, digest in provenance["files"].items():
        path = (root.parent / name).resolve()
        if (
            not path.is_relative_to(root.parent)
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError(f"MATPOWER source integrity failed: {name}")
    executable = shutil.which(octave)
    if executable is None:
        raise RuntimeError("GNU Octave is required; independent validation cannot be simulated")
    settings_file = output / "solver_settings.json"
    settings_file.write_text(json.dumps(settings, indent=2))
    raw_file = output / "matpower_raw.json"

    def quote(path: Path) -> str:
        return "'" + str(path.resolve()).replace("'", "''") + "'"

    expression = (
        f"addpath({quote(Path(__file__).parent)}); "
        f"matpower_bridge({quote(root)}, {quote(settings_file)}, {quote(raw_file)});"
    )
    process = subprocess.run(
        [executable, "--no-gui", "--quiet", "--eval", expression],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    (output / "octave_stdout.log").write_text(process.stdout)
    (output / "octave_stderr.log").write_text(process.stderr)
    if process.returncode != 0 or not raw_file.exists():
        raise RuntimeError(f"MATPOWER process failed ({process.returncode}); inspect octave logs")
    data = json.loads(raw_file.read_text())
    if data["matpower_version"] != "8.1" or set(data["runs"]) != set(RUNS):
        raise ValueError("Wrong MATPOWER version or incomplete run set")
    if not all(data["runs"][name]["success"] for name in RUNS):
        raise RuntimeError("MATPOWER reported nonconvergence")
    return data
