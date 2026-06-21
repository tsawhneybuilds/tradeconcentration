#!/usr/bin/env python3
"""Mechanism tests for the population gradient in import product concentration.

These regressions are descriptive. They ask whether the negative relationship
between population and import concentration is accounted for by observable
basket breadth, common zero-universe construction, hubs/microstates, use-bin
composition, openness/income controls, and lumpy top product categories.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from concentration_metrics import active_gini, weighted_gini  # noqa: E402
from run_world_relative_product_gini import compute_country_year_metrics  # noqa: E402
from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
FLOW = "Imports"
START_YEAR = 2000
END_YEAR = 2024
EXPECTED_BALANCED_COUNTRIES = 55
EXPECTED_ROWS = EXPECTED_BALANCED_COUNTRIES * (END_YEAR - START_YEAR + 1)
OUT_DIRNAME = "import_size_mechanism_tests"

WR_PANEL = (
    "world_relative_import_product_gini_tables/"
    "world_relative_import_product_gini_all_years.csv"
)
COUNTRY_PRODUCT = "world_relative_import_product_gini_harmonized_hs6_family_rd2_product_imports.parquet"
WORLD_PRODUCT = (
    ROOT
    / "data"
    / "processed"
    / "samples"
    / "world_broad"
    / "world_relative_import_product_gini_harmonized_hs6_family_world_product_imports.parquet"
)
COUNTRY_SIZE_PANEL = "country_size_effect_panel.parquet"
IMPORT_BIN_PANEL = "exercise_03_import_bin_concentration.parquet"
EXPLANATORY_PANEL = (
    ROOT
    / "results"
    / "samples"
    / COUNTRY_SAMPLE
    / "import_concentration_explanatory_regressions"
    / "analysis_panel.csv"
)
TOP_DRIVERS = (
    ROOT
    / "results"
    / "samples"
    / COUNTRY_SAMPLE
    / "world_relative_import_product_gini_contributions"
    / "world_relative_import_product_contribution_top_drivers.csv"
)

BASE_TERMS = ["log_population", "log_gdp_per_capita"]
PPP_TERMS = ["log_population", "log_gdp_pc_ppp_constant_2021_intl_usd"]
HUB_MICRO_ISO3 = {"HKG", "SGP", "LUX", "ISL", "GUY"}
MAIN_IMPORT_BINS = ["intermediates", "capital_goods", "final_consumption", "energy"]

LUMPY_CATEGORY_ORDER = [
    "aircraft",
    "gold_precious",
    "pharma",
    "vehicles",
    "food_staples",
]
ENERGY_CATEGORY = "energy"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = sorted(set(keys) - set(df.columns))
    if missing:
        raise RuntimeError(f"{label} is missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(10).to_dict("records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def assert_no_999999(frame: pd.DataFrame, column: str, label: str) -> None:
    if column not in frame.columns:
        raise RuntimeError(f"{label} is missing `{column}`.")
    text = frame[column].astype("string")
    count = int(text.str.contains("999999", regex=False, na=False).sum())
    if count:
        raise RuntimeError(f"{label} contains {count:,} product ids with excluded HS6 999999.")


def safe_log(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.where(values > 0, np.log(values), np.nan), index=series.index)


def parse_hs6(product_id: object) -> str:
    text = "" if product_id is None else str(product_id)
    matches = re.findall(r"(\d{6})", text)
    return str(matches[-1]).zfill(6) if matches else ""


def parse_hs6_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.extract(r"(\d{6})", expand=False).fillna("").astype(str)


def lumpy_category_from_hs6(hs6: str) -> str:
    if not hs6 or hs6 == "999999":
        return ""
    hs2 = hs6[:2]
    hs4 = hs6[:4]
    if hs4 in {"8802", "8803"}:
        return "aircraft"
    if hs2 == "71":
        return "gold_precious"
    if hs2 == "30":
        return "pharma"
    if hs2 == "87":
        return "vehicles"
    if hs2 in {"10", "11", "15", "17"}:
        return "food_staples"
    if hs2 == "27":
        return ENERGY_CATEGORY
    return ""


def gini_with_common_zeros(active_values: pd.Series | np.ndarray, universe_size: int) -> float:
    values = pd.to_numeric(pd.Series(active_values), errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0 or universe_size <= 0:
        return np.nan
    if values.size > universe_size:
        raise RuntimeError(f"Active product count {values.size:,} exceeds common universe size {universe_size:,}.")
    values.sort()
    total = float(values.sum())
    if total <= 0:
        return np.nan
    zeros = universe_size - values.size
    ranks = np.arange(zeros + 1, universe_size + 1, dtype=float)
    numerator = float(np.sum((2 * ranks - universe_size - 1) * values))
    return numerator / (universe_size * total)


def load_world_relative_panel(country_sample: str) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / WR_PANEL
    if not path.exists():
        raise FileNotFoundError(f"Missing world-relative import panel: {path}")
    df = pd.read_csv(path)
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "metric_valid",
        "world_relative_import_product_gini",
        "active_product_gini",
        "active_product_count",
        "country_active_products",
        "world_benchmark_products",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"World-relative import panel missing columns: {missing}")
    df = df[df["flow"].eq(FLOW) & df["metric_valid"].astype(bool)].copy()
    df["reporter_code"] = pd.to_numeric(df["reporter_code"], errors="coerce").astype("Int64")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["reporter_code", "year"]).copy()
    df["reporter_code"] = df["reporter_code"].astype(int)
    df["year"] = df["year"].astype(int)
    df = df[df["year"].between(START_YEAR, END_YEAR)].copy()
    validate_unique(df, ["reporter_code", "year"], "world-relative import panel")
    if len(df) != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS:,} balanced rows; found {len(df):,}.")
    if df["reporter_code"].nunique() != EXPECTED_BALANCED_COUNTRIES:
        raise RuntimeError(
            f"Expected {EXPECTED_BALANCED_COUNTRIES} balanced countries; "
            f"found {df['reporter_code'].nunique()}."
        )
    per_country = df.groupby("reporter_code")["year"].nunique()
    if not per_country.eq(END_YEAR - START_YEAR + 1).all():
        bad = per_country[~per_country.eq(END_YEAR - START_YEAR + 1)].to_dict()
        raise RuntimeError(f"World-relative panel is not balanced by country: {bad}")
    out = df[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "world_relative_import_product_gini",
            "active_product_gini",
            "active_product_count",
            "country_active_products",
            "world_benchmark_products",
        ]
    ].copy()
    out["log_standard_active_import_products"] = safe_log(out["active_product_count"])
    out["log_harmonized_active_import_products"] = safe_log(out["country_active_products"])
    return out.sort_values(["country", "year"]).reset_index(drop=True)


def load_controls(country_sample: str, panel: pd.DataFrame) -> pd.DataFrame:
    size_path = sample_processed_path(COUNTRY_SIZE_PANEL, country_sample)
    if not size_path.exists():
        raise FileNotFoundError(f"Missing country-size panel: {size_path}")
    size = pd.read_parquet(size_path)
    size = size[size["flow"].eq(FLOW) & size["variant"].astype(str).str.lower().eq("baseline")].copy()
    size = size[
        [
            "reporter_code",
            "year",
            "log_population",
            "log_gdp_per_capita",
            "population",
            "gdp_current_usd",
        ]
    ].drop_duplicates(["reporter_code", "year"])
    validate_unique(size, ["reporter_code", "year"], "country-size controls")

    if not EXPLANATORY_PANEL.exists():
        raise FileNotFoundError(f"Missing explanatory controls panel: {EXPLANATORY_PANEL}")
    explanatory = pd.read_csv(EXPLANATORY_PANEL)
    explanatory = explanatory[
        [
            "reporter_code",
            "year",
            "trade_openness_pct_gdp",
            "merchandise_trade_openness_pct_gdp",
            "wdi_goods_services_trade_openness_pct_gdp",
            "tariff_applied_weighted_mean_pct",
            "log_gdp_pc_ppp_constant_2021_intl_usd",
            "oil_export_share",
        ]
    ].drop_duplicates(["reporter_code", "year"])
    validate_unique(explanatory, ["reporter_code", "year"], "import explanatory controls")

    out = (
        panel[["reporter_code", "year"]]
        .drop_duplicates()
        .merge(size, on=["reporter_code", "year"], how="left", validate="one_to_one")
        .merge(explanatory, on=["reporter_code", "year"], how="left", validate="one_to_one")
    )
    missing_main = int(out[["log_population", "log_gdp_per_capita"]].isna().any(axis=1).sum())
    if missing_main:
        examples = out[out[["log_population", "log_gdp_per_capita"]].isna().any(axis=1)].head(10).to_dict("records")
        raise RuntimeError(f"Missing main population/GDP controls for {missing_main:,} rows: {examples}")
    return out


def product_metrics_for_groups(product: pd.DataFrame, universe: pd.Series, prefix: str) -> pd.DataFrame:
    universe_size = int(universe.nunique())
    grouped = product.groupby(["reporter_code", "year"], sort=True)["trade_value"]
    rows = []
    for (reporter_code, year), values in grouped:
        rows.append(
            {
                "reporter_code": int(reporter_code),
                "year": int(year),
                f"{prefix}_active_gini": active_gini(values),
                f"{prefix}_common_zero_gini": gini_with_common_zeros(values, universe_size),
                f"{prefix}_active_products": int(pd.to_numeric(values, errors="coerce").gt(0).sum()),
                f"{prefix}_total_imports": float(pd.to_numeric(values, errors="coerce").sum()),
                f"{prefix}_common_universe_products": universe_size,
            }
        )
    return pd.DataFrame(rows)


def load_product_cells_and_metrics(country_sample: str, panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = sample_processed_path(COUNTRY_PRODUCT, country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing country product import cells: {path}")
    product = pd.read_parquet(path)
    required = {"reporter_code", "year", "product_id", "trade_value"}
    missing = sorted(required - set(product.columns))
    if missing:
        raise RuntimeError(f"Country product cells missing columns: {missing}")
    assert_no_999999(product, "product_id", "country product cells")
    product["reporter_code"] = pd.to_numeric(product["reporter_code"], errors="coerce").astype("Int64")
    product["year"] = pd.to_numeric(product["year"], errors="coerce").astype("Int64")
    product = product.dropna(subset=["reporter_code", "year", "product_id", "trade_value"]).copy()
    product["reporter_code"] = product["reporter_code"].astype(int)
    product["year"] = product["year"].astype(int)
    product["trade_value"] = pd.to_numeric(product["trade_value"], errors="coerce")
    product = product[product["trade_value"].gt(0)].copy()
    panel_keys = panel[["reporter_code", "year"]].drop_duplicates()
    product = product.merge(panel_keys, on=["reporter_code", "year"], how="inner", validate="many_to_one")
    validate_unique(product, ["reporter_code", "year", "product_id"], "balanced country product cells")
    product["hs6"] = parse_hs6_series(product["product_id"])
    if product["hs6"].eq("999999").any():
        raise RuntimeError("Parsed HS6 code 999999 from harmonized product cells.")
    product["lumpy_category"] = product["hs6"].map(lumpy_category_from_hs6)
    product["is_lumpy_main"] = product["lumpy_category"].isin(LUMPY_CATEGORY_ORDER)
    product["is_lumpy_plus_energy"] = product["is_lumpy_main"] | product["lumpy_category"].eq(ENERGY_CATEGORY)

    all_metrics = product_metrics_for_groups(product, product["product_id"], "harmonized")
    no_lumpy = product[~product["is_lumpy_main"]].copy()
    no_lumpy_metrics = product_metrics_for_groups(no_lumpy, no_lumpy["product_id"], "no_lumpy")
    no_lumpy_energy = product[~product["is_lumpy_plus_energy"]].copy()
    no_lumpy_energy_metrics = product_metrics_for_groups(no_lumpy_energy, no_lumpy_energy["product_id"], "no_lumpy_energy")
    metrics = (
        all_metrics.merge(no_lumpy_metrics, on=["reporter_code", "year"], how="left", validate="one_to_one")
        .merge(no_lumpy_energy_metrics, on=["reporter_code", "year"], how="left", validate="one_to_one")
    )
    for col in [
        "harmonized_active_products",
        "no_lumpy_active_products",
        "no_lumpy_energy_active_products",
    ]:
        metrics[f"log_{col}"] = safe_log(metrics[col])
    return product, metrics


def compute_world_relative_after_exclusions(
    product: pd.DataFrame,
    panel: pd.DataFrame,
    exclude_column: str,
    output_col: str,
) -> pd.DataFrame:
    if not WORLD_PRODUCT.exists():
        raise FileNotFoundError(f"Missing world benchmark product imports: {WORLD_PRODUCT}")
    world = pd.read_parquet(WORLD_PRODUCT)
    required = {"year", "product_id", "world_product_imports"}
    missing = sorted(required - set(world.columns))
    if missing:
        raise RuntimeError(f"World product benchmark missing columns: {missing}")
    assert_no_999999(world, "product_id", "world product benchmark")
    world["year"] = pd.to_numeric(world["year"], errors="coerce").astype("Int64")
    world = world.dropna(subset=["year", "product_id", "world_product_imports"]).copy()
    world["year"] = world["year"].astype(int)
    world["world_product_imports"] = pd.to_numeric(world["world_product_imports"], errors="coerce")
    world = world[world["year"].between(START_YEAR, END_YEAR) & world["world_product_imports"].gt(0)].copy()
    world["hs6"] = parse_hs6_series(world["product_id"])
    if world["hs6"].eq("999999").any():
        raise RuntimeError("Parsed HS6 code 999999 from world benchmark product cells.")
    world["lumpy_category"] = world["hs6"].map(lumpy_category_from_hs6)
    world["is_lumpy_main"] = world["lumpy_category"].isin(LUMPY_CATEGORY_ORDER)
    world["is_lumpy_plus_energy"] = world["is_lumpy_main"] | world["lumpy_category"].eq(ENERGY_CATEGORY)
    if exclude_column not in product.columns or exclude_column not in world.columns:
        raise RuntimeError(f"Missing exclusion column `{exclude_column}`.")

    country_filtered = product[~product[exclude_column]].copy()
    world_filtered = world[~world[exclude_column]].copy()
    world_by_year = {int(year): group.reset_index(drop=True) for year, group in world_filtered.groupby("year", sort=True)}
    rows: list[dict[str, Any]] = []
    for (reporter_code, year), group in country_filtered.groupby(["reporter_code", "year"], sort=True):
        world_year = world_by_year.get(int(year))
        if world_year is None or world_year.empty:
            continue
        metrics = compute_country_year_metrics(group[["product_id", "trade_value"]], world_year, FLOW)
        rows.append(
            {
                "reporter_code": int(reporter_code),
                "year": int(year),
                output_col: metrics["world_relative_import_product_gini"],
                f"{output_col}_country_active_products": metrics["country_active_products"],
                f"{output_col}_world_benchmark_products": metrics["world_benchmark_products"],
                f"{output_col}_metric_valid": bool(metrics["metric_valid"]),
                f"{output_col}_invalid_reason": metrics["invalid_reason"],
                f"{output_col}_zero_weight_share": metrics["zero_weight_country_import_share"],
            }
        )
    out = pd.DataFrame(rows)
    validate_unique(out, ["reporter_code", "year"], f"{output_col} world-relative exclusion metrics")
    out = panel[["reporter_code", "year"]].merge(out, on=["reporter_code", "year"], how="left", validate="one_to_one")
    missing_rows = int(out[output_col].isna().sum())
    if missing_rows:
        examples = out[out[output_col].isna()].head(10).to_dict("records")
        raise RuntimeError(f"{output_col} missing for {missing_rows:,} balanced rows: {examples}")
    return out


def load_bin_panel(country_sample: str, panel: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    path = sample_processed_path(IMPORT_BIN_PANEL, country_sample)
    if not path.exists():
        raise FileNotFoundError(f"Missing import-bin concentration panel: {path}")
    bins = pd.read_parquet(path)
    required = {"country", "iso3", "reporter_code", "year", "import_bin", "product_gini", "active_products"}
    missing = sorted(required - set(bins.columns))
    if missing:
        raise RuntimeError(f"Import-bin panel missing columns: {missing}")
    bins["reporter_code"] = pd.to_numeric(bins["reporter_code"], errors="coerce").astype("Int64")
    bins["year"] = pd.to_numeric(bins["year"], errors="coerce").astype("Int64")
    bins = bins.dropna(subset=["reporter_code", "year"]).copy()
    bins["reporter_code"] = bins["reporter_code"].astype(int)
    bins["year"] = bins["year"].astype(int)
    bins = bins[bins["year"].between(START_YEAR, END_YEAR) & bins["import_bin"].isin(MAIN_IMPORT_BINS)].copy()
    validate_unique(bins, ["reporter_code", "year", "import_bin"], "import-bin concentration panel")
    panel_keys = panel[["reporter_code", "year"]].drop_duplicates()
    bins = bins.merge(panel_keys, on=["reporter_code", "year"], how="inner", validate="many_to_one")
    bins = bins.merge(controls, on=["reporter_code", "year"], how="left", validate="many_to_one")
    bins["log_bin_active_import_products"] = safe_log(bins["active_products"])
    return bins


def load_top_driver_measures(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not TOP_DRIVERS.exists():
        raise FileNotFoundError(f"Missing top-driver contribution file: {TOP_DRIVERS}")
    drivers = pd.read_csv(TOP_DRIVERS)
    required = {
        "reporter_code",
        "year",
        "driver_rank",
        "positive_loo_gini_contribution",
        "representative_cmd_code",
        "product_description",
    }
    missing = sorted(required - set(drivers.columns))
    if missing:
        raise RuntimeError(f"Top-driver file missing columns: {missing}")
    panel_keys = panel[["reporter_code", "year"]].drop_duplicates()
    drivers["reporter_code"] = pd.to_numeric(drivers["reporter_code"], errors="coerce").astype("Int64")
    drivers["year"] = pd.to_numeric(drivers["year"], errors="coerce").astype("Int64")
    drivers = drivers.dropna(subset=["reporter_code", "year"]).copy()
    drivers["reporter_code"] = drivers["reporter_code"].astype(int)
    drivers["year"] = drivers["year"].astype(int)
    drivers = drivers.merge(panel_keys, on=["reporter_code", "year"], how="inner", validate="many_to_one")
    drivers["hs6"] = parse_hs6_series(drivers["representative_cmd_code"])
    drivers["lumpy_category"] = drivers["hs6"].map(lumpy_category_from_hs6)
    drivers["is_lumpy_main"] = drivers["lumpy_category"].isin(LUMPY_CATEGORY_ORDER)
    drivers["is_energy"] = drivers["lumpy_category"].eq(ENERGY_CATEGORY)
    drivers["is_lumpy_plus_energy"] = drivers["is_lumpy_main"] | drivers["is_energy"]
    drivers["positive_loo_gini_contribution"] = pd.to_numeric(
        drivers["positive_loo_gini_contribution"], errors="coerce"
    ).fillna(0.0)
    grouped = drivers.groupby(["reporter_code", "year"], sort=True)
    rows: list[dict[str, Any]] = []
    for (reporter_code, year), group in grouped:
        positive_sum = float(group["positive_loo_gini_contribution"].clip(lower=0).sum())
        main_sum = float(group.loc[group["is_lumpy_main"], "positive_loo_gini_contribution"].clip(lower=0).sum())
        energy_sum = float(group.loc[group["is_energy"], "positive_loo_gini_contribution"].clip(lower=0).sum())
        plus_energy_sum = float(group.loc[group["is_lumpy_plus_energy"], "positive_loo_gini_contribution"].clip(lower=0).sum())
        rows.append(
            {
                "reporter_code": int(reporter_code),
                "year": int(year),
                "top_driver_positive_loo_sum": positive_sum,
                "top_driver_lumpy_positive_share": main_sum / positive_sum if positive_sum > 0 else np.nan,
                "top_driver_energy_positive_share": energy_sum / positive_sum if positive_sum > 0 else np.nan,
                "top_driver_lumpy_plus_energy_positive_share": plus_energy_sum / positive_sum if positive_sum > 0 else np.nan,
                "top_driver_count": int(len(group)),
                "top_driver_lumpy_count": int(group["is_lumpy_main"].sum()),
                "top_driver_energy_count": int(group["is_energy"].sum()),
            }
        )
    summary = pd.DataFrame(rows)
    validate_unique(summary, ["reporter_code", "year"], "top-driver mechanism summary")
    summary = panel[["reporter_code", "year"]].merge(summary, on=["reporter_code", "year"], how="left", validate="one_to_one")
    if summary["top_driver_lumpy_positive_share"].isna().any():
        bad = summary[summary["top_driver_lumpy_positive_share"].isna()].head(10).to_dict("records")
        raise RuntimeError(f"Missing top-driver summaries for balanced rows: {bad}")
    return drivers, summary


def model_frame(results: list[cse.ModelResult], exercise_family: str, hypothesis: str) -> pd.DataFrame:
    out = cse.model_results_to_frame(results)
    out.insert(0, "hypothesis", hypothesis)
    out.insert(0, "exercise_family", exercise_family)
    return out


def run_one(
    df: pd.DataFrame,
    outcome: str,
    terms: list[str],
    model_label: str,
    metric: str,
    exercise_family: str,
    hypothesis: str,
    fixed_effects: list[str] | None = None,
    sample_label: str = COUNTRY_SAMPLE,
) -> pd.DataFrame:
    result = cse.run_ols_model(
        df,
        outcome,
        terms,
        fixed_effects or ["year"],
        model_label,
        sample_label,
        FLOW,
        "product",
        metric,
        cluster_col="reporter_code",
    )
    return model_frame([result], exercise_family, hypothesis)


def build_models(panel: pd.DataFrame, bins: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            BASE_TERMS,
            "wr_baseline_year_fe",
            "world_relative_import_product_gini",
            "baseline",
            "Population gradient before adding mechanism controls.",
        )
    )
    frames.append(
        run_one(
            panel,
            "active_product_gini",
            BASE_TERMS,
            "standard_active_hs6_baseline_year_fe",
            "standard_active_import_product_gini",
            "baseline",
            "Standard active-HS6 Product Gini comparison.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*BASE_TERMS, "log_standard_active_import_products"],
            "wr_plus_standard_active_count",
            "world_relative_import_product_gini",
            "active_count",
            "If active variety breadth explains the gradient, the population coefficient should shrink.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*BASE_TERMS, "log_harmonized_active_import_products"],
            "wr_plus_harmonized_active_count",
            "world_relative_import_product_gini",
            "active_count",
            "If harmonized product-family breadth explains the gradient, the population coefficient should shrink.",
        )
    )
    frames.append(
        run_one(
            panel,
            "log_harmonized_active_import_products",
            BASE_TERMS,
            "harmonized_active_count_outcome",
            "log_harmonized_active_import_products",
            "active_count",
            "Large countries should have broader active import baskets if the variety-count mechanism is real.",
        )
    )
    frames.append(
        run_one(
            panel,
            "harmonized_common_zero_gini",
            BASE_TERMS,
            "common_zero_baseline_year_fe",
            "harmonized_common_zero_product_gini",
            "common_zero_universe",
            "If large countries are less concentrated even over a common product universe, the coefficient remains negative.",
        )
    )
    frames.append(
        run_one(
            panel,
            "harmonized_common_zero_gini",
            [*BASE_TERMS, "log_harmonized_active_import_products"],
            "common_zero_plus_harmonized_active_count",
            "harmonized_common_zero_product_gini",
            "common_zero_universe",
            "If common-zero concentration is mostly active-product coverage, active count should absorb population.",
        )
    )
    no_hubs = panel[~panel["iso3"].isin(HUB_MICRO_ISO3)].copy()
    frames.append(
        run_one(
            no_hubs,
            "world_relative_import_product_gini",
            BASE_TERMS,
            "wr_drop_hkg_sgp_lux_isl_guy",
            "world_relative_import_product_gini",
            "drop_hubs_microstates",
            "If hubs and microstates drive the slope, dropping them should flatten the population coefficient.",
            sample_label=f"{COUNTRY_SAMPLE}_drop_hubs_microstates",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*BASE_TERMS, "trade_openness_pct_gdp"],
            "wr_plus_trade_openness",
            "world_relative_import_product_gini",
            "openness_income_controls",
            "If small open trade platforms drive concentration, openness should absorb population.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            PPP_TERMS,
            "wr_ppp_gdppc_baseline_year_fe",
            "world_relative_import_product_gini",
            "openness_income_controls",
            "PPP GDP per capita robustness for the development-stage control.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*PPP_TERMS, "trade_openness_pct_gdp"],
            "wr_ppp_gdppc_plus_trade_openness",
            "world_relative_import_product_gini",
            "openness_income_controls",
            "PPP GDP per capita plus openness robustness.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*PPP_TERMS, "tariff_applied_weighted_mean_pct"],
            "wr_ppp_gdppc_plus_tariff",
            "world_relative_import_product_gini",
            "openness_income_controls",
            "Tariff barrier check; sample is thinner than openness.",
        )
    )
    frames.append(
        run_one(
            panel,
            "wr_no_lumpy_main",
            BASE_TERMS,
            "wr_after_dropping_aircraft_gold_precious_pharma_vehicles_staples",
            "world_relative_import_product_gini_no_lumpy",
            "lumpy_leave_out",
            "If lumpy top categories drive the population slope, removing them should flatten it.",
        )
    )
    frames.append(
        run_one(
            panel,
            "wr_no_lumpy_plus_energy",
            BASE_TERMS,
            "wr_after_dropping_lumpy_plus_energy",
            "world_relative_import_product_gini_no_lumpy_plus_energy",
            "lumpy_leave_out",
            "Energy-inclusive lumpy sensitivity.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*BASE_TERMS, "top_driver_lumpy_positive_share"],
            "wr_plus_top_driver_lumpy_share",
            "world_relative_import_product_gini",
            "lumpy_leave_out",
            "Top-driver control: aircraft/gold/precious/pharma/vehicles/staples share of positive LOO contribution.",
        )
    )
    frames.append(
        run_one(
            panel,
            "world_relative_import_product_gini",
            [*BASE_TERMS, "top_driver_lumpy_plus_energy_positive_share"],
            "wr_plus_top_driver_lumpy_plus_energy_share",
            "world_relative_import_product_gini",
            "lumpy_leave_out",
            "Top-driver control including energy.",
        )
    )
    frames.append(
        run_one(
            panel,
            "top_driver_lumpy_plus_energy_positive_share",
            BASE_TERMS,
            "lumpy_plus_energy_driver_share_outcome",
            "top_driver_lumpy_plus_energy_share",
            "lumpy_leave_out",
            "Small countries should have larger lumpy-driver shares if lumpy products mediate the gradient.",
        )
    )

    for import_bin in MAIN_IMPORT_BINS:
        sub = bins[bins["import_bin"].eq(import_bin)].copy()
        label = f"bin_{import_bin}"
        frames.append(
            run_one(
                sub,
                "product_gini",
                BASE_TERMS,
                f"{label}_baseline_year_fe",
                f"{import_bin}_import_product_gini",
                "import_bin_split",
                "The GVC story predicts the population gradient should be strongest in intermediate/capital bins.",
            )
        )
        frames.append(
            run_one(
                sub,
                "product_gini",
                [*BASE_TERMS, "log_bin_active_import_products"],
                f"{label}_plus_active_count",
                f"{import_bin}_import_product_gini",
                "import_bin_split",
                "If within-bin active product breadth explains bin concentration, active count should absorb population.",
            )
        )
        frames.append(
            run_one(
                sub,
                "log_bin_active_import_products",
                BASE_TERMS,
                f"{label}_active_count_outcome",
                f"{import_bin}_log_active_import_products",
                "import_bin_split",
                "Population should predict more active products inside the bin if breadth is the channel.",
            )
        )
    models = pd.concat(frames, ignore_index=True)
    models["raw_p_lt_005"] = pd.to_numeric(models["p_value"], errors="coerce").lt(0.05)
    models["q_value"] = np.nan
    for family, idx in models.groupby("exercise_family").groups.items():
        models.loc[idx, "q_value"] = cse.benjamini_hochberg(models.loc[idx, "p_value"])
    models["q_lt_005"] = pd.to_numeric(models["q_value"], errors="coerce").lt(0.05)
    return models


def coefficient_rows(models: pd.DataFrame) -> pd.DataFrame:
    key_terms = {
        "log_population",
        "log_gdp_per_capita",
        "log_gdp_pc_ppp_constant_2021_intl_usd",
        "log_standard_active_import_products",
        "log_harmonized_active_import_products",
        "trade_openness_pct_gdp",
        "tariff_applied_weighted_mean_pct",
        "log_bin_active_import_products",
        "top_driver_lumpy_positive_share",
        "top_driver_lumpy_plus_energy_positive_share",
    }
    key = models[models["term"].isin(key_terms)].copy()
    baseline = key[
        key["model_label"].eq("wr_baseline_year_fe")
        & key["term"].eq("log_population")
        & key["status"].eq("ok")
    ]
    baseline_beta = float(baseline["coefficient"].iloc[0]) if len(baseline) else np.nan
    key["baseline_wr_log_population_beta"] = baseline_beta
    comparable_wr_model = (
        key["model_label"].astype(str).str.startswith("wr_")
        | key["model_label"].astype(str).str.startswith("wr.")
    )
    logpop = key["term"].eq("log_population") & comparable_wr_model & np.isfinite(baseline_beta)
    key["absolute_shrink_vs_wr_baseline_pct"] = np.nan
    key.loc[logpop, "absolute_shrink_vs_wr_baseline_pct"] = (
        100
        * (
            1
            - key.loc[logpop, "coefficient"].abs()
            / abs(baseline_beta)
        )
    )
    key["per_population_doubling_effect"] = np.where(
        key["term"].eq("log_population"),
        pd.to_numeric(key["coefficient"], errors="coerce") * math.log(2),
        np.nan,
    )
    return key.sort_values(["exercise_family", "model_label", "term"]).reset_index(drop=True)


def diagnostics(
    panel: pd.DataFrame,
    product: pd.DataFrame,
    bins: pd.DataFrame,
    drivers: pd.DataFrame,
) -> pd.DataFrame:
    lumpy_counts = (
        product.groupby("lumpy_category", dropna=False)
        .agg(rows=("trade_value", "size"), import_value=("trade_value", "sum"), products=("product_id", "nunique"))
        .reset_index()
    )
    lumpy_counts["lumpy_category"] = lumpy_counts["lumpy_category"].replace("", "not_lumpy")
    rows: list[dict[str, Any]] = [
        {
            "diagnostic": "balanced_panel_rows",
            "value": len(panel),
            "detail": f"{panel['reporter_code'].nunique()} countries x {panel['year'].nunique()} years",
        },
        {
            "diagnostic": "balanced_panel_duplicate_reporter_year",
            "value": int(panel.duplicated(["reporter_code", "year"]).sum()),
            "detail": "",
        },
        {
            "diagnostic": "country_product_rows_balanced_sample",
            "value": len(product),
            "detail": f"{product['product_id'].nunique()} harmonized product ids",
        },
        {
            "diagnostic": "country_product_duplicate_reporter_year_product",
            "value": int(product.duplicated(["reporter_code", "year", "product_id"]).sum()),
            "detail": "",
        },
        {
            "diagnostic": "country_product_999999_rows",
            "value": int(product["product_id"].astype("string").str.contains("999999", regex=False, na=False).sum()),
            "detail": "Must be zero under repo product-level rule.",
        },
        {
            "diagnostic": "hubs_microstates_rows_present",
            "value": int(panel["iso3"].isin(HUB_MICRO_ISO3).sum()),
            "detail": "Country-year rows among GUY,HKG,ISL,LUX,SGP.",
        },
        {
            "diagnostic": "hubs_microstates_countries_present",
            "value": int(panel.loc[panel["iso3"].isin(HUB_MICRO_ISO3), "iso3"].nunique()),
            "detail": ",".join(sorted(set(panel.loc[panel["iso3"].isin(HUB_MICRO_ISO3), "iso3"]))),
        },
        {
            "diagnostic": "import_bin_rows_balanced_sample",
            "value": len(bins),
            "detail": ",".join(sorted(bins["import_bin"].unique())),
        },
        {
            "diagnostic": "top_driver_rows_balanced_sample",
            "value": len(drivers),
            "detail": f"{drivers['reporter_code'].nunique()} countries",
        },
    ]
    for row in lumpy_counts.to_dict("records"):
        rows.append(
            {
                "diagnostic": f"product_lumpy_category_{row['lumpy_category']}",
                "value": int(row["rows"]),
                "detail": f"products={int(row['products'])}; import_value={float(row['import_value']):.4g}",
            }
        )
    return pd.DataFrame(rows)


def lumpy_product_summary(product: pd.DataFrame) -> pd.DataFrame:
    summary = (
        product.groupby(["lumpy_category", "hs6", "product_id"], dropna=False)
        .agg(
            product_cell_rows=("trade_value", "size"),
            country_years=("year", "nunique"),
            reporters=("reporter_code", "nunique"),
            import_value=("trade_value", "sum"),
        )
        .reset_index()
    )
    summary["lumpy_category"] = summary["lumpy_category"].replace("", "not_lumpy")
    summary = summary.sort_values(["lumpy_category", "import_value"], ascending=[True, False]).reset_index(drop=True)
    summary["rank_within_category"] = summary.groupby("lumpy_category")["import_value"].rank(
        method="first", ascending=False
    ).astype(int)
    return summary


def format_num(value: object, digits: int = 4) -> str:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(x):
        return ""
    if abs(x) >= 100:
        return f"{x:,.1f}"
    if abs(x) >= 1:
        return f"{x:,.3f}"
    if abs(x) >= 0.001:
        return f"{x:.4f}"
    return f"{x:.2e}"


def maybe_bold(value: str, significant: bool) -> str:
    return f"**{value}**" if significant and value else value


def markdown_table(rows: pd.DataFrame, columns: list[str]) -> str:
    if rows.empty:
        return "_No rows._"
    out = rows[columns].copy()
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(str(row[col]) for col in columns) + " |" for _, row in out.iterrows()]
    return "\n".join([header, sep, *body])


def summarize_population_models(key: pd.DataFrame) -> pd.DataFrame:
    wanted = [
        "wr_baseline_year_fe",
        "wr_plus_standard_active_count",
        "wr_plus_harmonized_active_count",
        "common_zero_baseline_year_fe",
        "common_zero_plus_harmonized_active_count",
        "wr_drop_hkg_sgp_lux_isl_guy",
        "wr_plus_trade_openness",
        "wr_ppp_gdppc_baseline_year_fe",
        "wr_ppp_gdppc_plus_trade_openness",
        "wr_ppp_gdppc_plus_tariff",
        "wr_after_dropping_aircraft_gold_precious_pharma_vehicles_staples",
        "wr_after_dropping_lumpy_plus_energy",
        "wr_plus_top_driver_lumpy_share",
        "wr_plus_top_driver_lumpy_plus_energy_share",
    ]
    rows = key[key["term"].eq("log_population") & key["model_label"].isin(wanted)].copy()
    rows["order"] = rows["model_label"].map({label: idx for idx, label in enumerate(wanted)})
    rows = rows.sort_values("order")
    rows["model"] = rows["model_label"]
    rows["beta"] = rows.apply(
        lambda r: maybe_bold(format_num(r["coefficient"]), bool(r["raw_p_lt_005"])),
        axis=1,
    )
    rows["p"] = rows.apply(lambda r: maybe_bold(format_num(r["p_value"]), bool(r["raw_p_lt_005"])), axis=1)
    rows["n"] = rows["nobs"].map(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    rows["clusters"] = rows["clusters"].map(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    rows["doubling_effect"] = rows["per_population_doubling_effect"].map(format_num)
    rows["shrink_vs_baseline"] = rows["absolute_shrink_vs_wr_baseline_pct"].map(
        lambda x: "" if not np.isfinite(float(x)) else f"{float(x):.1f}%"
    )
    return rows[["model", "beta", "p", "n", "clusters", "doubling_effect", "shrink_vs_baseline"]]


def summarize_bin_models(key: pd.DataFrame) -> pd.DataFrame:
    rows = key[
        key["term"].eq("log_population")
        & key["model_label"].str.match(r"bin_.*_baseline_year_fe")
    ].copy()
    rows["bin"] = rows["model_label"].str.replace("bin_", "", regex=False).str.replace("_baseline_year_fe", "", regex=False)
    rows["beta"] = rows.apply(
        lambda r: maybe_bold(format_num(r["coefficient"]), bool(r["raw_p_lt_005"])),
        axis=1,
    )
    rows["p"] = rows.apply(lambda r: maybe_bold(format_num(r["p_value"]), bool(r["raw_p_lt_005"])), axis=1)
    rows["n"] = rows["nobs"].map(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    rows["doubling_effect"] = rows["per_population_doubling_effect"].map(format_num)
    return rows[["bin", "beta", "p", "n", "doubling_effect"]].sort_values("bin")


def write_memo(
    path: Path,
    key: pd.DataFrame,
    diag: pd.DataFrame,
    output_paths: dict[str, Path],
) -> None:
    summary = summarize_population_models(key)
    bin_summary = summarize_bin_models(key)
    baseline = key[(key["model_label"].eq("wr_baseline_year_fe")) & key["term"].eq("log_population")]
    plus_count = key[(key["model_label"].eq("wr_plus_harmonized_active_count")) & key["term"].eq("log_population")]
    common_zero = key[(key["model_label"].eq("common_zero_baseline_year_fe")) & key["term"].eq("log_population")]
    no_hubs = key[(key["model_label"].eq("wr_drop_hkg_sgp_lux_isl_guy")) & key["term"].eq("log_population")]
    no_lumpy = key[
        (key["model_label"].eq("wr_after_dropping_aircraft_gold_precious_pharma_vehicles_staples"))
        & key["term"].eq("log_population")
    ]

    def beta_p(row: pd.DataFrame) -> str:
        if row.empty:
            return "not estimated"
        r = row.iloc[0]
        return f"{format_num(r['coefficient'])}, p={format_num(r['p_value'])}, n={int(r['nobs']):,}"

    lines = [
        "# Import Size Mechanism Tests",
        "",
        f"Generated: {now_utc()}",
        "",
        "## Purpose",
        "",
        "These tests ask why larger countries have lower World-Relative Import Product Gini. "
        "They are descriptive country-year regressions on the balanced `rd2_countries` 2000-2024 import panel, "
        "with year fixed effects and country-clustered standard errors. Product-level inputs exclude HS6 `999999` upstream.",
        "",
        "Main estimating equation:",
        "",
        "`concentration_ct = beta log_population_ct + gamma log_gdp_per_capita_ct + year_FE_t + error_ct`",
        "",
        "Mechanism checks add active-product count, openness/tariffs, or top-driver controls; some checks change the outcome "
        "to a common-zero-universe Gini, import-bin Gini, or lumpy-product-excluded world-relative Gini.",
        "",
        "## Bottom Line",
        "",
        f"- Baseline World-Relative Import Product Gini population coefficient: {beta_p(baseline)}.",
        f"- Adding harmonized active import product count: {beta_p(plus_count)}.",
        f"- Common product universe with zeros: {beta_p(common_zero)}.",
        f"- Dropping Hong Kong, Singapore, Luxembourg, Iceland, and Guyana: {beta_p(no_hubs)}.",
        f"- Dropping aircraft/gold/precious metals/pharma/vehicles/staples from both country and world product baskets: {beta_p(no_lumpy)}.",
        "",
        "Interpretation rule: if the absolute `log_population` coefficient collapses after a mechanism control or exclusion, "
        "that mechanism is a plausible accounting channel for the population gradient. If it stays similar, that mechanism "
        "is not doing most of the explanatory work.",
        "",
        "## Key Population Coefficients",
        "",
        markdown_table(
            summary,
            ["model", "beta", "p", "n", "clusters", "doubling_effect", "shrink_vs_baseline"],
        ),
        "",
        "Bold beta/p-value entries have raw p < 0.05. `doubling_effect` is the implied change in the Gini outcome from doubling population. "
        "`shrink_vs_baseline` is shown only for world-relative Gini variants, because active, common-zero, and bin-specific Ginis are on different outcome scales.",
        "",
        "## Import-Bin Split",
        "",
        markdown_table(bin_summary, ["bin", "beta", "p", "n", "doubling_effect"]),
        "",
        "The bin split uses the Exercise 3 BEC-style import bins and the same balanced country-year sample. "
        "It is not world-relative; it is within-bin active Product Gini.",
        "",
        "## Validation Diagnostics",
        "",
        markdown_table(diag.head(40).assign(value=lambda d: d["value"].astype(str)), ["diagnostic", "value", "detail"]),
        "",
        "## Output Files",
        "",
    ]
    for label, out_path in output_paths.items():
        lines.append(f"- {label}: `{rel(out_path)}`")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- These are descriptive accounting regressions, not causal estimates of population.",
            "- Active-count controls are post-treatment style mechanism controls: useful for decomposition, not causal adjustment.",
            "- The lumpy top-driver control uses the saved top-driver contribution file, so it summarizes the largest drivers rather than every product's leave-one-out contribution.",
            "- Tariff regressions use a smaller sample because WDI/WITS tariff coverage is incomplete.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_population_ladder(key: pd.DataFrame, path: Path) -> None:
    rows = key[key["term"].eq("log_population")].copy()
    keep = [
        "wr_baseline_year_fe",
        "wr_plus_harmonized_active_count",
        "common_zero_baseline_year_fe",
        "common_zero_plus_harmonized_active_count",
        "wr_drop_hkg_sgp_lux_isl_guy",
        "wr_plus_trade_openness",
        "wr_after_dropping_aircraft_gold_pharma_vehicles_staples",
        "wr_after_dropping_lumpy_plus_energy",
    ]
    rows = rows[rows["model_label"].isin(keep)].copy()
    rows["order"] = rows["model_label"].map({label: idx for idx, label in enumerate(keep)})
    rows = rows.sort_values("order")
    if rows.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    y = np.arange(len(rows))
    x = pd.to_numeric(rows["coefficient"], errors="coerce")
    lo = pd.to_numeric(rows["ci_low"], errors="coerce")
    hi = pd.to_numeric(rows["ci_high"], errors="coerce")
    ax.errorbar(x, y, xerr=[x - lo, hi - x], fmt="o", color="#1f4e79", ecolor="#9ab0c8", capsize=3)
    ax.axvline(0, color="#444444", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(rows["model_label"])
    ax.invert_yaxis()
    ax.set_xlabel("Coefficient on log population")
    ax.set_title("Population Gradient Across Import Concentration Mechanism Tests")
    ax.grid(axis="x", color="#dddddd", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run(args: argparse.Namespace) -> None:
    if args.country_sample != COUNTRY_SAMPLE:
        raise RuntimeError("Website-facing and rd2 mechanism outputs must use --country-sample rd2_countries.")
    out_dir = sample_results_dir(args.country_sample) / OUT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    panel = load_world_relative_panel(args.country_sample)
    controls = load_controls(args.country_sample, panel)
    product, product_metrics = load_product_cells_and_metrics(args.country_sample, panel)
    wr_no_lumpy = compute_world_relative_after_exclusions(product, panel, "is_lumpy_main", "wr_no_lumpy_main")
    wr_no_lumpy_energy = compute_world_relative_after_exclusions(
        product, panel, "is_lumpy_plus_energy", "wr_no_lumpy_plus_energy"
    )
    drivers, driver_summary = load_top_driver_measures(panel)
    panel = (
        panel.merge(controls, on=["reporter_code", "year"], how="left", validate="one_to_one")
        .merge(product_metrics, on=["reporter_code", "year"], how="left", validate="one_to_one")
        .merge(wr_no_lumpy[["reporter_code", "year", "wr_no_lumpy_main"]], on=["reporter_code", "year"], how="left", validate="one_to_one")
        .merge(
            wr_no_lumpy_energy[["reporter_code", "year", "wr_no_lumpy_plus_energy"]],
            on=["reporter_code", "year"],
            how="left",
            validate="one_to_one",
        )
        .merge(driver_summary, on=["reporter_code", "year"], how="left", validate="one_to_one")
    )
    validate_unique(panel, ["reporter_code", "year"], "mechanism regression panel")
    missing = int(panel[["world_relative_import_product_gini", "log_population", "log_gdp_per_capita"]].isna().any(axis=1).sum())
    if missing:
        raise RuntimeError(f"Mechanism panel has {missing:,} rows missing core regression variables.")

    bins = load_bin_panel(args.country_sample, panel, controls)
    models = build_models(panel, bins)
    key = coefficient_rows(models)
    diag = diagnostics(panel, product, bins, drivers)

    panel_path = out_dir / "import_size_mechanism_panel.csv"
    models_path = out_dir / "import_size_mechanism_models.csv"
    key_path = out_dir / "import_size_mechanism_key_coefficients.csv"
    diag_path = out_dir / "import_size_mechanism_diagnostics.csv"
    product_lumpy_path = out_dir / "import_size_lumpy_product_summary.csv"
    driver_path = out_dir / "import_size_top_driver_measures.csv"
    plot_path = out_dir / "import_size_population_coefficient_ladder.png"
    memo_path = out_dir / "import_size_mechanism_tests.md"
    manifest_path = out_dir / "run_manifest_import_size_mechanism_tests.json"

    panel.to_csv(panel_path, index=False)
    models.to_csv(models_path, index=False)
    key.to_csv(key_path, index=False)
    diag.to_csv(diag_path, index=False)
    lumpy_product_summary(product).to_csv(product_lumpy_path, index=False)
    driver_summary.to_csv(driver_path, index=False)
    plot_population_ladder(key, plot_path)
    write_memo(
        memo_path,
        key,
        diag,
        {
            "mechanism panel": panel_path,
            "all models": models_path,
            "key coefficients": key_path,
            "diagnostics": diag_path,
            "lumpy product summary": product_lumpy_path,
            "top-driver measures": driver_path,
            "coefficient ladder plot": plot_path,
        },
    )
    manifest = {
        "generated_at": now_utc(),
        "country_sample": args.country_sample,
        "flow": FLOW,
        "years": [START_YEAR, END_YEAR],
        "balanced_countries": int(panel["reporter_code"].nunique()),
        "rows": int(len(panel)),
        "product_level_999999_rule": "Excluded upstream and hard-checked in this script.",
        "hubs_microstates_dropped": sorted(HUB_MICRO_ISO3),
        "lumpy_categories": LUMPY_CATEGORY_ORDER,
        "energy_category": ENERGY_CATEGORY,
        "outputs": {label: rel(path) for label, path in {
            "mechanism panel": panel_path,
            "all models": models_path,
            "key coefficients": key_path,
            "diagnostics": diag_path,
            "memo": memo_path,
            "coefficient ladder plot": plot_path,
        }.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {rel(memo_path)}")
    print(f"Wrote {rel(key_path)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=[COUNTRY_SAMPLE])
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
