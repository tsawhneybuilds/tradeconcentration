#!/usr/bin/env python3
"""Plot rd2 top-five import product concentration with and without energy."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    ROOT
    / "data"
    / "processed"
    / "samples"
    / "rd2_countries"
    / "exercise_03_import_bin_decomposition.parquet"
)
OUT_DIR = ROOT / "results" / "samples" / "rd2_countries" / "top5_import_product_concentration_energy"

REQUIRED_COLUMNS = {
    "country",
    "iso3",
    "reporter_code",
    "year",
    "import_bin",
    "total_top_5_product_share",
    "top_5_product_share_without_bin",
    "import_value_share",
}


def load_energy_panel() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing rd2 Exercise 3 decomposition artifact: {DATA_PATH}")
    panel = pd.read_parquet(DATA_PATH)
    missing = REQUIRED_COLUMNS.difference(panel.columns)
    if missing:
        raise RuntimeError(f"{DATA_PATH} is missing required columns: {sorted(missing)}")

    energy = panel.loc[panel["import_bin"].eq("energy"), sorted(REQUIRED_COLUMNS)].copy()
    if energy.empty:
        raise RuntimeError("No `energy` bin rows found in Exercise 3 decomposition artifact.")
    duplicates = int(energy.duplicated(["reporter_code", "year"]).sum())
    if duplicates:
        raise RuntimeError(f"Energy panel has {duplicates:,} duplicate reporter-year rows.")

    for col in ["total_top_5_product_share", "top_5_product_share_without_bin", "import_value_share"]:
        bad = energy[col].isna() | energy[col].lt(0) | energy[col].gt(1)
        if bool(bad.any()):
            raise RuntimeError(f"{col} has {int(bad.sum()):,} missing or out-of-bounds values.")

    return energy.rename(
        columns={
            "total_top_5_product_share": "top5_with_energy",
            "top_5_product_share_without_bin": "top5_ex_energy",
            "import_value_share": "energy_import_share",
        }
    )


def yearly_summary(panel: pd.DataFrame) -> pd.DataFrame:
    yearly = (
        panel.groupby("year", as_index=False)
        .agg(
            countries=("country", "nunique"),
            mean_with_energy=("top5_with_energy", "mean"),
            median_with_energy=("top5_with_energy", "median"),
            mean_ex_energy=("top5_ex_energy", "mean"),
            median_ex_energy=("top5_ex_energy", "median"),
            mean_energy_import_share=("energy_import_share", "mean"),
            median_energy_import_share=("energy_import_share", "median"),
        )
        .sort_values("year")
    )
    yearly["mean_energy_gap"] = yearly["mean_with_energy"] - yearly["mean_ex_energy"]
    yearly["median_energy_gap"] = yearly["median_with_energy"] - yearly["median_ex_energy"]
    return yearly


def balanced_panel(panel: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    window = panel.loc[panel["year"].between(start_year, end_year)].copy()
    required_years = end_year - start_year + 1
    complete_counts = window.groupby("country")["year"].nunique()
    complete_countries = complete_counts.loc[complete_counts.eq(required_years)].index
    return window.loc[window["country"].isin(complete_countries)].copy()


def label_latest(ax: plt.Axes, x: pd.Series, y: pd.Series, text: str, color: str, y_offset: float = 0.0) -> None:
    if x.empty or y.empty:
        return
    ax.text(
        float(x.iloc[-1]) + 0.25,
        float(y.iloc[-1]) + y_offset,
        f"{text} {y.iloc[-1]:.0%}",
        color=color,
        fontsize=9,
        va="center",
    )


def plot_yearly_summary(yearly: pd.DataFrame, outfile: Path, title: str, note: str) -> None:
    colors = {"with": "#1f5f8b", "ex": "#b03a2e"}
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, sharey=True, constrained_layout=True)
    specs = [
        ("mean_with_energy", "mean_ex_energy", "Mean across countries"),
        ("median_with_energy", "median_ex_energy", "Median country"),
    ]

    for ax, (with_col, ex_col, panel_title) in zip(axes, specs):
        ax.plot(yearly["year"], yearly[with_col], color=colors["with"], linewidth=2.4)
        ax.plot(yearly["year"], yearly[ex_col], color=colors["ex"], linewidth=2.4, linestyle="--")
        label_latest(ax, yearly["year"], yearly[with_col], "With energy", colors["with"], y_offset=0.006)
        label_latest(ax, yearly["year"], yearly[ex_col], "Ex energy", colors["ex"], y_offset=-0.006)
        ax.set_title(panel_title, loc="left", fontsize=12)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.grid(True, axis="y", color="#e5e7eb", linewidth=0.9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylabel("Top-five import share")

    axes[-1].set_xlabel("Year")
    x_min = int(yearly["year"].min())
    x_max = int(yearly["year"].max())
    axes[-1].set_xlim(x_min, x_max + 4)
    fig.suptitle(title, x=0.02, ha="left", fontsize=16)
    fig.text(
        0.02,
        -0.02,
        note,
        ha="left",
        va="top",
        fontsize=9,
        color="#4b5563",
        wrap=True,
    )
    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, dpi=220, bbox_inches="tight")
    plt.close(fig)


def write_summary_note(all_yearly: pd.DataFrame, balanced_yearly: pd.DataFrame, balanced_country_count: int) -> None:
    latest = all_yearly.iloc[-1]
    note = f"""# Top-Five Import Product Concentration With and Without Energy

Measure: for each country-year, top-five import product concentration is

`C5_{{country,year}} = (sum of import value for the five largest positive HS6 products) / (total import value)`.

The with-energy series uses all mapped import products after the project-level HS6 `999999` exclusion. The ex-energy series recomputes the same top-five share after dropping HS6 products mapped to the Exercise 3 `energy` bin. Higher values mean that a country's import basket is more concentrated in its five largest HS6 products.

Sample: `rd2_countries`. All-year plot uses all available country-years from {int(all_yearly["year"].min())} to {int(all_yearly["year"].max())}; country coverage ranges from {int(all_yearly["countries"].min())} to {int(all_yearly["countries"].max())} countries per year. The balanced plot uses {balanced_country_count} countries observed in every year from {int(balanced_yearly["year"].min())} to {int(balanced_yearly["year"].max())}.

Latest all-available year ({int(latest["year"])}): mean top-five share is {latest["mean_with_energy"]:.1%} with energy and {latest["mean_ex_energy"]:.1%} excluding energy; median top-five share is {latest["median_with_energy"]:.1%} with energy and {latest["median_ex_energy"]:.1%} excluding energy.
"""
    (OUT_DIR / "top5_import_product_concentration_with_vs_ex_energy_summary.md").write_text(note)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = load_energy_panel()

    all_yearly = yearly_summary(panel)
    all_yearly.to_csv(
        OUT_DIR / "top5_import_product_concentration_with_vs_ex_energy_yearly_all_rd2.csv",
        index=False,
    )
    all_note = (
        "rd2_countries; top five means exact five largest positive HS6 import products in each country-year. "
        "HS6 999999 is excluded upstream. Ex-energy recomputes the share after dropping products mapped to energy. "
        f"Countries per year: {int(all_yearly['countries'].min())}-{int(all_yearly['countries'].max())}; "
        f"{int(all_yearly.iloc[-1]['year'])} has {int(all_yearly.iloc[-1]['countries'])} countries."
    )
    plot_yearly_summary(
        all_yearly,
        OUT_DIR / "mean_median_top5_import_product_concentration_with_vs_ex_energy_all_rd2.png",
        "Top-five import concentration is higher when energy remains in the basket",
        all_note,
    )

    balanced = balanced_panel(panel, 2000, 2024)
    if balanced.empty:
        raise RuntimeError("No complete balanced panel for 2000-2024.")
    balanced_yearly = yearly_summary(balanced)
    balanced_yearly.to_csv(
        OUT_DIR / "top5_import_product_concentration_with_vs_ex_energy_yearly_balanced_2000_2024.csv",
        index=False,
    )
    balanced_note = (
        "Balanced rd2 panel, 2000-2024; top five means exact five largest positive HS6 import products in each country-year. "
        "HS6 999999 is excluded upstream. Ex-energy recomputes the share after dropping products mapped to energy. "
        f"Countries in every year: {int(balanced_yearly.iloc[0]['countries'])}."
    )
    plot_yearly_summary(
        balanced_yearly,
        OUT_DIR / "mean_median_top5_import_product_concentration_with_vs_ex_energy_balanced_2000_2024.png",
        "Balanced panel: energy keeps top-five import concentration visibly higher",
        balanced_note,
    )

    write_summary_note(all_yearly, balanced_yearly, int(balanced_yearly.iloc[0]["countries"]))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
