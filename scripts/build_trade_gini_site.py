#!/usr/bin/env python3
"""Build the static Panagariya-Bagaria trade concentration research site.

The site is generated from committed result artifacts, not from raw Comtrade
files. It writes a complete GitHub Pages-ready site to /tmp/trade-gini-map-site
by default while leaving the local research repo and the Pages repo histories
separate.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("/tmp/trade-gini-map-site")
PDF_GUIDANCE = Path("/Users/tanushsawhney/Downloads/Untitled document.pdf")

SOURCE_FILES = {
    "exercise_1_panel": ROOT / "results/exercise_01_tables/concentration_all_years.csv",
    "exercise_1_top5_summary": ROOT / "results/exercise_01_tables/top5_trade_concentration_summary.csv",
    "exercise_1_top5_latest": ROOT / "results/exercise_01_tables/top5_trade_concentration_latest_summary.csv",
    "exercise_1_top5_frequency": ROOT / "results/exercise_01_tables/top5_item_frequency_latest.csv",
    "exercise_1_top5_leave_one_out": ROOT / "results/exercise_01_tables/top5_item_leave_one_out_latest.csv",
    "exercise_2_growth": ROOT / "results/exercise_02_tables/bucket_growth_summary.csv",
    "exercise_3_bins": ROOT / "results/exercise_03_tables/import_bin_concentration.csv",
    "exercise_3_decomposition": ROOT / "results/exercise_03_tables/import_bin_decomposition.csv",
    "exercise_3_total": ROOT / "results/exercise_03_tables/import_total_concentration.csv",
    "exercise_4_suppliers": ROOT / "results/exercise_04_tables/dominant_supplier_importer_summary.csv",
    "exercise_6_exclusions": ROOT / "results/exercise_06_tables/concentration_exclusions_all_years.csv",
    "exercise_10_hs2": ROOT / "results/exercise_10_tables/random_benchmark_hs2_product_all_years.csv",
    "exercise_10_active": ROOT / "results/exercise_10_tables/random_benchmark_active_count_null_all_years.csv",
    "exercise_11_io_summary": ROOT / "results/exercise_11_tables/country_year_input_output_linkage_summary.csv",
    "exercise_11_coefficients": ROOT / "results/exercise_11_product_export_linkage_tables/selected_regression_coefficients.csv",
    "exercise_11_intermediate_effects": ROOT / "results/exercise_11_product_export_linkage_tables/intermediate_effects.csv",
    "exercise_11_hs2_regressions": ROOT / "results/exercise_11_product_export_linkage_tables/hs2_regressions.csv",
    "exercise_11_commodity_comparison": ROOT / "results/exercise_11_product_export_linkage_tables/commodity_exclusion_regression_comparison.csv",
    "exercise_11_commodity_stats": ROOT / "results/exercise_11_product_export_linkage_tables/commodity_outlier_exclusion_stats.csv",
}

FIGURES = {
    "ex1_loo_all_reporters": ROOT / "results/exercise_01_figures/top5_item_leave_one_out_latest_all_reporters.png",
    "ex1_loo_top5_reporters": ROOT / "results/exercise_01_figures/top5_item_leave_one_out_latest_top5_reporters.png",
    "ex3_value_share": ROOT / "results/exercise_03_figures/median_import_value_share_by_bin.png",
    "ex3_leave_one_out": ROOT / "results/exercise_03_figures/latest_year_gini_reduction_when_bin_excluded.png",
    "ex4_supplier_time": ROOT / "results/exercise_04_figures/dominant_supplier_summary_over_time.png",
    "ex4_supplier_distribution": ROOT / "results/exercise_04_figures/latest_year_top_supplier_share_distribution.png",
    "ex6_before_after": ROOT / "results/exercise_06_figures/before_after_product_gini_over_time.png",
    "ex6_removed": ROOT / "results/exercise_06_figures/trade_share_removed_over_time.png",
    "ex10_actual_vs_benchmark": ROOT / "results/exercise_10_figures/actual_vs_simulated_gini_product_hs2_preserved.png",
    "ex10_percentile": ROOT / "results/exercise_10_figures/share_above_95th_percentile_product_hs2_preserved.png",
    "ex11_india_io": ROOT / "results/exercise_11_figures/india_top_export_input_exposure_over_time.png",
    "ex11_export_linkage_decile": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_export_linkage_by_loo_decile.png",
    "ex11_hs2_linkage_decile": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_hs2_export_linkage_by_loo_decile.png",
    "ex11_coefficients": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_intermediate_channel_coefficients.png",
    "ex11_india_supplier_scatter": ROOT / "results/exercise_11_product_export_linkage_figures/ex11_india_product_supplier_loo_scatter.png",
}

DOWNLOADS = {
    "exercise_01_concentration_all_years.csv": SOURCE_FILES["exercise_1_panel"],
    "exercise_01_top5_latest_summary.csv": SOURCE_FILES["exercise_1_top5_latest"],
    "exercise_01_top5_item_leave_one_out_latest.csv": SOURCE_FILES["exercise_1_top5_leave_one_out"],
    "exercise_03_import_bin_concentration.csv": SOURCE_FILES["exercise_3_bins"],
    "exercise_04_dominant_supplier_importer_summary.csv": SOURCE_FILES["exercise_4_suppliers"],
    "exercise_06_concentration_exclusions_all_years.csv": SOURCE_FILES["exercise_6_exclusions"],
    "exercise_10_hs2_product_benchmark_all_years.csv": SOURCE_FILES["exercise_10_hs2"],
    "exercise_11_country_year_input_output_linkage_summary.csv": SOURCE_FILES["exercise_11_io_summary"],
    "exercise_11_selected_regression_coefficients.csv": SOURCE_FILES["exercise_11_coefficients"],
    "exercise_11_intermediate_effects.csv": SOURCE_FILES["exercise_11_intermediate_effects"],
    "exercise_11_hs2_regressions.csv": SOURCE_FILES["exercise_11_hs2_regressions"],
    "exercise_11_commodity_exclusion_regression_comparison.csv": SOURCE_FILES["exercise_11_commodity_comparison"],
    "exercise_11_commodity_outlier_exclusion_stats.csv": SOURCE_FILES["exercise_11_commodity_stats"],
}

FLOW_ORDER = ["Exports", "Imports"]
METRIC_LABELS = {
    "product_gini": "Product Gini (HS6 products)",
    "partner_gini": "Partner Gini (trade partners)",
    "product_partner_cell_gini": "Product-partner cell Gini (HS6-by-partner cells)",
}
EXCLUSION_LABELS = {
    "baseline": "Baseline",
    "oil_only": "No oil/mineral fuels",
    "oil_aircraft": "No oil + aircraft",
    "oil_aircraft_precious": "No oil + aircraft + precious metals",
    "full_exclusion": "No oil, precious metals, aircraft, ships, arms",
}
BIN_LABELS = {
    "capital_goods": "Capital goods",
    "energy": "Energy",
    "final_consumption": "Final consumption",
    "intermediates": "Intermediates",
    "unmapped_or_ambiguous": "Unmapped or ambiguous",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_csv(name: str) -> pd.DataFrame:
    path = SOURCE_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"Required result table is missing: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"Required result table has zero rows: {path}")
    return df


def require_columns(df: pd.DataFrame, name: str, columns: set[str]) -> None:
    missing = columns - set(df.columns)
    if missing:
        raise RuntimeError(f"{name} is missing columns: {sorted(missing)}")


def clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(float(value)):
            return None
        return round(float(value), 12)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def clean_records(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    safe = df.loc[:, columns].copy()
    rows: list[dict[str, Any]] = []
    for row in safe.to_dict(orient="records"):
        rows.append({key: clean_scalar(value) for key, value in row.items()})
    return rows


def round_map(row: pd.Series, columns: list[str]) -> dict[str, Any]:
    return {column: clean_scalar(row[column]) for column in columns}


def median_records(
    df: pd.DataFrame,
    group_cols: list[str],
    value_cols: list[str],
    rename: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    med = df.groupby(group_cols, dropna=False)[value_cols].median(numeric_only=True).reset_index()
    if rename:
        med = med.rename(columns=rename)
    return clean_records(med, list(med.columns))


def top_loo_highlights(top5_loo: pd.DataFrame) -> dict[str, Any]:
    metrics = {
        "all_reporters": "mean_loo_gini_contribution_all_reporters",
        "top5_reporters": "mean_loo_gini_contribution_top5_reporters",
    }
    groups = {
        "import_suppliers": ("Imports", "partner"),
        "import_products": ("Imports", "product"),
        "export_destinations": ("Exports", "partner"),
        "export_products": ("Exports", "product"),
    }
    highlights: dict[str, Any] = {}
    for metric_key, metric in metrics.items():
        highlights[metric_key] = {}
        for group_key, (flow, dimension) in groups.items():
            sub = top5_loo[(top5_loo["flow"].eq(flow)) & (top5_loo["dimension"].eq(dimension))].copy()
            sub[metric] = pd.to_numeric(sub[metric], errors="coerce")
            sub["top5_reporter_count"] = pd.to_numeric(sub["top5_reporter_count"], errors="coerce")
            sub = sub.sort_values(metric, ascending=False).head(8)
            highlights[metric_key][group_key] = clean_records(
                sub,
                [
                    "display_label",
                    "top5_reporter_count",
                    "mean_loo_gini_contribution_all_reporters",
                    "mean_loo_gini_contribution_top5_reporters",
                ],
            )
    return highlights


def pick_regression_row(
    df: pd.DataFrame,
    model_label: str,
    term: str,
    sample: str | None = None,
) -> pd.Series:
    mask = df["model_label"].astype(str).eq(model_label) & df["term"].astype(str).eq(term)
    if sample is not None and "sample" in df.columns:
        mask &= df["sample"].astype(str).eq(sample)
    rows = df.loc[mask]
    if rows.empty:
        sample_msg = f", sample={sample}" if sample is not None else ""
        raise RuntimeError(f"Missing regression row: model_label={model_label}, term={term}{sample_msg}")
    return rows.iloc[0]


def regression_display_row(label: str, row: pd.Series, interpretation: str) -> dict[str, Any]:
    return {
        "result": label,
        "outcome": clean_scalar(row.get("outcome")),
        "term": clean_scalar(row.get("term")),
        "coef": clean_scalar(row.get("coef")),
        "std_error": clean_scalar(row.get("std_error")),
        "p_value": clean_scalar(row.get("p_value")),
        "nobs": clean_scalar(row.get("nobs")),
        "interpretation": interpretation,
    }


def pct(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{100 * float(value):.{digits}f}%"


def dec(value: float | None, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{float(value):.{digits}f}"


def money(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    value = float(value)
    if abs(value) >= 1e12:
        return f"${value / 1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"${value / 1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def table_rows(rows: list[dict[str, Any]], columns: list[tuple[str, str, str]]) -> str:
    head = "".join(f"<th>{label}</th>" for _, label, _ in columns)
    body = []
    for row in rows:
        cells = []
        for key, _, kind in columns:
            value = row.get(key)
            if kind == "pct":
                text = pct(value)
            elif kind == "dec":
                text = dec(value)
            elif kind == "money":
                text = money(value)
            elif kind == "int":
                text = "n/a" if value is None else f"{int(value):,}"
            else:
                text = "" if value is None else str(value)
            cells.append(f"<td>{text}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def evidence_links(items: list[tuple[str, str]]) -> str:
    return "".join(f'<a href="{href}">{label}</a>' for label, href in items)


def hypothesis_card(
    eyebrow: str,
    title: str,
    question: str,
    supports: str,
    weakens: str,
    answer: str,
    evidence: list[tuple[str, str]],
) -> str:
    return f"""
      <article class="hypothesis-card">
        <div class="hypothesis-kicker">{eyebrow}</div>
        <h3>{title}</h3>
        <dl>
          <dt>Question</dt><dd>{question}</dd>
          <dt>Supports yes if</dt><dd>{supports}</dd>
          <dt>Weakens yes if</dt><dd>{weakens}</dd>
          <dt>Current answer</dt><dd>{answer}</dd>
        </dl>
        <div class="evidence-links">{evidence_links(evidence)}</div>
      </article>
    """


def hypothesis_grid(cards: list[str]) -> str:
    return f'<div class="hypothesis-grid">{"".join(cards)}</div>'


def evidence_note(question: str, how: str, supports: str, result: str) -> str:
    return f"""
      <article class="evidence-note">
        <dl>
          <dt>Question this answers</dt><dd>{question}</dd>
          <dt>Supports the hypothesis if</dt><dd>{supports}</dd>
          <dt>Current result</dt><dd>{result}</dd>
        </dl>
      </article>
    """


def source_link(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def validate_source_shapes(ex1: pd.DataFrame) -> dict[str, Any]:
    countries = sorted(ex1["country"].dropna().unique())
    year_min = int(ex1["year"].min())
    year_max = int(ex1["year"].max())
    if len(countries) != 33:
        raise RuntimeError(f"Expected 33 countries in Exercise 1 panel, found {len(countries)}.")
    if (year_min, year_max) != (1988, 2025):
        raise RuntimeError(f"Expected Exercise 1 year range 1988-2025, found {year_min}-{year_max}.")
    return {"countries": len(countries), "year_min": year_min, "year_max": year_max}


def build_data() -> tuple[dict[str, Any], dict[str, str]]:
    ex1 = read_csv("exercise_1_panel")
    require_columns(
        ex1,
        "Exercise 1 panel",
        {
            "country",
            "iso3",
            "reporter_code",
            "year",
            "flow",
            "variant",
            "total_trade_value",
            "product_gini",
            "partner_gini",
            "product_partner_cell_gini",
            "product_top_1pct_share",
            "product_top_5pct_share",
            "top_5_partner_share",
        },
    )
    ex1 = ex1[ex1["variant"].astype(str).str.lower().eq("baseline")].copy()
    for column in [
        "year",
        "total_trade_value",
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "product_top_1pct_share",
        "product_top_5pct_share",
        "top_5_partner_share",
    ]:
        ex1[column] = pd.to_numeric(ex1[column], errors="coerce")
    shape = validate_source_shapes(ex1)

    top5 = read_csv("exercise_1_top5_summary")
    top5_latest = read_csv("exercise_1_top5_latest")
    top5_freq = read_csv("exercise_1_top5_frequency")
    top5_loo = read_csv("exercise_1_top5_leave_one_out")
    growth = read_csv("exercise_2_growth")
    bins = read_csv("exercise_3_bins")
    decomp = read_csv("exercise_3_decomposition")
    total_import = read_csv("exercise_3_total")
    suppliers = read_csv("exercise_4_suppliers")
    exclusions = read_csv("exercise_6_exclusions")
    hs2 = read_csv("exercise_10_hs2")
    active = read_csv("exercise_10_active")
    io = read_csv("exercise_11_io_summary")
    coefs = read_csv("exercise_11_coefficients")
    intermediate_effects = read_csv("exercise_11_intermediate_effects")
    hs2_regressions = read_csv("exercise_11_hs2_regressions")
    commodity_comparison = read_csv("exercise_11_commodity_comparison")
    commodity_stats = read_csv("exercise_11_commodity_stats")

    required_nonempty = {
        name: len(read_csv(name))
        for name in SOURCE_FILES
        if name not in {"exercise_1_panel"}
    }

    selected_years = [1988, 2001, 2025]
    ex1_medians = (
        ex1.groupby("flow")[
            [
                "product_gini",
                "partner_gini",
                "product_partner_cell_gini",
                "product_top_1pct_share",
                "product_top_5pct_share",
                "top_5_partner_share",
            ]
        ]
        .median()
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    ex1_year_medians = (
        ex1[ex1["year"].isin(selected_years)]
        .groupby(["flow", "year"])[
            [
                "product_gini",
                "partner_gini",
                "product_partner_cell_gini",
                "product_top_1pct_share",
                "product_top_5pct_share",
                "top_5_partner_share",
            ]
        ]
        .median()
        .reset_index()
        .sort_values(["flow", "year"])
    )

    map_year = int(ex1["year"].max())
    panel_columns = [
        "iso3",
        "country",
        "year",
        "flow",
        "total_trade_value",
        "product_gini",
        "partner_gini",
        "product_partner_cell_gini",
        "product_top_1pct_share",
        "product_top_5pct_share",
        "top_5_partner_share",
    ]
    country_panel = clean_records(ex1.sort_values(["country", "year", "flow"]), panel_columns)
    latest_map = clean_records(ex1[ex1["year"].eq(map_year)].sort_values(["flow", "country"]), panel_columns)
    countries = clean_records(ex1[["iso3", "country"]].drop_duplicates().sort_values("country"), ["iso3", "country"])

    top5_latest_med = (
        top5_latest.groupby(["flow", "dimension"])[["top_1_item_share", "cumulative_top_5_share", "gini", "active_count"]]
        .median(numeric_only=True)
        .reset_index()
        .sort_values(["flow", "dimension"])
    )
    top5_frequency = top5_freq.sort_values(
        ["flow", "dimension", "reporter_count", "weighted_mean_share"], ascending=[True, True, False, False]
    )
    top5_frequency = top5_frequency.groupby(["flow", "dimension"]).head(6).reset_index(drop=True)

    growth_summary = clean_records(
        growth.sort_values(["horizon", "concentration_bucket"]),
        [
            "horizon",
            "concentration_bucket",
            "observations",
            "mean_annualized_log_growth",
            "median_annualized_log_growth",
            "mean_export_growth_pct",
            "median_initial_exports",
        ],
    )

    ex_export = exclusions[exclusions["flow"].eq("Exports")].copy()
    exclusion_medians = (
        ex_export.groupby("variant")[
            ["product_gini", "product_top_1pct_share", "product_top_5pct_share", "trade_share_removed"]
        ]
        .median(numeric_only=True)
        .reset_index()
    )
    exclusion_medians["label"] = exclusion_medians["variant"].map(EXCLUSION_LABELS).fillna(exclusion_medians["variant"])
    exclusion_order = list(EXCLUSION_LABELS)
    exclusion_medians["order"] = exclusion_medians["variant"].map({value: i for i, value in enumerate(exclusion_order)})
    exclusion_medians = exclusion_medians.sort_values("order")
    exclusion_years = (
        ex_export.groupby(["year", "variant"])[["product_gini", "trade_share_removed"]]
        .median(numeric_only=True)
        .reset_index()
    )
    exclusion_years["label"] = exclusion_years["variant"].map(EXCLUSION_LABELS).fillna(exclusion_years["variant"])

    hs2_summary = (
        hs2.groupby("flow")[["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]]
        .median(numeric_only=True)
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    active_product = active[active["dimension"].eq("product")].copy()
    active_summary = (
        active_product.groupby("flow")[["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]]
        .median(numeric_only=True)
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    hs2_latest = (
        hs2[hs2["year"].eq(hs2["year"].max())]
        .groupby("flow")[["actual_gini", "sim_gini_median", "actual_minus_sim_median_gini", "actual_gini_percentile"]]
        .median(numeric_only=True)
        .reindex(FLOW_ORDER)
        .reset_index()
    )
    benchmark_ladder = []
    for null_label, frame in [("Active-count-only null", active_summary), ("HS2-preserving null", hs2_summary)]:
        for row in frame.to_dict(orient="records"):
            benchmark_ladder.append(
                {
                    "benchmark": null_label,
                    "flow": row["flow"],
                    "actual_gini": clean_scalar(row["actual_gini"]),
                    "sim_gini_median": clean_scalar(row["sim_gini_median"]),
                    "gap": clean_scalar(row["actual_minus_sim_median_gini"]),
                    "percentile": clean_scalar(row["actual_gini_percentile"]),
                }
            )

    bins_summary = (
        bins.groupby("import_bin")[["product_gini", "top_1_product_share", "active_products"]]
        .median(numeric_only=True)
        .reset_index()
    )
    decomp_summary = (
        decomp.groupby("import_bin")[
            [
                "import_value_share",
                "top_10_product_share_contribution",
                "product_gini_without_bin",
                "product_gini_reduction_when_excluded",
            ]
        ]
        .median(numeric_only=True)
        .reset_index()
    )
    bin_summary = bins_summary.merge(decomp_summary, on="import_bin", how="outer")
    bin_summary["label"] = bin_summary["import_bin"].map(BIN_LABELS).fillna(bin_summary["import_bin"])
    total_import_summary = (
        total_import[["product_gini", "top_1_product_share", "top_5_product_share", "top_10_product_share", "active_products"]]
        .median(numeric_only=True)
        .to_dict()
    )

    supplier_summary = suppliers[
        [
            "weighted_mean_top_supplier_share",
            "weighted_mean_source_hhi",
            "median_top_supplier_share",
            "share_products_top_supplier_ge_75",
            "import_value_share_products_top_supplier_ge_75",
        ]
    ].median(numeric_only=True)
    india_2024 = suppliers[(suppliers["iso3"].eq("IND")) & (suppliers["year"].eq(2024))]
    india_supplier = india_2024.iloc[0] if not india_2024.empty else pd.Series(dtype=object)
    supplier_years = (
        suppliers.groupby("year")[
            [
                "weighted_mean_top_supplier_share",
                "median_top_supplier_share",
                "share_products_top_supplier_ge_75",
                "import_value_share_products_top_supplier_ge_75",
            ]
        ]
        .median(numeric_only=True)
        .reset_index()
    )

    io_valid = io.dropna(subset=["weighted_top_sector_input_product_gini"]).copy()
    io_medians = io_valid[
        [
            "weighted_top_sector_input_product_gini",
            "weighted_top_sector_top_supplier_share",
            "weighted_top_sector_source_hhi",
            "median_top_sector_matched_requirement_share",
            "top_export_value_share",
        ]
    ].median(numeric_only=True)
    india_io_valid = io_valid[io_valid["iso3"].eq("IND")].sort_values("year")
    india_io_latest = india_io_valid.iloc[-1] if not india_io_valid.empty else pd.Series(dtype=object)
    io_years = (
        io_valid.groupby("year")[
            [
                "weighted_top_sector_input_product_gini",
                "weighted_top_sector_top_supplier_share",
                "median_top_sector_matched_requirement_share",
            ]
        ]
        .median(numeric_only=True)
        .reset_index()
    )

    hs6_value = pick_regression_row(coefs, "product_export_value_gini", "loo_gini_contribution_z", "baseline")
    hs6_any = pick_regression_row(coefs, "product_export_any_gini", "loo_gini_contribution_z", "baseline")
    partner_hhi = pick_regression_row(coefs, "product_export_value_partner_hhi", "loo_partner_hhi_contribution_z", "baseline")
    intermediate_base = pick_regression_row(
        coefs,
        "product_export_value_intermediate_interaction",
        "loo_gini_contribution_z",
        "baseline",
    )
    intermediate_interaction = pick_regression_row(
        coefs,
        "product_export_value_intermediate_interaction",
        "loo_gini_x_intermediate_z",
        "baseline",
    )
    hs2_value = pick_regression_row(hs2_regressions, "hs2_export_value_gini", "hs2_product_loo_gini_sum_z")
    hs2_any = pick_regression_row(hs2_regressions, "hs2_export_any_gini", "hs2_product_loo_gini_sum_z")
    hs2_share = pick_regression_row(hs2_regressions, "hs2_export_share_gini", "hs2_product_loo_gini_sum_z")
    hs2_interaction = pick_regression_row(
        hs2_regressions,
        "hs2_export_value_intermediate_intensity",
        "hs2_product_loo_gini_sum_x_intermediate_share_z",
    )

    ex11_regression_summary = [
        regression_display_row("HS6 product-Gini contribution", hs6_value, "Negative export-value linkage"),
        regression_display_row("HS6 export probability", hs6_any, "Negative export-probability linkage"),
        regression_display_row("HS6 supplier-country HHI contribution", partner_hhi, "Positive export-value linkage"),
        regression_display_row("Intermediate interaction", intermediate_interaction, "Intermediates are not more export-linked"),
        regression_display_row("HS2 product-Gini contribution", hs2_value, "Still negative after broadening to HS2"),
        regression_display_row("HS2 export probability", hs2_any, "Small and not statistically distinguishable from zero"),
        regression_display_row("HS2 export share", hs2_share, "Small and not statistically distinguishable from zero"),
        regression_display_row("HS2 intermediate-intensity interaction", hs2_interaction, "Does not rescue the intermediate channel"),
    ]

    commodity_summary_rows = commodity_comparison[
        (
            commodity_comparison["sample"].astype(str).isin(["baseline", "excluding oil/gas/gold/coal"])
        )
        & (
            commodity_comparison["check"].astype(str).isin(
                [
                    "Export value: product-Gini contribution",
                    "Export probability: product-Gini contribution",
                    "Export value: partner-HHI contribution",
                    "Intermediate interaction",
                ]
            )
        )
    ].copy()
    commodity_summary_rows["result"] = commodity_summary_rows["sample"].astype(str) + " - " + commodity_summary_rows["check"].astype(str)

    commodity_stats_map = {
        str(row["measure"]): clean_scalar(row["value"])
        for row in commodity_stats.to_dict(orient="records")
    }

    data = {
        "metadata": {
            "created_at_utc": now_utc(),
            "source_root": "local research repository",
            "pdf_guidance_present": PDF_GUIDANCE.exists(),
            "site_scope": "Exercises 1, 2 descriptive growth note, 3, 4, 6, 10, and 11.",
            "data_checks": {"exercise_1": shape, "required_table_rows": required_nonempty},
        },
        "labels": {
            "metrics": METRIC_LABELS,
            "exclusions": EXCLUSION_LABELS,
            "bins": BIN_LABELS,
        },
        "countries": countries,
        "exercise1": {
            "panel": country_panel,
            "latest_map": latest_map,
            "median_by_flow": clean_records(ex1_medians, list(ex1_medians.columns)),
            "selected_year_medians": clean_records(ex1_year_medians, list(ex1_year_medians.columns)),
            "top5_latest_medians": clean_records(top5_latest_med, list(top5_latest_med.columns)),
            "top5_frequency_latest": clean_records(
                top5_frequency,
                [
                    "flow",
                    "dimension",
                    "display_label",
                    "reporter_count",
                    "reporter_share",
                    "mean_rank",
                    "median_share",
                    "weighted_mean_share",
                ],
            ),
            "top5_leave_one_out_highlights": top_loo_highlights(top5_loo),
        },
        "exercise2": {"growth_summary": growth_summary},
        "exercise3": {
            "bin_summary": clean_records(bin_summary, list(bin_summary.columns)),
            "total_import_summary": {key: clean_scalar(value) for key, value in total_import_summary.items()},
        },
        "exercise4": {
            "summary": {key: clean_scalar(value) for key, value in supplier_summary.items()},
            "india_2024": {
                key: clean_scalar(india_supplier.get(key))
                for key in [
                    "year",
                    "total_imports",
                    "import_products",
                    "weighted_mean_top_supplier_share",
                    "weighted_mean_source_hhi",
                    "median_top_supplier_share",
                    "share_products_top_supplier_ge_75",
                    "import_value_share_products_top_supplier_ge_75",
                ]
            },
            "year_series": clean_records(supplier_years, list(supplier_years.columns)),
        },
        "exercise6": {
            "median_by_variant": clean_records(exclusion_medians, list(exclusion_medians.columns)),
            "year_series": clean_records(exclusion_years, list(exclusion_years.columns)),
        },
        "exercise10": {
            "benchmark_ladder": benchmark_ladder,
            "hs2_summary": clean_records(hs2_summary, list(hs2_summary.columns)),
            "hs2_latest": clean_records(hs2_latest, list(hs2_latest.columns)),
            "active_product_summary": clean_records(active_summary, list(active_summary.columns)),
        },
        "exercise11": {
            "summary": {key: clean_scalar(value) for key, value in io_medians.items()},
            "india_latest": {
                key: clean_scalar(india_io_latest.get(key))
                for key in [
                    "year",
                    "weighted_top_sector_input_product_gini",
                    "weighted_top_sector_top_supplier_share",
                    "weighted_top_sector_source_hhi",
                    "median_top_sector_matched_requirement_share",
                    "top_export_value_share",
                    "total_exports",
                ]
            },
            "year_series": clean_records(io_years, list(io_years.columns)),
            "coefficients": ex11_regression_summary,
            "intermediate_effects": clean_records(
                intermediate_effects,
                ["effect", "coef", "std_error", "ci_low", "ci_high"],
            ),
            "commodity_comparison": clean_records(
                commodity_summary_rows,
                ["result", "sample", "check", "outcome", "term", "coef", "std_error", "p_value", "nobs", "clusters", "r2_within"],
            ),
            "commodity_stats": commodity_stats_map,
        },
    }

    pages = build_page_context(data)
    return data, pages


def find_value(rows: list[dict[str, Any]], **filters: Any) -> dict[str, Any]:
    for row in rows:
        if all(row.get(key) == value for key, value in filters.items()):
            return row
    return {}


def build_page_context(data: dict[str, Any]) -> dict[str, str]:
    ex1 = data["exercise1"]
    ex3 = data["exercise3"]
    ex4 = data["exercise4"]
    ex6 = data["exercise6"]
    ex10 = data["exercise10"]
    ex11 = data["exercise11"]

    exp = find_value(ex1["median_by_flow"], flow="Exports")
    imp = find_value(ex1["median_by_flow"], flow="Imports")
    exp_1988 = find_value(ex1["selected_year_medians"], flow="Exports", year=1988)
    exp_2025 = find_value(ex1["selected_year_medians"], flow="Exports", year=2025)
    imp_1988 = find_value(ex1["selected_year_medians"], flow="Imports", year=1988)
    imp_2025 = find_value(ex1["selected_year_medians"], flow="Imports", year=2025)
    baseline = find_value(ex6["median_by_variant"], variant="baseline")
    full_excl = find_value(ex6["median_by_variant"], variant="full_exclusion")
    energy = find_value(ex3["bin_summary"], import_bin="energy")
    intermediates = find_value(ex3["bin_summary"], import_bin="intermediates")
    india_supplier = ex4["india_2024"]
    india_io = ex11["india_latest"]
    loo = ex1["top5_leave_one_out_highlights"]
    all_import_supplier = loo["all_reporters"]["import_suppliers"][0]
    all_export_destination = loo["all_reporters"]["export_destinations"][0]
    all_import_product = loo["all_reporters"]["import_products"][0]
    all_export_product = loo["all_reporters"]["export_products"][0]
    conditional_import_supplier = loo["top5_reporters"]["import_suppliers"][0]
    conditional_export_destination = loo["top5_reporters"]["export_destinations"][0]
    ex11_main = find_value(ex11["coefficients"], result="HS6 product-Gini contribution")
    ex11_any = find_value(ex11["coefficients"], result="HS6 export probability")
    ex11_supplier = find_value(ex11["coefficients"], result="HS6 supplier-country HHI contribution")
    ex11_interaction = find_value(ex11["coefficients"], result="Intermediate interaction")
    ex11_hs2_value = find_value(ex11["coefficients"], result="HS2 product-Gini contribution")
    ex11_hs2_any = find_value(ex11["coefficients"], result="HS2 export probability")
    ex11_hs2_share = find_value(ex11["coefficients"], result="HS2 export share")
    ex11_hs2_interaction = find_value(ex11["coefficients"], result="HS2 intermediate-intensity interaction")
    commodity_stats = ex11["commodity_stats"]

    source_table = table_rows(
        [
            {"source": label, "path": source_link(path), "rows": len(pd.read_csv(path))}
            for label, path in SOURCE_FILES.items()
        ],
        [("source", "Artifact", "text"), ("path", "Local source", "text"), ("rows", "Rows", "int")],
    )
    countries_table = table_rows(data["countries"], [("country", "Country", "text"), ("iso3", "ISO3", "text")])

    overview_cards = f"""
      <div class="stat-grid">
        <article class="stat-card"><span>Median export Product Gini</span><strong>{dec(exp.get("product_gini"))}</strong><small>across HS6 products, 1988-2025</small></article>
        <article class="stat-card"><span>Median import Product Gini</span><strong>{dec(imp.get("product_gini"))}</strong><small>across HS6 products, same panel</small></article>
        <article class="stat-card"><span>Full lumpy exclusion</span><strong>{dec(full_excl.get("product_gini"))}</strong><small>export Product Gini, from {dec(baseline.get("product_gini"))}</small></article>
        <article class="stat-card"><span>Energy import-bin Product Gini</span><strong>{dec(energy.get("product_gini"))}</strong><small>within HS6 energy products; top-1 share {pct(energy.get("top_1_product_share"))}</small></article>
      </div>
    """

    index_hypothesis = hypothesis_grid(
        [
            hypothesis_card(
                "Framing question",
                "Extending the 2001 concentration",
                "Does the Panagariya-Bagaria concentration pattern persist when the same broad country set is followed across many years rather than one central cross-section?",
                "Product Gini, Partner Gini, and Product-partner cell Gini stay high across countries and years.",
                "The high concentration pattern disappears, flips, or depends mainly on one year/sample.",
                f"Supports. In the 33-country 1988-2025 panel, median Product Ginis across HS6 products are {dec(exp.get('product_gini'))} for exports and {dec(imp.get('product_gini'))} for imports, and median Product-partner cell Ginis across HS6-by-partner cells are {dec(exp.get('product_partner_cell_gini'))} and {dec(imp.get('product_partner_cell_gini'))}.",
                [
                    ("Extension page", "extension.html#map-lines"),
                    ("Top shares", "extension.html#top-share-evidence"),
                    ("Import mechanisms", "imports.html#import-bins"),
                    ("Data downloads", "methods.html#downloads"),
                ],
            )
        ]
    )

    extension_hypotheses = hypothesis_grid(
        [
            hypothesis_card(
                "Exercise 1",
                "Persistent aggregate concentration",
                "Concentration is a persistent aggregate fact, not a one-year artifact.",
                "Product Gini and Partner Gini stay high across countries and years.",
                "Concentration disappears or changes sharply by year/sample.",
                f"Supports. Median export Product Gini across HS6 products rises from {dec(exp_1988.get('product_gini'))} in 1988 to {dec(exp_2025.get('product_gini'))} in 2025; import Product Gini rises from {dec(imp_1988.get('product_gini'))} to {dec(imp_2025.get('product_gini'))}. The top-share tables also show large latest-year top HS6-product and partner shares.",
                [
                    ("Map and lines", "#map-lines"),
                    ("Top-share table", "#top-share-evidence"),
                    ("Leave-one-out graphs", "#top-five-loo"),
                    ("Panel CSV", "assets/downloads/exercise_01_concentration_all_years.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 6",
                "Lumpy-product explanation",
                "Concentration is mostly driven by oil, aircraft, precious metals/gold, ships, arms, or other obvious lumpy categories.",
                "Ginis fall sharply after excluding these product groups.",
                "Ginis remain high after the exclusions.",
                f"Weakens the mostly-lumpy explanation. The full export-side exclusion lowers median Product Gini across HS6 products only from {dec(baseline.get('product_gini'))} to {dec(full_excl.get('product_gini'))}, while removing a median {pct(full_excl.get('trade_share_removed'))} of trade value.",
                [
                    ("Exclusion table", "#lumpy-exclusions"),
                    ("Exclusion CSV", "assets/downloads/exercise_06_concentration_exclusions_all_years.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 10",
                "Benchmark/null model",
                "Observed concentration is higher than what would arise mechanically from scale, sparsity, active products, and broad HS2 sector composition.",
                "Actual concentration sits well above simulated/random benchmarks for most countries and years.",
                "Actual concentration is close to what the benchmark would generate.",
                "Supports. Actual Product Ginis across HS6 products sit above both the loose active-count-only benchmark and the conservative HS2-preserving benchmark. The HS2 benchmark is conditional, not complete randomization.",
                [
                    ("Benchmark ladder", "#benchmark-ladder"),
                    ("Benchmark CSV", "assets/downloads/exercise_10_hs2_product_benchmark_all_years.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 2",
                "Growth-bucket context",
                "Product-Gini and Partner-Gini concentration predict future export growth.",
                "High-Product-Gini/high-Partner-Gini countries grow meaningfully differently from low-low countries.",
                "Buckets show no meaningful growth differences.",
                "Mixed/descriptive. The bucket table is useful context, but this site treats it as descriptive rather than causal evidence about growth.",
                [
                    ("Growth buckets", "#growth-buckets"),
                    ("Methods", "methods.html#source-artifacts"),
                ],
            ),
        ]
    )

    imports_hypotheses = hypothesis_grid(
        [
            hypothesis_card(
                "Exercise 3",
                "Import bins",
                "Import concentration is driven by energy, capital goods, or key intermediates rather than final consumption goods.",
                "Those bins are internally concentrated and explain large top-product shares or reduce aggregate Gini when excluded.",
                "Final goods are equally concentrated, or high-concentration bins are too small to explain aggregate concentration.",
                f"Supports a two-part answer. Energy is the sharpest spike, with median bin Gini {dec(energy.get('product_gini'))} and top-1 share {pct(energy.get('top_1_product_share'))}; intermediates are the largest part of the bill, with median import value share {pct(intermediates.get('import_value_share'))}.",
                [
                    ("Import-bin table", "#import-bins"),
                    ("Import-bin CSV", "assets/downloads/exercise_03_import_bin_concentration.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 4",
                "Dominant supplier by product",
                "Imports are concentrated because each product has one dominant global source.",
                "For many products, country imports come mostly from the top source country.",
                "Import concentration remains high even when supplier shares within products are diffuse.",
                f"Supports product-level supplier dominance mechanically, but not the stronger claim that more supplier concentration maps to more import value. The median product top-supplier share is {pct(ex4['summary'].get('median_top_supplier_share'))}; products above 75% top-supplier share are {pct(ex4['summary'].get('share_products_top_supplier_ge_75'))} of rows but only {pct(ex4['summary'].get('import_value_share_products_top_supplier_ge_75'))} of value. The value regression did not show that more concentrated supplier sourcing is associated with higher import value, so this should be read as evidence that suppliers are often concentrated within products, not that those concentrated products dominate the import bill.",
                [
                    ("Supplier dominance", "#supplier-dominance"),
                    ("Supplier CSV", "assets/downloads/exercise_04_dominant_supplier_importer_summary.csv"),
                ],
            ),
            hypothesis_card(
                "Exercise 11",
                "Do concentration-driving imports map to exports?",
                "Import concentration is tied to export production chains.",
                "Concentration-driving imported intermediates are more export-linked than other concentration-driving imports.",
                "They are less export-linked, or no more export-linked, than non-intermediates.",
                f"Weakens the broad processing claim, but supports a narrower supplier-exposure channel. Product-Gini contribution is negatively linked to export value ({dec(ex11_main.get('coef'))}) and export probability ({dec(ex11_any.get('coef'))}), while supplier-country HHI contribution is positively linked to export value ({dec(ex11_supplier.get('coef'))}).",
                [
                    ("Exercise 11 findings", "#io-linkage"),
                    ("Regression table", "#ex11-regressions"),
                    ("Regression coefficients", "assets/downloads/exercise_11_selected_regression_coefficients.csv"),
                ],
            ),
        ]
    )

    methods_hypothesis = hypothesis_grid(
        [
            hypothesis_card(
                "Replication question",
                "Replicability and provenance",
                "Can a reader trace the public brief back to its result artifacts?",
                "The site lists coverage, definitions, generated tables, figures, and downloadable CSVs without requiring raw Comtrade files.",
                "Numeric claims appear without a source table, or the generated data contains unresolved placeholders/private context.",
                "Supports. The generator records the exact result tables used, the Methods page lists source artifacts, and the public site ships selected CSVs for inspection.",
                [
                    ("Source artifacts", "#source-artifacts"),
                    ("Downloads", "#downloads"),
                    ("Definitions", "#definitions"),
                ],
            )
        ]
    )

    pages = {
        "index_hypothesis": index_hypothesis,
        "extension_hypotheses": extension_hypotheses,
        "imports_hypotheses": imports_hypotheses,
        "methods_hypothesis": methods_hypothesis,
        "overview_cards": overview_cards,
        "summary_text": (
            f"The empirical extension keeps the 33-country Panagariya-Bagaria sample and expands the time "
            f"dimension to {data['metadata']['data_checks']['exercise_1']['year_min']}-"
            f"{data['metadata']['data_checks']['exercise_1']['year_max']}. Median Product Ginis across HS6 products are "
            f"{dec(exp.get('product_gini'))} for exports and {dec(imp.get('product_gini'))} for imports; "
            f"the Product-partner cell Gini medians across HS6-by-partner cells are {dec(exp.get('product_partner_cell_gini'))} and "
            f"{dec(imp.get('product_partner_cell_gini'))}."
        ),
        "extension_takeaways": f"""
          <ul class="callout-list">
            <li>Product Gini measures concentration across HS6 products: exports <strong>{dec(exp.get("product_gini"))}</strong>, imports <strong>{dec(imp.get("product_gini"))}</strong>.</li>
            <li>Partner Gini measures concentration across destination/source partners: exports <strong>{dec(exp.get("partner_gini"))}</strong>, imports <strong>{dec(imp.get("partner_gini"))}</strong>.</li>
            <li>Product-partner cell Gini measures concentration across HS6-by-partner cells: exports <strong>{dec(exp.get("product_partner_cell_gini"))}</strong>, imports <strong>{dec(imp.get("product_partner_cell_gini"))}</strong>.</li>
            <li>Median export Product Gini rises from <strong>{dec(exp_1988.get("product_gini"))}</strong> in 1988 to <strong>{dec(exp_2025.get("product_gini"))}</strong> in 2025; import Product Gini rises from <strong>{dec(imp_1988.get("product_gini"))}</strong> to <strong>{dec(imp_2025.get("product_gini"))}</strong>.</li>
          </ul>
        """,
        "map_note": evidence_note(
            "Are high trade Ginis broad across countries, or driven by only a few outliers?",
            "Select flow, metric, and year; darker countries have higher concentration for that country-year-flow.",
            "Many countries remain dark across the panel rather than only one or two outliers driving the picture.",
            "High concentration appears across much of the 33-country sample, not just one country.",
        ),
        "line_note": evidence_note(
            "Is concentration persistent over time within countries?",
            "Select countries, flow, and metric; high, fairly flat lines mean concentration persists within countries.",
            "Country lines stay high across decades rather than collapsing after the 2001 cross-section.",
            "Many countries remain highly concentrated across decades, supporting the extension beyond 2001.",
        ),
        "top_share_note": evidence_note(
            "Are high Ginis economically meaningful in share terms?",
            "Compare median top-item and top-five shares by product versus partner.",
            "The largest products or partners account for substantial shares of trade, not just high index values.",
            "Top partners and products account for large trade shares, so the Gini is not just an abstract index.",
        ),
        "top_frequency_note": evidence_note(
            "Which products or partners repeatedly appear in countries' top-five baskets?",
            "Higher country counts mean the item is commonly important across reporters in the latest year.",
            "A small set of products or partners appears repeatedly across many countries.",
            "Repeated appearances point to common concentration sources like major destinations, energy, gold, vehicles, medicines, and electronics.",
        ),
        "loo_note": evidence_note(
            "Which top-five items actually raise Gini the most?",
            "Positive values mean removing the item lowers Gini, so that item is concentration-raising.",
            "The same high-share products or partners have positive leave-one-out contributions.",
            "Large partners and lumpy goods explain part of concentration, but not all of it.",
        ),
        "lumpy_note": evidence_note(
            "Does concentration disappear after removing oil, gold/precious metals, aircraft, ships, and arms?",
            "Compare baseline Gini with exclusion variants and the trade share removed.",
            "The lumpy-product story would be strong if Gini fell sharply after these exclusions.",
            "Concentration falls only modestly, so lumpy products matter but do not explain the whole pattern.",
        ),
        "benchmark_note": evidence_note(
            "Is high concentration just what we would expect from sparse product counts or broad HS2 structure?",
            "Compare actual Ginis with the active-count-only and HS2-preserving null benchmarks.",
            "Actual Ginis sit well above the benchmark distributions.",
            "Actual Ginis remain above both benchmarks; HS2 preservation is a conservative benchmark, not complete randomization.",
        ),
        "growth_note": evidence_note(
            "Do more concentrated export baskets predict different later growth patterns?",
            "Compare annualized growth across concentration buckets and horizons.",
            "High-concentration buckets grow meaningfully differently from low-concentration buckets.",
            "This is descriptive only; it is useful for scoping follow-up questions, not a causal claim.",
        ),
        "top_share_table": table_rows(
            ex1["top5_latest_medians"],
            [
                ("flow", "Flow", "text"),
                ("dimension", "Dimension", "text"),
                ("top_1_item_share", "Median top item", "pct"),
                ("cumulative_top_5_share", "Median top five", "pct"),
                ("gini", "Median Gini", "dec"),
                ("active_count", "Active items", "int"),
            ],
        ),
        "top_frequency_table": table_rows(
            ex1["top5_frequency_latest"],
            [
                ("flow", "Flow", "text"),
                ("dimension", "Dimension", "Dimension"),
                ("display_label", "Item", "text"),
                ("reporter_count", "Countries", "int"),
                ("median_share", "Median share", "pct"),
                ("weighted_mean_share", "Weighted mean share", "pct"),
            ],
        ),
        "loo_interpretation": f"""
          <div class="interpretation-grid">
            <article class="note">
              <h3>All-reporter average</h3>
              <p>This is the broader panel comparison because the contribution is averaged across all latest-year reporters, including countries where the item is not in the top five. Positive values mean removing the item lowers Gini, so the item is concentration-raising.</p>
              <p>The largest partner-side signals are <strong>{all_export_destination["display_label"]}</strong> for export destinations ({dec(all_export_destination["mean_loo_gini_contribution_all_reporters"])}) and <strong>{all_import_supplier["display_label"]}</strong> for import suppliers ({dec(all_import_supplier["mean_loo_gini_contribution_all_reporters"])}). On the product side, <strong>{all_import_product["display_label"]}</strong> is the largest import contributor ({dec(all_import_product["mean_loo_gini_contribution_all_reporters"])}), while <strong>{all_export_product["display_label"]}</strong> leads exported products ({dec(all_export_product["mean_loo_gini_contribution_all_reporters"])}).</p>
            </article>
            <article class="note">
              <h3>Conditional on being top five</h3>
              <p>This view asks how much the item raises concentration in countries where it actually appears in that country's top five. It is useful for mechanism spotting, but rare items can look large because the average is over fewer reporters.</p>
              <p>The conditional partner signals remain large for <strong>{conditional_export_destination["display_label"]}</strong> as an export destination ({dec(conditional_export_destination["mean_loo_gini_contribution_top5_reporters"])}) and <strong>{conditional_import_supplier["display_label"]}</strong> as an import supplier ({dec(conditional_import_supplier["mean_loo_gini_contribution_top5_reporters"])}). The product panels reinforce the lumpy-goods story: oil, gold, aircraft, pharmaceuticals, vehicles, and chips repeatedly show positive contributions where they enter top-five baskets.</p>
            </article>
          </div>
        """,
        "lumpy_text": (
            f"The full exclusion lowers the median export Product Gini across HS6 products from {dec(baseline.get('product_gini'))} "
            f"to {dec(full_excl.get('product_gini'))}, while the median removed trade share is "
            f"{pct(full_excl.get('trade_share_removed'))}. This is currently an export-side test."
        ),
        "exclusion_table": table_rows(
            ex6["median_by_variant"],
            [
                ("label", "Specification", "text"),
                ("product_gini", "Median Product Gini (HS6 products)", "dec"),
                ("product_top_1pct_share", "Top 1% share", "pct"),
                ("product_top_5pct_share", "Top 5% share", "pct"),
                ("trade_share_removed", "Trade share removed", "pct"),
            ],
        ),
        "benchmark_table": table_rows(
            ex10["benchmark_ladder"],
            [
                ("benchmark", "Benchmark", "text"),
                ("flow", "Flow", "text"),
                ("actual_gini", "Actual", "dec"),
                ("sim_gini_median", "Benchmark median", "dec"),
                ("gap", "Actual minus benchmark", "dec"),
                ("percentile", "Percentile", "dec"),
            ],
        ),
        "growth_table": table_rows(
            data["exercise2"]["growth_summary"],
            [
                ("horizon", "Horizon", "int"),
                ("concentration_bucket", "Bucket", "text"),
                ("observations", "Obs.", "int"),
                ("mean_annualized_log_growth", "Mean annualized log growth", "pct"),
                ("median_annualized_log_growth", "Median annualized log growth", "pct"),
            ],
        ),
        "imports_takeaways": f"""
          <ul class="callout-list">
            <li>Energy has the sharpest within-bin Product Gini across HS6 energy products: median <strong>{dec(energy.get("product_gini"))}</strong>, median top-1 share <strong>{pct(energy.get("top_1_product_share"))}</strong>.</li>
            <li>Intermediates are the largest import bucket: median import value share <strong>{pct(intermediates.get("import_value_share"))}</strong>.</li>
            <li>Across importer-years, the median product top-supplier share is <strong>{pct(ex4["summary"].get("median_top_supplier_share"))}</strong>.</li>
            <li>Products with top supplier share at least 75% are <strong>{pct(ex4["summary"].get("share_products_top_supplier_ge_75"))}</strong> of product rows but <strong>{pct(ex4["summary"].get("import_value_share_products_top_supplier_ge_75"))}</strong> of import value.</li>
          </ul>
        """,
        "bin_table": table_rows(
            ex3["bin_summary"],
            [
                ("label", "Import bin", "text"),
                ("product_gini", "Median Product Gini within bin", "dec"),
                ("top_1_product_share", "Median top-1 share", "pct"),
                ("import_value_share", "Median import value share", "pct"),
                ("product_gini_reduction_when_excluded", "Leave-one-out Gini effect", "dec"),
                ("active_products", "Active HS6 products", "int"),
            ],
        ),
        "supplier_text": (
            f"For India in 2024, top-supplier share is at least 75% in "
            f"{pct(india_supplier.get('share_products_top_supplier_ge_75'))} of imported HS6 rows, "
            f"accounting for {pct(india_supplier.get('import_value_share_products_top_supplier_ge_75'))} "
            f"of import value."
        ),
        "io_text": (
            f"Bottom line: Exercise 11 weakens the broad intermediate-processing claim. The import products that raise total Product-Gini concentration across HS6 products are generally less export-linked, including among intermediates. The stronger evidence is supplier-country concentration, not Product-Gini concentration; this leaves room for a narrower China/electronics/machinery-style supplier-exposure story."
        ),
        "ex11_result_ladder": f"""
          <div class="result-ladder">
            <article><span>Product-Gini linkage</span><strong>Negative</strong><p>HS6 Product-Gini contribution to export value: {dec(ex11_main.get("coef"))}; export probability: {dec(ex11_any.get("coef"))}.</p></article>
            <article><span>Intermediate channel</span><strong>Negative</strong><p>Intermediate minus non-intermediate slope: {dec(ex11_interaction.get("coef"))}; concentration-driving intermediates are not more export-linked.</p></article>
            <article><span>Supplier-country exposure</span><strong>Positive</strong><p>Partner-HHI contribution to export value: {dec(ex11_supplier.get("coef"))}.</p></article>
            <article><span>HS2 robustness</span><strong>Does not rescue</strong><p>HS2 export value remains negative ({dec(ex11_hs2_value.get("coef"))}); probability/share and intermediate intensity are small or not significant.</p></article>
            <article><span>Commodity exclusion</span><strong>Result survives</strong><p>Oil/gas/gold/coal rows are {pct(commodity_stats.get("commodity_outlier_row_share"))} of rows and {pct(commodity_stats.get("commodity_outlier_import_value_share"))} of import value; the core signs remain.</p></article>
          </div>
        """,
        "ex11_detail_blocks": f"""
          <div class="interpretation-grid">
            <article class="note">
              <h3>1. HS6 product-level result</h3>
              <p>Within the same country-year, after controlling for product import share and BEC bin, HS6 products with higher contribution to total import Product Gini tend to have lower export value. The export-value coefficient is <strong>{dec(ex11_main.get("coef"))}</strong>; the export-probability coefficient is <strong>{dec(ex11_any.get("coef"))}</strong>.</p>
            </article>
            <article class="note">
              <h3>2. Intermediate-channel test</h3>
              <p>The direct intermediate test is negative. The intermediate minus non-intermediate slope is <strong>{dec(ex11_interaction.get("coef"))}</strong>, so concentration-driving intermediate imports are not more export-linked than concentration-driving non-intermediates.</p>
            </article>
            <article class="note">
              <h3>3. Supplier-country concentration</h3>
              <p>This is the more supportive channel. Products that make import sourcing more concentrated by partner country are more export-linked; the Partner-HHI coefficient is <strong>{dec(ex11_supplier.get("coef"))}</strong>.</p>
            </article>
            <article class="note">
              <h3>4. HS2 robustness</h3>
              <p>Broadening from HS6 products to HS2 chapters does not rescue the intermediate-processing hypothesis. HS2 export value remains negative at <strong>{dec(ex11_hs2_value.get("coef"))}</strong>, export probability is <strong>{dec(ex11_hs2_any.get("coef"))}</strong>, export share is <strong>{dec(ex11_hs2_share.get("coef"))}</strong>, and the intermediate-intensity interaction is <strong>{dec(ex11_hs2_interaction.get("coef"))}</strong>.</p>
            </article>
            <article class="note">
              <h3>5. Oil/gas/gold/coal exclusion</h3>
              <p>Excluding HS4 codes 2701, 2709, 2710, 2711, and 7108 does not overturn the result. These rows are only {pct(commodity_stats.get("commodity_outlier_row_share"))} of product rows but {pct(commodity_stats.get("commodity_outlier_import_value_share"))} of import value; after excluding them, the Product-Gini and intermediate coefficients remain negative and Partner-HHI remains positive.</p>
            </article>
          </div>
        """,
        "coefs_table": table_rows(
            ex11["coefficients"],
            [
                ("result", "Result", "text"),
                ("outcome", "Outcome", "text"),
                ("coef", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("nobs", "Obs.", "int"),
                ("interpretation", "Interpretation", "text"),
            ],
        ),
        "intermediate_effects_table": table_rows(
            ex11["intermediate_effects"],
            [
                ("effect", "Effect", "text"),
                ("coef", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("ci_low", "CI low", "dec"),
                ("ci_high", "CI high", "dec"),
            ],
        ),
        "commodity_table": table_rows(
            ex11["commodity_comparison"],
            [
                ("result", "Check", "text"),
                ("coef", "Coef.", "dec"),
                ("std_error", "SE", "dec"),
                ("p_value", "p-value", "dec"),
                ("nobs", "Obs.", "int"),
            ],
        ),
        "methods_source_table": source_table,
        "countries_table": countries_table,
    }
    return pages


def nav(active: str) -> str:
    links = [
        ("index.html", "Overview", "overview"),
        ("extension.html", "Extending 2001", "extension"),
        ("imports.html", "Import concentration", "imports"),
        ("methods.html", "Methods", "methods"),
    ]
    return "".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in links
    )


def layout(title: str, page: str, body: str) -> str:
    build_stamp = now_utc().replace("-", "").replace(":", "").replace("+", "").replace("T", "").replace("Z", "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="assets/site.css?v={build_stamp}">
</head>
<body data-page="{page}">
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="index.html">Trade Concentration Brief</a>
      <nav aria-label="Primary navigation">{nav(page)}</nav>
    </div>
  </header>
  <main>
{body}
  </main>
  <footer class="site-footer">
    <p>Generated from local research outputs on {now_utc()}.</p>
  </footer>
  <script src="assets/vendor/plotly.min.js"></script>
  <script src="assets/site-data.js?v={build_stamp}"></script>
  <script src="assets/site.js?v={build_stamp}"></script>
</body>
</html>
"""


def render_pages(context: dict[str, str]) -> dict[str, str]:
    index_body = f"""
    <section class="hero">
      <div class="eyebrow">Research memo</div>
      <h1>Extending Panagariya-Bagaria Trade Concentration Evidence Across Years</h1>
      <p>{context["summary_text"]}</p>
      <div class="hero-actions">
        <a class="button primary" href="extension.html">Explore the extension</a>
        <a class="button" href="imports.html">View import mechanisms</a>
      </div>
    </section>

    <section class="section hypothesis-section">
      {context["index_hypothesis"]}
    </section>

    <section class="section" id="headline-findings">
      <div class="section-heading">
        <h2>Headline Findings</h2>
      </div>
      {context["overview_cards"]}
    </section>

    <section class="section" id="sendable-brief">
      <article>
        <h2>Purpose of This Brief</h2>
        <ul class="callout-list">
          <li><strong>Extension:</strong> the Product-Gini, Partner-Gini, and Product-partner-cell-Gini concentration facts remain visible in the 33-country panel from 1988 to 2025.</li>
          <li><strong>Robustness:</strong> removing oil, precious metals/gold, aircraft, ships, and arms lowers export concentration only modestly.</li>
          <li><strong>Mechanisms:</strong> import concentration has energy, supplier-dominance, and input-output pieces, but the broad intermediate-processing story is weakened by the product-level Exercise 11 regressions.</li>
        </ul>
      </article>
    </section>



    <section class="section link-grid">
      <a href="extension.html"><span>01</span><strong>Extending 2001</strong><small>World map, country lines, top-share facts, exclusions, and null benchmarks.</small></a>
      <a href="imports.html"><span>02</span><strong>Imports</strong><small>Energy, intermediates, dominant suppliers, and input-output linkages.</small></a>
      <a href="methods.html"><span>03</span><strong>Methods</strong><small>Data coverage, definitions, and downloadable CSVs.</small></a>
    </section>
    """

    extension_body = f"""
    <section class="page-title">
      <div class="eyebrow">Extension of the 2001 cross-section</div>
      <h1>Concentration Persists Through the Full 1988-2025 Panel</h1>
    </section>

    <section class="section hypothesis-section">
      {context["extension_hypotheses"]}
    </section>

    <section class="section" id="extension-summary">
      <div class="section-heading">
        <h2>Interesting things</h2>
        {context["extension_takeaways"]}
      </div>
    </section>

    <section class="section tool-section" id="map-lines">
      <div class="tool-header">
        <div>
          <h2>Map and Country Lines</h2>
          <p>Click a map country or a line to identify it. Use the controls to compare selected countries.</p>
        </div>
        <div class="controls compact">
          <label>Flow <select id="map-flow"><option>Exports</option><option>Imports</option></select></label>
          <label>Metric <select id="map-metric"><option value="product_gini">Product Gini (HS6 products)</option><option value="partner_gini">Partner Gini (trade partners)</option><option value="product_partner_cell_gini">Product-partner cell Gini (HS6-by-partner)</option></select></label>
          <div class="year-control">
            <div class="year-control-head"><span>Year</span><output id="map-year-label" for="map-year-slider"></output></div>
            <input id="map-year-slider" type="range" min="1988" max="2025" step="1">
            <div class="year-range-labels"><span id="map-year-min"></span><span id="map-year-max"></span></div>
            <select id="map-year" class="sr-only" aria-label="Map year"></select>
            <p class="control-note">Drag the year bar to see how country Ginis change over time.</p>
          </div>
        </div>
      </div>
      {context["map_note"]}
      <div id="world-map" class="chart tall"></div>
      <div class="tool-grid">
        <aside class="selector-panel">
          <div class="selector-actions">
            <input id="country-search" type="search" placeholder="Filter countries">
            <button type="button" id="select-all-countries">All</button>
            <button type="button" id="clear-countries">Clear</button>
          </div>
          <div id="country-checkboxes" class="country-list"></div>
        </aside>
        <div>
          <div class="controls compact">
            <label>Line flow <select id="line-flow"><option>Exports</option><option>Imports</option></select></label>
            <label>Line metric <select id="line-metric"><option value="product_gini">Product Gini (HS6 products)</option><option value="partner_gini">Partner Gini (trade partners)</option><option value="product_partner_cell_gini">Product-partner cell Gini (HS6-by-partner)</option></select></label>
          </div>
          {context["line_note"]}
          <div id="country-lines" class="chart tall"></div>
          <div id="line-detail" class="detail-box">Click a line or map country to see country details.</div>
        </div>
      </div>
    </section>

    <section class="section two-col" id="top-share-evidence">
      <article>
        <h2>Top-Share Evidence</h2>
        <p>Ginis are high partly because the top products and partners carry large trade shares. “Top item” is the largest single product or partner in a country’s trade basket; “top five” is the combined share of the five largest products or partners. Partner top shares are higher because countries often trade with a small number of major destinations or sources, while product baskets contain thousands of HS6 items.</p>
        {context["top_share_note"]}
        {context["top_share_table"]}
      </article>
      <article>
        <h2>Common Top-Five Items</h2>
        <p>These are the latest-year products or partners that appear most often in country top-five lists.</p>
        {context["top_frequency_note"]}
        {context["top_frequency_table"]}
      </article>
    </section>

    <section class="section" id="top-five-loo">
      <div class="section-heading">
        <h2>Which Top-Five Items Actually Raise Gini?</h2>
        <p>The frequency tables show what appears often. The leave-one-out charts ask a different question: if the item is removed from a country's latest-year trade basket, how much does the Gini fall?</p>
      </div>
      {context["loo_note"]}
      {context["loo_interpretation"]}
      <div class="figure-row full-width">
        <figure><a class="figure-link" href="assets/figures/ex1_loo_all_reporters.png"><img src="assets/figures/ex1_loo_all_reporters.png" alt="Mean item leave-one-out Gini contribution across all reporters"></a><figcaption>All-reporter average: best for identifying broad, system-wide top-five items that raise concentration across the full latest-year reporter sample.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex1_loo_top5_reporters.png"><img src="assets/figures/ex1_loo_top5_reporters.png" alt="Mean item leave-one-out Gini contribution where item is top five"></a><figcaption>Conditional average where the item is actually in a reporter's top five: best for mechanism spotting, but rare items can have large conditional effects.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="lumpy-exclusions">
      <div class="section-heading">
        <h2>Lumpy-Product Exclusions</h2>
        <p>{context["lumpy_text"]}</p>
      </div>
      {context["lumpy_note"]}
      <div id="exclusion-chart" class="chart"></div>
      {context["exclusion_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex6_before_after.png"><img src="assets/figures/ex6_before_after.png" alt="Before and after export Product Gini over time"></a><figcaption>Export Product Gini across HS6 products before and after full lumpy-product exclusion.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex6_removed.png"><img src="assets/figures/ex6_removed.png" alt="Trade share removed over time"></a><figcaption>Trade share removed by exclusion specification.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="benchmark-ladder">
      <div class="section-heading">
        <h2>Benchmark Ladder</h2>
        <p>Exercise 10 is best read as a ladder of benchmarks. The active-count-only null is a loose benchmark. The HS2-preserving null is more conservative because it keeps broad HS2 sector totals intact, so it is explicitly not complete randomization.</p>
      </div>
      {context["benchmark_note"]}
      <div id="benchmark-chart" class="chart"></div>
      {context["benchmark_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex10_actual_vs_benchmark.png"><img src="assets/figures/ex10_actual_vs_benchmark.png" alt="Actual versus HS2-preserved benchmark Product Gini"></a><figcaption>Actual Product Ginis across HS6 products remain above the HS2-preserved random benchmark.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex10_percentile.png"><img src="assets/figures/ex10_percentile.png" alt="Share above the 95th benchmark percentile"></a><figcaption>Country-year observations above the 95th simulation percentile.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="growth-buckets">
      <div class="section-heading">
        <h2>Descriptive Growth Buckets</h2>
        <p>This local Exercise 2 output is included as context only: it buckets export concentration states and reports subsequent growth. It should not be read as causal evidence.</p>
      </div>
      {context["growth_note"]}
      {context["growth_table"]}
    </section>
    """

    imports_body = f"""
    <section class="page-title">
      <div class="eyebrow">Import concentration mechanisms</div>
      <h1>Energy, Intermediates, Suppliers, and Input-Output Linkages</h1>
    </section>

    <section class="section hypothesis-section">
      {context["imports_hypotheses"]}
    </section>

    <section class="section" id="imports-summary">
      <div class="section-heading">
        <h2>Interesting things</h2>
        {context["imports_takeaways"]}
      </div>
    </section>

    <section class="section" id="import-bins">
      <div class="section-heading">
        <h2>Exercise 3: Import Bins</h2>
        <p>Energy has the strongest within-bin Product Gini across HS6 products and a positive leave-one-bin-out contribution. Intermediates matter more by scale: they are a large part of the import bill and include specialized input categories where a few HS6 lines can carry meaningful value.</p>
      </div>
      <div class="note">
        <p><strong>Import value share</strong> means the bin's share of a country's total import value in a country-year. <strong>Product Gini within bin</strong> measures concentration across HS6 products inside that bin. <strong>Top-1 product share</strong> is the largest HS6 product's share of that bin. <strong>Leave-one-out Gini effect</strong> is the change in overall import Product Gini when the bin is removed; positive values mean the bin raises concentration.</p>
      </div>
      <div id="import-bin-chart" class="chart"></div>
      {context["bin_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex3_value_share.png"><img src="assets/figures/ex3_value_share.png" alt="Median import value share by bin"></a><figcaption>Median import value share by BEC-style bin.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex3_leave_one_out.png"><img src="assets/figures/ex3_leave_one_out.png" alt="Gini reduction when each bin is excluded"></a><figcaption>Leave-one-bin-out effect on latest-year import Product Gini across HS6 products.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="supplier-dominance">
      <div class="section-heading">
        <h2>Exercise 4: Dominant Suppliers</h2>
        <p>{context["supplier_text"]}</p>
      </div>
      <div id="supplier-chart" class="chart"></div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex4_supplier_time.png"><img src="assets/figures/ex4_supplier_time.png" alt="Dominant supplier summary over time"></a><figcaption>Dominant supplier metrics over time.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex4_supplier_distribution.png"><img src="assets/figures/ex4_supplier_distribution.png" alt="Latest-year distribution of top supplier shares"></a><figcaption>Latest-year top-supplier-share distribution.</figcaption></figure>
      </div>
    </section>

    <section class="section" id="io-linkage">
      <div class="section-heading">
        <h2>Exercise 11: What the Import-Linkage Test Says</h2>
        <p>{context["io_text"]}</p>
      </div>
      {context["ex11_result_ladder"]}
      <div id="io-chart" class="chart"></div>
      <p class="note">The IO chart remains useful descriptive context: top export sectors often have concentrated imported-input baskets. But the HS6 product-level linkage test below shows that the specific import products driving aggregate Product-Gini concentration are generally not the export-linked products.</p>
    </section>

    <section class="section" id="ex11-regressions">
      <div class="section-heading">
        <h2>Exercise 11 Regression Audit Trail</h2>
        <p>The table and figures separate Product-Gini concentration from supplier-country concentration. This weakens the broad intermediate-processing claim and points to a narrower supplier-exposure channel.</p>
      </div>
      {context["ex11_detail_blocks"]}
      {context["coefs_table"]}
      <h3 class="subsection-title">Intermediate slopes</h3>
      {context["intermediate_effects_table"]}
      <h3 class="subsection-title">Commodity-exclusion robustness</h3>
      {context["commodity_table"]}
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex11_export_linkage_decile.png"><img src="assets/figures/ex11_export_linkage_decile.png" alt="Export linkage by Product-Gini leave-one-out decile"></a><figcaption>HS6 export linkage by Product-Gini contribution decile.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex11_hs2_linkage_decile.png"><img src="assets/figures/ex11_hs2_linkage_decile.png" alt="HS2 export linkage by leave-one-out decile"></a><figcaption>HS2 robustness: export linkage by aggregated concentration-contribution decile.</figcaption></figure>
      </div>
      <div class="figure-row">
        <figure><a class="figure-link" href="assets/figures/ex11_india_io.png"><img src="assets/figures/ex11_india_io.png" alt="India top export input exposure over time"></a><figcaption>India top-export-sector imported-input exposure.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex11_coefficients.png"><img src="assets/figures/ex11_coefficients.png" alt="Intermediate channel coefficients"></a><figcaption>Intermediate-channel regression coefficients.</figcaption></figure>
        <figure><a class="figure-link" href="assets/figures/ex11_india_supplier_scatter.png"><img src="assets/figures/ex11_india_supplier_scatter.png" alt="India supplier concentration linkage scatter"></a><figcaption>India supplier concentration and export linkage scatter.</figcaption></figure>
      </div>
    </section>
    """

    methods_body = f"""
    <section class="page-title">
      <div class="eyebrow">Definitions and data</div>
      <h1>Methods, Coverage, and Downloads</h1>
      <p>The site is static, but it is generated from a reproducible Python script and a fixed set of local result artifacts.</p>
    </section>

    <section class="section hypothesis-section">
      {context["methods_hypothesis"]}
    </section>

    <section class="section two-col" id="definitions">
      <article>
        <h2>Coverage</h2>
        <p>The core panel covers 33 countries, annual observations from 1988 through 2025, and two flows: exports and imports. The empirical sample follows the local Exercise 1 output, which is the extension of the Panagariya-Bagaria country set.</p>
        {context["countries_table"]}
      </article>
      <article>
        <h2>Definitions</h2>
        <ul class="callout-list">
          <li><strong>Product Gini:</strong> concentration across HS6 product totals within a country-year-flow.</li>
          <li><strong>Partner Gini:</strong> concentration across destination or source partner totals within a country-year-flow.</li>
          <li><strong>Product-partner cell Gini:</strong> concentration across HS6 product-by-partner cells within a country-year-flow; this is the product-partner/partner-product measure.</li>
          <li><strong>Lumpy-product exclusions:</strong> HS27 oil/mineral fuels, HS71 precious stones/metals, HS88 aircraft, HS89 ships, and HS93 arms.</li>
          <li><strong>HS2-preserving benchmark:</strong> randomizes within broad HS2 sectors while preserving HS2 totals and active HS6 counts; it is a conditional benchmark, not complete randomization.</li>
        </ul>
      </article>
    </section>

    <section class="section" id="source-artifacts">
      <div class="section-heading">
        <h2>Source Artifacts Used</h2>
        <p>All numeric claims on the site come from these tables. The public-paper/draft PDF context informed editorial framing only.</p>
      </div>
      {context["methods_source_table"]}
    </section>

    <section class="section" id="downloads">
      <div class="section-heading">
        <h2>Downloadable Tables</h2>
        <p>These CSVs are copied into the site so the small public brief can be inspected without the raw Comtrade files or large Parquet checkpoints.</p>
      </div>
      <div class="download-grid">
        {"".join(f'<a href="assets/downloads/{name}">{name}</a>' for name in DOWNLOADS)}
      </div>
    </section>
    """

    return {
        "index.html": layout("Trade Concentration Brief", "overview", index_body),
        "extension.html": layout("Extending the 2001 Trade Concentration Evidence", "extension", extension_body),
        "imports.html": layout("Import Concentration Mechanisms", "imports", imports_body),
        "methods.html": layout("Methods and Downloads", "methods", methods_body),
    }


def site_css() -> str:
    return """
:root {
  --bg: #fbfbfa;
  --paper: #ffffff;
  --ink: #1f2933;
  --muted: #667085;
  --line: #e2e5e9;
  --accent: #0b6b62;
  --accent-dark: #064e49;
  --blue: #2563eb;
  --gold: #b7791f;
  --shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
* { box-sizing: border-box; }
html { scroll-padding-top: 112px; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
a { color: inherit; }
.site-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid var(--line);
}
.header-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 14px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.brand {
  font-weight: 700;
  text-decoration: none;
}
nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
nav a {
  text-decoration: none;
  color: var(--muted);
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 14px;
}
nav a.active, nav a:hover {
  color: var(--ink);
  background: #eef2f6;
}
main { max-width: 1160px; margin: 0 auto; padding: 24px 22px 56px; }
.section, .page-title, .hero, :target { scroll-margin-top: 112px; }
.hero, .page-title {
  padding: 34px 0 20px;
  border-bottom: 1px solid var(--line);
}
.hero h1, .page-title h1 {
  font-size: 44px;
  line-height: 1.08;
  letter-spacing: 0;
  max-width: 940px;
  margin: 8px 0 14px;
}
.hero p, .page-title p {
  max-width: 860px;
  color: var(--muted);
  font-size: 18px;
}
.eyebrow {
  color: var(--accent-dark);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
}
.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 24px; }
.button {
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  text-decoration: none;
  background: var(--paper);
}
.button.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.section { padding: 30px 0; border-bottom: 1px solid var(--line); }
.section-heading {
  display: grid;
  grid-template-columns: minmax(220px, 0.55fr) minmax(260px, 1fr);
  gap: 24px;
  align-items: start;
  margin-bottom: 18px;
}
.section-heading h2, .two-col h2, .tool-header h2 { margin: 0 0 8px; font-size: 24px; line-height: 1.2; }
.section-heading p, .two-col p, .tool-header p { color: var(--muted); margin-top: 0; }
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.stat-card, .note, .selector-panel, .link-grid a, .hypothesis-card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.stat-card { padding: 18px; min-height: 142px; }
.stat-card span, .stat-card small { display: block; color: var(--muted); }
.stat-card strong { display: block; font-size: 36px; line-height: 1; margin: 14px 0; }
.two-col {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 28px;
}
.note { padding: 18px; }
.link-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 14px;
}
.link-grid a {
  display: block;
  text-decoration: none;
  padding: 18px;
}
.link-grid span { color: var(--accent); font-weight: 700; }
.link-grid strong { display: block; font-size: 21px; margin: 8px 0; }
.link-grid small { color: var(--muted); }
.hypothesis-section { padding-top: 22px; }
.hypothesis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.hypothesis-card {
  padding: 16px;
}
.hypothesis-kicker {
  color: var(--accent-dark);
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.hypothesis-card h3 {
  margin: 0 0 12px;
  font-size: 20px;
  line-height: 1.2;
}
.hypothesis-card dl {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
}
.hypothesis-card dt {
  color: var(--muted);
  font-weight: 700;
  font-size: 13px;
}
.hypothesis-card dd {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
}
.evidence-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.evidence-links a {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--accent-dark);
  text-decoration: none;
  font-size: 13px;
  background: #f8faf9;
}
.evidence-links a:hover { border-color: var(--accent); }
.evidence-note {
  border: 1px solid var(--line);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px 14px;
  margin: 12px 0 18px;
}
.evidence-note dl {
  display: grid;
  grid-template-columns: 170px minmax(0, 1fr);
  gap: 6px 14px;
  margin: 0;
}
.evidence-note dt {
  color: var(--accent-dark);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.evidence-note dd {
  margin: 0;
  color: var(--ink);
  font-size: 14px;
}
.result-ladder {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0 20px;
}
.result-ladder article {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  padding: 12px;
}
.result-ladder span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.result-ladder strong {
  display: block;
  margin: 6px 0;
  color: var(--accent-dark);
  font-size: 18px;
  line-height: 1.15;
}
.result-ladder p {
  color: var(--muted);
  font-size: 13px;
  margin: 0;
}
.interpretation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.next-step-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin: 18px 0;
}
.subsection-title {
  margin: 24px 0 10px;
  font-size: 18px;
}
.callout-list { margin: 0; padding-left: 18px; color: var(--ink); }
.callout-list li { margin: 8px 0; }
.tool-section {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 22px;
  margin-top: 26px;
}
.tool-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.controls label {
  color: var(--muted);
  font-size: 13px;
  display: grid;
  gap: 4px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.year-control {
  min-width: 280px;
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
}
.year-control-head, .year-range-labels {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}
.year-control-head span {
  font-weight: 600;
}
#map-year-label {
  color: var(--ink);
  font-weight: 700;
  font-size: 18px;
}
input[type="range"] {
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
}
.control-note {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
select, input[type="search"] {
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: white;
  color: var(--ink);
  padding: 8px 10px;
  font: inherit;
}
button {
  min-height: 36px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f8fafc;
  color: var(--ink);
  padding: 8px 11px;
  cursor: pointer;
}
button:hover { border-color: var(--accent); }
.chart {
  width: 100%;
  min-height: 430px;
  margin: 14px 0;
}
.chart.tall { min-height: 560px; }
.tool-grid {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}
.selector-panel { padding: 12px; max-height: 660px; overflow: hidden; }
.selector-actions {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 6px;
  margin-bottom: 10px;
}
.country-list {
  display: grid;
  gap: 6px;
  max-height: 570px;
  overflow: auto;
  padding-right: 4px;
}
.country-list label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 14px;
}
.detail-box {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
  color: var(--muted);
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow-x: auto;
  display: block;
  max-width: 100%;
}
thead, tbody, tr { width: 100%; }
th, td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
  font-size: 13px;
}
th { background: #eef2f6; font-weight: 700; white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
.figure-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}
.figure-row.full-width { grid-template-columns: 1fr; }
.figure-row.full-width figure { max-width: 980px; margin: 0 auto; }
.figure-row figure {
  margin: 0;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
}
.figure-link { display: block; }
.figure-row img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 4px;
}
figcaption {
  color: var(--muted);
  font-size: 13px;
  margin-top: 8px;
}
.download-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.download-grid a {
  display: block;
  padding: 12px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--accent-dark);
  overflow-wrap: anywhere;
}
.site-footer {
  max-width: 1180px;
  margin: 0 auto;
  padding: 18px 22px 40px;
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 860px) {
  .header-inner, .tool-header, .section-heading { display: block; }
  nav { justify-content: flex-start; margin-top: 12px; }
  .stat-grid, .two-col, .link-grid, .hypothesis-grid, .result-ladder, .interpretation-grid, .next-step-grid, .tool-grid, .figure-row, .download-grid {
    grid-template-columns: 1fr;
  }
  .hero h1, .page-title h1 { font-size: 32px; }
  .hero p, .page-title p { font-size: 16px; }
  .hypothesis-card dl { grid-template-columns: 1fr; gap: 4px; }
  .evidence-note dl { grid-template-columns: 1fr; }
  .tool-section { padding: 14px; }
  .controls { align-items: stretch; }
  .controls label, .year-control { width: 100%; min-width: 0; }
  .chart, .chart.tall { min-height: 430px; }
  table { overflow-x: auto; }
}
"""


def site_js() -> str:
    return """
(function () {
  const DATA = window.TRADE_GINI_DATA || {};
  const COLORS = ['#0f766e', '#2563eb', '#b7791f', '#dc2626', '#7c3aed', '#0891b2', '#4d7c0f', '#be123c', '#4338ca', '#a16207', '#0f172a', '#ea580c'];
  const config = { responsive: true, displayModeBar: true, displaylogo: false };

  function fmt(value, digits = 3) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
    return Number(value).toFixed(digits);
  }

  function pct(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
    return (100 * Number(value)).toFixed(digits) + '%';
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function relayout() {
    document.querySelectorAll('.js-plotly-plot').forEach((node) => Plotly.Plots.resize(node));
  }

  function layout(title, ytitle) {
    return {
      title: { text: title, x: 0, xanchor: 'left', font: { size: 18 } },
      margin: { l: 56, r: 24, t: 52, b: 48 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: '#ffffff',
      hovermode: 'closest',
      xaxis: { gridcolor: '#e5e7eb', zeroline: false },
      yaxis: { title: ytitle || '', gridcolor: '#e5e7eb', zeroline: false },
      legend: { orientation: 'h', y: -0.2 }
    };
  }

  function rowsFor(flow, metric, year) {
    return (DATA.exercise1?.panel || []).filter((row) => row.flow === flow && Number(row.year) === Number(year) && row[metric] !== null);
  }

  function mapScaleRange(flow, metric) {
    const values = (DATA.exercise1?.panel || [])
      .filter((row) => row.flow === flow && row[metric] !== null)
      .map((row) => Number(row[metric]))
      .filter((value) => Number.isFinite(value));
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return null;
    return { min, max };
  }

  function currentMapYear() {
    return byId('map-year-slider')?.value || byId('map-year')?.value;
  }

  function setMapYear(value) {
    const slider = byId('map-year-slider');
    const select = byId('map-year');
    const label = byId('map-year-label');
    if (slider) slider.value = value;
    if (select) select.value = value;
    if (label) label.textContent = value;
  }

  function selectedCountries() {
    return Array.from(document.querySelectorAll('.country-check:checked')).map((el) => el.value);
  }

  function setDetail(row, metric) {
    const box = byId('line-detail');
    if (!box || !row) return;
    box.innerHTML = '<strong>' + row.country + '</strong> (' + row.iso3 + '), ' + row.year + ' ' + row.flow +
      '<br>' + (DATA.labels?.metrics?.[metric] || metric) + ': ' + fmt(row[metric]) +
      '<br>Product Gini (HS6 products): ' + fmt(row.product_gini) +
      ' | Partner Gini: ' + fmt(row.partner_gini) +
      ' | Cell Gini: ' + fmt(row.product_partner_cell_gini);
  }

  function renderMap() {
    const node = byId('world-map');
    if (!node) return;
    const flow = byId('map-flow').value;
    const metric = byId('map-metric').value;
    const year = currentMapYear();
    const rows = rowsFor(flow, metric, year);
    const scaleRange = mapScaleRange(flow, metric);
    const trace = {
      type: 'choropleth',
      locations: rows.map((r) => r.iso3),
      z: rows.map((r) => r[metric]),
      text: rows.map((r) => r.country),
      customdata: rows,
      colorscale: [
        [0, '#e0f2fe'],
        [0.5, '#2dd4bf'],
        [1, '#0f172a']
      ],
      zauto: !scaleRange,
      zmin: scaleRange?.min,
      zmax: scaleRange?.max,
      colorbar: { title: DATA.labels?.metrics?.[metric] || metric },
      marker: { line: { color: '#ffffff', width: 0.4 } },
      hovertemplate: '<b>%{text}</b><br>Gini: %{z:.3f}<extra></extra>'
    };
    Plotly.react(node, [trace], {
      margin: { l: 0, r: 0, t: 10, b: 0 },
      geo: {
        projection: { type: 'natural earth' },
        showframe: false,
        showcoastlines: true,
        coastlinecolor: '#94a3b8',
        bgcolor: 'rgba(0,0,0,0)'
      },
      paper_bgcolor: 'rgba(0,0,0,0)'
    }, config);
    node.on('plotly_click', (event) => {
      const row = event.points?.[0]?.customdata;
      if (!row) return;
      const check = document.querySelector('.country-check[value="' + row.iso3 + '"]');
      if (check) check.checked = true;
      setDetail(row, metric);
      renderLines();
    });
  }

  function renderCountryList() {
    const list = byId('country-checkboxes');
    if (!list) return;
    const selectedDefaults = new Set(['IND', 'USA', 'CHN', 'DEU', 'JPN']);
    list.innerHTML = '';
    (DATA.countries || []).forEach((country) => {
      const label = document.createElement('label');
      label.dataset.country = (country.country || '').toLowerCase();
      label.dataset.iso3 = country.iso3;
      label.innerHTML = '<input class="country-check" type="checkbox" value="' + country.iso3 + '"' +
        (selectedDefaults.has(country.iso3) ? ' checked' : '') + '> ' + country.country;
      list.appendChild(label);
    });
    list.addEventListener('change', renderLines);
  }

  function filterCountryList() {
    const query = (byId('country-search')?.value || '').toLowerCase();
    document.querySelectorAll('#country-checkboxes label').forEach((label) => {
      const match = label.dataset.country.includes(query) || label.dataset.iso3.toLowerCase().includes(query);
      label.style.display = match ? 'flex' : 'none';
    });
  }

  function renderLines() {
    const node = byId('country-lines');
    if (!node) return;
    const flow = byId('line-flow').value;
    const metric = byId('line-metric').value;
    const selected = selectedCountries();
    const rows = (DATA.exercise1?.panel || []).filter((row) => row.flow === flow && selected.includes(row.iso3));
    const grouped = new Map();
    rows.forEach((row) => {
      if (!grouped.has(row.iso3)) grouped.set(row.iso3, []);
      grouped.get(row.iso3).push(row);
    });
    const traces = Array.from(grouped.entries()).map(([iso3, group], index) => {
      group.sort((a, b) => Number(a.year) - Number(b.year));
      return {
        type: 'scatter',
        mode: 'lines+markers',
        name: group[0]?.country || iso3,
        x: group.map((r) => r.year),
        y: group.map((r) => r[metric]),
        customdata: group,
        line: { color: COLORS[index % COLORS.length], width: 2 },
        marker: { size: 5 },
        hovertemplate: '<b>%{fullData.name}</b><br>%{x}: %{y:.3f}<extra></extra>'
      };
    });
    Plotly.react(node, traces, layout((DATA.labels?.metrics?.[metric] || metric) + ' over time', 'Gini'), config);
    node.on('plotly_click', (event) => {
      const row = event.points?.[0]?.customdata;
      setDetail(row, metric);
    });
  }

  function setupExtension() {
    const years = Array.from(new Set((DATA.exercise1?.panel || []).map((row) => row.year))).sort((a, b) => a - b);
    const yearSelect = byId('map-year');
    const yearSlider = byId('map-year-slider');
    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    years.forEach((year) => {
      const option = document.createElement('option');
      option.value = year;
      option.textContent = year;
      if (year === maxYear) option.selected = true;
      yearSelect.appendChild(option);
    });
    if (yearSlider) {
      yearSlider.min = minYear;
      yearSlider.max = maxYear;
      yearSlider.step = 1;
      yearSlider.value = maxYear;
      byId('map-year-min').textContent = minYear;
      byId('map-year-max').textContent = maxYear;
    }
    setMapYear(maxYear);
    renderCountryList();
    ['map-flow', 'map-metric'].forEach((id) => byId(id)?.addEventListener('change', renderMap));
    byId('map-year')?.addEventListener('change', (event) => {
      setMapYear(event.target.value);
      renderMap();
    });
    byId('map-year-slider')?.addEventListener('input', (event) => {
      setMapYear(event.target.value);
      renderMap();
    });
    byId('map-year-slider')?.addEventListener('change', (event) => {
      setMapYear(event.target.value);
      renderMap();
    });
    ['line-flow', 'line-metric'].forEach((id) => byId(id)?.addEventListener('change', renderLines));
    byId('country-search')?.addEventListener('input', filterCountryList);
    byId('select-all-countries')?.addEventListener('click', () => {
      document.querySelectorAll('.country-check').forEach((el) => { el.checked = true; });
      renderLines();
    });
    byId('clear-countries')?.addEventListener('click', () => {
      document.querySelectorAll('.country-check').forEach((el) => { el.checked = false; });
      renderLines();
    });
    renderMap();
    renderLines();
    renderExclusionChart();
    renderBenchmarkChart();
  }

  function renderExclusionChart() {
    const node = byId('exclusion-chart');
    if (!node) return;
    const rows = DATA.exercise6?.median_by_variant || [];
    const trace = {
      type: 'bar',
      x: rows.map((r) => r.label),
      y: rows.map((r) => r.product_gini),
      marker: { color: '#0f766e' },
      hovertemplate: '%{x}<br>Median Product Gini (HS6 products): %{y:.3f}<extra></extra>'
    };
    Plotly.react(node, [trace], layout('Median export Product Gini after lumpy-product exclusions', 'Product Gini'), config);
  }

  function renderBenchmarkChart() {
    const node = byId('benchmark-chart');
    if (!node) return;
    const rows = DATA.exercise10?.benchmark_ladder || [];
    const traces = ['Exports', 'Imports'].map((flow, index) => {
      const flowRows = rows.filter((r) => r.flow === flow);
      return {
        type: 'bar',
        name: flow,
        x: flowRows.map((r) => r.benchmark),
        y: flowRows.map((r) => r.gap),
        marker: { color: COLORS[index] },
        hovertemplate: flow + '<br>%{x}<br>Actual minus benchmark: %{y:.3f}<extra></extra>'
      };
    });
    const chartLayout = layout('How far actual Product Ginis sit above random benchmarks', 'Actual minus benchmark Product Gini');
    chartLayout.barmode = 'group';
    Plotly.react(node, traces, chartLayout, config);
  }

  function setupImports() {
    renderImportBins();
    renderSupplierChart();
    renderIoChart();
  }

  function renderImportBins() {
    const node = byId('import-bin-chart');
    if (!node) return;
    const rows = DATA.exercise3?.bin_summary || [];
    const traces = [
      { name: 'Product Gini (within bin)', y: rows.map((r) => r.product_gini), marker: { color: '#0f766e' } },
      { name: 'Top-1 product share', y: rows.map((r) => r.top_1_product_share), marker: { color: '#b7791f' } },
      { name: 'Import value share', y: rows.map((r) => r.import_value_share), marker: { color: '#2563eb' } }
    ].map((trace) => ({
      type: 'bar',
      name: trace.name,
      x: rows.map((r) => r.label),
      y: trace.y,
      marker: trace.marker,
      hovertemplate: trace.name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    const chartLayout = layout('Import bins: concentration versus scale', 'Share or Gini');
    chartLayout.barmode = 'group';
    Plotly.react(node, traces, chartLayout, config);
  }

  function renderSupplierChart() {
    const node = byId('supplier-chart');
    if (!node) return;
    const rows = DATA.exercise4?.year_series || [];
    const traces = [
      ['median_top_supplier_share', 'Median top-supplier share', '#0f766e'],
      ['share_products_top_supplier_ge_75', 'Share of products with top supplier >=75%', '#b7791f'],
      ['import_value_share_products_top_supplier_ge_75', 'Import value share in >=75% rows', '#2563eb']
    ].map(([key, name, color]) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: rows.map((r) => r.year),
      y: rows.map((r) => r[key]),
      line: { color, width: 2 },
      hovertemplate: name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    Plotly.react(node, traces, layout('Dominant supplier measures over time', 'Share'), config);
  }

  function renderIoChart() {
    const node = byId('io-chart');
    if (!node) return;
    const rows = DATA.exercise11?.year_series || [];
    const traces = [
      ['weighted_top_sector_input_product_gini', 'Top-sector input Product Gini', '#0f766e'],
      ['weighted_top_sector_top_supplier_share', 'Top-sector top-supplier share', '#b7791f'],
      ['median_top_sector_matched_requirement_share', 'Matched requirement share', '#2563eb']
    ].map(([key, name, color]) => ({
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: rows.map((r) => r.year),
      y: rows.map((r) => r[key]),
      line: { color, width: 2 },
      hovertemplate: name + '<br>%{x}: %{y:.3f}<extra></extra>'
    }));
    Plotly.react(node, traces, layout('Top export sector imported-input exposure', 'Share or Gini'), config);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.dataset.page;
    if (page === 'extension') setupExtension();
    if (page === 'imports') setupImports();
    window.addEventListener('resize', relayout);
  });
})();
"""


def write_json_assets(output: Path, data: dict[str, Any]) -> None:
    json_text = json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    (output / "assets/site-data.json").write_text(json_text + "\n", encoding="utf-8")
    (output / "assets/site-data.js").write_text(
        "window.TRADE_GINI_DATA=" + json_text.replace("</", "<\\/") + ";\n",
        encoding="utf-8",
    )
    for needle in ["NaN", "undefined", "__PLACEHOLDER__"]:
        if needle in json_text:
            raise RuntimeError(f"Generated site data contains forbidden token: {needle}")


def prepare_output(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in ["assets", "index.html", "extension.html", "imports.html", "methods.html", "README.md"]:
        target = output / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    (output / "assets/vendor").mkdir(parents=True, exist_ok=True)
    (output / "assets/figures").mkdir(parents=True, exist_ok=True)
    (output / "assets/downloads").mkdir(parents=True, exist_ok=True)


def copy_assets(output: Path) -> None:
    for key, source in FIGURES.items():
        if not source.exists():
            raise FileNotFoundError(f"Required figure is missing: {source}")
        shutil.copy2(source, output / "assets/figures" / f"{key}.png")
    for filename, source in DOWNLOADS.items():
        if not source.exists():
            raise FileNotFoundError(f"Required downloadable CSV is missing: {source}")
        shutil.copy2(source, output / "assets/downloads" / filename)


def write_site(output: Path) -> None:
    data, context = build_data()
    pages = render_pages(context)
    prepare_output(output)
    for filename, html in pages.items():
        (output / filename).write_text(html, encoding="utf-8")
    (output / "assets/site.css").write_text(site_css(), encoding="utf-8")
    (output / "assets/site.js").write_text(site_js(), encoding="utf-8")
    (output / "assets/vendor/plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    write_json_assets(output, data)
    copy_assets(output)
    (output / "README.md").write_text(
        "# Trade Concentration Research Brief\n\n"
        "Generated by `scripts/build_trade_gini_site.py` from local result artifacts.\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory for the static site.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    write_site(args.output)
    print(f"Wrote static site to {args.output}")


if __name__ == "__main__":
    main()
