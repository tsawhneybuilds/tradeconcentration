#!/usr/bin/env python3
"""Explain product drivers of World-Relative Product Gini for rd2 exports."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import trade_concentration_pipeline as tcp  # noqa: E402
from concentration_metrics import weighted_gini, weighted_loo_gini_contributions  # noqa: E402
from run_world_relative_product_gini import (  # noqa: E402
    artifact_stem,
    flow_slug,
    flow_value_noun,
    metric_alias_column,
    tables_dirname,
    world_product_column,
    zero_weight_column,
)


COUNTRY_SAMPLE = "rd2_countries"
BENCHMARK_SAMPLE = "world_broad"
FLOW = "Exports"
FLOW_CHOICES = ("Exports", "Imports")
PRODUCT_ID_MODE = "harmonized_hs6_family"
EXCLUDED_HS6_CODES = {"999999"}
OVERWEIGHT_THRESHOLD = 1.05
UNDERWEIGHT_THRESHOLD = 0.95
NICHE_PERCENTILE_CUTOFF = 0.50
LARGE_WORLD_PERCENTILE_CUTOFF = 0.90
EXPECTED_COUNTRY_YEARS = 1375
EXPECTED_BALANCED_COUNTRIES = 55
EXPECTED_START_YEAR = 2000
EXPECTED_END_YEAR = 2024
EXPECTED_YEARS = EXPECTED_END_YEAR - EXPECTED_START_YEAR + 1
DRIVER_BUCKETS = [
    "overweight_niche_product",
    "overweight_large_world_product",
    "overweight_mid_world_product",
    "missing_large_world_product",
    "underweight_large_world_product",
    "underweight_other_product",
    "near_world_share",
]

COUNTRY_SIZE_PANEL = tcp.sample_processed_dir(COUNTRY_SAMPLE) / "country_size_effect_panel.parquet"
LT_HGL_WEIGHT_MAP = tcp.LT_HGL_NORMALIZED_WEIGHTS_PATH
HS_DESCRIPTION_MAP = ROOT / "data" / "processed" / "exercise_03_bec5_mapping_approved.csv"


def contribution_dir(flow: str) -> Path:
    if flow == "Exports":
        return tcp.sample_results_dir(COUNTRY_SAMPLE) / "world_relative_product_gini_contributions"
    return tcp.sample_results_dir(COUNTRY_SAMPLE) / "world_relative_import_product_gini_contributions"


def rd2_product_path(flow: str) -> Path:
    return (
        tcp.sample_processed_dir(COUNTRY_SAMPLE)
        / f"{artifact_stem(flow)}_{PRODUCT_ID_MODE}_rd2_product_{flow_value_noun(flow)}.parquet"
    )


def world_product_path(flow: str) -> Path:
    return (
        tcp.sample_processed_dir(BENCHMARK_SAMPLE)
        / f"{artifact_stem(flow)}_{PRODUCT_ID_MODE}_world_product_{flow_value_noun(flow)}.parquet"
    )


def world_relative_panel_path(flow: str) -> Path:
    return tcp.sample_processed_dir(COUNTRY_SAMPLE) / f"{artifact_stem(flow)}_panel.parquet"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def now_utc() -> str:
    return tcp.now_utc()


def normalize_hs6(value: object) -> str:
    text = "" if value is None else str(value)
    extracted = pd.Series([text], dtype="string").str.extract(r"(\d{1,6})", expand=False).iloc[0]
    if pd.isna(extracted):
        return ""
    return str(extracted).zfill(6)


def assert_no_excluded_product_ids(frame: pd.DataFrame, label: str, product_col: str = "product_id") -> None:
    if product_col not in frame.columns:
        raise RuntimeError(f"{label} is missing `{product_col}`.")
    product_text = frame[product_col].astype("string")
    exact = product_text.isin(EXCLUDED_HS6_CODES)
    embedded = product_text.str.contains("|".join(EXCLUDED_HS6_CODES), regex=False, na=False)
    count = int((exact | embedded).sum())
    if count:
        raise RuntimeError(f"{label} contains {count:,} excluded HS6 999999 product ids.")


def require_paths(paths: list[Path]) -> None:
    missing = [rel(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required input artifacts: {missing}")


def load_world_relative_panel(flow: str = FLOW) -> pd.DataFrame:
    panel = pd.read_parquet(world_relative_panel_path(flow))
    metric_col = metric_alias_column(flow)
    zero_col = zero_weight_column(flow)
    country_total_col = f"country_total_{flow_value_noun(flow)}"
    required = {
        "country",
        "iso3",
        "reporter_code",
        "year",
        "flow",
        "world_relative_product_gini",
        metric_col,
        "world_weighted_product_coverage",
        "active_product_gini",
        country_total_col,
        "country_active_products",
        "world_benchmark_products",
        "sample_window",
        zero_col,
    }
    missing = required - set(panel.columns)
    if missing:
        raise RuntimeError(f"World-relative panel is missing columns: {sorted(missing)}")
    panel = panel[panel["flow"].eq(flow)].copy()
    panel["reporter_code"] = panel["reporter_code"].astype(int)
    panel["year"] = panel["year"].astype(int)
    if len(panel) != EXPECTED_COUNTRY_YEARS:
        raise RuntimeError(f"Expected {EXPECTED_COUNTRY_YEARS:,} world-relative rows, found {len(panel):,}.")
    if panel["reporter_code"].nunique() != EXPECTED_BALANCED_COUNTRIES:
        raise RuntimeError(
            f"Expected {EXPECTED_BALANCED_COUNTRIES} balanced countries, found {panel['reporter_code'].nunique()}."
        )
    years = sorted(panel["year"].astype(int).unique().tolist())
    expected_years = list(range(EXPECTED_START_YEAR, EXPECTED_END_YEAR + 1))
    if years != expected_years:
        raise RuntimeError("World-relative panel is not the expected 2000-2024 balanced window.")
    duplicates = panel.duplicated(["reporter_code", "year"], keep=False)
    if duplicates.any():
        examples = panel.loc[duplicates, ["reporter_code", "year"]].head(10).to_dict(orient="records")
        raise RuntimeError(f"Duplicate world-relative panel keys: {examples}")
    per_year = panel.groupby("year")["reporter_code"].nunique()
    if not per_year.eq(EXPECTED_BALANCED_COUNTRIES).all():
        bad = per_year[~per_year.eq(EXPECTED_BALANCED_COUNTRIES)].head(10).to_dict()
        raise RuntimeError(f"World-relative panel is not balanced by year: {bad}")
    per_country = panel.groupby("reporter_code")["year"].nunique()
    if not per_country.eq(EXPECTED_YEARS).all():
        bad = per_country[~per_country.eq(EXPECTED_YEARS)].head(10).to_dict()
        raise RuntimeError(f"World-relative panel is not balanced by country: {bad}")
    return panel.sort_values(["year", "reporter_code"]).reset_index(drop=True)


def load_population_quartiles(panel: pd.DataFrame, flow: str = FLOW) -> pd.DataFrame:
    size = pd.read_parquet(COUNTRY_SIZE_PANEL)
    required = {"reporter_code", "year", "flow", "variant", "population", "log_population"}
    missing = required - set(size.columns)
    if missing:
        raise RuntimeError(f"Country-size panel is missing columns: {sorted(missing)}")
    size = size[size["flow"].eq(flow) & size["variant"].astype(str).str.lower().eq("baseline")].copy()
    size = size[["reporter_code", "year", "population", "log_population"]].drop_duplicates(["reporter_code", "year"])
    size["reporter_code"] = size["reporter_code"].astype(int)
    size["year"] = size["year"].astype(int)
    out = panel[["reporter_code", "year"]].merge(size, on=["reporter_code", "year"], how="left", validate="one_to_one")
    if out[["population", "log_population"]].isna().any().any():
        missing_rows = out[out[["population", "log_population"]].isna().any(axis=1)].head(10).to_dict(orient="records")
        raise RuntimeError(f"Missing population controls for world-relative contribution rows: {missing_rows}")
    out["population_quartile"] = (
        out.groupby("year", group_keys=False)["population"]
        .apply(lambda col: pd.qcut(col.rank(method="first"), 4, labels=[1, 2, 3, 4]))
        .astype(int)
    )
    out["is_bottom_population_quartile"] = out["population_quartile"].eq(1)
    return out


def load_product_inputs(panel: pd.DataFrame, flow: str = FLOW) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    years = set(panel["year"].astype(int))
    value_noun = flow_value_noun(flow)
    world_col = world_product_column(flow)
    country = pd.read_parquet(rd2_product_path(flow))
    world = pd.read_parquet(world_product_path(flow))
    raw_country_rows = int(len(country))
    raw_world_rows = int(len(world))
    for label, frame, required in [
        (f"rd2 product {value_noun}", country, {"reporter_code", "year", "product_id", "trade_value"}),
        (f"world product {value_noun}", world, {"year", "product_id", world_col}),
    ]:
        missing = required - set(frame.columns)
        if missing:
            raise RuntimeError(f"{label} is missing columns: {sorted(missing)}")
        assert_no_excluded_product_ids(frame, label)
    country["reporter_code"] = country["reporter_code"].astype(int)
    country["year"] = country["year"].astype(int)
    world["year"] = world["year"].astype(int)
    panel_keys = panel[["reporter_code", "year"]].drop_duplicates()
    country = country.merge(panel_keys, on=["reporter_code", "year"], how="inner", validate="many_to_one")
    world = world[world["year"].isin(years)].copy()
    after_panel_country_rows = int(len(country))
    after_year_world_rows = int(len(world))
    country["trade_value"] = pd.to_numeric(country["trade_value"], errors="coerce")
    world[world_col] = pd.to_numeric(world[world_col], errors="coerce")
    country = country.dropna(subset=["reporter_code", "year", "product_id", "trade_value"])
    world = world.dropna(subset=["year", "product_id", world_col])
    after_missing_country_rows = int(len(country))
    after_missing_world_rows = int(len(world))
    country = country[country["trade_value"] > 0].copy()
    world = world[world[world_col] > 0].copy()
    duplicate_country = country.duplicated(["reporter_code", "year", "product_id"], keep=False)
    duplicate_world = world.duplicated(["year", "product_id"], keep=False)
    if duplicate_country.any():
        examples = country.loc[duplicate_country, ["reporter_code", "year", "product_id"]].head(10).to_dict(orient="records")
        raise RuntimeError(f"Duplicate rd2 product keys: {examples}")
    if duplicate_world.any():
        examples = world.loc[duplicate_world, ["year", "product_id"]].head(10).to_dict(orient="records")
        raise RuntimeError(f"Duplicate world product keys: {examples}")
    metadata = {
        f"rd2_product_{value_noun}_raw": raw_country_rows,
        f"rd2_product_{value_noun}_dropped_outside_panel": raw_country_rows - after_panel_country_rows,
        f"rd2_product_{value_noun}_after_panel_filter": after_panel_country_rows,
        f"rd2_product_{value_noun}_dropped_missing_value": after_panel_country_rows - after_missing_country_rows,
        f"rd2_product_{value_noun}": int(len(country)),
        f"world_product_{value_noun}_raw": raw_world_rows,
        f"world_product_{value_noun}_dropped_outside_year_window": raw_world_rows - after_year_world_rows,
        f"world_product_{value_noun}_after_year_filter": after_year_world_rows,
        f"world_product_{value_noun}_dropped_missing_value": after_year_world_rows - after_missing_world_rows,
        f"world_product_{value_noun}": int(len(world)),
    }
    return country, world, metadata


def world_weight_percentile(weights: pd.Series) -> pd.Series:
    return weights.rank(method="average", pct=True)


def classify_driver_buckets(frame: pd.DataFrame) -> pd.Series:
    relative = pd.to_numeric(frame["relative_intensity"], errors="coerce")
    country_share = pd.to_numeric(frame["country_share"], errors="coerce").fillna(0.0)
    pct = pd.to_numeric(frame["world_weight_percentile"], errors="coerce")
    conditions = [
        country_share.eq(0.0) & pct.ge(LARGE_WORLD_PERCENTILE_CUTOFF),
        relative.gt(OVERWEIGHT_THRESHOLD) & pct.ge(LARGE_WORLD_PERCENTILE_CUTOFF),
        relative.gt(OVERWEIGHT_THRESHOLD) & pct.lt(NICHE_PERCENTILE_CUTOFF),
        relative.gt(OVERWEIGHT_THRESHOLD),
        relative.lt(UNDERWEIGHT_THRESHOLD) & country_share.gt(0.0) & pct.ge(LARGE_WORLD_PERCENTILE_CUTOFF),
        relative.lt(UNDERWEIGHT_THRESHOLD),
    ]
    choices = [
        "missing_large_world_product",
        "overweight_large_world_product",
        "overweight_niche_product",
        "overweight_mid_world_product",
        "underweight_large_world_product",
        "underweight_other_product",
    ]
    return pd.Series(np.select(conditions, choices, default="near_world_share"), index=frame.index, dtype="string")


def compute_country_year_product_frame(
    country: pd.DataFrame,
    world: pd.DataFrame,
    flow: str = FLOW,
) -> tuple[pd.DataFrame, dict[str, float]]:
    value_noun = flow_value_noun(flow)
    world_col = world_product_column(flow)
    country_total_col = f"country_total_{value_noun}_recomputed"
    world_total_col = f"world_total_{value_noun}_recomputed"
    leave_one_out_col = f"leave_one_out_world_{value_noun}_recomputed"
    zero_col = f"{zero_weight_column(flow)}_recomputed"
    country = country[["product_id", "trade_value"]].rename(columns={"trade_value": "country_product_trade"}).copy()
    world = world[["product_id", world_col]].rename(columns={world_col: "world_product_trade"}).copy()
    merged = world.merge(country, on="product_id", how="outer")
    merged["world_product_trade"] = pd.to_numeric(merged["world_product_trade"], errors="coerce").fillna(0.0)
    merged["country_product_trade"] = pd.to_numeric(merged["country_product_trade"], errors="coerce").fillna(0.0)
    merged = merged[(merged["world_product_trade"] > 0) | (merged["country_product_trade"] > 0)].copy()
    if merged.empty:
        raise RuntimeError("Empty country-year product frame.")
    country_total = float(merged["country_product_trade"].sum())
    world_total = float(merged["world_product_trade"].sum())
    if country_total <= 0 or world_total <= 0:
        raise RuntimeError(f"Country-year has nonpositive country or world {value_noun}.")
    merged["country_share"] = merged["country_product_trade"] / country_total
    merged["leave_one_out_product_trade"] = merged["world_product_trade"] - merged["country_product_trade"]
    small_negative = merged["leave_one_out_product_trade"].between(-1e-6, 0, inclusive="left")
    if small_negative.any():
        merged.loc[small_negative, "leave_one_out_product_trade"] = 0.0
    negative = merged["leave_one_out_product_trade"] < -1e-6
    if negative.any():
        examples = merged.loc[negative, ["product_id", "world_product_trade", "country_product_trade"]].head(10).to_dict(
            orient="records"
        )
        raise RuntimeError(f"Negative leave-one-out product {value_noun}: {examples}")
    valid = merged["leave_one_out_product_trade"] > 0
    benchmark_total = float(merged.loc[valid, "leave_one_out_product_trade"].sum())
    if benchmark_total <= 0 or not valid.any():
        raise RuntimeError("Country-year has empty leave-one-out benchmark.")
    out = merged.loc[valid].copy()
    out["leave_one_out_world_weight"] = out["leave_one_out_product_trade"] / benchmark_total
    out["relative_intensity"] = out["country_share"] / out["leave_one_out_world_weight"]
    out["world_weight_percentile"] = world_weight_percentile(out["leave_one_out_world_weight"])
    values = out["relative_intensity"].to_numpy(dtype=float)
    weights = out["leave_one_out_world_weight"].to_numpy(dtype=float)
    out["loo_gini_contribution"] = weighted_loo_gini_contributions(values, weights)
    out["positive_loo_gini_contribution"] = out["loo_gini_contribution"].clip(lower=0)
    out["driver_bucket"] = classify_driver_buckets(out)
    if flow == "Exports":
        out["country_product_exports"] = out["country_product_trade"]
        out["leave_one_out_product_exports"] = out["leave_one_out_product_trade"]
    else:
        out["country_product_imports"] = out["country_product_trade"]
        out["leave_one_out_product_imports"] = out["leave_one_out_product_trade"]
    metrics = {
        "world_relative_product_gini_recomputed": weighted_gini(values, weights),
        country_total_col: country_total,
        world_total_col: world_total,
        leave_one_out_col: benchmark_total,
        "country_active_products_recomputed": float((merged["country_product_trade"] > 0).sum()),
        "world_benchmark_products_recomputed": float(valid.sum()),
        zero_col: float(merged.loc[~valid, "country_share"].sum()),
    }
    if flow == "Exports":
        metrics["country_total_exports_recomputed"] = country_total
        metrics["world_total_exports_recomputed"] = world_total
        metrics["leave_one_out_world_exports_recomputed"] = benchmark_total
        metrics["zero_weight_country_export_share_recomputed"] = metrics[zero_col]
    else:
        metrics["world_relative_import_product_gini_recomputed"] = metrics["world_relative_product_gini_recomputed"]
    return out.reset_index(drop=True), metrics


def load_product_labels() -> pd.DataFrame:
    columns = ["classification_code", "cmd_code", "hs_desc_official", "hs_desc_if_available"]
    desc = pd.read_csv(HS_DESCRIPTION_MAP, usecols=lambda col: col in columns, dtype=str)
    desc["classification_code"] = desc["classification_code"].fillna("").astype(str).str.strip().str.upper()
    desc["cmd_code"] = desc["cmd_code"].map(normalize_hs6)
    desc["product_description"] = desc.get("hs_desc_official", pd.Series(index=desc.index, dtype=object))
    desc["product_description"] = desc["product_description"].fillna(desc.get("hs_desc_if_available", ""))
    desc["product_description"] = desc["product_description"].fillna("").astype(str).str.strip()
    desc = desc[desc["cmd_code"].ne("") & desc["cmd_code"].ne("999999")].copy()
    desc["revision_priority"] = desc["classification_code"].str.extract(r"(\d+)", expand=False).fillna("-1").astype(int)
    desc = desc.sort_values(["cmd_code", "revision_priority", "product_description"], ascending=[True, False, True])
    h0 = desc[desc["classification_code"].eq(tcp.LT_HGL_TARGET_REVISION)].copy()
    if h0.empty:
        h0 = desc.drop_duplicates("cmd_code", keep="first").copy()
    labels = h0.drop_duplicates("cmd_code", keep="first")[
        ["cmd_code", "product_description"]
    ].rename(
        columns={"cmd_code": "representative_cmd_code"}
    )
    labels["product_id"] = f"{tcp.LT_HGL_TARGET_LABEL}:" + labels["representative_cmd_code"]
    labels["representative_classification_code"] = tcp.LT_HGL_TARGET_REVISION
    labels["product_description"] = labels["product_description"].fillna("").astype(str).str.strip()
    labels["product_label"] = np.where(
        labels["product_description"].ne(""),
        labels["representative_cmd_code"] + " - " + labels["product_description"],
        labels["representative_cmd_code"],
    )
    return labels[
        ["product_id", "representative_classification_code", "representative_cmd_code", "product_description", "product_label"]
    ]


def add_fallback_product_labels(top: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    out = top.merge(labels, on="product_id", how="left")
    missing = out["representative_cmd_code"].isna()
    if missing.any():
        parsed = out.loc[missing, "product_id"].astype(str).str.extract(r"([A-Za-z0-9]+)[:_]([0-9]{6})")
        out.loc[missing, "representative_classification_code"] = parsed[0].fillna("")
        out.loc[missing, "representative_cmd_code"] = parsed[1].fillna("")
        out.loc[missing, "product_description"] = ""
        out.loc[missing, "product_label"] = out.loc[missing, "product_id"]
    out["product_description"] = out["product_description"].fillna("").astype(str)
    out["product_label"] = out["product_label"].fillna(out["product_id"]).astype(str)
    return out


def bucket_aggregate(product_frame: pd.DataFrame, base: dict[str, Any], flow: str = FLOW) -> pd.DataFrame:
    country_product_col = "country_product_exports" if flow == "Exports" else "country_product_imports"
    share_sum_col = f"country_{flow_slug(flow)}_share_sum"
    rows = (
        product_frame.groupby("driver_bucket", as_index=False, observed=True)
        .agg(
            products=("product_id", "size"),
            active_products=(country_product_col, lambda col: int((col > 0).sum())),
            **{share_sum_col: ("country_share", "sum")},
            world_weight_sum=("leave_one_out_world_weight", "sum"),
            positive_loo_contribution_sum=("positive_loo_gini_contribution", "sum"),
            raw_loo_contribution_sum=("loo_gini_contribution", "sum"),
            mean_relative_intensity=("relative_intensity", "mean"),
            max_relative_intensity=("relative_intensity", "max"),
        )
        .copy()
    )
    total_positive = float(rows["positive_loo_contribution_sum"].sum())
    rows["positive_loo_contribution_share"] = np.where(
        total_positive > 0,
        rows["positive_loo_contribution_sum"] / total_positive,
        0.0,
    )
    for key, value in base.items():
        rows[key] = value
    return rows


def country_year_summary(bucket_rows: pd.DataFrame, product_frame: pd.DataFrame, base: dict[str, Any]) -> dict[str, Any]:
    total_positive = float(bucket_rows["positive_loo_contribution_sum"].sum())
    positive = {f"{bucket}_positive_share": 0.0 for bucket in DRIVER_BUCKETS}
    sums = {f"{bucket}_positive_contribution": 0.0 for bucket in DRIVER_BUCKETS}
    for row in bucket_rows.itertuples(index=False):
        positive[f"{row.driver_bucket}_positive_share"] = float(row.positive_loo_contribution_share)
        sums[f"{row.driver_bucket}_positive_contribution"] = float(row.positive_loo_contribution_sum)
    if total_positive > 0:
        main_bucket = str(bucket_rows.sort_values("positive_loo_contribution_sum", ascending=False).iloc[0]["driver_bucket"])
    else:
        main_bucket = "none"
    positive_rows = product_frame[product_frame["positive_loo_gini_contribution"] > 0].copy()
    if positive_rows.empty:
        top_product_id = ""
        top_product_contribution = 0.0
    else:
        top = positive_rows.sort_values("positive_loo_gini_contribution", ascending=False).iloc[0]
        top_product_id = str(top["product_id"])
        top_product_contribution = float(top["positive_loo_gini_contribution"])
    return {
        **base,
        "total_positive_loo_contribution": total_positive,
        "total_raw_loo_contribution": float(product_frame["loo_gini_contribution"].sum()),
        "positive_driver_product_count": int((product_frame["positive_loo_gini_contribution"] > 0).sum()),
        "main_positive_driver_bucket": main_bucket,
        "top_positive_driver_product_id": top_product_id,
        "top_positive_driver_contribution": top_product_contribution,
        **positive,
        **sums,
    }


def top_driver_rows(product_frame: pd.DataFrame, base: dict[str, Any], top_n: int, flow: str = FLOW) -> pd.DataFrame:
    top = product_frame[product_frame["positive_loo_gini_contribution"] > 1e-15].copy()
    if top.empty:
        return pd.DataFrame()
    top = top.sort_values("positive_loo_gini_contribution", ascending=False).head(top_n).copy()
    top.insert(0, "driver_rank", np.arange(1, len(top) + 1))
    for key, value in base.items():
        top[key] = value
    country_product_col = "country_product_exports" if flow == "Exports" else "country_product_imports"
    leave_one_out_col = "leave_one_out_product_exports" if flow == "Exports" else "leave_one_out_product_imports"
    metric_col = metric_alias_column(flow)
    keep = [
        "country",
        "iso3",
        "reporter_code",
        "year",
        "population",
        "population_quartile",
        "is_bottom_population_quartile",
        "world_relative_product_gini",
        metric_col,
        "active_product_gini",
        "driver_rank",
        "product_id",
        country_product_col,
        "country_share",
        leave_one_out_col,
        "leave_one_out_world_weight",
        "world_weight_percentile",
        "relative_intensity",
        "loo_gini_contribution",
        "positive_loo_gini_contribution",
        "driver_bucket",
    ]
    return top[list(dict.fromkeys(keep))]


def write_memo(
    summary: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    latest_small: pd.DataFrame,
    validation: pd.DataFrame,
    output_paths: dict[str, Path],
    out_dir: Path,
    flow: str = FLOW,
) -> None:
    value_noun = flow_value_noun(flow)
    metric_col = metric_alias_column(flow)
    latest_year = int(summary["year"].max())
    latest = summary[summary["year"].eq(latest_year)].copy()
    small = latest[latest["is_bottom_population_quartile"]].copy()
    bucket_latest_small = bucket_summary[
        bucket_summary["year"].eq(latest_year) & bucket_summary["is_bottom_population_quartile"]
    ].copy()
    bucket_latest_small = (
        bucket_latest_small.groupby("driver_bucket", as_index=False)
        .agg(
            mean_positive_share=("positive_loo_contribution_share", "mean"),
            median_positive_share=("positive_loo_contribution_share", "median"),
            country_years=("reporter_code", "size"),
        )
        .sort_values("median_positive_share", ascending=False)
    )
    lines = [
        "# World-Relative Product Gini Contribution Diagnostics" if flow == "Exports" else "# World-Relative Import Product Gini Contribution Diagnostics",
        "",
        "This diagnostic explains why a country-year has a high World-Relative Product Gini."
        if flow == "Exports"
        else "This diagnostic explains why a country-year has a high World-Relative Import Product Gini.",
        "It separates two mechanisms: over-specialization in products where the country is far above the leave-one-out world share, and benchmark-feasibility pressure from missing or underweight large world-trade products.",
        "",
        "The contribution measure is diagnostic. For each country-year-product, it computes the full weighted Gini minus the weighted Gini after removing that product from the benchmark set. Because a Gini is nonlinear, these leave-one-out values are not a clean additive decomposition and should not be summed as structural shares of the index.",
        "",
        "## Construction",
        "",
        f"- Sample: `{COUNTRY_SAMPLE}`, {flow_slug(flow)}-only, balanced {EXPECTED_START_YEAR}-{EXPECTED_END_YEAR}.",
        f"- Benchmark: `{BENCHMARK_SAMPLE}` leave-one-out world product {value_noun} weights.",
        f"- Product ID: LT/HGL weighted HS6 conversion to `{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}`.",
        "- Product descriptions are plain-English labels for the HS1992 target code where available; the product ID remains the authoritative identifier.",
        "- HS6 `999999` is excluded upstream and blocked in these outputs.",
        f"- Overweight means relative intensity above `{OVERWEIGHT_THRESHOLD}`; underweight means below `{UNDERWEIGHT_THRESHOLD}`.",
        f"- Large world products are at or above the within-country-year `{LARGE_WORLD_PERCENTILE_CUTOFF:.0%}` leave-one-out world-weight percentile.",
        f"- Niche products are below the within-country-year `{NICHE_PERCENTILE_CUTOFF:.0%}` leave-one-out world-weight percentile.",
        "",
        "## Latest-Year Small-Country Pattern",
        "",
        f"Latest year: `{latest_year}`. Small countries are the bottom within-year population quartile.",
        "",
        latest_small[
            [
                "country",
                "iso3",
                metric_col,
                "main_positive_driver_bucket",
                "overweight_niche_product_positive_share",
                "missing_large_world_product_positive_share",
                "underweight_large_world_product_positive_share",
                "overweight_large_world_product_positive_share",
            ]
        ]
        .round(4)
        .to_markdown(index=False),
        "",
        "## Bucket Shares Among Latest-Year Small Countries",
        "",
        bucket_latest_small.round(4).to_markdown(index=False),
        "",
        "## Validation",
        "",
        validation.round(12).to_markdown(index=False),
        "",
        "## Output Files",
        "",
    ]
    for label, path in output_paths.items():
        lines.append(f"- {label}: `{rel(path)}`")
    memo_name = "world_relative_product_contributions.md" if flow == "Exports" else "world_relative_import_product_contributions.md"
    (out_dir / memo_name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(
    top: pd.DataFrame,
    summary: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    validation: pd.DataFrame,
    args: argparse.Namespace,
    input_counts: dict[str, int],
) -> dict[str, Path]:
    flow = args.flow
    out_dir = contribution_dir(flow)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = "world_relative_product_contribution" if flow == "Exports" else "world_relative_import_product_contribution"
    metric_col = metric_alias_column(flow)
    value_noun = flow_value_noun(flow)
    latest_year = int(summary["year"].max())
    latest_small = summary[summary["year"].eq(latest_year) & summary["is_bottom_population_quartile"]].copy()
    latest_small = latest_small.sort_values(metric_col, ascending=False)

    paths = {
        "top_drivers": out_dir / f"{prefix}_top_drivers.csv",
        "country_year_summary": out_dir / f"{prefix}_country_year_summary.csv",
        "latest_small_countries": out_dir / f"{prefix}_latest_small_countries.csv",
        "bucket_summary": out_dir / f"{prefix}_bucket_summary.csv",
        "validation": out_dir / f"{prefix}_validation.csv",
        "manifest": out_dir / f"run_manifest_{prefix}s.json",
    }
    top.to_csv(paths["top_drivers"], index=False)
    summary.to_csv(paths["country_year_summary"], index=False)
    latest_small.to_csv(paths["latest_small_countries"], index=False)
    bucket_summary.to_csv(paths["bucket_summary"], index=False)
    validation.to_csv(paths["validation"], index=False)

    manifest = {
        "created_at_utc": now_utc(),
        "status": "complete",
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "country_sample": args.country_sample,
        "benchmark_sample": BENCHMARK_SAMPLE,
        "benchmark_flow": flow,
        "product_id_mode": PRODUCT_ID_MODE,
        "product_harmonization": {
            "method": "official LT/HGL weighted conversion to HS1992/H0",
            "source_doi": tcp.LT_HGL_DATASET_DOI,
            "source_version": tcp.LT_HGL_DATASET_VERSION,
            "target": f"{tcp.LT_HGL_TARGET_LABEL}/{tcp.LT_HGL_TARGET_REVISION}",
        },
        "flow": flow,
        "excluded_hs6_codes": sorted(EXCLUDED_HS6_CODES),
        "thresholds": {
            "overweight_relative_intensity_gt": OVERWEIGHT_THRESHOLD,
            "underweight_relative_intensity_lt": UNDERWEIGHT_THRESHOLD,
            "niche_world_weight_percentile_lt": NICHE_PERCENTILE_CUTOFF,
            "large_world_weight_percentile_ge": LARGE_WORLD_PERCENTILE_CUTOFF,
            "small_country_population_quartile": 1,
        },
        "row_counts": {
            **input_counts,
            "top_drivers": int(len(top)),
            "country_year_summary": int(len(summary)),
            "latest_small_countries": int(len(latest_small)),
            "bucket_summary": int(len(bucket_summary)),
            "validation": int(len(validation)),
        },
        "validation": {
            "max_abs_world_relative_gini_diff": float(validation["max_abs_world_relative_gini_diff"].max()),
            f"max_abs_country_total_{value_noun}_diff": float(validation[f"max_abs_country_total_{value_noun}_diff"].max()),
            "max_abs_world_benchmark_products_diff": float(validation["max_abs_world_benchmark_products_diff"].max()),
            "duplicate_top_driver_keys": int(top.duplicated(["reporter_code", "year", "product_id"]).sum()),
            "summary_country_year_rows": int(len(summary)),
            "summary_country_years": int(summary[["reporter_code", "year"]].drop_duplicates().shape[0]),
        },
        "inputs": {
            f"rd2_product_{value_noun}": rel(rd2_product_path(flow)),
            f"world_product_{value_noun}": rel(world_product_path(flow)),
            "world_relative_panel": rel(world_relative_panel_path(flow)),
            "country_size_panel": rel(COUNTRY_SIZE_PANEL),
            "lt_hgl_weight_map": rel(LT_HGL_WEIGHT_MAP),
            "hs_description_map": rel(HS_DESCRIPTION_MAP),
        },
        "outputs": {label: rel(path) for label, path in paths.items()},
        "notes": [
            "Leave-one-out product contributions are diagnostic, not an additive Gini decomposition.",
            "Positive contribution shares are computed over positive LOO contributions within each country-year.",
            "Product descriptions are labels for the HS1992 target code where available; product_id is the authoritative identifier.",
            "Row counts without a raw suffix are the rows used after balanced-panel, year-window, missing-value, and positive-value filters.",
        ],
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_memo(summary, bucket_summary, latest_small, validation, paths, out_dir, flow)
    return paths


def build_contribution_artifacts(args: argparse.Namespace) -> dict[str, Path]:
    if args.country_sample != COUNTRY_SAMPLE:
        raise RuntimeError("World-relative contribution outputs are rd2-only; use --country-sample rd2_countries.")
    flow = args.flow
    value_noun = flow_value_noun(flow)
    metric_col = metric_alias_column(flow)
    country_total_col = f"country_total_{value_noun}"
    require_paths([rd2_product_path(flow), world_product_path(flow), world_relative_panel_path(flow), COUNTRY_SIZE_PANEL, LT_HGL_WEIGHT_MAP, HS_DESCRIPTION_MAP])
    panel = load_world_relative_panel(flow)
    population = load_population_quartiles(panel, flow)
    panel = panel.merge(population, on=["reporter_code", "year"], how="left", validate="one_to_one")
    country_product, world_product, product_input_counts = load_product_inputs(panel, flow)
    world_by_year = {int(year): group.reset_index(drop=True) for year, group in world_product.groupby("year", sort=True)}
    country_groups = country_product.groupby(["reporter_code", "year"], sort=False)

    summary_rows: list[dict[str, Any]] = []
    bucket_frames: list[pd.DataFrame] = []
    top_frames: list[pd.DataFrame] = []
    validation_rows: list[dict[str, Any]] = []

    for row in panel.sort_values(["year", "reporter_code"]).itertuples(index=False):
        reporter_code = int(row.reporter_code)
        year = int(row.year)
        try:
            country_group = country_groups.get_group((reporter_code, year)).reset_index(drop=True)
        except KeyError as exc:
            raise RuntimeError(f"Missing rd2 product {value_noun} for reporter-year {reporter_code}-{year}.") from exc
        world_year = world_by_year.get(year)
        if world_year is None or world_year.empty:
            raise RuntimeError(f"Missing world product {value_noun} for year {year}.")
        product_frame, metrics = compute_country_year_product_frame(country_group, world_year, flow)
        base = {
            "country": row.country,
            "iso3": row.iso3,
            "reporter_code": reporter_code,
            "year": year,
            "population": float(row.population),
            "log_population": float(row.log_population),
            "population_quartile": int(row.population_quartile),
            "is_bottom_population_quartile": bool(row.is_bottom_population_quartile),
            "world_relative_product_gini": float(row.world_relative_product_gini),
            "active_product_gini": float(row.active_product_gini),
            "world_weighted_product_coverage": float(row.world_weighted_product_coverage),
            country_total_col: float(getattr(row, country_total_col)),
            "country_active_products": int(row.country_active_products),
            "world_benchmark_products": int(row.world_benchmark_products),
            "sample_window": row.sample_window,
        }
        if flow == "Imports":
            base["world_relative_import_product_gini"] = float(getattr(row, "world_relative_import_product_gini"))
        buckets = bucket_aggregate(product_frame, base, flow)
        summary_rows.append(country_year_summary(buckets, product_frame, base))
        bucket_frames.append(buckets)
        top_frames.append(top_driver_rows(product_frame, base, int(args.top_drivers_per_country_year), flow))
        country_total_recomputed_col = f"country_total_{value_noun}_recomputed"
        validation_rows.append(
            {
                "country": row.country,
                "iso3": row.iso3,
                "reporter_code": reporter_code,
                "year": year,
                "world_relative_product_gini": float(row.world_relative_product_gini),
                metric_col: float(getattr(row, metric_col)),
                **metrics,
                "abs_world_relative_gini_diff": abs(
                    float(getattr(row, metric_col)) - metrics["world_relative_product_gini_recomputed"]
                ),
                f"abs_country_total_{value_noun}_diff": abs(
                    float(getattr(row, country_total_col)) - metrics[country_total_recomputed_col]
                ),
                "abs_world_benchmark_products_diff": abs(
                    float(row.world_benchmark_products) - metrics["world_benchmark_products_recomputed"]
                ),
            }
        )

    summary = pd.DataFrame(summary_rows)
    bucket_summary = pd.concat(bucket_frames, ignore_index=True) if bucket_frames else pd.DataFrame()
    top = pd.concat([frame for frame in top_frames if not frame.empty], ignore_index=True) if top_frames else pd.DataFrame()
    labels = load_product_labels()
    top = add_fallback_product_labels(top, labels) if not top.empty else top
    validation = pd.DataFrame(validation_rows)
    validation_summary = pd.DataFrame(
        [
            {
                "check": "world_relative_gini_recomputed",
                "max_abs_world_relative_gini_diff": float(validation["abs_world_relative_gini_diff"].max()),
                f"max_abs_country_total_{value_noun}_diff": float(validation[f"abs_country_total_{value_noun}_diff"].max()),
                "max_abs_world_benchmark_products_diff": float(validation["abs_world_benchmark_products_diff"].max()),
                "country_year_rows": int(len(validation)),
                "countries": int(validation["reporter_code"].nunique()),
                "years": int(validation["year"].nunique()),
            }
        ]
    )
    if len(summary) != EXPECTED_COUNTRY_YEARS:
        raise RuntimeError(f"Expected {EXPECTED_COUNTRY_YEARS:,} summary rows, found {len(summary):,}.")
    if validation_summary["max_abs_world_relative_gini_diff"].iloc[0] > 1e-10:
        raise RuntimeError("Recomputed World-Relative Product Gini differs from existing panel beyond tolerance.")
    if validation_summary["max_abs_world_benchmark_products_diff"].iloc[0] > 0:
        raise RuntimeError("Recomputed world benchmark product count differs from existing panel.")
    if not top.empty and top.duplicated(["reporter_code", "year", "product_id"]).any():
        raise RuntimeError("Top-driver output has duplicate reporter-year-product keys.")
    for label, frame in [
        ("top drivers", top),
        ("country-year summary", summary),
        ("bucket summary", bucket_summary),
    ]:
        if "product_id" in frame.columns:
            assert_no_excluded_product_ids(frame, label)

    input_counts = {
        "world_relative_panel": int(len(panel)),
        **product_input_counts,
    }
    return write_outputs(top, summary, bucket_summary, validation_summary, args, input_counts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=[COUNTRY_SAMPLE], default=COUNTRY_SAMPLE)
    parser.add_argument("--flow", choices=FLOW_CHOICES, default=FLOW)
    parser.add_argument("--top-drivers-per-country-year", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if int(args.top_drivers_per_country_year) <= 0:
        raise RuntimeError("--top-drivers-per-country-year must be positive.")
    paths = build_contribution_artifacts(args)
    label = "World-Relative Product Gini" if args.flow == "Exports" else "World-Relative Import Product Gini"
    print(f"Wrote {label} contribution artifacts:")
    for label, path in paths.items():
        print(f"- {label}: {rel(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
