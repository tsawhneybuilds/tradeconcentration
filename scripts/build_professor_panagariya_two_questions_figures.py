#!/usr/bin/env python3
"""Build two question-led figures for the Professor Panagariya results brief.

Figure 1 contract:
Question: Were larger-GDP countries more exposed to globally large products?
Answer: The annual rank correlation was positive in 23 of 25 years.
Comparison: Annual Spearman correlations against zero.
Unit: Year.
Sample: rd2_countries exports, 2000-2024.

Figure 2 contract:
Question: Does the level-PPP product-concentration hump survive country fixed effects?
Answer: The export quadratic disappears, while the import quadratic becomes smaller.
Comparison: Pooled and country-fixed-effect quadratic estimates with 95% intervals.
Unit: Regression specification.
Sample: cadot_broad_156 complete-case panel, 2000-2024.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


BASE = Path(__file__).resolve().parents[1]
OUT_DIR = BASE / "results" / "prof_p_replication" / "figures"

YEARLY_PATH = (
    BASE
    / "results"
    / "samples"
    / "rd2_countries"
    / "world_large_product_exposure_tables"
    / "world_large_product_exposure_yearly_spearman.csv"
)
HUMP_MODELS_PATH = (
    BASE
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_broad_ppp_hump_regression_tables"
    / "ppp_hump_regression_models.csv"
)
HUMP_SUMMARY_PATH = (
    BASE
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_broad_ppp_hump_regression_tables"
    / "ppp_hump_regression_summary.csv"
)

INK = "#202124"
MUTED = "#6b7280"
LIGHT = "#d9dde3"
BLUE = "#246a8d"
RED = "#b44335"
GRAY = "#858b91"


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 15,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": MUTED,
            "axes.linewidth": 0.8,
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )


def save_figure(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=240, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def build_world_product_exposure_figure() -> None:
    yearly = pd.read_csv(YEARLY_PATH)
    plot = yearly[
        yearly["outcome"].eq("world_share_exposure")
        & yearly["size_variable"].eq("log_gdp_current_usd")
    ].copy()
    plot = plot.sort_values("year")
    if len(plot) != 25:
        raise RuntimeError(f"Expected 25 annual GDP exposure correlations, found {len(plot)}.")

    positive_years = int(plot["spearman_size_outcome"].gt(0).sum())
    mean_corr = float(plot["spearman_size_outcome"].mean())
    recent = plot[plot["year"].isin([2023, 2024])].copy()

    fig, ax = plt.subplots(figsize=(9.0, 5.1))
    ax.axhline(0, color=INK, linewidth=0.9)
    ax.axhline(mean_corr, color=GRAY, linewidth=1.1, linestyle=(0, (3, 3)))
    ax.plot(
        plot["year"],
        plot["spearman_size_outcome"],
        color=BLUE,
        linewidth=1.8,
        zorder=2,
    )
    ax.scatter(
        plot["year"],
        plot["spearman_size_outcome"],
        s=30,
        color=BLUE,
        edgecolor="white",
        linewidth=0.55,
        zorder=3,
    )
    ax.scatter(
        recent["year"],
        recent["spearman_size_outcome"],
        s=42,
        color=RED,
        edgecolor="white",
        linewidth=0.65,
        zorder=4,
    )

    ax.text(
        2000.2,
        mean_corr + 0.012,
        f"Mean = {mean_corr:.2f}",
        color=MUTED,
        fontsize=9.5,
        va="bottom",
    )
    for row in recent.itertuples(index=False):
        ax.annotate(
            f"{int(row.year)}: {row.spearman_size_outcome:.2f}",
            xy=(row.year, row.spearman_size_outcome),
            xytext=(-7, -18 if row.year == 2023 else 9),
            textcoords="offset points",
            ha="right",
            color=RED,
            fontsize=9.5,
        )

    ax.set_title(
        f"The GDP-world-product correlation was positive in {positive_years} of 25 years",
        loc="left",
        color=INK,
        weight="bold",
        pad=16,
    )
    ax.text(
        0,
        1.015,
        "Annual Spearman correlation between log GDP and world-product exposure",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10.5,
        va="bottom",
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Spearman correlation")
    ax.set_xlim(1999.5, 2024.7)
    ax.set_ylim(-0.10, 0.50)
    ax.set_xticks([2000, 2004, 2008, 2012, 2016, 2020, 2024])
    ax.set_yticks([-0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    ax.grid(axis="y", color=LIGHT, linewidth=0.65)
    ax.grid(axis="x", visible=False)

    fig.text(
        0.01,
        0.01,
        "Sample: rd2_countries exports, 2000-2024. Each point uses 56-60 countries. "
        "Exposure weights country product shares by world product-share rank. "
        'HS6 999999 ("Commodities not specified") is excluded.',
        fontsize=8.5,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save_figure(fig, "large_economies_world_product_exposure")


def build_product_rank_alignment_figure() -> None:
    yearly = pd.read_csv(YEARLY_PATH)
    plot = yearly[
        yearly["outcome"].eq("spearman_product_alignment")
        & yearly["size_variable"].eq("log_gdp_current_usd")
    ].copy()
    plot = plot.sort_values("year")
    if len(plot) != 25:
        raise RuntimeError(f"Expected 25 annual GDP alignment correlations, found {len(plot)}.")

    mean_corr = float(plot["spearman_size_outcome"].mean())
    min_row = plot.loc[plot["spearman_size_outcome"].idxmin()]
    max_row = plot.loc[plot["spearman_size_outcome"].idxmax()]
    latest_row = plot.iloc[-1]

    fig, ax = plt.subplots(figsize=(9.0, 5.1))
    ax.axhline(mean_corr, color=GRAY, linewidth=1.1, linestyle=(0, (3, 3)))
    ax.plot(
        plot["year"],
        plot["spearman_size_outcome"],
        color=BLUE,
        linewidth=1.8,
        zorder=2,
    )
    ax.scatter(
        plot["year"],
        plot["spearman_size_outcome"],
        s=30,
        color=BLUE,
        edgecolor="white",
        linewidth=0.55,
        zorder=3,
    )
    ax.scatter(
        [min_row["year"], max_row["year"]],
        [min_row["spearman_size_outcome"], max_row["spearman_size_outcome"]],
        s=42,
        color=RED,
        edgecolor="white",
        linewidth=0.65,
        zorder=4,
    )

    ax.text(
        2013.5,
        mean_corr + 0.004,
        f"Mean = {mean_corr:.2f}",
        color=MUTED,
        fontsize=9.5,
        va="bottom",
    )
    for row, offset, alignment in [
        (max_row, (6, 8), "left"),
        (min_row, (6, -17), "left"),
        (latest_row, (-5, 8), "right"),
    ]:
        ax.annotate(
            f"{int(row['year'])}: {row['spearman_size_outcome']:.2f}",
            xy=(row["year"], row["spearman_size_outcome"]),
            xytext=offset,
            textcoords="offset points",
            ha=alignment,
            color=RED if int(row["year"]) in {int(min_row["year"]), int(max_row["year"])} else BLUE,
            fontsize=9.5,
        )

    ax.set_title(
        "GDP-product-rank alignment remained above 0.72 in every year",
        loc="left",
        color=INK,
        weight="bold",
        pad=16,
    )
    ax.text(
        0,
        1.015,
        "Annual Spearman correlation between log GDP and country product-rank alignment",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=10.5,
        va="bottom",
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Spearman correlation")
    ax.set_xlim(1999.5, 2024.7)
    ax.set_ylim(0.68, 0.87)
    ax.set_xticks([2000, 2004, 2008, 2012, 2016, 2020, 2024])
    ax.set_yticks([0.70, 0.75, 0.80, 0.85])
    ax.grid(axis="y", color=LIGHT, linewidth=0.65)
    ax.grid(axis="x", visible=False)

    fig.text(
        0.01,
        0.01,
        "Sample: rd2_countries exports, 2000-2024. Each point uses 56-60 countries. "
        "Country alignment is the within-country Spearman correlation between country and world product export shares. "
        'HS6 999999 ("Commodities not specified") is excluded.',
        fontsize=8.5,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save_figure(fig, "yearly_within_country_product_rank_alignment")


def build_hump_country_fe_figure() -> None:
    models = pd.read_csv(HUMP_MODELS_PATH)
    summary = pd.read_csv(HUMP_SUMMARY_PATH)

    rows = models[
        models["income_form"].eq("level_ppp")
        & models["outcome"].eq("product_gini")
        & models["flow"].isin(["Exports", "Imports"])
        & models["estimator"].isin(["pooled_year_fe", "country_year_fe"])
        & models["term"].eq("gdp_pc_ppp_constant_2021_intl_usd_10k_sq")
    ].copy()
    if len(rows) != 4:
        raise RuntimeError(f"Expected four broad Product Gini quadratic rows, found {len(rows)}.")

    support = summary[
        summary["income_form"].eq("level_ppp")
        & summary["outcome_label"].isin(["Export Product Gini", "Import Product Gini"])
        & summary["estimator"].isin(["pooled_year_fe", "country_year_fe"])
    ][
        [
            "flow",
            "estimator",
            "turning_point_ppp_constant_2021_intl_usd",
            "turning_point_inside_p05_p95",
            "verdict",
        ]
    ].copy().rename(
        columns={
            "turning_point_ppp_constant_2021_intl_usd": "summary_turning_point",
        }
    )
    rows = rows.merge(support, on=["flow", "estimator"], how="left", validate="one_to_one")
    rows["estimate_plot"] = rows["coefficient"] * 1000
    rows["ci_low_plot"] = rows["ci_low"] * 1000
    rows["ci_high_plot"] = rows["ci_high"] * 1000

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.35), sharex=True, sharey=True)
    order = [("pooled_year_fe", "Pooled + year FE"), ("country_year_fe", "Country + year FE")]
    y_positions = {"pooled_year_fe": 1, "country_year_fe": 0}

    for ax, flow in zip(axes, ["Exports", "Imports"]):
        subset = rows[rows["flow"].eq(flow)].copy()
        ax.axvline(0, color=INK, linewidth=0.9)
        for estimator, label in order:
            row = subset[subset["estimator"].eq(estimator)].iloc[0]
            y = y_positions[estimator]
            color = GRAY if estimator == "pooled_year_fe" else BLUE
            ax.hlines(y, row["ci_low_plot"], row["ci_high_plot"], color=color, linewidth=2.0)
            ax.scatter(
                row["estimate_plot"],
                y,
                s=58,
                color=color,
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
            p_text = "p < 0.001" if row["p_value"] < 0.001 else f"p = {row['p_value']:.3f}"
            ax.text(
                row["ci_high_plot"] + 0.045,
                y,
                p_text,
                va="center",
                ha="left",
                color=color,
                fontsize=9.2,
            )

        pooled = subset[subset["estimator"].eq("pooled_year_fe")].iloc[0]
        country_fe = subset[subset["estimator"].eq("country_year_fe")].iloc[0]
        if flow == "Exports":
            answer = "Country FE estimate is near zero"
            turning_point_note = (
                f"Pooled TP: USD {pooled['turning_point_ppp_constant_2021_intl_usd']/1000:.1f}k, above p95. "
                "Country-FE TP: outside support."
            )
        else:
            answer = "Country FE estimate is smaller"
            turning_point_note = (
                f"Pooled TP: USD {pooled['turning_point_ppp_constant_2021_intl_usd']/1000:.1f}k, within p5-p95. "
                f"Country-FE TP: USD {country_fe['turning_point_ppp_constant_2021_intl_usd']/1000:.1f}k, above p95."
            )
        ax.set_title(f"{flow}\n{answer}", loc="left", fontsize=12.5, weight="bold", color=INK)
        ax.text(
            0.02,
            -0.23,
            turning_point_note,
            transform=ax.transAxes,
            fontsize=8.5,
            color=MUTED,
            va="top",
        )
        ax.set_yticks([0, 1], ["Country + year FE", "Pooled + year FE"])
        ax.set_xlim(-0.5, 1.75)
        ax.set_ylim(-0.45, 1.45)
        ax.grid(axis="x", color=LIGHT, linewidth=0.65)
        ax.grid(axis="y", visible=False)

    fig.suptitle(
        "Does the product-concentration hump survive country fixed effects?",
        x=0.06,
        y=1.02,
        ha="left",
        fontsize=15,
        weight="bold",
        color=INK,
    )
    fig.text(
        0.06,
        0.94,
        "Quadratic coefficients from level-PPP Product Gini regressions",
        fontsize=10.5,
        color=MUTED,
    )
    fig.supxlabel(
        "Quadratic coefficient x 1,000; income is measured in $10,000 units",
        y=0.075,
        fontsize=10,
    )
    fig.text(
        0.01,
        0.01,
        "Lines are 95% country-clustered confidence intervals. "
        "The broad complete-case sample has 135 countries. "
        "Export N = 3,240. Import N = 3,236. "
        'HS6 999999 ("Commodities not specified") is excluded.',
        fontsize=8.5,
        color=MUTED,
    )
    fig.tight_layout(rect=(0.02, 0.13, 1, 0.89), w_pad=2.2)
    save_figure(fig, "gdp_per_capita_hump_country_fixed_effects")


def main() -> None:
    configure_style()
    build_world_product_exposure_figure()
    build_product_rank_alignment_figure()
    build_hump_country_fe_figure()
    print(f"Wrote figures to {OUT_DIR.relative_to(BASE)}")


if __name__ == "__main__":
    main()
