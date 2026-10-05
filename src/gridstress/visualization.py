"""Publication-oriented diagnostics from backend-independent tables."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gridstress.results import ResultTables


def plot_baseline(results: ResultTables, directory: Path) -> list[Path]:
    """Save vector PDF and 300 dpi PNG plots without changing global styles."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
        }
    ):

        def save(fig: plt.Figure, name: str) -> None:
            for suffix in ("pdf", "png"):
                path = directory / f"{name}.{suffix}"
                fig.savefig(path, bbox_inches="tight")
                paths.append(path)
            plt.close(fig)

        bus = results.buses.sort_values("bus_id")
        fig, ax = plt.subplots(figsize=(7.2, 3.6), layout="constrained")
        ax.plot(bus.bus_id, bus.vm_pu, "o-", color="#186b8a", markersize=3, label="AC solution")
        ax.plot(bus.bus_id, bus.min_vm_pu, "--", color="#b54b30", label="Source limits")
        ax.plot(bus.bus_id, bus.max_vm_pu, "--", color="#b54b30")
        ax.set(
            xlabel="Pandapower bus ID (zero-based)",
            ylabel="Voltage magnitude (pu)",
            title="IEEE-30 baseline | Bus voltages",
        )
        ax.grid(axis="y", alpha=0.2)
        ax.legend(frameon=False)
        save(fig, "bus_voltages")

        branch = results.branches.sort_values("loading_percent", ascending=False)
        fig, ax = plt.subplots(figsize=(7.2, 7), layout="constrained")
        y = np.arange(len(branch))
        colors = np.where(branch.loading_percent > branch.max_loading_percent, "#b54b30", "#186b8a")
        ax.barh(y, branch.loading_percent, color=colors, height=0.7)
        ax.scatter(
            branch.max_loading_percent,
            y,
            marker="|",
            color="black",
            s=45,
            label="Source loading limit",
        )
        ax.set_yticks(
            y, [f"{r.element_id}: {r.from_bus}–{r.to_bus}" for r in branch.itertuples()], fontsize=7
        )
        ax.invert_yaxis()
        ax.set(
            xlabel="Current-based branch loading (%)",
            ylabel="Line ID: from–to bus ID",
            title="IEEE-30 baseline | Branch loading",
        )
        ax.legend(frameon=False, loc="lower right")
        save(fig, "branch_loading")

        gen = results.generators
        x = np.arange(len(gen))
        fig, axes = plt.subplots(1, 2, figsize=(8, 3.8), layout="constrained")
        for ax, quantity, unit in zip(axes, ("p_mw", "q_mvar"), ("MW", "MVAr"), strict=True):
            ax.bar(x, gen[quantity], color="#186b8a", width=0.55, label="Solved dispatch")
            ax.scatter(
                x, gen[f"min_{quantity}"], marker="_", color="#b54b30", s=150, label="Source limits"
            )
            ax.scatter(x, gen[f"max_{quantity}"], marker="_", color="#b54b30", s=150)
            ax.set_xticks(
                x,
                [f"{r.element_type}:{r.element_id}" for r in gen.itertuples()],
                rotation=45,
                ha="right",
                fontsize=8,
            )
            ax.set(
                ylabel=f"Generation ({unit})",
                title="Active power" if unit == "MW" else "Reactive power",
            )
            ax.axhline(0, color="black", linewidth=0.6)
            ax.grid(axis="y", alpha=0.2)
        axes[0].legend(frameon=False, fontsize=8)
        fig.suptitle("IEEE-30 baseline | Generator dispatch (including slack)")
        save(fig, "generator_dispatch")
    return paths


def plot_congestion(
    summary: pd.DataFrame, dispatch: pd.DataFrame, tables: dict[str, ResultTables], directory: Path
) -> list[Path]:
    """Plot costs, redispatch and the current/MVA distinction; vector and raster outputs."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
        }
    ):

        def save(fig: plt.Figure, name: str) -> None:
            for suffix in ("png", "pdf"):
                path = directory / f"{name}.{suffix}"
                fig.savefig(path, bbox_inches="tight")
                paths.append(path)
            plt.close(fig)

        labels = {
            "raw_ac_pf": "Raw AC PF",
            "raw_dc_pf": "Raw DC PF",
            "ac_current": "AC OPF · current",
            "ac_mva": "AC OPF · MVA",
            "ac_thermal_relaxed": "AC OPF · thermal relaxed",
            "dc_opf": "DC OPF",
            "dc_thermal_relaxed": "DC OPF · thermal relaxed",
        }
        fig, ax = plt.subplots(figsize=(8, 4.4), layout="constrained")
        y = np.arange(len(summary))
        ax.barh(
            y,
            summary.dispatch_cost_per_hour,
            color=["#186b8a" if m == "ac" else "#7c8791" for m in summary.model],
        )
        ax.set_yticks(y, [labels[name] for name in summary.run_id])
        ax.invert_yaxis()
        for yi, cost in zip(y, summary.dispatch_cost_per_hour, strict=True):
            ax.text(cost + 3, yi, f"{cost:.2f}", va="center", fontsize=9)
        ax.set(
            xlim=(0, summary.dispatch_cost_per_hour.max() * 1.15),
            xlabel="Dispatch cost (source cost units/hour)",
            title="IEEE-30 | Economic dispatch and thermal constraints",
        )
        ax.grid(axis="x", alpha=0.2)
        save(fig, "dispatch_costs")

        selected = dispatch.query("candidate == 'ac_current' and reference == 'raw_ac_pf'")
        fig, ax = plt.subplots(figsize=(7.2, 3.8), layout="constrained")
        ax.bar(
            np.arange(len(selected)),
            selected.delta_p_mw,
            color=np.where(selected.delta_p_mw >= 0, "#186b8a", "#b54b30"),
        )
        ax.set_xticks(
            np.arange(len(selected)),
            [f"{r.element_type}:{r.element_id}" for r in selected.itertuples()],
        )
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set(
            ylabel="Change in active generation (MW)",
            title="Current-constrained AC OPF minus raw AC PF",
        )
        ax.grid(axis="y", alpha=0.2)
        save(fig, "active_redispatch")

        source = tables["raw_ac_pf"].branches
        critical = source.loc[(source.loading_percent / source.max_loading_percent).idxmax()]
        ids = ["raw_ac_pf", "ac_thermal_relaxed", "ac_current", "ac_mva"]
        currents, apparent = [], []
        for name in ids:
            row = tables[name].branches.set_index("element_id").loc[critical.element_id]
            currents.append(row.loading_percent / row.max_loading_percent * 100)
            apparent.append(row.apparent_loading_percent / row.max_loading_percent * 100)
        fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
        x = np.arange(len(ids))
        ax.bar(x - 0.18, currents, width=0.36, color="#186b8a", label="Terminal current / I limit")
        ax.bar(x + 0.18, apparent, width=0.36, color="#c8853a", label="Terminal MVA / RATE_A")
        ax.axhline(100, color="#b54b30", linestyle="--", label="Source limit")
        ax.set_xticks(x, [labels[name] for name in ids], fontsize=9)
        ax.set(
            ylabel="Utilization of respective source limit (%)",
            title=f"Line {int(critical.element_id)} | Current and MVA constraints differ",
        )
        ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.15))
        save(fig, "current_vs_mva")
    return paths
