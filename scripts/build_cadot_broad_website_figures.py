#!/usr/bin/env python3
"""Build website-facing Cadot figures from the broad-156 saved outputs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = (
    ROOT
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_hump_tribunal_tables"
)
FIGURE_DIR = (
    ROOT
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_hump_tribunal_figures"
)

NAVY = "#173b5e"
ORANGE = "#c4572d"
GREY = "#666666"
LIGHT_GREY = "#d9dde2"


def build_old_cone_figure() -> None:
    """Plot raw mismatch-bin exit rates and state the controlled interaction."""
    deciles = pd.read_csv(TABLE_DIR / "old_cone_exit_by_mismatch_decile.csv")
    models = pd.read_csv(TABLE_DIR / "old_cone_exit_models.csv")
    diagnostics = json.loads(
        (TABLE_DIR / "cadot_hump_diagnostics.json").read_text(encoding="utf-8")
    )

    primary = models[
        models["primary_spec"].astype(str).str.lower().eq("true")
        & models["term"].eq("mismatch_x_rich_side")
    ]
    if len(primary) != 1:
        raise RuntimeError("Expected one primary broad-156 old-cone interaction.")
    interaction = primary.iloc[0]

    # Very small bins are visually unstable. Keep them in the downloadable
    # table but require at least 1,000 product windows in the plotted series.
    plotted = deciles[deciles["rows"].ge(1_000)].copy()
    if plotted.empty:
        raise RuntimeError("No adequately supported old-cone bins to plot.")

    fig, ax = plt.subplots(figsize=(10.5, 6.3))
    styles = {
        0: ("Below rich-side cutoff", GREY),
        1: ("Above rich-side cutoff", ORANGE),
    }
    for rich_side, group in plotted.groupby("rich_side_ct", sort=True):
        label, color = styles[int(rich_side)]
        group = group.sort_values("median_mismatch")
        ax.plot(
            group["median_mismatch"],
            group["exit_rate"],
            marker="o",
            markersize=5,
            linewidth=2.2,
            color=color,
            label=label,
            zorder=3,
        )
        last = group.iloc[-1]
        ax.annotate(
            label,
            (last["median_mismatch"], last["exit_rate"]),
            xytext=(7, 0),
            textcoords="offset points",
            color=color,
            fontsize=9,
            va="center",
        )

    ax.axvline(0, color=LIGHT_GREY, linewidth=1.0, linestyle=(0, (3, 3)))
    ax.text(
        0,
        0.005,
        "income matches product PRODY",
        color="#777777",
        fontsize=8,
        ha="center",
        va="bottom",
    )
    ax.set_xlabel("Income–product mismatch: log(country GDP per capita / product PRODY)")
    ax.set_ylabel("Share of active HS4 products exiting within five years")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.grid(axis="y", color="#eceff2", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend().remove()

    threshold = diagnostics["turning_point"]
    rich_cutoff = threshold["rich_side_ppp_constant_2021_intl_usd_used"]
    ax.set_title(
        "Among richer country-years, product exit rises with income–PRODY mismatch",
        loc="left",
        fontsize=13.5,
        fontweight="bold",
        pad=18,
    )
    ax.text(
        0,
        1.015,
        (
            "Broad 156 sample, 2000–2024; raw mismatch-bin rates. "
            f"Rich side = observed income p75 (${rich_cutoff:,.0f}), not an estimated turning point."
        ),
        transform=ax.transAxes,
        fontsize=9,
        color="#555555",
        va="bottom",
    )
    fig.text(
        0.10,
        0.025,
        (
            f"Controlled interaction: +{100 * interaction['coef']:.2f} percentage points "
            f"per +1 log mismatch (reporter-clustered p={interaction['p_value']:.2g}).\n"
            "Interpret the slope difference, not the vertical gap; the plotted rates are descriptive."
        ),
        fontsize=8.5,
        color="#444444",
        va="bottom",
    )
    fig.subplots_adjust(left=0.10, right=0.83, top=0.82, bottom=0.22)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_DIR / "old_cone_exit_plot.png", dpi=200)
    plt.close(fig)


def build_quadratic_term_figure() -> None:
    """Replace the legacy rd2 robustness image with a broad-156 equivalent."""
    models = pd.read_csv(TABLE_DIR / "cadot_hump_models.csv")
    work = models[
        models["model_label"].eq("quadratic_controls_year_fe_country_cluster")
        & models["term"].eq("log_income_pc_sq")
    ].copy()
    labels = {
        "product_gini": "Active-product Gini",
        "product_theil_fixed_universe": "Fixed-universe Theil",
        "product_hhi": "Product HHI",
        "log_active_product_count": "Log active-product count",
        "top_product_1pct_share": "Top-1% product share",
    }
    work["label"] = work["metric"].map(labels)
    work = work.dropna(subset=["label", "coefficient", "std_error"]).copy()
    if len(work) != len(labels):
        raise RuntimeError("Broad-156 quadratic-term figure is missing outcomes.")

    work = work.sort_values("coefficient")
    y = np.arange(len(work))
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.errorbar(
        work["coefficient"],
        y,
        xerr=1.96 * work["std_error"],
        fmt="o",
        color=NAVY,
        ecolor="#9aa3ad",
        capsize=3,
    )
    ax.axvline(0, color="#333333", linewidth=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(work["label"])
    ax.set_xlabel("Quadratic log-income coefficient (95% clustered CI)")
    ax.set_title(
        "Broad 156: curvature differs across concentration measures",
        loc="left",
        fontsize=13,
        fontweight="bold",
    )
    ax.text(
        0,
        1.02,
        "Controlled year-FE models; coefficient magnitudes are not comparable across differently scaled outcomes.",
        transform=ax.transAxes,
        fontsize=8.5,
        color="#555555",
        va="bottom",
    )
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color="#eceff2", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "mechanical_robustness_ladder.png", dpi=200)
    plt.close(fig)


def validate_inputs() -> None:
    diagnostics = json.loads(
        (TABLE_DIR / "cadot_hump_diagnostics.json").read_text(encoding="utf-8")
    )
    required = {
        "country_sample": "cadot_broad_156",
        "selected_reporters": 156,
        "observed_reporters": 156,
        "reporters_in_episode_scorecard": 156,
    }
    failures = {
        key: (diagnostics.get(key), expected)
        for key, expected in required.items()
        if diagnostics.get(key) != expected
    }
    if failures:
        raise RuntimeError(f"Broad-156 website figure lineage failed: {failures}")


def main() -> None:
    validate_inputs()
    build_old_cone_figure()
    build_quadratic_term_figure()
    print(f"Built broad-156 website figures under {FIGURE_DIR}")


if __name__ == "__main__":
    main()
