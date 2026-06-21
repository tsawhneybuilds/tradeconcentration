#!/usr/bin/env python3
"""Plot pooled linear, quadratic, and LOWESS Cadot export-concentration fits."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.nonparametric.smoothers_lowess import lowess


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    ROOT
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_broad_ppp_hump_regression_tables"
    / "ppp_hump_analysis_panel.csv"
)
OUTPUT_DIR = (
    ROOT
    / "results"
    / "samples"
    / "cadot_broad_156"
    / "cadot_broad_ppp_hump_regression_figures"
)
PNG_PATH = OUTPUT_DIR / "export_gini_theil_linear_quadratic_lowess.png"
PDF_PATH = OUTPUT_DIR / "export_gini_theil_linear_quadratic_lowess.pdf"
SUMMARY_PATH = OUTPUT_DIR / "export_gini_theil_fit_summary.csv"

INCOME_COL = "gdp_pc_ppp_constant_2021_intl_usd"
OUTCOMES = [
    ("export_product_gini", "Active-product Gini", "Inequality among positive export products"),
    ("export_product_theil", "Fixed-universe Theil", "Concentration including inactive product support"),
]

NAVY = "#17324D"
ORANGE = "#B65A32"
MID_GREY = "#777777"
LIGHT_GREY = "#C9CDD1"
VERY_LIGHT_GREY = "#F1F2F3"
POINT_GREY = "#7D858C"


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "axes.edgecolor": MID_GREY,
            "axes.linewidth": 0.7,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "text.color": "#222222",
            "xtick.color": "#333333",
            "ytick.color": "#333333",
        }
    )


def load_panel() -> pd.DataFrame:
    panel = pd.read_csv(INPUT_PATH)
    required = {"country", "year", INCOME_COL, *(outcome[0] for outcome in OUTCOMES)}
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    panel = panel.dropna(subset=[INCOME_COL, *(outcome[0] for outcome in OUTCOMES)]).copy()
    panel["gdp_pc_ppp_2021_thousands"] = panel[INCOME_COL] / 1_000.0
    if panel.empty:
        raise ValueError("No complete observations available for plotting.")
    return panel


def ols_fit(x: np.ndarray, y: np.ndarray, degree: int, grid: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    columns = [np.ones_like(x), x]
    grid_columns = [np.ones_like(grid), grid]
    if degree == 2:
        columns.append(x**2)
        grid_columns.append(grid**2)
    design = np.column_stack(columns)
    grid_design = np.column_stack(grid_columns)
    model = sm.OLS(y, design).fit()
    return model.params, grid_design @ model.params, float(model.rsquared)


def equal_count_bins(x: np.ndarray, y: np.ndarray, bins: int = 32) -> pd.DataFrame:
    frame = pd.DataFrame({"x": x, "y": y})
    frame["bin"] = pd.qcut(frame["x"], q=bins, labels=False, duplicates="drop")
    return frame.groupby("bin", as_index=False).agg(x=("x", "mean"), y=("y", "mean"), n=("y", "size"))


def fit_outcome(panel: pd.DataFrame, outcome: str, grid: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    x = panel["gdp_pc_ppp_2021_thousands"].to_numpy(dtype=float)
    y = panel[outcome].to_numpy(dtype=float)
    linear_params, linear_pred, linear_r2 = ols_fit(x, y, 1, grid)
    quadratic_params, quadratic_pred, quadratic_r2 = ols_fit(x, y, 2, grid)
    smooth = lowess(y, x, frac=0.30, it=3, return_sorted=True)
    lowess_pred = np.interp(grid, smooth[:, 0], smooth[:, 1])
    turning = np.nan
    if quadratic_params[2] != 0:
        turning = -quadratic_params[1] / (2 * quadratic_params[2])
    return (
        {"linear": linear_pred, "quadratic": quadratic_pred, "lowess": lowess_pred},
        {
            "linear_intercept": float(linear_params[0]),
            "linear_income_coefficient_per_1000_ppp_usd": float(linear_params[1]),
            "linear_r_squared": linear_r2,
            "quadratic_intercept": float(quadratic_params[0]),
            "quadratic_income_coefficient_per_1000_ppp_usd": float(quadratic_params[1]),
            "quadratic_income_squared_coefficient": float(quadratic_params[2]),
            "quadratic_r_squared": quadratic_r2,
            "quadratic_turning_point_ppp_2021_usd": float(turning * 1_000.0),
            "lowess_fraction": 0.30,
        },
    )


def money_thousands(value: float, _: int) -> str:
    return f"${value:,.0f}k"


def build_figure(panel: pd.DataFrame) -> tuple[plt.Figure, pd.DataFrame]:
    x = panel["gdp_pc_ppp_2021_thousands"].to_numpy(dtype=float)
    x_min, x_max = float(np.min(x)), float(np.max(x))
    x_p05, x_p95 = np.quantile(x, [0.05, 0.95])
    grid = np.linspace(x_min, x_max, 500)

    fig, axes = plt.subplots(1, 2, figsize=(12.0, 5.8), sharex=True)
    summary_rows: list[dict[str, float | str | int]] = []

    for ax, (outcome, title, subtitle) in zip(axes, OUTCOMES, strict=True):
        y = panel[outcome].to_numpy(dtype=float)
        predictions, summary = fit_outcome(panel, outcome, grid)
        bins = equal_count_bins(x, y)

        ax.axvspan(x_min, x_p05, color=VERY_LIGHT_GREY, zorder=0)
        ax.axvspan(x_p95, x_max, color=VERY_LIGHT_GREY, zorder=0)
        ax.axvline(x_p05, color=LIGHT_GREY, linewidth=0.8, linestyle=(0, (2, 3)), zorder=1)
        ax.axvline(x_p95, color=LIGHT_GREY, linewidth=0.8, linestyle=(0, (2, 3)), zorder=1)
        ax.scatter(x, y, s=10, color=POINT_GREY, alpha=0.10, linewidths=0, rasterized=True, zorder=1)
        ax.scatter(bins["x"], bins["y"], s=22, color="#222222", alpha=0.78, linewidths=0, zorder=4)
        ax.plot(grid, predictions["linear"], color=MID_GREY, linewidth=1.8, linestyle=(0, (5, 4)), zorder=2)
        ax.plot(grid, predictions["quadratic"], color=NAVY, linewidth=2.4, zorder=3)
        ax.plot(grid, predictions["lowess"], color=ORANGE, linewidth=2.2, linestyle=(0, (7, 2, 1.5, 2)), zorder=3)

        turning_k = summary["quadratic_turning_point_ppp_2021_usd"] / 1_000.0
        if x_min <= turning_k <= x_max:
            turning_y = np.interp(turning_k, grid, predictions["quadratic"])
            ax.scatter([turning_k], [turning_y], s=42, color=NAVY, edgecolor="white", linewidth=0.8, zorder=5)
            ax.annotate(
                f"quadratic trough\n${turning_k:,.0f}k",
                (turning_k, turning_y),
                xytext=(8, -25),
                textcoords="offset points",
                fontsize=8.5,
                color=NAVY,
                ha="left",
            )

        ax.set_title(title, loc="left", fontweight="bold", pad=20)
        ax.text(0.0, 1.01, subtitle, transform=ax.transAxes, ha="left", va="bottom", fontsize=9, color="#555555")
        ax.xaxis.set_major_locator(MultipleLocator(25))
        ax.xaxis.set_major_formatter(FuncFormatter(money_thousands))
        ax.grid(axis="y", color=VERY_LIGHT_GREY, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlim(0, 180)
        ax.set_xlabel("Real GDP per capita, constant-2021 PPP dollars")
        ax.text(
            (x_p05 + x_p95) / 2,
            0.985,
            f"central 90%: ${x_p05:,.0f}k–${x_p95:,.0f}k",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8,
            color="#666666",
        )

        if outcome == "export_product_gini":
            fitted_upper = max(float(np.max(values)) for values in predictions.values())
            ax.set_ylim(0.75, max(1.035, fitted_upper + 0.012))
            ax.axhline(1.0, color=LIGHT_GREY, linewidth=0.8, linestyle=(0, (2, 3)), zorder=1)
            ax.text(
                0.99,
                1.0,
                "Gini upper bound",
                transform=ax.get_yaxis_transform(),
                ha="right",
                va="bottom",
                fontsize=7.8,
                color="#777777",
            )
            offscale = int(np.sum(y < 0.75))
            ax.text(
                0.01,
                0.03,
                f"{offscale} observation below display range; retained in every fit.",
                transform=ax.transAxes,
                fontsize=7.8,
                color="#666666",
            )
        else:
            plotted_min = min(float(np.min(y)), *(float(np.min(values)) for values in predictions.values()))
            plotted_max = max(float(np.max(y)), *(float(np.max(values)) for values in predictions.values()))
            pad = 0.04 * (plotted_max - plotted_min)
            ax.set_ylim(plotted_min - pad, plotted_max + pad)

        summary_rows.append(
            {
                "outcome": outcome,
                "outcome_label": title,
                "observations": len(panel),
                "reporters": int(panel["reporter_code"].nunique()),
                "year_min": int(panel["year"].min()),
                "year_max": int(panel["year"].max()),
                "income_min_ppp_2021_usd": x_min * 1_000.0,
                "income_p05_ppp_2021_usd": x_p05 * 1_000.0,
                "income_p95_ppp_2021_usd": x_p95 * 1_000.0,
                "income_max_ppp_2021_usd": x_max * 1_000.0,
                **summary,
            }
        )

    legend_items = [
        Line2D([0], [0], marker="o", linestyle="none", markersize=4.5, color="#222222", label="Equal-count bin mean"),
        Line2D([0], [0], color=MID_GREY, linewidth=1.8, linestyle=(0, (5, 4)), label="Linear OLS"),
        Line2D([0], [0], color=NAVY, linewidth=2.4, label="Quadratic OLS"),
        Line2D([0], [0], color=ORANGE, linewidth=2.2, linestyle=(0, (7, 2, 1.5, 2)), label="LOWESS (30% span)"),
    ]
    fig.legend(handles=legend_items, loc="lower center", bbox_to_anchor=(0.5, 0.105), ncol=4, frameon=False, fontsize=9)
    fig.suptitle(
        "Export concentration falls with income, then bends upward in the rich-country tail",
        x=0.07,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.905,
        "Pooled bivariate fits across reporter-years; Gini and Theil use different product-support conventions.",
        ha="left",
        fontsize=10,
        color="#444444",
    )
    fig.text(
        0.07,
        0.015,
        "Notes: Cadot broad sample, 135 complete-case reporters, 2000–2024 (N = 3,240). Raw observations are faint; black dots are 32 equal-count bin means. "
        "All fits use the full observed income range and are unweighted, unconditional, and descriptive. LOWESS uses a robust 30% span. "
        "Product-level inputs exclude HS6 999999 before aggregation. The shaded tails lie outside the income p05–p95 interval.",
        ha="left",
        va="bottom",
        fontsize=8.2,
        color="#555555",
        wrap=True,
    )
    fig.subplots_adjust(left=0.07, right=0.985, top=0.80, bottom=0.23, wspace=0.16)
    return fig, pd.DataFrame(summary_rows)


def main() -> None:
    configure_style()
    panel = load_panel()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig, summary = build_figure(panel)
    fig.savefig(PNG_PATH, dpi=240, bbox_inches="tight")
    fig.savefig(PDF_PATH, bbox_inches="tight")
    plt.close(fig)
    summary.to_csv(SUMMARY_PATH, index=False)
    print(f"Wrote {PNG_PATH.relative_to(ROOT)}")
    print(f"Wrote {PDF_PATH.relative_to(ROOT)}")
    print(f"Wrote {SUMMARY_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
