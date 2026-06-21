#!/usr/bin/env python3
"""Cadot-style export reconcentration mechanism tribunal for rd2 countries.

The runner assembles existing rd2 concentration, world-relative, commodity,
HS2 benchmark, and Exercise 12 HS4 transition artifacts into one forensic
workspace. It is descriptive: the development hump is not treated as a causal
effect of income.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from scipy.stats import t as student_t
except ImportError:  # pragma: no cover - scipy is available in the project env
    student_t = None

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
import run_ppp_hump_regressions as ppp  # noqa: E402
from concentration_metrics import active_gini, active_top_share  # noqa: E402
from run_exercise_12_ev_hs4_expansion import ACTIVE_THRESHOLD_USD_2024, load_us_gdp_deflator  # noqa: E402
from trade_concentration_pipeline import sample_processed_dir, sample_results_dir  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
FLOW = "Exports"
EXCLUDED_HS6_CODES = {"999999"}
SECTION_16_HS2 = {"84", "85"}
INCOME_VALUE_COL = ppp.PPP_VALUE_COL
INCOME_LOG_COL = ppp.PPP_LOG_COL
INCOME_ALIAS_COL = "log_income_pc"
INCOME_ALIAS_SQ_COL = "log_income_pc_sq"
INCOME_LABEL = "GDP per capita, PPP (constant 2021 international $)"
FIXED_RICH_SIDE_PPP_CONSTANT_2021_INTL_USD = 25_000.0
PRODY_MIN_EXPORTERS = 3
MAIN_HORIZON = 5


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    if pd.isna(value):
        return None
    return value


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = sorted(set(keys) - set(df.columns))
    if missing:
        raise RuntimeError(f"{label} is missing keys: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df.loc[df.duplicated(keys, keep=False), keys].head(10).to_dict(orient="records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def read_csv_required(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return pd.read_csv(path)


def read_parquet_required(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return pd.read_parquet(path)


def normalize_hs6(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).fillna("").str.zfill(6)


def resolve_log_income_col(frame: pd.DataFrame) -> str:
    for col in [
        INCOME_ALIAS_COL,
        INCOME_LOG_COL,
        "log_gni_per_capita_constant_2015_usd",
        "log_gni_per_capita_current_usd",
    ]:
        if col in frame.columns:
            return col
    raise RuntimeError("No log income column found in controls.")


def load_controls(country_sample: str, start_year: int = 2000, end_year: int = 2024) -> pd.DataFrame:
    path = sample_processed_dir(country_sample) / "future_growth_concentration_panel.parquet"
    panel = read_parquet_required(path, "future-growth controls panel")
    panel = panel[panel["flow"].eq(FLOW) & panel["variant"].eq("baseline")].copy()
    keep = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "population",
        "gni_per_capita_current_usd",
        "gni_per_capita_constant_2015_usd",
        "log_gni_per_capita_current_usd",
        "log_gni_per_capita_constant_2015_usd",
        "log_population",
        "oil_export_share",
        "region",
        "income_group",
    ]
    controls = panel[[col for col in keep if col in panel.columns]].drop_duplicates(["reporter_code", "year"])
    controls["iso3"] = controls["iso3"].astype(str).str.upper()
    controls["reporter_code"] = pd.to_numeric(controls["reporter_code"], errors="coerce").astype("Int64")
    controls["year"] = pd.to_numeric(controls["year"], errors="coerce").astype("Int64")
    controls = controls.dropna(subset=["reporter_code", "year"]).copy()
    controls["reporter_code"] = controls["reporter_code"].astype(int)
    controls["year"] = controls["year"].astype(int)
    ppp_controls = ppp.load_or_fetch_ppp_controls(country_sample, start_year, end_year, refresh=False)
    controls = controls.merge(ppp_controls, on=["iso3", "year"], how="left", validate="many_to_one")
    controls[INCOME_VALUE_COL] = pd.to_numeric(controls[INCOME_VALUE_COL], errors="coerce")
    controls[INCOME_LOG_COL] = np.where(controls[INCOME_VALUE_COL] > 0, np.log(controls[INCOME_VALUE_COL]), np.nan)
    controls[INCOME_ALIAS_COL] = controls[INCOME_LOG_COL]
    controls[INCOME_ALIAS_SQ_COL] = controls[INCOME_ALIAS_COL] ** 2
    validate_unique(controls, ["reporter_code", "year"], "country-year controls")
    return controls


def load_standard_concentration(country_sample: str) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / "exercise_01_tables" / "concentration_all_years.csv"
    panel = read_csv_required(path, "Exercise 1 concentration panel")
    panel = panel[panel["flow"].eq(FLOW) & panel["variant"].eq("baseline")].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    validate_unique(panel, ["reporter_code", "year"], "standard concentration panel")
    return panel


def load_world_relative(country_sample: str) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / "world_relative_product_gini_tables" / "world_relative_product_gini_all_years.csv"
    panel = read_csv_required(path, "world-relative Product Gini panel")
    panel = panel[panel["flow"].eq(FLOW) & panel["metric_valid"].astype(bool)].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    validate_unique(panel, ["reporter_code", "year"], "world-relative panel")
    keep = [
        "reporter_code",
        "year",
        "world_relative_product_gini",
        "world_weighted_share_gini",
        "country_active_products",
        "zero_weight_country_export_share",
        "sample_window",
    ]
    return panel[[col for col in keep if col in panel.columns]].copy()


def load_main_country_year_panel(
    country_sample: str,
    start_year: int,
    end_year: int,
    controls: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    concentration = load_standard_concentration(country_sample)
    if controls is None:
        controls = load_controls(country_sample, start_year, end_year)
    world = load_world_relative(country_sample)
    keep = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "total_trade_value",
        "product_gini",
        "product_top_1pct_share",
        "product_top_5pct_share",
        "product_active_count",
        "product_partner_cell_gini",
        "product_partner_cell_top_1pct_share",
        "product_partner_cell_top_5pct_share",
        "product_partner_cell_active_count",
    ]
    panel = concentration[[col for col in keep if col in concentration.columns]].merge(
        world, on=["reporter_code", "year"], how="inner", validate="one_to_one"
    )
    panel = panel.merge(
        controls.drop(columns=[col for col in ["country", "iso3"] if col in controls.columns]),
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    panel["log_active_product_count"] = np.log(pd.to_numeric(panel["product_active_count"], errors="coerce"))
    panel[INCOME_ALIAS_COL] = pd.to_numeric(panel[INCOME_ALIAS_COL], errors="coerce")
    panel[INCOME_ALIAS_SQ_COL] = panel[INCOME_ALIAS_COL] ** 2
    panel["standard_minus_world_relative_gini"] = panel["product_gini"] - panel["world_relative_product_gini"]
    required = ["world_relative_product_gini", "product_gini", INCOME_ALIAS_COL, "log_population", "oil_export_share"]
    analytic = panel[panel["year"].between(start_year, end_year)].dropna(subset=required).copy()
    required_years = set(range(start_year, end_year + 1))
    country_years = analytic.groupby("reporter_code")["year"].apply(lambda x: set(x.astype(int)))
    balanced_reporters = sorted(int(code) for code, years in country_years.items() if required_years.issubset(years))
    balanced = analytic[analytic["reporter_code"].isin(balanced_reporters)].copy()
    expected_rows = len(balanced_reporters) * len(required_years)
    if len(balanced) != expected_rows:
        raise RuntimeError(f"Balanced panel construction failed: expected {expected_rows}, found {len(balanced)}")
    validate_unique(balanced, ["reporter_code", "year"], "main balanced country-year panel")
    return balanced.sort_values(["country", "year"]).reset_index(drop=True), panel


def load_product_exports(country_sample: str) -> pd.DataFrame:
    path = sample_processed_dir(country_sample) / "world_relative_product_gini_rd2_product_exports.parquet"
    products = read_parquet_required(path, "native HS6 reporter-year product exports")
    products = products.copy()
    products["reporter_code"] = pd.to_numeric(products["reporter_code"], errors="coerce").astype("Int64")
    products["year"] = pd.to_numeric(products["year"], errors="coerce").astype("Int64")
    products["cmd_code"] = normalize_hs6(products["cmd_code"])
    products["trade_value"] = pd.to_numeric(products["trade_value"], errors="coerce")
    products = products.dropna(subset=["reporter_code", "year", "cmd_code", "trade_value"]).copy()
    products["reporter_code"] = products["reporter_code"].astype(int)
    products["year"] = products["year"].astype(int)
    before = len(products)
    products = products[~products["cmd_code"].isin(EXCLUDED_HS6_CODES) & products["trade_value"].gt(0)].copy()
    products.attrs["excluded_999999_rows"] = int(before - len(products))
    products["hs2"] = products["cmd_code"].str[:2]
    products["hs4_id"] = "HS4:" + products["cmd_code"].str[:4]
    products["section16"] = products["hs2"].isin(SECTION_16_HS2)
    return products


def gini_variant_panel(product_exports: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []

    def summarize(values: pd.DataFrame, product_col: str, variant: str) -> pd.DataFrame:
        grouped = values.groupby(["reporter_code", "year", product_col], as_index=False)["trade_value"].sum()
        out = (
            grouped.groupby(["reporter_code", "year"])["trade_value"]
            .agg(
                product_gini=lambda x: active_gini(x),
                product_active_count=lambda x: int((pd.to_numeric(x, errors="coerce") > 0).sum()),
                product_top_1pct_share=lambda x: active_top_share(x, pct=0.01),
                total_trade_value="sum",
            )
            .reset_index()
        )
        out["mechanical_variant"] = variant
        return out

    rows.append(summarize(product_exports, "cmd_code", "native_hs6"))
    rows.append(summarize(product_exports[~product_exports["section16"]].copy(), "cmd_code", "native_hs6_excluding_section16"))
    rows.append(summarize(product_exports, "hs4_id", "native_hs4"))
    rows.append(summarize(product_exports, "hs2", "native_hs2"))

    section_counts = (
        product_exports[product_exports["section16"]]
        .groupby(["reporter_code", "year"], as_index=False)
        .agg(section16_value=("trade_value", "sum"), section16_lines=("cmd_code", "nunique"))
    )
    totals = (
        product_exports.groupby(["reporter_code", "year"], as_index=False)
        .agg(total_hs6_value=("trade_value", "sum"), total_hs6_lines=("cmd_code", "nunique"))
    )
    section = totals.merge(section_counts, on=["reporter_code", "year"], how="left")
    section["section16_value"] = section["section16_value"].fillna(0.0)
    section["section16_lines"] = section["section16_lines"].fillna(0).astype(int)
    section["section16_export_share"] = section["section16_value"] / section["total_hs6_value"]
    section["section16_line_share"] = section["section16_lines"] / section["total_hs6_lines"]

    panel = pd.concat(rows, ignore_index=True)
    panel = panel.merge(section, on=["reporter_code", "year"], how="left", validate="many_to_one")
    panel = panel.merge(
        controls[
            [
                "reporter_code",
                "year",
                INCOME_VALUE_COL,
                INCOME_LOG_COL,
                INCOME_ALIAS_COL,
                INCOME_ALIAS_SQ_COL,
                "log_population",
                "oil_export_share",
            ]
        ],
        on=["reporter_code", "year"],
        how="left",
        validate="many_to_one",
    )
    panel[INCOME_ALIAS_COL] = pd.to_numeric(panel[INCOME_ALIAS_COL], errors="coerce")
    panel[INCOME_ALIAS_SQ_COL] = panel[INCOME_ALIAS_COL] ** 2
    panel["log_active_product_count"] = np.log(pd.to_numeric(panel["product_active_count"], errors="coerce"))
    return panel


def load_commodity_panel(country_sample: str) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / "exercise_06_tables" / "concentration_exclusions_all_years.csv"
    panel = read_csv_required(path, "Exercise 6 concentration exclusions")
    panel = panel[panel["flow"].eq(FLOW) & panel["variant"].isin(["baseline", "full_exclusion"])].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    wide = panel.pivot_table(
        index=["reporter_code", "year"],
        columns="variant",
        values=["product_gini", "product_top_1pct_share", "product_active_count", "total_trade_value", "trade_share_removed"],
        aggfunc="first",
    )
    wide.columns = [f"{metric}_{variant}" for metric, variant in wide.columns]
    wide = wide.reset_index()
    wide["commodity_gini_delta"] = wide["product_gini_baseline"] - wide["product_gini_full_exclusion"]
    wide["commodity_top1_delta"] = wide["product_top_1pct_share_baseline"] - wide["product_top_1pct_share_full_exclusion"]
    wide["commodity_trade_share_removed"] = wide["trade_share_removed_full_exclusion"]
    validate_unique(wide, ["reporter_code", "year"], "commodity exclusion panel")
    return wide


def load_hs2_benchmark(country_sample: str) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / "exercise_10_tables" / "random_benchmark_hs2_product_all_years.csv"
    panel = read_csv_required(path, "Exercise 10 HS2-preserving benchmark")
    panel = panel[
        panel["flow"].eq(FLOW)
        & panel["exclusion_variant"].eq("none")
        & panel["dimension"].eq("product_hs2_preserved")
    ].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    keep = [
        "reporter_code",
        "year",
        "actual_gini",
        "sim_gini_median",
        "actual_minus_sim_median_gini",
        "actual_gini_percentile",
        "active_items",
        "active_hs2_count",
    ]
    out = panel[[col for col in keep if col in panel.columns]].copy()
    validate_unique(out, ["reporter_code", "year"], "HS2-preserving benchmark")
    return out


def run_hump_models(panel: pd.DataFrame, sample_label: str) -> pd.DataFrame:
    outcomes = [
        ("product_gini", "standard_product_gini"),
        ("world_relative_product_gini", "world_relative_product_gini"),
        ("log_active_product_count", "log_active_product_count"),
        ("product_top_1pct_share", "top_product_1pct_share"),
        ("product_partner_cell_top_1pct_share", "top_product_partner_cell_1pct_share"),
    ]
    rows: list[cse.ModelResult] = []
    for outcome, metric in outcomes:
        if outcome not in panel.columns:
            continue
        for label, terms, two_way in [
            ("quadratic_year_fe_country_cluster", [INCOME_ALIAS_COL, INCOME_ALIAS_SQ_COL], None),
            (
                "quadratic_controls_year_fe_country_cluster",
                [INCOME_ALIAS_COL, INCOME_ALIAS_SQ_COL, "log_population", "oil_export_share"],
                None,
            ),
            (
                "quadratic_controls_year_fe_two_way_cluster",
                [INCOME_ALIAS_COL, INCOME_ALIAS_SQ_COL, "log_population", "oil_export_share"],
                "year",
            ),
        ]:
            rows.append(
                cse.run_ols_model(
                    panel,
                    outcome,
                    terms,
                    ["year"],
                    label,
                    sample_label,
                    FLOW,
                    "product",
                    metric,
                    cluster_col="reporter_code",
                    two_way_cluster_col=two_way,
                )
            )
    models = cse.model_results_to_frame(rows)
    models = add_turning_points(models)
    return models


def add_turning_points(models: pd.DataFrame) -> pd.DataFrame:
    if models.empty:
        return models
    out = models.copy()
    out["turning_point_log_income_pc"] = np.nan
    out["turning_point_ppp_constant_2021_intl_usd"] = np.nan
    for keys, group in out.groupby(["model_label", "sample", "flow", "dimension", "metric", "outcome"], dropna=False):
        beta1 = group.loc[group["term"].eq(INCOME_ALIAS_COL), "coefficient"]
        beta2 = group.loc[group["term"].eq(INCOME_ALIAS_SQ_COL), "coefficient"]
        if beta1.empty or beta2.empty:
            continue
        b1 = float(beta1.iloc[0])
        b2 = float(beta2.iloc[0])
        if math.isfinite(b1) and math.isfinite(b2) and abs(b2) > 1e-12:
            tp = -b1 / (2 * b2)
            mask = np.ones(len(out), dtype=bool)
            for col, value in zip(["model_label", "sample", "flow", "dimension", "metric", "outcome"], keys):
                mask &= out[col].eq(value).to_numpy()
            out.loc[mask, "turning_point_log_income_pc"] = tp
            out.loc[mask, "turning_point_ppp_constant_2021_intl_usd"] = math.exp(tp) if -50 < tp < 50 else np.nan
    return out


def preferred_turning_point(models: pd.DataFrame, panel: pd.DataFrame) -> dict[str, Any]:
    preferred = models[
        models["model_label"].eq("quadratic_controls_year_fe_country_cluster")
        & models["metric"].eq("world_relative_product_gini")
    ].copy()
    tp = np.nan
    if not preferred.empty:
        values = preferred["turning_point_log_income_pc"].dropna()
        if not values.empty:
            tp = float(values.iloc[0])
    log_income = pd.to_numeric(panel[INCOME_ALIAS_COL], errors="coerce")
    p05 = float(log_income.quantile(0.05))
    p95 = float(log_income.quantile(0.95))
    valid = bool(math.isfinite(tp) and p05 <= tp <= p95)
    fixed = math.log(FIXED_RICH_SIDE_PPP_CONSTANT_2021_INTL_USD)
    return {
        "turning_point_log_income_pc": tp if math.isfinite(tp) else None,
        "turning_point_ppp_constant_2021_intl_usd": math.exp(tp) if math.isfinite(tp) and -50 < tp < 50 else None,
        "turning_point_inside_5_95pct_sample_support": valid,
        "sample_log_income_pc_p05": p05,
        "sample_log_income_pc_p95": p95,
        "fixed_threshold_log_income_pc": fixed,
        "fixed_threshold_ppp_constant_2021_intl_usd": FIXED_RICH_SIDE_PPP_CONSTANT_2021_INTL_USD,
        "rich_side_source": "estimated_turning_point" if valid else "fixed_25000_constant_ppp_threshold",
        "rich_side_log_threshold_used": tp if valid else fixed,
        "income_indicator": ppp.PPP_INDICATOR,
        "income_label": INCOME_LABEL,
    }


def balanced_sample_diagnostics(panel: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    required_years = set(range(start_year, end_year + 1))
    specs = [
        ("world_relative_only", []),
        ("constant_ppp_population_oil", [INCOME_ALIAS_COL, "log_population", "oil_export_share"]),
        ("legacy_current_gni_population_oil", ["log_gni_per_capita_current_usd", "log_population", "oil_export_share"]),
        ("legacy_constant_2015_gni_population_oil", ["log_gni_per_capita_constant_2015_usd", "log_population", "oil_export_share"]),
        ("main_constant_ppp_outcomes", [INCOME_ALIAS_COL, "log_population", "oil_export_share", "world_relative_product_gini"]),
    ]
    rows: list[dict[str, Any]] = []
    window = panel[panel["year"].between(start_year, end_year)].copy()
    for label, required in specs:
        available_required = [col for col in required if col in window.columns]
        missing_required_columns = sorted(set(required) - set(available_required))
        work = window.dropna(subset=available_required).copy() if available_required else window.copy()
        country_years = work.groupby("reporter_code")["year"].apply(lambda x: set(x.astype(int)))
        balanced_codes = sorted(int(code) for code, years in country_years.items() if required_years.issubset(years))
        rows.append(
            {
                "diagnostic": label,
                "required_columns": ",".join(required) or "none",
                "missing_required_columns": ",".join(missing_required_columns),
                "balanced_countries": len(balanced_codes),
                "balanced_rows": len(balanced_codes) * len(required_years),
                "candidate_rows_after_required_drop": int(len(work)),
                "reporter_codes": ",".join(str(code) for code in balanced_codes),
            }
        )
    return pd.DataFrame(rows)


def run_mechanical_variant_models(
    main_panel: pd.DataFrame,
    variants: pd.DataFrame,
    commodity: pd.DataFrame,
    hs2_benchmark: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base_keys = main_panel[["reporter_code", "year", "country", "iso3"]].copy()
    common = base_keys.merge(
        variants[variants["mechanical_variant"].eq("native_hs6_excluding_section16")][
            ["reporter_code", "year", "product_gini", "product_active_count"]
        ].rename(
            columns={
                "product_gini": "product_gini_no_section16",
                "product_active_count": "product_active_count_no_section16",
            }
        ),
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    for variant, prefix in [("native_hs4", "hs4"), ("native_hs2", "hs2")]:
        common = common.merge(
            variants[variants["mechanical_variant"].eq(variant)][
                ["reporter_code", "year", "product_gini", "product_active_count"]
            ].rename(columns={"product_gini": f"product_gini_{prefix}", "product_active_count": f"active_count_{prefix}"}),
            on=["reporter_code", "year"],
            how="left",
            validate="one_to_one",
        )
    common = common.merge(
        commodity[["reporter_code", "year", "product_gini_full_exclusion", "commodity_gini_delta", "commodity_trade_share_removed"]],
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    common = common.merge(
        hs2_benchmark[["reporter_code", "year", "actual_minus_sim_median_gini", "actual_gini_percentile"]],
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    common = common.merge(
        main_panel[
            [
                "reporter_code",
                "year",
                "product_gini",
                "world_relative_product_gini",
                INCOME_VALUE_COL,
                INCOME_LOG_COL,
                INCOME_ALIAS_COL,
                INCOME_ALIAS_SQ_COL,
                "log_population",
                "oil_export_share",
                "section16_export_share",
                "section16_line_share",
            ]
            if "section16_export_share" in main_panel.columns
            else [
                "reporter_code",
                "year",
                "product_gini",
                "world_relative_product_gini",
                INCOME_VALUE_COL,
                INCOME_LOG_COL,
                INCOME_ALIAS_COL,
                INCOME_ALIAS_SQ_COL,
                "log_population",
                "oil_export_share",
            ]
        ],
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )
    common["hs_design_gini_delta_section16"] = common["product_gini"] - common["product_gini_no_section16"]
    common["hs4_gini_delta"] = common["product_gini"] - common["product_gini_hs4"]
    common["hs2_gini_delta"] = common["product_gini"] - common["product_gini_hs2"]
    common = common[common["year"].between(start_year, end_year)].copy()

    model_specs = [
        ("product_gini", "standard_hs6"),
        ("world_relative_product_gini", "harmonized_world_relative_hs6_family"),
        ("product_gini_no_section16", "native_hs6_excluding_section16"),
        ("product_gini_hs4", "native_hs4"),
        ("product_gini_hs2", "native_hs2"),
        ("product_gini_full_exclusion", "hs6_lumpy_commodity_excluded"),
        ("actual_minus_sim_median_gini", "hs2_preserving_benchmark_residual"),
    ]
    results: list[cse.ModelResult] = []
    for outcome, metric in model_specs:
        if outcome not in common.columns:
            continue
        results.append(
            cse.run_ols_model(
                common,
                outcome,
                [INCOME_ALIAS_COL, INCOME_ALIAS_SQ_COL, "log_population", "oil_export_share"],
                ["year"],
                "mechanical_variant_common_sample",
                COUNTRY_SAMPLE,
                FLOW,
                "product",
                metric,
                cluster_col="reporter_code",
            )
        )
    models = add_turning_points(cse.model_results_to_frame(results))
    return common, models


def build_hs4_country_year(product_exports: pd.DataFrame) -> pd.DataFrame:
    deflator = load_us_gdp_deflator()
    work = product_exports[["reporter_code", "year", "hs4_id", "trade_value"]].copy()
    work["deflator_factor_to_2024_usd"] = work["year"].map(deflator.factors)
    work = work.dropna(subset=["deflator_factor_to_2024_usd"]).copy()
    work["trade_value_2024_usd"] = work["trade_value"] * work["deflator_factor_to_2024_usd"]
    hs4 = (
        work.groupby(["reporter_code", "year", "hs4_id"], as_index=False)["trade_value_2024_usd"]
        .sum()
        .rename(columns={"hs4_id": "product_id"})
    )
    hs4 = hs4[hs4["trade_value_2024_usd"] > 0].reset_index(drop=True)
    return hs4


def build_prody(hs4: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    source_col = resolve_log_income_col(controls)
    controls = controls[["reporter_code", "year", source_col]].copy()
    controls = controls.rename(columns={source_col: INCOME_ALIAS_COL})
    work = hs4.merge(controls, on=["reporter_code", "year"], how="inner", validate="many_to_one")
    work = work.dropna(subset=[INCOME_ALIAS_COL]).copy()
    totals = work.groupby(["reporter_code", "year"], as_index=False)["trade_value_2024_usd"].sum().rename(
        columns={"trade_value_2024_usd": "country_total_exports_2024_usd"}
    )
    work = work.merge(totals, on=["reporter_code", "year"], how="left", validate="many_to_one")
    work["country_product_export_share"] = work["trade_value_2024_usd"] / work["country_total_exports_2024_usd"]
    work["weighted_log_income"] = work["country_product_export_share"] * work[INCOME_ALIAS_COL]
    sums = (
        work.groupby(["year", "product_id"], as_index=False)
        .agg(
            prody_share_sum=("country_product_export_share", "sum"),
            prody_weighted_log_income_sum=("weighted_log_income", "sum"),
            prody_exporter_count=("reporter_code", "nunique"),
        )
    )
    out = work.merge(sums, on=["year", "product_id"], how="left", validate="many_to_one")
    out["loo_share_sum"] = out["prody_share_sum"] - out["country_product_export_share"]
    out["loo_weighted_log_income_sum"] = out["prody_weighted_log_income_sum"] - out["weighted_log_income"]
    out["prody_log_income_pc_loo"] = out["loo_weighted_log_income_sum"] / out["loo_share_sum"]
    out.loc[
        (out["loo_share_sum"] <= 0) | (out["prody_exporter_count"] < PRODY_MIN_EXPORTERS),
        "prody_log_income_pc_loo",
    ] = np.nan
    out["prody_log_gni_pc_loo"] = out["prody_log_income_pc_loo"]
    return out[
        [
            "reporter_code",
            "year",
            "product_id",
            "trade_value_2024_usd",
            "country_product_export_share",
            INCOME_ALIAS_COL,
            "prody_log_income_pc_loo",
            "prody_log_gni_pc_loo",
            "prody_exporter_count",
        ]
    ].copy()


def window_values(group: pd.DataFrame, year: int) -> pd.Series:
    subset = group[group["year"].eq(int(year))]
    if subset.empty:
        return pd.Series(dtype=float)
    return subset.set_index("product_id")["trade_value_2024_usd"].astype(float)


def build_hs4_exit_windows(
    hs4: pd.DataFrame,
    controls: pd.DataFrame,
    threshold: float,
    start_year: int,
    end_year: int,
    horizon: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    income_col = resolve_log_income_col(controls)
    control_keep = controls[["reporter_code", "year", "country", "iso3", income_col]].rename(
        columns={"year": "base_year", income_col: "base_log_income_pc"}
    )
    max_base_year = end_year - horizon - 1
    for reporter_code, group in hs4.groupby("reporter_code", sort=True):
        group = group.sort_values(["year", "product_id"])
        for base_year in range(start_year, max_base_year + 1):
            years = [base_year, base_year + 1, base_year + horizon, base_year + horizon + 1]
            series = {year: window_values(group, year) for year in years}
            index = sorted(set().union(*(set(s.index) for s in series.values())))
            if not index:
                continue
            frame = pd.DataFrame({"product_id": index})
            frame["reporter_code"] = int(reporter_code)
            frame["base_year"] = int(base_year)
            frame["future_year"] = int(base_year + horizon)
            frame["horizon"] = int(horizon)
            frame["base_y1"] = frame["product_id"].map(series[base_year]).fillna(0.0).astype(float)
            frame["base_y2"] = frame["product_id"].map(series[base_year + 1]).fillna(0.0).astype(float)
            frame["future_y1"] = frame["product_id"].map(series[base_year + horizon]).fillna(0.0).astype(float)
            frame["future_y2"] = frame["product_id"].map(series[base_year + horizon + 1]).fillna(0.0).astype(float)
            frame["base_active"] = frame["base_y1"].ge(threshold) & frame["base_y2"].ge(threshold)
            frame["future_active"] = frame["future_y1"].ge(threshold) & frame["future_y2"].ge(threshold)
            frame["base_value_2024_usd"] = (frame["base_y1"] + frame["base_y2"]) / 2
            frame["future_value_2024_usd"] = (frame["future_y1"] + frame["future_y2"]) / 2
            frame["net_contribution_2024_usd"] = frame["future_value_2024_usd"] - frame["base_value_2024_usd"]
            frame["contraction_2024_usd"] = (-frame["net_contribution_2024_usd"]).clip(lower=0.0)
            frame["positive_expansion_2024_usd"] = frame["net_contribution_2024_usd"].clip(lower=0.0)
            frame["product_channel"] = np.select(
                [
                    ~frame["base_active"] & frame["future_active"],
                    frame["base_active"] & frame["future_active"],
                    frame["base_active"] & ~frame["future_active"],
                    ~frame["base_active"] & ~frame["future_active"],
                ],
                ["new_product", "continuing_product", "dying_product", "below_threshold_residual"],
                default="unclassified",
            )
            rows.append(frame)
    if not rows:
        return pd.DataFrame()
    windows = pd.concat(rows, ignore_index=True)
    windows = windows.merge(control_keep, on=["reporter_code", "base_year"], how="left", validate="many_to_one")
    return windows


def attach_prody_to_windows(windows: pd.DataFrame, prody: pd.DataFrame, threshold_info: dict[str, Any]) -> pd.DataFrame:
    prody_base = prody[["reporter_code", "year", "product_id", "prody_log_income_pc_loo", "prody_exporter_count"]].rename(
        columns={"year": "base_year"}
    )
    out = windows.merge(prody_base, on=["reporter_code", "base_year", "product_id"], how="left", validate="many_to_one")
    if "base_log_income_pc" not in out.columns and "base_log_gni_pc" in out.columns:
        out["base_log_income_pc"] = out["base_log_gni_pc"]
    out["mismatch_log_income_minus_prody"] = out["base_log_income_pc"] - out["prody_log_income_pc_loo"]
    out["mismatch_log_gni_minus_prody"] = out["mismatch_log_income_minus_prody"]
    threshold = float(threshold_info["rich_side_log_threshold_used"])
    out["rich_side_ct"] = (pd.to_numeric(out["base_log_income_pc"], errors="coerce") >= threshold).astype(int)
    out["fixed_rich_side_ct"] = (
        pd.to_numeric(out["base_log_income_pc"], errors="coerce") >= math.log(FIXED_RICH_SIDE_PPP_CONSTANT_2021_INTL_USD)
    ).astype(int)
    out["exit_next_window"] = out["product_channel"].eq("dying_product").astype(int)
    out["entry_next_window"] = out["product_channel"].eq("new_product").astype(int)
    out["mismatch_x_rich_side"] = out["mismatch_log_income_minus_prody"] * out["rich_side_ct"]
    return out


def residualize_fixed_effects(work: pd.DataFrame, cols: list[str], fe_cols: list[str], max_iter: int = 80, tol: float = 1e-10) -> np.ndarray:
    values = work[cols].to_numpy(dtype=float)
    residual = values - values.mean(axis=0, keepdims=True)
    for _ in range(max_iter):
        old = residual.copy()
        residual_df = pd.DataFrame(residual, columns=cols, index=work.index)
        for fe in fe_cols:
            means = residual_df.groupby(work[fe], observed=True)[cols].transform("mean").to_numpy(dtype=float)
            residual -= means
            residual_df.iloc[:, :] = residual
        if float(np.max(np.abs(residual - old))) < tol:
            break
    return residual


def p_value_from_t(t_stat: float, df: float) -> float:
    if not math.isfinite(t_stat) or not math.isfinite(df) or df <= 0:
        return np.nan
    if student_t is None:
        return float(2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2)))))
    return float(2 * student_t.sf(abs(t_stat), df))


def fixed_effect_exit_regression(windows: pd.DataFrame) -> pd.DataFrame:
    terms = ["mismatch_log_income_minus_prody", "rich_side_ct", "mismatch_x_rich_side"]
    required = ["exit_next_window", *terms, "reporter_code", "product_id", "base_year"]
    work = windows[windows["product_channel"].isin(["continuing_product", "dying_product"])].copy()
    candidate_rows = int(len(work))
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    if len(work) < 100 or work["reporter_code"].nunique() < 2:
        return pd.DataFrame(
            [
                {
                    "model_label": "old_cone_exit_hs4_lpm",
                    "term": term,
                    "coef": np.nan,
                    "std_error": np.nan,
                    "p_value": np.nan,
                    "nobs": int(len(work)),
                    "candidate_rows": candidate_rows,
                    "clusters": int(work["reporter_code"].nunique()) if not work.empty else 0,
                    "status": "insufficient_sample",
                }
                for term in terms
            ]
        )
    cols = ["exit_next_window", *terms]
    residual = residualize_fixed_effects(work, cols, ["reporter_code", "product_id", "base_year"])
    y = residual[:, 0]
    x = residual[:, 1:]
    keep = np.isfinite(y) & np.isfinite(x).all(axis=1)
    y = y[keep]
    x = x[keep]
    used = work.loc[keep].copy()
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    cov = cse.cluster_robust_covariance(x, resid, used["reporter_code"])
    se = np.sqrt(np.maximum(np.diag(cov), 0)) if np.isfinite(cov).any() else np.full(len(terms), np.nan)
    clusters = int(used["reporter_code"].nunique())
    rows: list[dict[str, Any]] = []
    for idx, term in enumerate(terms):
        t_stat = float(beta[idx] / se[idx]) if se[idx] > 0 else np.nan
        rows.append(
            {
                "model_label": "old_cone_exit_hs4_lpm",
                "outcome": "exit_next_window",
                "term": term,
                "coef": float(beta[idx]),
                "std_error": float(se[idx]) if math.isfinite(se[idx]) else np.nan,
                "t_stat": t_stat,
                "p_value": p_value_from_t(t_stat, clusters - 1),
                "nobs": int(len(used)),
                "candidate_rows": candidate_rows,
                "clusters": clusters,
                "fixed_effects": "reporter_code,product_id,base_year",
                "cluster_col": "reporter_code",
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def summarize_old_cone(windows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    usable = windows.dropna(subset=["mismatch_log_income_minus_prody"]).copy()
    usable = usable[usable["product_channel"].isin(["new_product", "continuing_product", "dying_product"])].copy()
    summary = (
        usable.groupby(["rich_side_ct", "product_channel"], as_index=False)
        .agg(
            rows=("product_id", "size"),
            countries=("reporter_code", "nunique"),
            median_mismatch=("mismatch_log_income_minus_prody", "median"),
            mean_mismatch=("mismatch_log_income_minus_prody", "mean"),
            median_prody=("prody_log_income_pc_loo", "median"),
            median_base_log_income=("base_log_income_pc", "median"),
            total_base_value_2024_usd=("base_value_2024_usd", "sum"),
            total_future_value_2024_usd=("future_value_2024_usd", "sum"),
            total_contraction_2024_usd=("contraction_2024_usd", "sum"),
            total_positive_expansion_2024_usd=("positive_expansion_2024_usd", "sum"),
        )
    )
    exit_sample = usable[usable["product_channel"].isin(["continuing_product", "dying_product"])].copy()
    if exit_sample.empty:
        deciles = pd.DataFrame()
    else:
        exit_sample["mismatch_decile"] = pd.qcut(
            exit_sample["mismatch_log_income_minus_prody"], 10, labels=False, duplicates="drop"
        )
        deciles = (
            exit_sample.groupby(["rich_side_ct", "mismatch_decile"], as_index=False)
            .agg(
                rows=("product_id", "size"),
                exit_rate=("exit_next_window", "mean"),
                median_mismatch=("mismatch_log_income_minus_prody", "median"),
                countries=("reporter_code", "nunique"),
            )
            .dropna(subset=["mismatch_decile"])
        )
    return summary, deciles


def load_transition_channels(country_sample: str) -> pd.DataFrame:
    path = sample_results_dir(country_sample) / "exercise_12_ev_hs4_expansion_tables" / "ev_hs4_country_window_decomposition.csv"
    panel = read_csv_required(path, "Exercise 12 EV HS4 country-window decomposition")
    panel = panel[panel["channel_type"].eq("product")].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["base_year"] = pd.to_numeric(panel["base_year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "base_year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["base_year"] = panel["base_year"].astype(int)
    return panel


def build_episode_scorecard(
    main_panel: pd.DataFrame,
    transition_channels: pd.DataFrame,
    commodity: pd.DataFrame,
    mechanical: pd.DataFrame,
    old_cone_windows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = main_panel[
        [
            "country",
            "iso3",
            "reporter_code",
            "year",
            "product_gini",
            "world_relative_product_gini",
            "product_active_count",
            "product_top_1pct_share",
            "product_partner_cell_top_1pct_share",
            "oil_export_share",
        ]
    ].copy()
    base = metrics.rename(
        columns={
            "year": "base_year",
            "product_gini": "base_product_gini",
            "world_relative_product_gini": "base_world_relative_product_gini",
            "product_active_count": "base_product_active_count",
            "product_top_1pct_share": "base_product_top_1pct_share",
            "product_partner_cell_top_1pct_share": "base_cell_top_1pct_share",
            "oil_export_share": "base_oil_export_share",
        }
    )
    future = metrics.rename(
        columns={
            "year": "future_year",
            "product_gini": "future_product_gini",
            "world_relative_product_gini": "future_world_relative_product_gini",
            "product_active_count": "future_product_active_count",
            "product_top_1pct_share": "future_product_top_1pct_share",
            "product_partner_cell_top_1pct_share": "future_cell_top_1pct_share",
            "oil_export_share": "future_oil_export_share",
        }
    )
    channels = transition_channels[transition_channels["horizon"].eq(MAIN_HORIZON)].copy()
    pivot = channels.pivot_table(
        index=["country", "iso3", "reporter_code", "base_year", "future_year", "horizon"],
        columns="channel",
        values=["positive_expansion_share", "contraction_share", "net_growth_share", "product_count"],
        aggfunc="first",
    )
    pivot.columns = [f"{channel}_{metric}" for metric, channel in pivot.columns]
    pivot = pivot.reset_index()
    episodes = pivot.merge(base, on=["country", "iso3", "reporter_code", "base_year"], how="inner", validate="many_to_one")
    episodes = episodes.merge(future, on=["country", "iso3", "reporter_code", "future_year"], how="inner", validate="many_to_one")
    episodes["delta_product_gini"] = episodes["future_product_gini"] - episodes["base_product_gini"]
    episodes["delta_world_relative_product_gini"] = (
        episodes["future_world_relative_product_gini"] - episodes["base_world_relative_product_gini"]
    )
    episodes["delta_active_product_count"] = episodes["future_product_active_count"] - episodes["base_product_active_count"]
    episodes["delta_top_product_share"] = episodes["future_product_top_1pct_share"] - episodes["base_product_top_1pct_share"]
    episodes["delta_top_cell_share"] = episodes["future_cell_top_1pct_share"] - episodes["base_cell_top_1pct_share"]
    episodes["reconcentration_episode"] = episodes["delta_world_relative_product_gini"].gt(0)

    commodity_base = commodity[["reporter_code", "year", "commodity_gini_delta", "commodity_trade_share_removed"]].rename(
        columns={"year": "base_year"}
    )
    episodes = episodes.merge(commodity_base, on=["reporter_code", "base_year"], how="left", validate="many_to_one")
    mech_base = mechanical[
        [
            "reporter_code",
            "year",
            "hs_design_gini_delta_section16",
            "hs4_gini_delta",
            "hs2_gini_delta",
            "section16_export_share",
            "section16_line_share",
        ]
        if "section16_export_share" in mechanical.columns
        else ["reporter_code", "year", "hs_design_gini_delta_section16", "hs4_gini_delta", "hs2_gini_delta"]
    ].rename(columns={"year": "base_year"})
    episodes = episodes.merge(mech_base, on=["reporter_code", "base_year"], how="left", validate="many_to_one")

    old = old_cone_windows[old_cone_windows["horizon"].eq(MAIN_HORIZON)].copy()
    old = old.dropna(subset=["mismatch_log_income_minus_prody"])
    old_summary = (
        old.groupby(["reporter_code", "base_year"], as_index=False)
        .agg(
            dying_median_mismatch=("mismatch_log_income_minus_prody", lambda x: float(np.nanmedian(x[old.loc[x.index, "product_channel"].eq("dying_product")])) if old.loc[x.index, "product_channel"].eq("dying_product").any() else np.nan),
            continuing_median_mismatch=("mismatch_log_income_minus_prody", lambda x: float(np.nanmedian(x[old.loc[x.index, "product_channel"].eq("continuing_product")])) if old.loc[x.index, "product_channel"].eq("continuing_product").any() else np.nan),
            new_median_mismatch=("mismatch_log_income_minus_prody", lambda x: float(np.nanmedian(x[old.loc[x.index, "product_channel"].eq("new_product")])) if old.loc[x.index, "product_channel"].eq("new_product").any() else np.nan),
            rich_side_ct=("rich_side_ct", "max"),
        )
    )
    old_summary["old_cone_mismatch_gap"] = old_summary["dying_median_mismatch"] - old_summary["continuing_median_mismatch"]
    episodes = episodes.merge(old_summary, on=["reporter_code", "base_year"], how="left", validate="many_to_one")

    episodes["commodity_spike"] = (
        episodes["commodity_trade_share_removed"].fillna(0).ge(0.20)
        | episodes["base_oil_export_share"].fillna(0).ge(0.25)
        | episodes["commodity_gini_delta"].fillna(0).ge(0.05)
    )
    episodes["section16_hs_design_sensitive"] = (
        episodes["hs_design_gini_delta_section16"].abs().fillna(0).ge(0.03)
        | episodes.get("section16_export_share", pd.Series(0, index=episodes.index)).fillna(0).ge(0.30)
    )
    episodes["old_cone_pruning"] = (
        episodes["rich_side_ct"].fillna(0).astype(int).eq(1)
        & episodes["old_cone_mismatch_gap"].fillna(0).gt(0)
        & episodes.get("dying_product_contraction_share", pd.Series(0, index=episodes.index)).fillna(0).gt(0.05)
    )
    episodes["continuing_product_superstar_scaling"] = (
        episodes.get("continuing_product_positive_expansion_share", pd.Series(0, index=episodes.index)).fillna(0).ge(0.75)
        & episodes["delta_top_product_share"].fillna(0).gt(0)
    )
    mechanism_flags = [
        "commodity_spike",
        "section16_hs_design_sensitive",
        "old_cone_pruning",
        "continuing_product_superstar_scaling",
    ]
    episodes["broad_unexplained_reconcentration"] = episodes["reconcentration_episode"] & ~episodes[mechanism_flags].any(axis=1)
    summary_rows: list[dict[str, Any]] = []
    recon = episodes[episodes["reconcentration_episode"]].copy()
    for flag in [*mechanism_flags, "broad_unexplained_reconcentration"]:
        summary_rows.append(
            {
                "mechanism": flag,
                "reconcentration_episodes": int(len(recon)),
                "flagged_episodes": int(recon[flag].sum()) if flag in recon.columns else 0,
                "flagged_share": float(recon[flag].mean()) if flag in recon.columns and len(recon) else np.nan,
            }
        )
    for channel in ["new_product", "continuing_product", "dying_product"]:
        for metric in ["positive_expansion_share", "contraction_share", "net_growth_share"]:
            col = f"{channel}_{metric}"
            if col in recon.columns:
                summary_rows.append(
                    {
                        "mechanism": f"{channel}_{metric}",
                        "reconcentration_episodes": int(len(recon)),
                        "flagged_episodes": np.nan,
                        "flagged_share": float(recon[col].median()) if len(recon) else np.nan,
                    }
                )
    return episodes, pd.DataFrame(summary_rows)


def plot_hump(panel: pd.DataFrame, out: Path) -> None:
    work = panel.dropna(subset=[INCOME_ALIAS_COL, "world_relative_product_gini"]).copy()
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    ax.scatter(np.exp(work[INCOME_ALIAS_COL]), work["world_relative_product_gini"], s=18, alpha=0.35, color="#295f8a")
    bins = pd.qcut(work[INCOME_ALIAS_COL], 12, duplicates="drop")
    binned = work.groupby(bins, observed=True).agg(
        log_income_pc=(INCOME_ALIAS_COL, "mean"), world_relative_product_gini=("world_relative_product_gini", "median")
    )
    ax.plot(np.exp(binned["log_income_pc"]), binned["world_relative_product_gini"], color="#b33a3a", lw=2.2, marker="o")
    ax.set_xscale("log")
    ax.set_xlabel("GDP per capita, PPP, constant 2021 international $ (log scale)")
    ax.set_ylabel("World-Relative Product Gini")
    ax.set_title("Development Hump Check, rd2 Balanced 2000-2024")
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)


def plot_mechanism_summary(summary: pd.DataFrame, out: Path) -> None:
    flags = summary[summary["mechanism"].isin(
        [
            "commodity_spike",
            "section16_hs_design_sensitive",
            "old_cone_pruning",
            "continuing_product_superstar_scaling",
            "broad_unexplained_reconcentration",
        ]
    )].copy()
    if flags.empty:
        return
    labels = [
        "Commodity",
        "HS design",
        "Old-cone exit",
        "Continuing scale",
        "Unexplained",
    ][: len(flags)]
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ax.barh(labels, flags["flagged_share"].fillna(0), color=["#7c3f2d", "#6b7280", "#0b6b62", "#295f8a", "#a16207"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of 5-year reconcentration episodes")
    ax.set_title("Mechanism Scorecard")
    for i, value in enumerate(flags["flagged_share"].fillna(0)):
        ax.text(float(value) + 0.01, i, f"{value:.0%}", va="center")
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)


def plot_robustness_ladder(models: pd.DataFrame, out: Path) -> None:
    rows = models[models["term"].eq(INCOME_ALIAS_SQ_COL)].copy()
    rows = rows.sort_values("metric")
    if rows.empty:
        return
    fig, ax = plt.subplots(figsize=(9.2, 5.5))
    y = np.arange(len(rows))
    ax.errorbar(rows["coefficient"], y, xerr=1.96 * rows["std_error"].abs(), fmt="o", color="#295f8a", ecolor="#9ca3af")
    ax.axvline(0, color="#111827", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(rows["metric"].astype(str).str.replace("_", " "))
    ax.set_xlabel("Quadratic log constant-PPP GDPpc coefficient")
    ax.set_title("Robustness Ladder: Is the Hump Mechanical?")
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)


def plot_old_cone(deciles: pd.DataFrame, out: Path) -> None:
    if deciles.empty:
        return
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    for rich, group in deciles.groupby("rich_side_ct"):
        label = "Right/rich side" if int(rich) == 1 else "Left/non-rich side"
        ax.plot(group["median_mismatch"], group["exit_rate"], marker="o", lw=2, label=label)
    ax.set_xlabel("Median mismatch: log constant-PPP GDPpc minus product PRODY")
    ax.set_ylabel("HS4 exit rate")
    ax.set_title("Old-Cone Exit Test")
    ax.legend(frameon=False)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)


def write_markdown(
    path: Path,
    *,
    diagnostics: dict[str, Any],
    hump_models: pd.DataFrame,
    mechanism_summary: pd.DataFrame,
    old_cone_models: pd.DataFrame,
) -> None:
    preferred = hump_models[
        hump_models["model_label"].eq("quadratic_controls_year_fe_country_cluster")
        & hump_models["metric"].eq("world_relative_product_gini")
    ]
    coef_rows = preferred[preferred["term"].isin([INCOME_ALIAS_COL, INCOME_ALIAS_SQ_COL])][
        ["term", "coefficient", "std_error", "p_value", "turning_point_ppp_constant_2021_intl_usd", "status"]
    ]
    old_interaction = old_cone_models[old_cone_models["term"].eq("mismatch_x_rich_side")]
    old_text = "No old-cone interaction estimate."
    if not old_interaction.empty:
        row = old_interaction.iloc[0]
        old_text = (
            f"The mismatch x rich-side coefficient is {row['coef']:.4f} "
            f"(SE {row['std_error']:.4f}, p={row['p_value']:.3f}, n={int(row['nobs']):,})."
        )
    text = [
        "# Cadot Hump Mechanism Tribunal",
        "",
        f"Created: {diagnostics['created_at_utc']}",
        "",
        "This is a descriptive mechanism-classification exercise for rd2 exports. It asks whether rising export concentration is better read as mechanical HS design, commodity exposure, active-line loss, continuing-product scaling, or old-cone exit into a higher-sophistication basket. It is not a causal claim that development itself causes reconcentration.",
        "",
        "## Main Sample",
        "",
        f"- Balanced panel: {diagnostics['main_balanced_countries']} countries x {diagnostics['main_balanced_years']} years = {diagnostics['main_balanced_rows']} country-years.",
        f"- Main years: {diagnostics['main_start_year']}-{diagnostics['main_end_year']}.",
            f"- Rich-side definition used in mechanism tests: `{diagnostics['turning_point']['rich_side_source']}`.",
        f"- HS6 999999 rows excluded before product-dependent aggregation: {diagnostics['excluded_999999_rows_from_product_exports']:,}.",
        "",
        "## Hump Result",
        "",
        coef_rows.round(4).to_markdown(index=False) if not coef_rows.empty else "Preferred hump model did not estimate.",
        "",
        "Read this as a shape diagnostic. If the quadratic term is not positive and the turning point is not inside the sample support, the rd2 balanced panel does not give a clean Cadot-style U-shape for the world-relative measure.",
        "",
        "## Mechanism Scorecard",
        "",
        mechanism_summary.round(4).to_markdown(index=False) if not mechanism_summary.empty else "No mechanism summary.",
        "",
        "## Old-Cone Exit Test",
        "",
        old_text,
        "",
        "Structural-upgrading evidence requires all three conditions: concentration rises, exited products are lower-sophistication or farther below the country's constant-PPP income position, and surviving/new products are closer to the constant-PPP position or world-relevant. The scorecard only classifies episodes; it does not prove a structural mechanism.",
        "",
        "## Key Artifacts",
        "",
        "- `cadot_hump_country_year_panel.csv`: main balanced country-year panel.",
        "- `cadot_hump_models.csv`: quadratic development-hump models.",
        "- `mechanical_variant_models.csv`: Section 16, HS4, HS2, commodity, and HS2-preserving residual robustness.",
        "- `reconcentration_episode_scorecard.csv`: country-window mechanism flags.",
        "- `old_cone_exit_models.csv`: HS4 exit regressions with country, product, and base-year fixed effects.",
        "- `cadot_hump_tribunal_adversarial_review.md`: local trust audit.",
    ]
    path.write_text("\n".join(text) + "\n", encoding="utf-8")


def write_adversarial_review(path: Path, diagnostics: dict[str, Any]) -> None:
    text = f"""# Adversarial Econometrics Review: Cadot Hump Tribunal

Created: {now_utc()}

Review independence: **not independent**. Subagent delegation was not explicitly authorized in the current request, so this is a local adversarial pass by the same Codex session.

## Verdict

Use the outputs as a first-pass descriptive tribunal, not as final causal evidence. The pipeline is useful for separating mechanisms, but the old-cone sophistication proxy is an rd2 leave-one-out PRODY proxy based on constant-PPP GDP per capita rather than a true global PRODY unless broader country income controls are added.

## Checks

- Data lineage: country-year outcomes come from Exercise 1, harmonized world-relative Product Gini, Exercise 6 lumpy exclusions, Exercise 10 HS2-preserving benchmarks, and Exercise 12 HS4 transition outputs.
- Product-dependent exclusion: native HS6 product exports exclude `999999` before HS6/HS4/HS2, Section 16, PRODY, and exit-window aggregation. Excluded rows recorded by the runner: {diagnostics['excluded_999999_rows_from_product_exports']:,}.
- Main sample: balanced {diagnostics['main_start_year']}-{diagnostics['main_end_year']} rd2 world-relative panel has {diagnostics['main_balanced_rows']} rows and {diagnostics['main_balanced_countries']} countries.
- Duplicate keys: runner validates country-year uniqueness for controls, standard concentration, world-relative panel, HS2 benchmark, commodity panel, and final country-year panel.
- Leave-one-out PRODY: product sophistication subtracts the focal country-product contribution from both numerator and denominator and uses World Bank `{ppp.PPP_INDICATOR}` constant-PPP GDP per capita; products with fewer than {PRODY_MIN_EXPORTERS} exporters are set missing.
- Exit definition: HS4 exit follows the Exercise 12-style adjacent 2+2 persistence rule with the ${ACTIVE_THRESHOLD_USD_2024:,.0f} constant-2024-USD activity threshold.
- Inference: hump regressions are descriptive OLS with year fixed effects and clustered/two-way-clustered SE variants. The old-cone model is a linear probability model residualized by country, product, and base-year fixed effects, clustered by country.
- Website consistency: the site page reads static CSV/PNG outputs from `rd2_countries`; no result should be interpreted for `prof_p_33` or `world_broad`.

## Remaining Caveats

- The PRODY proxy is sample-internal to rd2 because the available world-broad product totals do not include a complete matched world-broad income-control panel in this runner.
- HS revision harmonization is handled in the world-relative measure, but the old-cone HS4 windows use native HS4 prefixes; that is appropriate for first-pass transition mechanics but not a final harmonized product-life-cycle test.
- Section 16 sensitivity drops chapters 84-85 at native HS6 level; it does not solve all cross-section differences in HS code density.
- Commodity classification uses the existing Exercise 6 lumpy bundle and oil export share, so commodity-driven reconcentration outside those categories may remain in the unexplained bucket.
- Mechanism flags use transparent thresholds; they should be treated as triage labels, not hypothesis tests.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--appendix-start-year", type=int, default=1988)
    parser.add_argument("--appendix-end-year", type=int, default=2025)
    parser.add_argument("--horizon", type=int, default=MAIN_HORIZON)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.country_sample != COUNTRY_SAMPLE:
        raise RuntimeError("Cadot hump tribunal is currently implemented for rd2_countries only.")
    if args.horizon != MAIN_HORIZON:
        raise RuntimeError("Only the 5-year tribunal horizon is currently supported.")

    result_base = sample_results_dir(args.country_sample)
    table_dir = result_base / "cadot_hump_tribunal_tables"
    figure_dir = result_base / "cadot_hump_tribunal_figures"
    processed_dir = sample_processed_dir(args.country_sample)
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    controls = load_controls(args.country_sample, args.start_year, args.end_year)
    main_panel, all_country_year = load_main_country_year_panel(
        args.country_sample,
        args.start_year,
        args.end_year,
        controls=controls,
    )
    product_exports = load_product_exports(args.country_sample)
    variants = gini_variant_panel(product_exports, controls)
    section = variants[variants["mechanical_variant"].eq("native_hs6")][
        ["reporter_code", "year", "section16_export_share", "section16_line_share"]
    ].drop_duplicates(["reporter_code", "year"])
    main_panel = main_panel.merge(section, on=["reporter_code", "year"], how="left", validate="one_to_one")
    all_country_year = all_country_year.merge(section, on=["reporter_code", "year"], how="left", validate="one_to_one")

    commodity = load_commodity_panel(args.country_sample)
    hs2_benchmark = load_hs2_benchmark(args.country_sample)
    main_panel = main_panel.merge(
        commodity[["reporter_code", "year", "commodity_gini_delta", "commodity_trade_share_removed"]],
        on=["reporter_code", "year"],
        how="left",
        validate="one_to_one",
    )

    hump_models = run_hump_models(main_panel, "rd2_balanced_2000_2024")
    turning = preferred_turning_point(hump_models, main_panel)
    mechanical_common, mechanical_models = run_mechanical_variant_models(
        main_panel, variants, commodity, hs2_benchmark, args.start_year, args.end_year
    )

    balanced_reporters = set(main_panel["reporter_code"].astype(int))
    hs4 = build_hs4_country_year(product_exports[product_exports["reporter_code"].isin(balanced_reporters)].copy())
    prody = build_prody(hs4, controls)
    windows = build_hs4_exit_windows(
        hs4,
        controls,
        ACTIVE_THRESHOLD_USD_2024,
        args.start_year,
        args.end_year,
        MAIN_HORIZON,
    )
    old_cone_windows = attach_prody_to_windows(windows, prody, turning)
    old_cone_models = fixed_effect_exit_regression(old_cone_windows)
    old_cone_summary, old_cone_deciles = summarize_old_cone(old_cone_windows)

    transitions = load_transition_channels(args.country_sample)
    episodes, mechanism_summary = build_episode_scorecard(
        main_panel, transitions, commodity, mechanical_common, old_cone_windows
    )

    diagnostics = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "main_start_year": args.start_year,
        "main_end_year": args.end_year,
        "appendix_start_year": args.appendix_start_year,
        "appendix_end_year": args.appendix_end_year,
        "main_balanced_rows": int(len(main_panel)),
        "main_balanced_countries": int(main_panel["reporter_code"].nunique()),
        "main_balanced_years": int(main_panel["year"].nunique()),
        "main_expected_rows": int(main_panel["reporter_code"].nunique() * main_panel["year"].nunique()),
        "excluded_999999_rows_from_product_exports": int(product_exports.attrs.get("excluded_999999_rows", 0)),
        "hs4_country_year_rows": int(len(hs4)),
        "prody_rows": int(len(prody)),
        "old_cone_window_rows": int(len(old_cone_windows)),
        "old_cone_complete_mismatch_rows": int(old_cone_windows["mismatch_log_income_minus_prody"].notna().sum()),
        "reconcentration_episode_rows": int(len(episodes)),
        "reconcentration_episode_count": int(episodes["reconcentration_episode"].sum()) if not episodes.empty else 0,
        "turning_point": turning,
        "sample_balance_diagnostics": balanced_sample_diagnostics(all_country_year, args.start_year, args.end_year).to_dict(orient="records"),
        "prody_scope": "rd2 leave-one-out PRODY proxy using exporter product shares and log GDP per capita at PPP in constant 2021 international dollars",
        "income_indicator": ppp.PPP_INDICATOR,
        "income_label": INCOME_LABEL,
        "product_excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
    }

    main_panel.to_csv(table_dir / "cadot_hump_country_year_panel.csv", index=False)
    all_country_year.to_csv(table_dir / "cadot_hump_appendix_country_year_panel.csv", index=False)
    balanced_sample_diagnostics(all_country_year, args.start_year, args.end_year).to_csv(
        table_dir / "cadot_hump_sample_diagnostics.csv", index=False
    )
    hump_models.to_csv(table_dir / "cadot_hump_models.csv", index=False)
    variants.to_csv(table_dir / "mechanical_variant_country_year_panel.csv", index=False)
    mechanical_common.to_csv(table_dir / "mechanical_common_sample_panel.csv", index=False)
    mechanical_models.to_csv(table_dir / "mechanical_variant_models.csv", index=False)
    commodity.to_csv(table_dir / "commodity_mechanism_panel.csv", index=False)
    hs2_benchmark.to_csv(table_dir / "hs2_preserving_benchmark_panel.csv", index=False)
    transitions.to_csv(table_dir / "exercise12_hs4_transition_channels.csv", index=False)
    prody.to_parquet(processed_dir / "cadot_hump_hs4_rd2_leave_one_out_prody.parquet", index=False)
    old_cone_windows.to_parquet(processed_dir / "cadot_hump_old_cone_exit_windows.parquet", index=False)
    old_cone_windows.sample(min(100_000, len(old_cone_windows)), random_state=123).to_csv(
        table_dir / "old_cone_exit_windows_sample.csv", index=False
    )
    old_cone_models.to_csv(table_dir / "old_cone_exit_models.csv", index=False)
    old_cone_summary.to_csv(table_dir / "old_cone_channel_summary.csv", index=False)
    old_cone_deciles.to_csv(table_dir / "old_cone_exit_by_mismatch_decile.csv", index=False)
    episodes.to_csv(table_dir / "reconcentration_episode_scorecard.csv", index=False)
    mechanism_summary.to_csv(table_dir / "mechanism_scorecard_summary.csv", index=False)
    (table_dir / "cadot_hump_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True, default=clean_scalar) + "\n",
        encoding="utf-8",
    )
    (result_base / "run_manifest_cadot_hump_tribunal.json").write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True, default=clean_scalar) + "\n",
        encoding="utf-8",
    )

    plot_hump(main_panel, figure_dir / "cadot_hump_curve.png")
    plot_mechanism_summary(mechanism_summary, figure_dir / "mechanism_scorecard.png")
    plot_robustness_ladder(mechanical_models, figure_dir / "mechanical_robustness_ladder.png")
    plot_old_cone(old_cone_deciles, figure_dir / "old_cone_exit_plot.png")

    write_markdown(
        result_base / "cadot_hump_tribunal.md",
        diagnostics=diagnostics,
        hump_models=hump_models,
        mechanism_summary=mechanism_summary,
        old_cone_models=old_cone_models,
    )
    write_adversarial_review(result_base / "cadot_hump_tribunal_adversarial_review.md", diagnostics)

    print(f"Wrote {rel(table_dir)}")
    print(f"Wrote {rel(figure_dir)}")
    print(f"Wrote {rel(result_base / 'cadot_hump_tribunal.md')}")


if __name__ == "__main__":
    main()
