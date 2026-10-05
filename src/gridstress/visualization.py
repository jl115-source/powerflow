"""Publication-oriented diagnostics from backend-independent tables."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

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
