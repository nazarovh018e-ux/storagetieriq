"""
storagetieriq.reporting.dashboard
----------------------------------
Charts and the multi-panel PNG dashboard.

Uses the non-interactive "Agg" matplotlib backend so it renders headless
(CI servers, containers) without a display.  Import is isolated to this
module so the rest of the package works even if matplotlib is absent --
the CLI imports it lazily and degrades gracefully with ``--no-dashboard``.
"""

from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("Agg")  # headless rendering

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

warnings.filterwarnings("ignore")

# ── Color palette ────────────────────────────────────────────────────────
TIER_COLORS = {
    "hot": "#E8593C",
    "warm": "#F2A623",
    "cold": "#1D9E75",
    "HOT": "#E8593C",
    "WARM": "#F2A623",
    "COLD": "#1D9E75",
}
BG_COLOR = "#FAFAF8"
CARD_COLOR = "#FFFFFF"
TEXT_COLOR = "#2C2C2A"
MUTED = "#888780"


def _set_style():
    plt.rcParams.update(
        {
            "figure.facecolor": BG_COLOR,
            "axes.facecolor": CARD_COLOR,
            "axes.edgecolor": "#D3D1C7",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.labelcolor": TEXT_COLOR,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": TEXT_COLOR,
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlepad": 10,
        }
    )


# ── Individual plots ──────────────────────────────────────────────────────
def plot_tier_distribution(classified: pd.DataFrame, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    counts = classified["tier"].value_counts().reindex(["hot", "warm", "cold"]).fillna(0)
    colors = [TIER_COLORS[t] for t in counts.index]
    wedges, texts, autotexts = ax.pie(
        counts.values,
        labels=[t.upper() for t in counts.index],
        colors=colors,
        autopct="%1.1f%%",
        startangle=90,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=10),
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color("white")
        at.set_fontweight("bold")
    ax.set_title("Record Distribution by Tier")
    return ax


def plot_storage_by_tier(classified: pd.DataFrame, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 3))
    data = (classified.groupby("tier")["size_mb"].sum() / 1024).reindex(
        ["hot", "warm", "cold"]
    ).fillna(0)
    colors = [TIER_COLORS[t] for t in data.index]
    bars = ax.barh(
        [t.upper() for t in data.index],
        data.values,
        color=colors,
        height=0.5,
        edgecolor="white",
    )
    for bar, val in zip(bars, data.values):
        ax.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f} GB",
            va="center",
            fontsize=9,
            color=MUTED,
        )
    ax.set_xlabel("Total Storage (GB)")
    ax.set_title("Storage Volume per Tier")
    ax.set_xlim(0, max(data.max() * 1.2, 1))
    return ax


def plot_cost_comparison(result: dict, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    per_tier = result["per_tier"]
    tiers = per_tier["tier"].tolist()
    storage_costs = per_tier["storage_cost_$"].tolist()
    retrieval_costs = per_tier["retrieval_cost_$"].tolist()
    x = np.arange(len(tiers))
    w = 0.35
    b1 = ax.bar(
        x - w / 2,
        storage_costs,
        w,
        label="Storage cost",
        color=[TIER_COLORS[t] for t in tiers],
        alpha=0.9,
        edgecolor="white",
    )
    ax.bar(
        x + w / 2,
        retrieval_costs,
        w,
        label="Retrieval cost",
        color=[TIER_COLORS[t] for t in tiers],
        alpha=0.4,
        edgecolor="white",
        hatch="///",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(tiers)
    ax.set_ylabel("Monthly Cost ($)")
    ax.set_title("Cost Breakdown per Tier")
    ax.legend(fontsize=8)
    for bar in b1:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            h + 0.2,
            f"${h:.2f}",
            ha="center",
            fontsize=8,
            color=MUTED,
        )
    return ax


def plot_cost_waterfall(result: dict, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    baseline = result["baseline"]
    tiered = result["tiered_total"]
    saving = result["monthly_savings"]
    categories = ["Flat SSD\n(baseline)", "Savings", "Tiered\n(actual)"]
    colors = ["#E8593C", "#1D9E75", "#1D9E75"]
    bars = ax.bar(
        categories,
        [baseline, saving, tiered],
        bottom=[0, tiered, 0],
        color=colors,
        alpha=0.85,
        edgecolor="white",
        width=0.5,
    )
    ax.set_ylabel("Monthly Cost ($)")
    ax.set_title("Cost Savings Waterfall")
    for bar, val, bot in zip(bars, [baseline, saving, tiered], [0, tiered, 0]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bot + bar.get_height() / 2,
            f"${abs(val):.2f}",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="white",
        )
    pct = result["savings_pct"]
    ax.text(
        1,
        tiered + saving * 0.5 + saving * 0.08,
        f"down {pct:.1f}%",
        ha="center",
        fontsize=9,
        color="#1D9E75",
        fontweight="bold",
    )
    return ax


def plot_age_access_scatter(classified: pd.DataFrame, ax=None, sample: int = 2000):
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4))
    sample_df = classified.sample(min(sample, len(classified)), random_state=42)
    for tier in ["cold", "warm", "hot"]:
        sub = sample_df[sample_df["tier"] == tier]
        ax.scatter(
            sub["age_days"],
            sub["access_count"],
            c=TIER_COLORS[tier],
            alpha=0.35,
            s=12,
            label=tier.upper(),
            rasterized=True,
        )
    ax.set_xlabel("Age (days)")
    ax.set_ylabel("Access Count")
    ax.set_title("Age vs Access Count (colored by assigned tier)")
    ax.legend(fontsize=8, markerscale=2)
    return ax


def plot_sensitivity(sens_df: pd.DataFrame, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    ax.plot(
        sens_df["hot_$/gb"],
        sens_df["annual_saving"],
        marker="o",
        color="#E8593C",
        linewidth=2,
        markersize=6,
    )
    ax.fill_between(
        sens_df["hot_$/gb"], sens_df["annual_saving"], alpha=0.12, color="#E8593C"
    )
    ax.set_xlabel("Hot-tier price ($/GB/month)")
    ax.set_ylabel("Annual Savings ($)")
    ax.set_title("Savings Sensitivity to Hot-Tier Price")
    for _, row in sens_df.iterrows():
        ax.annotate(
            f"${row['annual_saving']:.0f}",
            (row["hot_$/gb"], row["annual_saving"]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
            color=MUTED,
        )
    return ax


def plot_data_type_heatmap(classified: pd.DataFrame, ax=None):
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4))
    pivot = (
        classified.groupby(["data_type", "tier"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["hot", "warm", "cold"], fill_value=0)
    )
    pivot_pct = pivot.div(pivot.sum(axis=1).replace(0, 1), axis=0) * 100
    bottom = np.zeros(len(pivot_pct))
    for tier in ["hot", "warm", "cold"]:
        if tier in pivot_pct.columns:
            vals = pivot_pct[tier].values
            ax.bar(
                pivot_pct.index,
                vals,
                bottom=bottom,
                label=tier.upper(),
                color=TIER_COLORS[tier],
                alpha=0.85,
                edgecolor="white",
            )
            bottom += vals
    ax.set_xlabel("Data Type")
    ax.set_ylabel("% of Records")
    ax.set_title("Tier Distribution by Data Type")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_ylim(0, 105)
    return ax


# ── Full dashboard ─────────────────────────────────────────────────────────
def build_dashboard(
    classified: pd.DataFrame,
    result: dict,
    sens_df: pd.DataFrame,
    policy_name: str = "default",
    output_path: str = "storage_tiering_dashboard.png",
) -> str:
    """Assemble the multi-panel dashboard and save to PNG. Returns the path."""
    _set_style()
    fig = plt.figure(figsize=(18, 13), facecolor=BG_COLOR)
    fig.suptitle(
        f"StorageTierIQ - Cost-Optimized Storage Tiering Report  ·  "
        f"Policy: '{policy_name}'",
        fontsize=16,
        fontweight="bold",
        color=TEXT_COLOR,
        y=0.97,
    )
    gs = GridSpec(
        3, 3, figure=fig, hspace=0.42, wspace=0.35,
        left=0.06, right=0.97, top=0.92, bottom=0.06,
    )
    plot_tier_distribution(classified, ax=fig.add_subplot(gs[0, 0]))
    plot_storage_by_tier(classified, ax=fig.add_subplot(gs[0, 1]))
    plot_cost_waterfall(result, ax=fig.add_subplot(gs[0, 2]))
    plot_cost_comparison(result, ax=fig.add_subplot(gs[1, 0:2]))
    plot_age_access_scatter(classified, ax=fig.add_subplot(gs[1, 2]))
    plot_data_type_heatmap(classified, ax=fig.add_subplot(gs[2, 0:2]))
    plot_sensitivity(sens_df, ax=fig.add_subplot(gs[2, 2]))

    kpi_labels = [
        ("Total Data", f"{result['total_gb']:.1f} GB"),
        ("Baseline Cost", f"${result['baseline']:,.2f}/mo"),
        ("Tiered Cost", f"${result['tiered_total']:,.2f}/mo"),
        ("Monthly Savings", f"${result['monthly_savings']:,.2f}"),
        ("Savings %", f"{result['savings_pct']:.1f}%"),
        ("Annual Savings", f"${result['annual_savings']:,.2f}"),
    ]
    for i, (label, val) in enumerate(kpi_labels):
        fig.text(
            0.01 + i * 0.165, 0.97, f"{label}: {val}",
            ha="left", va="top", fontsize=7.5, color=TEXT_COLOR,
            transform=fig.transFigure,
        )

    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    return output_path


__all__ = ["build_dashboard"]
