#!/usr/bin/env python3
"""Build Partner-Gini counterfactual outputs for Exercise 4.

The counterfactual is descriptive, not causal. It asks how much aggregate import
Partner Gini would fall if each HS6 product's observed suppliers received equal
shares of that product's import value.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CELL_DIR = ROOT / "data/processed/exercise_04_file_aggregates"
TABLE_DIR = ROOT / "results/exercise_04_tables"
FIGURE_DIR = ROOT / "results/exercise_04_figures"
EX1_SOURCE = ROOT / "results/exercise_01_tables/concentration_all_years.csv"
SUMMARY_SOURCE = TABLE_DIR / "dominant_supplier_importer_summary.csv"

COUNTRY_YEAR_OUTPUT = TABLE_DIR / "partner_gini_counterfactual_country_year.csv"
LATEST_OUTPUT = TABLE_DIR / "partner_gini_counterfactual_latest.csv"
LATEST_FIGURE = FIGURE_DIR / "partner_gini_counterfactual_latest.png"
INDIA_FIGURE = FIGURE_DIR / "india_partner_gini_counterfactual_timeseries.png"

CELL_COLUMNS = ["reporter_code", "year", "cmd_code", "partner_code", "trade_value"]
DEFAULT_GINI_VALIDATION_TOLERANCE = 0.012
TOTAL_TOLERANCE_RELATIVE = 1e-8


def gini(values: pd.Series | np.ndarray | list[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return np.nan
    arr.sort()
    n = arr.size
    total = arr.sum()
    if total <= 0:
        return np.nan
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * arr) / (n * total)) - ((n + 1) / n))


def pct_axis(ax: plt.Axes) -> None:
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{100 * value:.0f}%")


def read_reference_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not EX1_SOURCE.exists():
        raise FileNotFoundError(f"Missing Exercise 1 concentration table: {EX1_SOURCE}")
    if not SUMMARY_SOURCE.exists():
        raise FileNotFoundError(f"Missing Exercise 4 summary table: {SUMMARY_SOURCE}")

    ex1 = pd.read_csv(
        EX1_SOURCE,
        usecols=[
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "variant",
            "total_trade_value",
            "partner_gini",
            "partner_active_count",
        ],
    )
    ex1 = ex1[
        ex1["flow"].astype(str).eq("Imports") & ex1["variant"].astype(str).str.lower().eq("baseline")
    ].copy()
    for column in ["reporter_code", "year", "total_trade_value", "partner_gini", "partner_active_count"]:
        ex1[column] = pd.to_numeric(ex1[column], errors="coerce")
    ex1 = ex1.dropna(subset=["reporter_code", "year", "iso3"]).copy()
    ex1["reporter_code"] = ex1["reporter_code"].astype(int)
    ex1["year"] = ex1["year"].astype(int)

    summary = pd.read_csv(
        SUMMARY_SOURCE,
        usecols=["reporter_code", "year", "total_imports", "import_products", "country", "iso3"],
    )
    for column in ["reporter_code", "year", "total_imports", "import_products"]:
        summary[column] = pd.to_numeric(summary[column], errors="coerce")
    summary = summary.dropna(subset=["reporter_code", "year", "iso3"]).copy()
    summary["reporter_code"] = summary["reporter_code"].astype(int)
    summary["year"] = summary["year"].astype(int)
    return ex1, summary


def normalize_cells(path: Path) -> pd.DataFrame:
    cells = pd.read_parquet(path, columns=CELL_COLUMNS)
    for column in ["reporter_code", "year", "partner_code", "trade_value"]:
        cells[column] = pd.to_numeric(cells[column], errors="coerce")
    cells["cmd_code"] = cells["cmd_code"].astype(str).str.zfill(6)
    cells = cells.dropna(subset=["reporter_code", "year", "cmd_code", "partner_code", "trade_value"])
    cells = cells[cells["trade_value"] > 0].copy()
    if cells.empty:
        raise RuntimeError(f"No positive import cells in {path}")
    cells["reporter_code"] = cells["reporter_code"].astype(int)
    cells["year"] = cells["year"].astype(int)
    cells["partner_code"] = cells["partner_code"].astype(int)
    return cells.groupby(["reporter_code", "year", "cmd_code", "partner_code"], as_index=False)["trade_value"].sum()


def compute_country_year(path: Path) -> dict[str, float | int | str]:
    cells = normalize_cells(path)
    reporter_code = int(cells["reporter_code"].iloc[0])
    year = int(cells["year"].iloc[0])
    if cells["reporter_code"].nunique() != 1 or cells["year"].nunique() != 1:
        raise RuntimeError(f"Expected one reporter-year per file, found multiple in {path}")

    actual_total = float(cells["trade_value"].sum())
    partner_totals = cells.groupby("partner_code")["trade_value"].sum()
    product_totals = cells.groupby("cmd_code", as_index=False)["trade_value"].sum().rename(
        columns={"trade_value": "product_total"}
    )
    supplier_counts = cells.groupby("cmd_code", as_index=False)["partner_code"].nunique().rename(
        columns={"partner_code": "observed_suppliers"}
    )
    product_stats = product_totals.merge(supplier_counts, on="cmd_code", how="inner")
    if (product_stats["observed_suppliers"] <= 0).any():
        raise RuntimeError(f"Observed supplier count is zero in {path}")

    equalized = cells.merge(product_stats, on="cmd_code", how="left")
    equalized["equalized_imports"] = equalized["product_total"] / equalized["observed_suppliers"]
    equalized_partner_totals = equalized.groupby("partner_code")["equalized_imports"].sum()
    equalized_product_totals = equalized.groupby("cmd_code")["equalized_imports"].sum()
    product_check = product_totals.set_index("cmd_code")["product_total"].sort_index()
    product_error = float((equalized_product_totals.sort_index() - product_check).abs().max())
    conservative_total = float(equalized_partner_totals.sum())

    active_partners = int(partner_totals.size)
    full_diffusion_partner_gini = 0.0 if active_partners > 0 else np.nan
    full_diffusion_total = float(product_stats["product_total"].sum())

    actual_partner_gini = gini(partner_totals)
    counterfactual_partner_gini = gini(equalized_partner_totals)
    reduction = actual_partner_gini - counterfactual_partner_gini
    explained_share = reduction / actual_partner_gini if actual_partner_gini > 0 else np.nan
    residual_share = counterfactual_partner_gini / actual_partner_gini if actual_partner_gini > 0 else np.nan
    full_diffusion_reduction = actual_partner_gini - full_diffusion_partner_gini
    full_diffusion_explained_share = (
        full_diffusion_reduction / actual_partner_gini if actual_partner_gini > 0 else np.nan
    )

    return {
        "source_file": path.name,
        "reporter_code": reporter_code,
        "year": year,
        "total_imports_cells": actual_total,
        "active_products": int(product_stats["cmd_code"].nunique()),
        "active_partners": active_partners,
        "actual_partner_gini": actual_partner_gini,
        "counterfactual_partner_gini": counterfactual_partner_gini,
        "partner_gini_reduction": reduction,
        "explained_share": explained_share,
        "counterfactual_residual_share": residual_share,
        "full_diffusion_partner_gini": full_diffusion_partner_gini,
        "full_diffusion_reduction": full_diffusion_reduction,
        "full_diffusion_explained_share": full_diffusion_explained_share,
        "conservative_total_abs_error": abs(conservative_total - actual_total),
        "full_diffusion_total_abs_error": abs(full_diffusion_total - actual_total),
        "conservative_product_total_max_abs_error": product_error,
    }


def build_counterfactual(ex1: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    files = sorted(CELL_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Exercise 4 parquet cells found in {CELL_DIR}")

    rows = [compute_country_year(path) for path in files]
    country_year = pd.DataFrame(rows)
    country_year = country_year.merge(
        ex1[
            [
                "country",
                "iso3",
                "reporter_code",
                "year",
                "total_trade_value",
                "partner_gini",
                "partner_active_count",
            ]
        ].rename(
            columns={
                "total_trade_value": "exercise1_total_imports",
                "partner_gini": "exercise1_partner_gini",
                "partner_active_count": "exercise1_partner_active_count",
            }
        ),
        on=["reporter_code", "year"],
        how="left",
    )
    country_year = country_year.merge(
        summary[
            ["reporter_code", "year", "total_imports", "import_products", "country", "iso3"]
        ].rename(
            columns={
                "total_imports": "exercise4_summary_total_imports",
                "import_products": "exercise4_summary_import_products",
                "country": "exercise4_country",
                "iso3": "exercise4_iso3",
            }
        ),
        on=["reporter_code", "year"],
        how="left",
    )
    country_year["country"] = country_year["country"].fillna(country_year["exercise4_country"])
    country_year["iso3"] = country_year["iso3"].fillna(country_year["exercise4_iso3"])
    country_year["partner_gini_validation_abs_diff"] = (
        country_year["actual_partner_gini"] - country_year["exercise1_partner_gini"]
    ).abs()
    country_year["exercise4_total_abs_diff"] = (
        country_year["total_imports_cells"] - country_year["exercise4_summary_total_imports"]
    ).abs()
    country_year["exercise1_total_abs_diff"] = (
        country_year["total_imports_cells"] - country_year["exercise1_total_imports"]
    ).abs()
    return country_year.sort_values(["country", "year"]).reset_index(drop=True)


def latest_rows(country_year: pd.DataFrame) -> pd.DataFrame:
    latest = country_year.sort_values(["iso3", "year"]).groupby("iso3", as_index=False).tail(1)
    return latest.sort_values(["partner_gini_reduction", "country"], ascending=[False, True]).reset_index(drop=True)


def validate_outputs(country_year: pd.DataFrame, gini_tolerance: float) -> None:
    if country_year["country"].isna().any() or country_year["iso3"].isna().any():
        missing = country_year[country_year["iso3"].isna() | country_year["country"].isna()]
        raise RuntimeError(f"Missing country metadata for {len(missing)} country-years.")

    max_product_error = float(country_year["conservative_product_total_max_abs_error"].max())
    max_conservative_total_error = float(country_year["conservative_total_abs_error"].max())
    max_full_total_error = float(country_year["full_diffusion_total_abs_error"].max())
    max_total = float(country_year["total_imports_cells"].max())
    total_tolerance = TOTAL_TOLERANCE_RELATIVE * max(1.0, max_total)
    if max_product_error > total_tolerance:
        raise RuntimeError(
            f"Conservative counterfactual product totals are not preserved; max error {max_product_error:g}"
        )
    if max_conservative_total_error > total_tolerance:
        raise RuntimeError(
            f"Conservative counterfactual country-year totals are not preserved; max error {max_conservative_total_error:g}"
        )
    if max_full_total_error > total_tolerance:
        raise RuntimeError(
            f"Full-diffusion counterfactual country-year totals are not preserved; max error {max_full_total_error:g}"
        )

    summary_total_error = float(country_year["exercise4_total_abs_diff"].max())
    if summary_total_error > total_tolerance:
        raise RuntimeError(f"Exercise 4 summary totals mismatch parquet cells; max error {summary_total_error:g}")

    max_gini_diff = float(country_year["partner_gini_validation_abs_diff"].max())
    if max_gini_diff > gini_tolerance:
        raise RuntimeError(
            "Recomputed Partner Gini differs from Exercise 1 beyond tolerance: "
            f"max diff {max_gini_diff:.6f}, tolerance {gini_tolerance:.6f}"
        )

    latest_count = latest_rows(country_year)["iso3"].nunique()
    if latest_count != 33:
        raise RuntimeError(f"Expected 33 latest country rows, found {latest_count}.")
    india = country_year[country_year["iso3"].eq("IND")]
    if india.empty:
        raise RuntimeError("India is missing from the Partner-Gini counterfactual output.")


def save_tables(country_year: pd.DataFrame, latest: pd.DataFrame) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    country_year.to_csv(COUNTRY_YEAR_OUTPUT, index=False)
    latest.to_csv(LATEST_OUTPUT, index=False)


def save_latest_figure(latest: pd.DataFrame) -> None:
    rows = latest.sort_values("partner_gini_reduction", ascending=True).copy()
    y = np.arange(len(rows))
    residual = rows["counterfactual_partner_gini"].to_numpy(dtype=float)
    contribution = rows["partner_gini_reduction"].to_numpy(dtype=float)
    positive = np.clip(contribution, 0, None)
    negative = np.clip(contribution, None, 0)

    fig, ax = plt.subplots(figsize=(9.8, 8.4), constrained_layout=True)
    ax.barh(y, residual, color="#94a3b8", label="Counterfactual residual")
    ax.barh(y, positive, left=residual, color="#0f766e", label="Within-product dominance contribution")
    if np.any(negative < 0):
        ax.barh(y, negative, left=residual, color="#b91c1c", label="Negative contribution")
    ax.scatter(rows["actual_partner_gini"], y, color="#111827", s=16, zorder=3, label="Actual Partner Gini")
    ax.set_yticks(y, rows["iso3"])
    ax.set_title("Latest available year: import Partner Gini counterfactual decomposition")
    ax.set_xlabel("Import Partner Gini")
    ax.set_ylabel("Country")
    ax.grid(True, axis="x", color="#e5e7eb")
    ax.legend(loc="lower right")
    max_x = float(np.nanmax([rows["actual_partner_gini"].max(), rows["counterfactual_partner_gini"].max()]))
    min_x = float(np.nanmin([0, rows["actual_partner_gini"].min(), rows["counterfactual_partner_gini"].min()]))
    ax.set_xlim(left=min_x, right=max_x + 0.03)
    fig.savefig(LATEST_FIGURE, dpi=180)
    plt.close(fig)


def save_india_figure(country_year: pd.DataFrame) -> None:
    india = country_year[country_year["iso3"].eq("IND")].sort_values("year").copy()
    if india.empty:
        raise RuntimeError("India is missing from the Partner-Gini counterfactual output.")

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(9.8, 7.0),
        sharex=True,
        gridspec_kw={"height_ratios": [2.0, 1.0]},
        constrained_layout=True,
    )
    ax = axes[0]
    ax.plot(india["year"], india["actual_partner_gini"], marker="o", color="#111827", label="Actual Partner Gini")
    ax.plot(
        india["year"],
        india["counterfactual_partner_gini"],
        marker="o",
        color="#0f766e",
        label="Conservative counterfactual Partner Gini",
    )
    ax.set_title("India: import Partner Gini under within-product supplier equalization")
    ax.set_ylabel("Partner Gini")
    ax.grid(True, color="#e5e7eb")
    ax.legend(loc="best")

    share_ax = axes[1]
    share_ax.plot(india["year"], india["explained_share"], marker="o", color="#b7791f", label="Explained share")
    share_ax.axhline(0, color="#94a3b8", linewidth=1)
    share_ax.set_xlabel("Year")
    share_ax.set_ylabel("Explained share")
    share_ax.grid(True, color="#e5e7eb")
    pct_axis(share_ax)
    fig.savefig(INDIA_FIGURE, dpi=180)
    plt.close(fig)


def save_figures(country_year: pd.DataFrame, latest: pd.DataFrame) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    save_latest_figure(latest)
    save_india_figure(country_year)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-figures", action="store_true", help="Write CSV outputs but skip PNG figure generation.")
    parser.add_argument(
        "--gini-validation-tolerance",
        type=float,
        default=DEFAULT_GINI_VALIDATION_TOLERANCE,
        help=(
            "Maximum allowed absolute difference between Partner Gini recomputed from Exercise 4 cells "
            "and Exercise 1 import Partner Gini."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ex1, summary = read_reference_tables()
    country_year = build_counterfactual(ex1, summary)
    latest = latest_rows(country_year)
    validate_outputs(country_year, args.gini_validation_tolerance)
    save_tables(country_year, latest)
    if not args.skip_figures:
        save_figures(country_year, latest)

    max_gini_diff = float(country_year["partner_gini_validation_abs_diff"].max())
    max_product_error = float(country_year["conservative_product_total_max_abs_error"].max())
    median_latest = latest[["actual_partner_gini", "counterfactual_partner_gini", "partner_gini_reduction", "explained_share"]].median(
        numeric_only=True
    )
    india_latest = country_year[country_year["iso3"].eq("IND")].sort_values("year").iloc[-1]
    print(f"Wrote {len(country_year):,} country-year rows and {len(latest):,} latest-country rows.")
    print(
        "Latest-country median: "
        f"actual Partner Gini={median_latest['actual_partner_gini']:.3f}, "
        f"counterfactual={median_latest['counterfactual_partner_gini']:.3f}, "
        f"reduction={median_latest['partner_gini_reduction']:.3f}, "
        f"explained share={median_latest['explained_share']:.1%}."
    )
    print(
        f"India latest {int(india_latest['year'])}: actual={india_latest['actual_partner_gini']:.3f}, "
        f"counterfactual={india_latest['counterfactual_partner_gini']:.3f}, "
        f"explained share={india_latest['explained_share']:.1%}."
    )
    print(
        f"Validation: max Partner-Gini diff vs Exercise 1={max_gini_diff:.6f}; "
        f"max conservative product-total error={max_product_error:.6g}."
    )


if __name__ == "__main__":
    main()
