#!/usr/bin/env python3
"""Run active Product Gini country-year exercises with fixed-universe Product Gini.

This script does not pretend every product-level exercise has a direct
country-year replacement. It reruns the exercises where active Product Gini was
used as a country-year outcome or predictor, and writes an applicability matrix
for exercises that require a new product-level fixed-universe definition.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_country_size_effect as cse  # noqa: E402
from trade_concentration_pipeline import sample_processed_path, sample_results_dir  # noqa: E402


COUNTRY_SAMPLE = "rd2_countries"
FLOW_CHOICES = ("Exports", "Imports")
OUTPUT_DIRNAME = "fixed_universe_gini_exercise_suite"
FIXED_RESULTS = (
    ROOT
    / "results/samples/rd2_countries/fixed_universe_product_gini_tables/fixed_universe_product_gini_all_years.csv"
)
COUNTRY_SIZE_TERMS = ["log_population", "log_gdp_per_capita"]
GROWTH_LEVEL_TERM = "lag_log_real_exports"
GROWTH_POP_TERM = "lag_log_population"
E2_OUTCOME = "annualized_export_growth_log"
PRIMARY_FUTURE_OUTCOME = "annualized_real_export_growth_log"
BASE_CONTROL_TERMS = [
    "log_initial_exports_constant_2015_usd",
    "oil_export_share",
    "log_gdp_constant_2015_usd",
    "log_population",
    "log_gni_per_capita_constant_2015_usd",
]
BUCKET_ORDER = (
    "high_product_high_partner",
    "high_product_low_partner",
    "low_product_high_partner",
)
BUCKET_TERMS = [f"fixed_bucket_{bucket}" for bucket in BUCKET_ORDER]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def current_rss_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return float(psutil.Process(os.getpid()).memory_info().rss / (1024**2))
    except Exception:
        try:
            rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except Exception:
            return None
        return rss / (1024**2) if sys.platform == "darwin" else rss / 1024


def log_resource(label: str, memory_budget_gb: float | None = None) -> None:
    rss = current_rss_mb()
    if rss is None:
        print(f"[resource] {label}: rss unavailable")
        return
    print(f"[resource] {label}: rss={rss:,.1f} MB")
    if memory_budget_gb and memory_budget_gb > 0 and rss > memory_budget_gb * 1024:
        raise RuntimeError(f"Memory budget exceeded after {label}: {rss / 1024:.2f} GB > {memory_budget_gb:.2f} GB")


def validate_unique(df: pd.DataFrame, keys: list[str], label: str) -> None:
    missing = sorted(set(keys) - set(df.columns))
    if missing:
        raise RuntimeError(f"{label} is missing key columns: {missing}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        examples = df[df.duplicated(keys, keep=False)][keys].head(10).to_dict(orient="records")
        raise RuntimeError(f"{label} has duplicate keys on {keys}: {examples}")


def model_frame(results: list[cse.ModelResult]) -> pd.DataFrame:
    return cse.model_results_to_frame(results)


def load_fixed_panel() -> pd.DataFrame:
    if not FIXED_RESULTS.exists():
        raise FileNotFoundError(f"Missing fixed-universe Gini results: {FIXED_RESULTS}")
    cols = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "product_id_mode",
        "fixed_universe_product_gini",
        "active_product_gini",
        "gini_extensive_gap",
        "active_product_count",
        "universe_product_count",
        "zero_product_count",
        "active_product_share",
        "total_trade_value",
        "balanced_panel_flag",
        "region",
        "income_group",
    ]
    df = pd.read_csv(FIXED_RESULTS, usecols=cols)
    df = df[df["product_id_mode"].eq("harmonized_hs6_family")].copy()
    df["reporter_code"] = pd.to_numeric(df["reporter_code"], errors="coerce").astype("Int64")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["reporter_code", "year"]).copy()
    df["reporter_code"] = df["reporter_code"].astype(int)
    df["year"] = df["year"].astype(int)
    validate_unique(df, ["reporter_code", "year", "flow"], "fixed-universe panel")
    if df["fixed_universe_product_gini"].isna().any():
        raise RuntimeError("Fixed-universe panel has missing fixed_universe_product_gini values.")
    if any(df[col].astype(str).str.contains("999999", na=False).any() for col in ["product_id_mode"]):
        raise RuntimeError("Fixed-universe panel contains excluded 999999 product text.")
    keep = [
        "reporter_code",
        "year",
        "flow",
        "fixed_universe_product_gini",
        "active_product_gini",
        "gini_extensive_gap",
        "active_product_count",
        "universe_product_count",
        "zero_product_count",
        "active_product_share",
        "balanced_panel_flag",
    ]
    return df[keep].rename(columns={"active_product_gini": "active_harmonized_product_gini"}).copy()


def fixed_flow(fixed: pd.DataFrame, flow: str) -> pd.DataFrame:
    out = fixed[fixed["flow"].eq(flow)].drop(columns=["flow"]).copy()
    validate_unique(out, ["reporter_code", "year"], f"fixed {flow} panel")
    return out


def load_flow_panel(path: Path, label: str, flow: str, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    panel = pd.read_parquet(path, columns=columns)
    if "flow" in panel.columns:
        panel = panel[panel["flow"].eq(flow)].copy()
    if "variant" in panel.columns:
        panel = panel[panel["variant"].eq("baseline")].copy()
    panel["reporter_code"] = pd.to_numeric(panel["reporter_code"], errors="coerce").astype("Int64")
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce").astype("Int64")
    panel = panel.dropna(subset=["reporter_code", "year"]).copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    return panel


def merge_fixed(panel: pd.DataFrame, fixed: pd.DataFrame, flow: str, label: str) -> pd.DataFrame:
    out = panel.merge(fixed_flow(fixed, flow), on=["reporter_code", "year"], how="inner", validate="many_to_one")
    if out.empty:
        raise RuntimeError(f"{label} has no rows after merging fixed-universe Gini.")
    return out


def load_country_size_controls_by_flow(country_sample: str) -> dict[str, pd.DataFrame]:
    country_size_path = sample_processed_path("country_size_effect_panel.parquet", country_sample)
    controls_by_flow: dict[str, pd.DataFrame] = {}
    for flow in FLOW_CHOICES:
        controls = load_flow_panel(
            country_size_path,
            "country size controls",
            flow,
            columns=[
                "reporter_code",
                "year",
                "flow",
                "variant",
                "product_gini",
                "log_population",
                "log_gdp_per_capita",
            ],
        )[["reporter_code", "year", "product_gini", "log_population", "log_gdp_per_capita"]].copy()
        validate_unique(controls, ["reporter_code", "year"], f"country size controls {flow}")
        controls_by_flow[flow] = controls
    return controls_by_flow


def merge_ex11_with_controls(
    ex11_country_year: pd.DataFrame,
    fixed: pd.DataFrame,
    controls_by_flow: dict[str, pd.DataFrame],
    flow: str,
) -> pd.DataFrame:
    if flow not in controls_by_flow:
        raise RuntimeError(f"Missing country size controls for {flow}.")
    return merge_fixed(ex11_country_year, fixed, flow, f"Exercise 11 aggregate {flow}").merge(
        controls_by_flow[flow], on=["reporter_code", "year"], how="left", validate="many_to_one"
    )


def merge_diagnostic_row(label: str, flow: str, base: pd.DataFrame, merged: pd.DataFrame, fixed: pd.DataFrame) -> dict[str, Any]:
    base_keys = base[["reporter_code", "year"]].drop_duplicates()
    merged_keys = merged[["reporter_code", "year"]].drop_duplicates()
    fixed_keys = fixed[fixed["flow"].eq(flow)][["reporter_code", "year"]].drop_duplicates()
    unmatched = base_keys.merge(fixed_keys, on=["reporter_code", "year"], how="left", indicator=True)
    fixed_missing = int(merged.get("fixed_universe_product_gini", pd.Series(dtype=float)).isna().sum())
    active_missing = int(merged.get("product_gini", pd.Series(dtype=float)).isna().sum())
    return {
        "panel": label,
        "flow": flow,
        "base_rows": int(len(base)),
        "base_country_years": int(len(base_keys)),
        "merged_rows": int(len(merged)),
        "merged_country_years": int(len(merged_keys)),
        "unmatched_country_years": int(unmatched["_merge"].eq("left_only").sum()),
        "country_year_merge_rate": float(len(merged_keys) / len(base_keys)) if len(base_keys) else np.nan,
        "fixed_gini_missing_after_merge": fixed_missing,
        "active_product_gini_missing_after_merge": active_missing,
    }


def outcome_specs() -> tuple[tuple[str, str], ...]:
    return (
        ("product_gini", "active_product_gini_legacy"),
        ("fixed_universe_product_gini", "fixed_universe_product_gini"),
    )


def add_fixed_buckets(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["median_fixed_universe_product_gini"] = out.groupby(["flow", "year"])[
        "fixed_universe_product_gini"
    ].transform("median")
    out["median_partner_gini_fixed_sample"] = out.groupby(["flow", "year"])["partner_gini"].transform("median")
    out["fixed_product_concentration_high"] = (
        out["fixed_universe_product_gini"] >= out["median_fixed_universe_product_gini"]
    )
    out["fixed_partner_concentration_high"] = out["partner_gini"] >= out["median_partner_gini_fixed_sample"]
    out["fixed_concentration_bucket"] = np.select(
        [
            out["fixed_product_concentration_high"] & out["fixed_partner_concentration_high"],
            out["fixed_product_concentration_high"] & ~out["fixed_partner_concentration_high"],
            ~out["fixed_product_concentration_high"] & out["fixed_partner_concentration_high"],
        ],
        list(BUCKET_ORDER),
        default="low_product_low_partner",
    )
    for bucket in BUCKET_ORDER:
        out[f"fixed_bucket_{bucket}"] = out["fixed_concentration_bucket"].eq(bucket).astype(float)
    out["fixed_universe_product_gini_x_partner_gini"] = (
        pd.to_numeric(out["fixed_universe_product_gini"], errors="coerce")
        * pd.to_numeric(out["partner_gini"], errors="coerce")
    )
    out["product_gini_x_partner_gini"] = (
        pd.to_numeric(out["product_gini"], errors="coerce") * pd.to_numeric(out["partner_gini"], errors="coerce")
    )
    return out


def run_country_size_models(panel: pd.DataFrame, flow: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    for outcome, metric in outcome_specs():
        for model_label, fixed_effects, two_way in [
            ("country_size_year_fe", ["year"], None),
            ("country_size_two_way_cluster", ["year"], "year"),
        ]:
            results.append(
                cse.run_ols_model(
                    panel,
                    outcome,
                    COUNTRY_SIZE_TERMS,
                    fixed_effects,
                    model_label,
                    COUNTRY_SAMPLE,
                    flow,
                    "product",
                    metric,
                    cluster_col="reporter_code",
                    two_way_cluster_col=two_way,
                )
            )
    out = model_frame(results)
    out.insert(0, "exercise_family", "country_size")
    return out


def run_growth_models(panel: pd.DataFrame, flow: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    specs = [
        ("growth_prior_country_year_fe", "prior_export_growth"),
        ("growth_contemporaneous_country_year_fe", "contemporaneous_export_growth"),
        ("growth_future_placebo_country_year_fe", "future_export_growth"),
    ]
    for outcome, metric in outcome_specs():
        for model_label, growth_term in specs:
            results.append(
                cse.run_ols_model(
                    panel,
                    outcome,
                    [growth_term, GROWTH_LEVEL_TERM, GROWTH_POP_TERM],
                    ["reporter_code", "year"],
                    model_label,
                    COUNTRY_SAMPLE,
                    flow,
                    "product",
                    metric,
                    cluster_col="reporter_code",
                )
            )
    out = model_frame(results)
    out.insert(0, "exercise_family", "growth_effect")
    return out


def run_exercise2_models(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = add_fixed_buckets(panel)
    results: list[cse.ModelResult] = []
    for horizon in sorted(work["horizon"].dropna().unique()):
        h = int(horizon)
        horizon_panel = work[work["horizon"].eq(horizon)].copy()
        for outcome, metric, product_term, interaction in [
            ("product_gini", "active_product_gini_legacy", "product_gini", "product_gini_x_partner_gini"),
            (
                "fixed_universe_product_gini",
                "fixed_universe_product_gini",
                "fixed_universe_product_gini",
                "fixed_universe_product_gini_x_partner_gini",
            ),
        ]:
            results.append(
                cse.run_ols_model(
                    horizon_panel,
                    E2_OUTCOME,
                    [product_term, "partner_gini", interaction, "log_initial_exports", "oil_export_share"],
                    ["reporter_code", "year"],
                    f"e2_continuous_gini_h{h}",
                    COUNTRY_SAMPLE,
                    "Exports",
                    "product",
                    metric,
                    cluster_col="reporter_code",
                )
            )
        results.append(
            cse.run_ols_model(
                horizon_panel,
                E2_OUTCOME,
                [*BUCKET_TERMS, "log_initial_exports", "oil_export_share"],
                ["reporter_code", "year"],
                f"e2_fixed_bucket_h{h}",
                COUNTRY_SAMPLE,
                "Exports",
                "product_partner_bucket",
                "fixed_universe_gini_bucket",
                cluster_col="reporter_code",
            )
        )
    models = model_frame(results)
    models.insert(0, "exercise_family", "exercise_02_growth")
    summary = (
        work.groupby(["horizon", "fixed_concentration_bucket"], as_index=False)
        .agg(
            rows=("reporter_code", "size"),
            countries=("reporter_code", "nunique"),
            mean_annualized_export_growth_log=(E2_OUTCOME, "mean"),
            median_annualized_export_growth_log=(E2_OUTCOME, "median"),
            mean_fixed_universe_product_gini=("fixed_universe_product_gini", "mean"),
            mean_partner_gini=("partner_gini", "mean"),
            mean_active_product_share=("active_product_share", "mean"),
        )
        .sort_values(["horizon", "fixed_concentration_bucket"])
    )
    return models, summary


def run_future_growth_models(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = add_fixed_buckets(panel)
    results: list[cse.ModelResult] = []
    for (flow, horizon), group in work.groupby(["flow", "horizon"], sort=True):
        h = int(horizon)
        for outcome, metric, term in [
            ("product_gini", "active_product_gini_legacy", "product_gini"),
            ("fixed_universe_product_gini", "fixed_universe_product_gini", "fixed_universe_product_gini"),
        ]:
            results.append(
                cse.run_ols_model(
                    group,
                    PRIMARY_FUTURE_OUTCOME,
                    [term, *BASE_CONTROL_TERMS],
                    ["reporter_code", "year"],
                    f"future_continuous_country_year_fe_h{h}",
                    COUNTRY_SAMPLE,
                    flow,
                    "product",
                    metric,
                    cluster_col="reporter_code",
                )
            )
        results.append(
            cse.run_ols_model(
                group,
                PRIMARY_FUTURE_OUTCOME,
                [*BUCKET_TERMS, *BASE_CONTROL_TERMS],
                ["reporter_code", "year"],
                f"future_fixed_bucket_country_year_fe_h{h}",
                COUNTRY_SAMPLE,
                flow,
                "product_partner_bucket",
                "fixed_universe_gini_bucket",
                cluster_col="reporter_code",
            )
        )
        results.append(
            cse.run_ols_model(
                group,
                PRIMARY_FUTURE_OUTCOME,
                ["fixed_universe_product_gini", "partner_gini", "fixed_universe_product_gini_x_partner_gini", *BASE_CONTROL_TERMS],
                ["reporter_code", "year"],
                f"future_fixed_paired_country_year_fe_h{h}",
                COUNTRY_SAMPLE,
                flow,
                "product_partner_pair",
                "fixed_universe_gini_partner_gini",
                cluster_col="reporter_code",
            )
        )
    models = model_frame(results)
    models.insert(0, "exercise_family", "future_growth_concentration")
    summary = (
        work.groupby(["flow", "horizon", "fixed_concentration_bucket"], as_index=False)
        .agg(
            rows=("reporter_code", "size"),
            countries=("reporter_code", "nunique"),
            mean_annualized_real_export_growth_log=(PRIMARY_FUTURE_OUTCOME, "mean"),
            median_annualized_real_export_growth_log=(PRIMARY_FUTURE_OUTCOME, "median"),
            mean_fixed_universe_product_gini=("fixed_universe_product_gini", "mean"),
            mean_partner_gini=("partner_gini", "mean"),
            mean_active_product_share=("active_product_share", "mean"),
        )
        .sort_values(["flow", "horizon", "fixed_concentration_bucket"])
    )
    return models, summary


def load_ex11_country_year() -> pd.DataFrame:
    path = sample_processed_path("exercise_11_product_export_linkage_panel.parquet", COUNTRY_SAMPLE)
    if not path.exists():
        raise FileNotFoundError(f"Missing Exercise 11 product panel: {path}")
    cols = [
        "reporter_code",
        "year",
        "country",
        "iso3",
        "import_value",
        "is_intermediate",
        "loo_gini_contribution",
        "total_import_product_gini",
    ]
    product = pd.read_parquet(path, columns=cols)
    product["reporter_code"] = pd.to_numeric(product["reporter_code"], errors="coerce").astype("Int64")
    product["year"] = pd.to_numeric(product["year"], errors="coerce").astype("Int64")
    product = product.dropna(subset=["reporter_code", "year"]).copy()
    product["reporter_code"] = product["reporter_code"].astype(int)
    product["year"] = product["year"].astype(int)
    product["import_value"] = pd.to_numeric(product["import_value"], errors="coerce").fillna(0.0)
    product["is_intermediate"] = pd.to_numeric(product["is_intermediate"], errors="coerce").fillna(0).astype(int)
    product["loo_gini_contribution"] = pd.to_numeric(product["loo_gini_contribution"], errors="coerce").fillna(0.0)
    product["positive_loo_gini_contribution"] = product["loo_gini_contribution"].clip(lower=0)
    product["intermediate_import_value"] = product["import_value"] * product["is_intermediate"]
    product["intermediate_positive_loo_gini_contribution"] = (
        product["positive_loo_gini_contribution"] * product["is_intermediate"]
    )
    grouped = (
        product.groupby(["reporter_code", "year"], as_index=False)
        .agg(
            country=("country", "first"),
            iso3=("iso3", "first"),
            total_imports_from_products=("import_value", "sum"),
            intermediate_imports=("intermediate_import_value", "sum"),
            positive_loo_gini_contribution=("positive_loo_gini_contribution", "sum"),
            intermediate_positive_loo_gini_contribution=("intermediate_positive_loo_gini_contribution", "sum"),
            total_import_product_gini=("total_import_product_gini", "first"),
            active_import_products=("import_value", "size"),
        )
        .reset_index(drop=True)
    )
    grouped["intermediate_import_share"] = grouped["intermediate_imports"] / grouped["total_imports_from_products"]
    grouped["intermediate_positive_loo_share"] = np.where(
        grouped["positive_loo_gini_contribution"] > 0,
        grouped["intermediate_positive_loo_gini_contribution"] / grouped["positive_loo_gini_contribution"],
        np.nan,
    )
    grouped["log_total_imports"] = np.where(
        grouped["total_imports_from_products"] > 0, np.log(grouped["total_imports_from_products"]), np.nan
    )
    del product
    gc.collect()
    return grouped


def run_intermediate_import_models(panel: pd.DataFrame, flow: str) -> pd.DataFrame:
    results: list[cse.ModelResult] = []
    specs = [
        (
            "ex11_aggregate_import_structure_year_fe",
            ["total_import_product_gini", "intermediate_import_share", "log_total_imports"],
            ["year"],
        ),
        (
            "ex11_aggregate_import_structure_country_year_fe",
            ["total_import_product_gini", "intermediate_import_share", "log_total_imports"],
            ["reporter_code", "year"],
        ),
        (
            "ex11_aggregate_positive_loo_share_country_year_fe",
            ["intermediate_positive_loo_share", "total_import_product_gini", "log_total_imports"],
            ["reporter_code", "year"],
        ),
    ]
    for outcome, metric in outcome_specs():
        for model_label, terms, fixed_effects in specs:
            results.append(
                cse.run_ols_model(
                    panel,
                    outcome,
                    terms,
                    fixed_effects,
                    model_label,
                    COUNTRY_SAMPLE,
                    flow,
                    "product",
                    metric,
                    cluster_col="reporter_code",
                )
            )
    out = model_frame(results)
    out.insert(0, "exercise_family", "exercise_11_intermediate_imports")
    return out


def exercise1_summary(fixed: pd.DataFrame, result_dir: Path) -> dict[str, Path]:
    panel = fixed.copy()
    yearly = (
        panel.groupby(["flow", "year"], as_index=False)
        .agg(
            countries=("reporter_code", "nunique"),
            median_fixed_universe_product_gini=("fixed_universe_product_gini", "median"),
            median_active_harmonized_product_gini=("active_harmonized_product_gini", "median"),
            median_gini_extensive_gap=("gini_extensive_gap", "median"),
            median_active_product_share=("active_product_share", "median"),
        )
        .sort_values(["flow", "year"])
    )
    latest = (
        panel.sort_values(["flow", "year", "fixed_universe_product_gini"], ascending=[True, False, False])
        .groupby("flow", as_index=False)
        .head(15)
        .copy()
    )
    correlations = []
    for (flow, year), group in panel.groupby(["flow", "year"], sort=True):
        correlations.append(
            {
                "flow": flow,
                "year": int(year),
                "countries": int(group["reporter_code"].nunique()),
                "corr_fixed_active_harmonized": float(
                    group["fixed_universe_product_gini"].corr(group["active_harmonized_product_gini"])
                ),
                "corr_fixed_active_product_share": float(
                    group["fixed_universe_product_gini"].corr(group["active_product_share"])
                ),
            }
        )
    paths = {
        "exercise_01_yearly_summary": result_dir / "exercise_01_fixed_universe_yearly_summary.csv",
        "exercise_01_latest_rankings": result_dir / "exercise_01_fixed_universe_latest_rankings.csv",
        "exercise_01_correlations": result_dir / "exercise_01_fixed_universe_correlations.csv",
    }
    yearly.to_csv(paths["exercise_01_yearly_summary"], index=False)
    latest.to_csv(paths["exercise_01_latest_rankings"], index=False)
    pd.DataFrame(correlations).to_csv(paths["exercise_01_correlations"], index=False)
    return paths


def key_coefficients(all_models: pd.DataFrame) -> pd.DataFrame:
    interest_terms = {
        "country_size": {"log_population", "log_gdp_per_capita"},
        "growth_effect": {"prior_export_growth", "contemporaneous_export_growth", "future_export_growth"},
        "exercise_02_growth": {
            "product_gini",
            "fixed_universe_product_gini",
            "partner_gini",
            "product_gini_x_partner_gini",
            "fixed_universe_product_gini_x_partner_gini",
            *BUCKET_TERMS,
        },
        "future_growth_concentration": {
            "product_gini",
            "fixed_universe_product_gini",
            "partner_gini",
            "fixed_universe_product_gini_x_partner_gini",
            *BUCKET_TERMS,
        },
        "exercise_11_intermediate_imports": {
            "total_import_product_gini",
            "intermediate_import_share",
            "intermediate_positive_loo_share",
        },
    }
    pieces = []
    for family, terms in interest_terms.items():
        mask = all_models["exercise_family"].eq(family) & all_models["term"].isin(terms)
        pieces.append(all_models.loc[mask].copy())
    out = pd.concat(pieces, ignore_index=True)
    out["significant_5pct"] = pd.to_numeric(out["p_value"], errors="coerce") < 0.05
    out["family_bh_q_value"] = np.nan
    for family, idx in out.groupby("exercise_family").groups.items():
        out.loc[idx, "family_bh_q_value"] = cse.benjamini_hochberg(
            pd.to_numeric(out.loc[idx, "p_value"], errors="coerce")
        )
    out["family_bh_significant_5pct"] = pd.to_numeric(out["family_bh_q_value"], errors="coerce") < 0.05
    return out


def sample_diagnostics(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, df in frames.items():
        rows.append(
            {
                "sample": name,
                "rows": int(len(df)),
                "countries": int(df["reporter_code"].nunique()) if "reporter_code" in df.columns else np.nan,
                "year_min": int(df["year"].min()) if "year" in df.columns and not df.empty else np.nan,
                "year_max": int(df["year"].max()) if "year" in df.columns and not df.empty else np.nan,
                "flows": ",".join(sorted(df["flow"].dropna().astype(str).unique())) if "flow" in df.columns else "",
                "fixed_nonmissing": int(df.get("fixed_universe_product_gini", pd.Series(dtype=float)).notna().sum()),
                "active_product_nonmissing": int(df.get("product_gini", pd.Series(dtype=float)).notna().sum()),
            }
        )
    return pd.DataFrame(rows)


def applicability_matrix() -> pd.DataFrame:
    rows = [
        ("exercise_01_descriptive", "direct_rerun_completed", "Country-year descriptive trend/ranking summary."),
        ("country_size_effect", "direct_rerun_completed", "Outcome swap: active Product Gini vs fixed-universe Product Gini."),
        ("growth_effect", "direct_rerun_completed", "Outcome swap using existing export-growth controls."),
        ("exercise_02_bucket_growth", "direct_rerun_completed_exports_only", "Fixed Gini rebuilds product high/low buckets; source panel is export-growth only."),
        ("future_growth_concentration", "direct_rerun_completed", "Fixed Gini as predictor, plus fixed product/partner buckets."),
        ("exercise_11_intermediate_imports", "aggregate_followup_completed", "Country-year import-structure predictors; not product-level replacement."),
        ("exercise_03_import_bins", "requires_new_product_level_design", "Needs bin-specific harmonized product universes and BEC mapping to HS1992 families."),
        ("exercise_06_exclusions", "requires_new_product_level_design", "Needs category-specific fixed universes after product exclusions."),
        ("exercise_10_random_benchmark", "requires_new_null_design", "Fixed-universe null must preserve zero mass and active-count support."),
        ("exercise_11_product_export_linkage", "no_direct_country_year_replacement", "Original estimand is product-level leave-one-product-out linkage."),
        ("exercise_12_transitions_extensive_margin", "not_a_gini_replacement", "Transition exercise is product/destination entry dynamics, not a Product Gini outcome."),
        ("exercise_13_import_hypotheses", "not_a_gini_replacement", "Supplier/source concentration exercise, not active Product Gini replacement."),
    ]
    return pd.DataFrame(rows, columns=["exercise", "fixed_universe_status", "reason"])


def format_model_row(row: pd.Series | None) -> str:
    if row is None or row.empty:
        return "not estimated"
    coef = row.get("coefficient")
    se = row.get("std_error")
    p_value = row.get("p_value")
    nobs = row.get("nobs")
    clusters = row.get("clusters")
    return f"{coef:.4f} (se {se:.4f}, p {p_value:.3g}, n {int(nobs):,}, clusters {int(clusters)})"


def pick(key: pd.DataFrame, family: str, metric: str, model_label_contains: str, term: str, flow: str | None = None) -> pd.Series | None:
    mask = (
        key["exercise_family"].eq(family)
        & key["metric"].eq(metric)
        & key["model_label"].astype(str).str.contains(model_label_contains)
        & key["term"].eq(term)
    )
    if flow is not None:
        mask &= key["flow"].eq(flow)
    match = key[mask]
    if match.empty:
        return None
    return match.iloc[0]


def write_memo(
    result_dir: Path,
    key: pd.DataFrame,
    diagnostics: pd.DataFrame,
    merge_diagnostics: pd.DataFrame,
    applicability: pd.DataFrame,
    exercise_paths: dict[str, Path],
) -> Path:
    memo_path = result_dir / "fixed_universe_gini_exercise_suite.md"
    cs_active = pick(key, "country_size", "active_product_gini_legacy", "country_size_year_fe", "log_population", "Exports")
    cs_fixed = pick(key, "country_size", "fixed_universe_product_gini", "country_size_year_fe", "log_population", "Exports")
    growth_active = pick(key, "growth_effect", "active_product_gini_legacy", "growth_prior", "prior_export_growth", "Exports")
    growth_fixed = pick(key, "growth_effect", "fixed_universe_product_gini", "growth_prior", "prior_export_growth", "Exports")
    e2_fixed = pick(key, "exercise_02_growth", "fixed_universe_product_gini", "e2_continuous_gini_h5", "fixed_universe_product_gini", "Exports")
    fg_fixed = pick(
        key,
        "future_growth_concentration",
        "fixed_universe_product_gini",
        "future_continuous_country_year_fe_h5",
        "fixed_universe_product_gini",
        "Exports",
    )
    ex11_fixed = pick(
        key,
        "exercise_11_intermediate_imports",
        "fixed_universe_product_gini",
        "ex11_aggregate_import_structure_country_year_fe",
        "intermediate_import_share",
        "Exports",
    )
    lines = [
        "# Fixed-Universe Product Gini Exercise Suite",
        "",
        f"Generated: {now_utc()}",
        "",
        "## Plan",
        "",
        "Rerun every exercise where active Product Gini appears as a country-year outcome or predictor, using `fixed_universe_product_gini` from the harmonized LT/HGL HS1992 fixed product universe. Product-level exercises are not force-swapped; they are listed in the applicability matrix with the design required for a valid fixed-universe version.",
        "",
        "## Main Results",
        "",
        "Country size, exports, year-FE model; term is `log_population`:",
        "",
        f"- Active Product Gini: {format_model_row(cs_active)}",
        f"- Fixed-Universe Product Gini: {format_model_row(cs_fixed)}",
        "",
        "Growth effect, exports, country-year FE model; term is `prior_export_growth`:",
        "",
        f"- Active Product Gini: {format_model_row(growth_active)}",
        f"- Fixed-Universe Product Gini: {format_model_row(growth_fixed)}",
        "",
        "Exercise 2 export-growth continuous model, 5-year horizon; term is `fixed_universe_product_gini`:",
        "",
        f"- Fixed-Universe Product Gini: {format_model_row(e2_fixed)}",
        "",
        "Future-growth concentration model, exports, 5-year horizon; term is `fixed_universe_product_gini`:",
        "",
        f"- Fixed-Universe Product Gini: {format_model_row(fg_fixed)}",
        "",
        "Exercise 11 aggregate import-structure follow-up, export fixed-Gini outcome; term is `intermediate_import_share`:",
        "",
        f"- Intermediate import share: {format_model_row(ex11_fixed)}",
        "",
        "## Sample Diagnostics",
        "",
        diagnostics.to_markdown(index=False),
        "",
        "## Merge Diagnostics",
        "",
        merge_diagnostics.to_markdown(index=False),
        "",
        "## Applicability Matrix",
        "",
        applicability.to_markdown(index=False),
        "",
        "## Outputs",
        "",
    ]
    for label, path in exercise_paths.items():
        lines.append(f"- {label}: `{rel(path)}`")
    memo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return memo_path


def run(args: argparse.Namespace) -> None:
    result_dir = sample_results_dir(args.country_sample) / OUTPUT_DIRNAME
    result_dir.mkdir(parents=True, exist_ok=True)
    fixed = load_fixed_panel()
    log_resource("loaded fixed-universe panel", args.memory_budget_gb)

    exercise_paths = exercise1_summary(fixed, result_dir)
    log_resource("finished exercise 01 summaries", args.memory_budget_gb)

    model_frames: list[pd.DataFrame] = []
    diagnostic_frames: dict[str, pd.DataFrame] = {}
    merge_rows: list[dict[str, Any]] = []

    for flow in FLOW_CHOICES:
        country_size_base = load_flow_panel(
            sample_processed_path("country_size_effect_panel.parquet", args.country_sample),
            "country size panel",
            flow,
        )
        country_size = merge_fixed(country_size_base, fixed, flow, f"country size {flow}")
        merge_rows.append(merge_diagnostic_row("country_size", flow, country_size_base, country_size, fixed))
        model_frames.append(run_country_size_models(country_size, flow))
        diagnostic_frames[f"country_size_common_fixed_{flow.lower()}"] = country_size
        del country_size_base, country_size
        gc.collect()
        log_resource(f"finished country size {flow}", args.memory_budget_gb)

        growth_base = load_flow_panel(
            sample_processed_path("growth_effect_panel.parquet", args.country_sample),
            "growth panel",
            flow,
        )
        growth = merge_fixed(growth_base, fixed, flow, f"growth {flow}")
        merge_rows.append(merge_diagnostic_row("growth", flow, growth_base, growth, fixed))
        model_frames.append(run_growth_models(growth, flow))
        diagnostic_frames[f"growth_common_fixed_{flow.lower()}"] = growth
        del growth_base, growth
        gc.collect()
        log_resource(f"finished growth {flow}", args.memory_budget_gb)

    ex2_base = load_flow_panel(
        sample_processed_path("exercise_02_bucket_growth_panel.parquet", args.country_sample),
        "Exercise 2 growth panel",
        "Exports",
    )
    ex2 = merge_fixed(ex2_base, fixed, "Exports", "Exercise 2 exports")
    merge_rows.append(merge_diagnostic_row("exercise_02", "Exports", ex2_base, ex2, fixed))
    ex2_models, ex2_summary = run_exercise2_models(ex2)
    model_frames.append(ex2_models)
    diagnostic_frames["exercise_02_common_fixed_exports"] = ex2
    ex2_summary_path = result_dir / "exercise_02_fixed_universe_bucket_summary.csv"
    ex2_summary.to_csv(ex2_summary_path, index=False)
    exercise_paths["exercise_02_bucket_summary"] = ex2_summary_path
    del ex2_base, ex2, ex2_models, ex2_summary
    gc.collect()
    log_resource("finished exercise 02", args.memory_budget_gb)

    future_base = load_flow_panel(
        sample_processed_path("future_growth_concentration_panel.parquet", args.country_sample),
        "future growth concentration panel",
        "Exports",
    )
    future_imports = load_flow_panel(
        sample_processed_path("future_growth_concentration_panel.parquet", args.country_sample),
        "future growth concentration panel",
        "Imports",
    )
    future_exports_merged = merge_fixed(future_base, fixed, "Exports", "future growth exports")
    future_imports_merged = merge_fixed(future_imports, fixed, "Imports", "future growth imports")
    merge_rows.append(merge_diagnostic_row("future_growth", "Exports", future_base, future_exports_merged, fixed))
    merge_rows.append(merge_diagnostic_row("future_growth", "Imports", future_imports, future_imports_merged, fixed))
    future = pd.concat(
        [
            future_exports_merged,
            future_imports_merged,
        ],
        ignore_index=True,
    )
    future_models, future_summary = run_future_growth_models(future)
    model_frames.append(future_models)
    diagnostic_frames["future_growth_common_fixed_all_flows"] = future
    future_summary_path = result_dir / "future_growth_fixed_universe_bucket_summary.csv"
    future_summary.to_csv(future_summary_path, index=False)
    exercise_paths["future_growth_bucket_summary"] = future_summary_path
    del future_base, future_imports, future_exports_merged, future_imports_merged, future, future_models, future_summary
    gc.collect()
    log_resource("finished future growth", args.memory_budget_gb)

    ex11_country_year = load_ex11_country_year()
    controls_by_flow = load_country_size_controls_by_flow(args.country_sample)
    for flow in FLOW_CHOICES:
        ex11 = merge_ex11_with_controls(ex11_country_year, fixed, controls_by_flow, flow)
        merge_rows.append(merge_diagnostic_row("exercise_11_aggregate", flow, ex11_country_year, ex11, fixed))
        model_frames.append(run_intermediate_import_models(ex11, flow))
        diagnostic_frames[f"exercise_11_aggregate_common_fixed_{flow.lower()}"] = ex11
        del ex11
        gc.collect()
        log_resource(f"finished exercise 11 aggregate {flow}", args.memory_budget_gb)
    del ex11_country_year, controls_by_flow
    gc.collect()

    all_models = pd.concat(model_frames, ignore_index=True)
    key = key_coefficients(all_models)
    diagnostics = sample_diagnostics(diagnostic_frames)
    merge_diagnostics = pd.DataFrame(merge_rows)
    applicability = applicability_matrix()

    all_path = result_dir / "fixed_universe_gini_exercise_suite_models.csv"
    key_path = result_dir / "fixed_universe_gini_exercise_suite_key_coefficients.csv"
    diag_path = result_dir / "fixed_universe_gini_exercise_suite_sample_diagnostics.csv"
    merge_diag_path = result_dir / "fixed_universe_gini_exercise_suite_merge_diagnostics.csv"
    applicability_path = result_dir / "fixed_universe_gini_exercise_suite_applicability.csv"
    manifest_path = result_dir / "run_manifest_fixed_universe_gini_exercise_suite.json"
    all_models.to_csv(all_path, index=False)
    key.to_csv(key_path, index=False)
    diagnostics.to_csv(diag_path, index=False)
    merge_diagnostics.to_csv(merge_diag_path, index=False)
    applicability.to_csv(applicability_path, index=False)
    exercise_paths.update(
        {
            "all models": all_path,
            "key coefficients": key_path,
            "sample diagnostics": diag_path,
            "merge diagnostics": merge_diag_path,
            "applicability matrix": applicability_path,
        }
    )
    memo_path = write_memo(result_dir, key, diagnostics, merge_diagnostics, applicability, exercise_paths)
    exercise_paths["memo"] = memo_path
    manifest = {
        "created_at_utc": now_utc(),
        "country_sample": args.country_sample,
        "fixed_universe_source": rel(FIXED_RESULTS),
        "product_id_mode": "harmonized_hs6_family",
        "included_direct_exercises": [
            "exercise_01_descriptive",
            "country_size_effect",
            "growth_effect",
            "exercise_02_bucket_growth_exports",
            "future_growth_concentration",
            "exercise_11_intermediate_imports_aggregate",
        ],
        "outputs": {label: rel(path) for label, path in exercise_paths.items()},
        "row_counts": {
            "all_models": int(len(all_models)),
            "key_coefficients": int(len(key)),
            "sample_diagnostics": int(len(diagnostics)),
            "merge_diagnostics": int(len(merge_diagnostics)),
            "applicability_rows": int(len(applicability)),
        },
        "sample_rows": diagnostics.to_dict(orient="records"),
        "merge_rows": merge_diagnostics.to_dict(orient="records"),
        "notes": [
            "Only country-year Product Gini substitutions are run directly.",
            "Product-level decomposition exercises are listed in the applicability matrix rather than force-swapped.",
            "Imports in growth regressions are cross-flow descriptive predictors/outcomes against export-growth controls, following the existing robustness convention.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")
    exercise_paths["manifest"] = manifest_path
    print(f"Wrote {rel(memo_path)}")
    print(f"Wrote {rel(key_path)}")
    print(f"Wrote {rel(applicability_path)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", default=COUNTRY_SAMPLE, choices=(COUNTRY_SAMPLE,))
    parser.add_argument(
        "--memory-budget-gb",
        type=float,
        default=float(os.getenv("FIXED_UNIVERSE_EXERCISE_MEMORY_BUDGET_GB", "0") or 0),
    )
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
