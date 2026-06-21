#!/usr/bin/env python3
"""EV-style Exercise 12 rerun with LT/HGL-weighted HS6-to-HS1992 products.

This is the fine-grained companion to ``run_exercise_12_ev_hs4_expansion.py``.
It keeps the same adjacent two-year base/future windows, constant-2024-dollar
threshold, and pooled positive-expansion denominator, but converts all HS6
vintages to HS1992/H0 using the official Harvard Growth Lab / Dataverse
weighted conversion tables motivated by Lukaszuk and Torun (2022).
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from run_exercise_12_extensive_margin import (  # noqa: E402
    CountryInfo,
    country_info_records,
    file_sha256,
    normalize_hs6_series,
    read_product_partner_for_reporter,
    safe_divide,
)
from run_exercise_12_ev_hs4_expansion import (  # noqa: E402
    ACTIVE_THRESHOLD_USD_2024,
    CONSTANT_USD_YEAR,
    DEFAULT_HORIZONS,
    LEAST_TRADED_BASE_SHARE,
    DeflatorInfo,
    add_bottom10_rows,
    build_combined_cell_window,
    build_partner_window,
    build_product_window,
    clean_scalar,
    compute_country_decomposition,
    equal_country_summary,
    latest_5y_combined_country_rows,
    latest_5y_country_rows,
    load_us_gdp_deflator,
    memory_status,
    now_utc,
    pooled_summary,
    robustness_summary,
    validate_outputs as validate_hs4_shape,
)
from trade_concentration_pipeline import (  # noqa: E402
    LT_HGL_DATASET_DOI,
    LT_HGL_DATASET_URL,
    LT_HGL_DATASET_VERSION,
    LT_HGL_TARGET_LABEL,
    LT_HGL_TARGET_REVISION,
    apply_lt_hgl_hs1992_conversion,
    configure_country_sample,
    load_lt_hgl_hs1992_conversion_weights,
    lt_hgl_hs1992_coverage,
    sample_processed_path,
    sample_results_dir,
    save_country_panel,
)


COUNTRY_SAMPLE = "rd2_countries"
PRODUCT_LEVEL = "hs6_harmonized_family"
PRODUCT_LEVEL_LABEL = "LT/HGL-weighted HS1992 products"
OUTPUT_STEM = "ev_hs6_harmonized"
RESULT_TABLE_DIR_NAME = "exercise_12_ev_hs6_harmonized_expansion_tables"
PROCESSED_OUTPUT_NAME = "exercise_12_ev_hs6_harmonized_expansion_decomposition.parquet"
CHECKPOINT_DIR_NAME = "exercise_12_ev_hs6_harmonized_checkpoints"

LUKASZUK_TORUN_CITATION = {
    "paper": "Lukaszuk and Torun (2022), Harmonizing the Harmonized System",
    "url": "https://econpapers.repec.org/paper/usgeconwp/2022_3a12.htm",
    "pdf": "https://ux-tauri.unisg.ch/RePEc/usg/econwp/EWP-2212.pdf",
    "reported_motivation": "HS updates can affect a large share of world trade; many-to-many HS links need weighted conversion instead of simple dropping or coarse aggregation.",
}

HARVARD_GROWTH_LAB_WEIGHTS = {
    "name": "Harvard Growth Lab Weighted Classification Conversion Tables",
    "doi": LT_HGL_DATASET_DOI,
    "url": LT_HGL_DATASET_URL,
    "version": LT_HGL_DATASET_VERSION,
    "target": f"{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}",
    "note": "This run uses the official precomputed adjacent HS weighted conversion tables and composes them back to HS1992/H0.",
    "methodology_url": "https://atlas.hks.harvard.edu/trade-data-methodology/",
}


def prepare_hs6_harmonized_values(
    values: pd.DataFrame,
    deflator: DeflatorInfo,
    hs_lookup: pd.DataFrame,
) -> tuple[pd.DataFrame, list[int]]:
    """Return deflated reporter-year-product-partner cells after LT/HGL HS1992 conversion."""
    if values.empty:
        columns = ["reporter_code", "year", "product_id", "partner_code", "trade_value_2024_usd"]
        return pd.DataFrame(columns=columns), []
    work = values[["reporter_code", "year", "classification_code", "cmd_code", "partner_code", "trade_value"]].copy()
    work["year"] = pd.to_numeric(work["year"], errors="coerce").astype("Int64")
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce")
    work = work.dropna(subset=["year", "trade_value"]).copy()
    source_years = sorted(int(year) for year in work["year"].dropna().unique())
    missing_years = [year for year in source_years if year not in deflator.factors]
    work["deflator_factor_to_2024_usd"] = work["year"].map(deflator.factors)
    work = work.dropna(subset=["deflator_factor_to_2024_usd"]).copy()
    work = apply_lt_hgl_hs1992_conversion(work, weights=hs_lookup)
    work["trade_value_2024_usd"] = work["trade_value"] * work["deflator_factor_to_2024_usd"]
    work = work.dropna(subset=["product_id", "partner_code", "trade_value_2024_usd"]).copy()
    work["reporter_code"] = pd.to_numeric(work["reporter_code"], errors="coerce").astype(int)
    work["year"] = work["year"].astype(int)
    work["partner_code"] = pd.to_numeric(work["partner_code"], errors="coerce").astype(int)
    out = (
        work.groupby(["reporter_code", "year", "product_id", "partner_code"], as_index=False, observed=True)[
            "trade_value_2024_usd"
        ]
        .sum()
        .sort_values(["year", "product_id", "partner_code"])
        .reset_index(drop=True)
    )
    out = out[out["trade_value_2024_usd"] > 0].reset_index(drop=True)
    return out, missing_years


def hs6_harmonization_value_diagnostics(values: pd.DataFrame, hs_lookup: pd.DataFrame) -> dict[str, Any]:
    """Report value conservation and source-code coverage under LT/HGL HS1992 conversion."""
    if values.empty:
        return {
            "harmonization_rows": 0,
            "observed_trade_value": 0.0,
            "clean_nonambiguous_trade_value": 0.0,
            "ambiguous_trade_value": 0.0,
            "unmatched_trade_value": 0.0,
            "converted_trade_value": 0.0,
            "conversion_value_residual": 0.0,
            "clean_nonambiguous_value_share": np.nan,
            "ambiguous_value_share": np.nan,
            "unmatched_value_share": np.nan,
            "lt_hgl_theoretical_assignable_value_share": np.nan,
            "lt_hgl_weighted_target_pairs": 0,
            "target_hs1992_product_count": 0,
        }
    work = values[["classification_code", "cmd_code", "trade_value"]].copy()
    work["trade_value"] = pd.to_numeric(work["trade_value"], errors="coerce").fillna(0.0)
    coverage = lt_hgl_hs1992_coverage(work, hs_lookup)
    total = float(work["trade_value"].sum())
    unmatched = float(coverage["lt_hgl_missing_trade_value"])
    converted = apply_lt_hgl_hs1992_conversion(work, weights=hs_lookup)
    converted_value = float(pd.to_numeric(converted["trade_value"], errors="coerce").fillna(0.0).sum())
    residual = converted_value - max(total - unmatched, 0.0)
    clean = max(total - unmatched, 0.0)
    return {
        "harmonization_rows": int(len(work)),
        "observed_trade_value": total,
        "clean_nonambiguous_trade_value": clean,
        "ambiguous_trade_value": 0.0,
        "unmatched_trade_value": unmatched,
        "converted_trade_value": converted_value,
        "conversion_value_residual": residual,
        "clean_nonambiguous_value_share": safe_divide(clean, total),
        "ambiguous_value_share": 0.0,
        "unmatched_value_share": safe_divide(unmatched, total),
        "lt_hgl_theoretical_assignable_value_share": safe_divide(clean, total),
        "lt_hgl_distinct_source_pairs": int(coverage["lt_hgl_distinct_source_pairs"]),
        "lt_hgl_missing_distinct_source_pairs": int(coverage["lt_hgl_missing_distinct_source_pairs"]),
        "lt_hgl_missing_rows": int(coverage["lt_hgl_missing_rows"]),
        "lt_hgl_weighted_target_pairs": int(coverage["lt_hgl_weighted_target_pairs"]),
        "target_hs1992_product_count": int(converted["product_id"].nunique()),
        "status_value_shares": {
            "lt_hgl_weighted_hs1992": safe_divide(clean, total),
            "lt_hgl_missing_weight": safe_divide(unmatched, total),
        },
    }


def relabel_for_hs6(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "product_level" in out.columns:
        out["product_level"] = PRODUCT_LEVEL
    if "channel_type" in out.columns:
        out["channel_type"] = out["channel_type"].astype(str).str.replace(
            "partner_spread_continuing_hs4",
            "partner_spread_continuing_hs6_harmonized",
            regex=False,
        )
    for col in ["channel_label", "channel_type_label", "product_definition_label"]:
        if col in out.columns:
            out[col] = (
                out[col]
                .astype(str)
                .str.replace("harmonized HS6 product families", "LT/HGL HS1992 products", regex=False)
                .str.replace("harmonized HS6 product family", "LT/HGL HS1992 product", regex=False)
                .str.replace("harmonized HS6 products", "LT/HGL HS1992 products", regex=False)
                .str.replace("harmonized HS6 product", "LT/HGL HS1992 product", regex=False)
                .str.replace("harmonized-HS6-by-partner", "LT/HGL HS1992 product-by-partner", regex=False)
                .str.replace("harmonized HS6", "LT/HGL HS1992", regex=False)
                .str.replace("Harmonized HS6", "LT/HGL HS1992", regex=False)
                .str.replace("harmonized-HS6", "LT/HGL HS1992", regex=False)
                .str.replace("HS4 products", "LT/HGL HS1992 products", regex=False)
                .str.replace("HS4 product", "LT/HGL HS1992 product", regex=False)
                .str.replace("HS4-by-partner", "LT/HGL HS1992 product-by-partner", regex=False)
                .str.replace("HS4", "LT/HGL HS1992", regex=False)
            )
    return out


def write_hs6_outputs(
    *,
    country_sample: str,
    aggregate_path: Path,
    deflator: DeflatorInfo,
    product_rows: pd.DataFrame,
    partner_rows: pd.DataFrame,
    combined_rows: pd.DataFrame,
    robustness_rows: pd.DataFrame,
    validation: dict[str, Any],
    started_at_utc: str,
    lt_hgl_weight_metadata: dict[str, Any],
) -> dict[str, Path]:
    processed_path = sample_processed_path(PROCESSED_OUTPUT_NAME, country_sample)
    results_dir = sample_results_dir(country_sample)
    tables_dir = results_dir / RESULT_TABLE_DIR_NAME
    tables_dir.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)

    product_rows = relabel_for_hs6(product_rows)
    partner_rows = relabel_for_hs6(partner_rows)
    combined_rows = relabel_for_hs6(combined_rows)
    robustness_rows = relabel_for_hs6(robustness_rows)

    summary_inputs = [df for df in [product_rows, partner_rows, combined_rows] if not df.empty]
    summary_source = pd.concat(summary_inputs, ignore_index=True) if summary_inputs else pd.DataFrame()
    summary = pooled_summary(summary_source)
    equal_country = equal_country_summary(summary_source)
    combined_summary = pooled_summary(combined_rows)
    combined_equal_country = equal_country_summary(combined_rows)
    robustness = robustness_summary(robustness_rows)
    latest = latest_5y_country_rows(product_rows)
    combined_latest = latest_5y_combined_country_rows(combined_rows)

    product_rows.to_parquet(processed_path, index=False)
    paths = {
        "processed": processed_path,
        "country_window": tables_dir / f"{OUTPUT_STEM}_country_window_decomposition.csv",
        "partner_spread_country_window": tables_dir / f"{OUTPUT_STEM}_partner_spread_country_window.csv",
        "combined_country_window": tables_dir / f"{OUTPUT_STEM}_combined_country_window_decomposition.csv",
        "combined_pooled_summary": tables_dir / f"{OUTPUT_STEM}_combined_pooled_summary.csv",
        "combined_equal_country_summary": tables_dir / f"{OUTPUT_STEM}_combined_equal_country_summary.csv",
        "combined_latest_5y": tables_dir / f"{OUTPUT_STEM}_combined_latest_5y_country.csv",
        "pooled_summary": tables_dir / f"{OUTPUT_STEM}_pooled_summary.csv",
        "equal_country_summary": tables_dir / f"{OUTPUT_STEM}_equal_country_summary.csv",
        "latest_5y": tables_dir / f"{OUTPUT_STEM}_latest_5y_country.csv",
        "bottom10_robustness": tables_dir / f"{OUTPUT_STEM}_bottom10_robustness.csv",
        "bottom10_robustness_summary": tables_dir / f"{OUTPUT_STEM}_bottom10_robustness_summary.csv",
        "validation": tables_dir / f"{OUTPUT_STEM}_validation.json",
        "memo": results_dir / "exercise_12_ev_hs6_harmonized_expansion.md",
        "manifest": results_dir / "run_manifest_exercise_12_ev_hs6_harmonized_expansion.json",
    }
    product_rows.to_csv(paths["country_window"], index=False)
    partner_rows.to_csv(paths["partner_spread_country_window"], index=False)
    combined_rows.to_csv(paths["combined_country_window"], index=False)
    combined_summary.to_csv(paths["combined_pooled_summary"], index=False)
    combined_equal_country.to_csv(paths["combined_equal_country_summary"], index=False)
    combined_latest.to_csv(paths["combined_latest_5y"], index=False)
    summary.to_csv(paths["pooled_summary"], index=False)
    equal_country.to_csv(paths["equal_country_summary"], index=False)
    latest.to_csv(paths["latest_5y"], index=False)
    robustness_rows.to_csv(paths["bottom10_robustness"], index=False)
    robustness.to_csv(paths["bottom10_robustness_summary"], index=False)
    paths["validation"].write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")

    h5_product = summary[(summary["channel_type"].eq("product")) & (summary["horizon"].eq(5))].copy()
    h5_combined = combined_summary[
        (combined_summary["channel_type"].eq("combined_product_first")) & (combined_summary["horizon"].eq(5))
    ].copy()
    coverage_share = validation.get("harmonization_value_diagnostics", {}).get("clean_nonambiguous_value_share")
    missing_share = validation.get("harmonization_value_diagnostics", {}).get("unmatched_value_share")
    residual = validation.get("harmonization_value_diagnostics", {}).get("conversion_value_residual")
    memo = f"""# Exercise 12 EV-Style LT/HGL HS1992 Expansion

Generated: {validation.get("created_at_utc")}

This rerun keeps the stricter Evenett-Venables-style Exercise 12 design from the HS4 headline, but changes the product identity to official LT/HGL weighted HS6 conversion to HS1992/H0.

## Design

- Sample: `{country_sample}`.
- Unit: reporter country x adjacent two-year base window x adjacent two-year future window x HS1992/H0 product after LT/HGL weighted conversion.
- Horizons: {', '.join(str(h) for h in validation.get('horizons', []))}.
- Activity rule: both base-window years and both future-window years must clear ${ACTIVE_THRESHOLD_USD_2024:,.0f} in constant {CONSTANT_USD_YEAR} USD.
- Product-dependent filters: HS6 `999999` is excluded before aggregation; `partnerCode == 0` is excluded.
- Main denominator: pooled positive expansion, `max(future two-year average - base two-year average, 0)`.

## Lukaszuk-Torun / Harvard Growth Lab Citation

This run cites Lukaszuk and Torun (2022), ["Harmonizing the Harmonized System"]({LUKASZUK_TORUN_CITATION['url']}), as the measurement motivation for weighted HS revision conversion. The conversion uses the official Harvard Growth Lab / Dataverse weighted classification conversion tables, DOI `{LT_HGL_DATASET_DOI}`, version `{LT_HGL_DATASET_VERSION}`, composed to `{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}`.

Filtered product trade value covered by official LT/HGL source weights: {coverage_share:.1%}. Missing source-weight value share: {missing_share:.1%}. Weighted value-conservation residual: {residual:,.6f}.

## Horizon-5 Pooled Product Summary

{h5_product[['channel', 'channel_label', 'pooled_positive_expansion_share', 'pooled_net_growth_share', 'median_positive_expansion_share']].to_markdown(index=False) if not h5_product.empty else 'No horizon-5 product rows.'}

## Horizon-5 Product-First Cell Summary

{h5_combined[['channel', 'channel_label', 'pooled_positive_expansion_share', 'pooled_net_growth_share', 'median_positive_expansion_share']].to_markdown(index=False) if not h5_combined.empty else 'No horizon-5 combined rows.'}

## Validation

- Status: `{validation.get('status')}`.
- Country count: {validation.get('country_count_product_decomposition')} of {validation.get('country_count_expected')}.
- Source rows after filters: {validation.get('source_rows_after_filters'):,}.
- HS6 `999999` after filters: {validation.get('source_hs6_999999_rows_after_filters')}.
- `partnerCode == 0` after filters: {validation.get('source_partner_code_0_rows_after_filters')}.
- Product accounting residual violations: {validation.get('product_accounting_residual_violations')}.
- Combined accounting residual violations: {validation.get('combined_accounting_residual_violations')}.

## Files

- Pooled summary: `{paths['pooled_summary'].relative_to(ROOT)}`.
- Combined pooled summary: `{paths['combined_pooled_summary'].relative_to(ROOT)}`.
- Country-window table: `{paths['country_window'].relative_to(ROOT)}`.
- Combined country-window table: `{paths['combined_country_window'].relative_to(ROOT)}`.
- Validation: `{paths['validation'].relative_to(ROOT)}`.
- Manifest: `{paths['manifest'].relative_to(ROOT)}`.

## Interpretation Limit

This is the LT/HGL-weighted HS1992/H0 appendix. It no longer treats many-to-many HS revision links as missing or ambiguous; those links are resolved by official conversion weights before aggregation.
"""
    paths["memo"].write_text(memo, encoding="utf-8")

    manifest = {
        "created_at_utc": now_utc(),
        "started_at_utc": started_at_utc,
        "country_sample": country_sample,
        "source_aggregate": str(aggregate_path.relative_to(ROOT)),
        "source_aggregate_sha256": file_sha256(aggregate_path),
        "deflator_source": str(deflator.source_path.relative_to(ROOT)),
        "deflator_source_sha256": file_sha256(deflator.source_path),
        "processed_output": str(processed_path.relative_to(ROOT)),
        "result_files": {key: str(path.relative_to(ROOT)) for key, path in paths.items() if key != "processed"},
        "row_counts": {
            "country_window": int(len(product_rows)),
            "partner_spread_country_window": int(len(partner_rows)),
            "combined_country_window": int(len(combined_rows)),
            "combined_pooled_summary": int(len(combined_summary)),
            "combined_equal_country_summary": int(len(combined_equal_country)),
            "combined_latest_5y": int(len(combined_latest)),
            "pooled_summary": int(len(summary)),
            "equal_country_summary": int(len(equal_country)),
            "latest_5y": int(len(latest)),
            "bottom10_robustness": int(len(robustness_rows)),
            "bottom10_robustness_summary": int(len(robustness)),
        },
        "definition": {
            "unit_of_observation": "reporter-country adjacent-2-year base window adjacent-2-year future window harmonized-HS6 product-family growth channel",
            "product_level": PRODUCT_LEVEL,
            "product_level_label": PRODUCT_LEVEL_LABEL,
            "persistence_rule": "base years t,t+1 below/above threshold and future years t+h,t+h+1 below/above threshold",
            "active_threshold_usd_2024": ACTIVE_THRESHOLD_USD_2024,
            "constant_usd_year": CONSTANT_USD_YEAR,
            "headline_share": "pooled positive expansion share",
            "net_growth_share_note": "Net-growth shares are companion accounting and can exceed 100 percent or be negative when contractions offset expansions.",
            "bottom_10pct_base_share": LEAST_TRADED_BASE_SHARE,
            "product_excluded_hs6_codes": ["999999"],
            "partner_code_0_excluded": True,
            "hs_harmonization_method_current": "official LT/HGL weighted conversion to HS1992/H0 from Harvard Dataverse",
            "lt_hgl_weighted_conversion_status": "official_precomputed_weights_loaded_validated_and_composed_to_hs1992",
            "lt_hgl_target": f"{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}",
            "lt_hgl_source_doi": LT_HGL_DATASET_DOI,
            "lt_hgl_source_version": LT_HGL_DATASET_VERSION,
        },
        "literature_and_tool_references": {
            "lukaszuk_torun_2022": LUKASZUK_TORUN_CITATION,
            "harvard_growth_lab_weights": HARVARD_GROWTH_LAB_WEIGHTS,
            "lt_hgl_weight_metadata": lt_hgl_weight_metadata,
        },
        "validation": validation,
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return paths


def hgl_repo_metadata(path: Path = Path("/tmp/comtrade-conversion-weights")) -> dict[str, Any]:
    if not path.exists():
        return {"inspected": False, "reason": "local HGL clone not found"}
    try:
        commit = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception as exc:  # pragma: no cover - defensive provenance
        commit = f"unavailable: {exc}"
    return {
        "inspected": True,
        "local_path": str(path),
        "commit": commit,
        "readme_present": (path / "README.md").exists(),
        "static_concordance_present": (path / "generator/data/static/HS_consolidated_comtrade_concordances.csv").exists(),
        "precomputed_optimized_weights_present": any((path / "generator/data/output").glob("**/*.csv"))
        if (path / "generator/data/output").exists()
        else False,
        "requires": ["raw Comtrade data", "R", "MATLAB R2021a", "Premium UN Comtrade API key"],
    }


def checkpoint_paths(checkpoint_dir: Path, reporter_code: int) -> dict[str, Path]:
    prefix = checkpoint_dir / f"reporter_{int(reporter_code)}"
    return {
        "product": prefix.with_name(prefix.name + "_product.parquet"),
        "partner": prefix.with_name(prefix.name + "_partner.parquet"),
        "combined": prefix.with_name(prefix.name + "_combined.parquet"),
        "robustness": prefix.with_name(prefix.name + "_robustness.parquet"),
        "source_check": prefix.with_name(prefix.name + "_source_check.json"),
    }


def read_country_checkpoint(paths: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]] | None:
    if not all(path.exists() for path in paths.values()):
        return None
    return (
        pd.read_parquet(paths["product"]),
        pd.read_parquet(paths["partner"]),
        pd.read_parquet(paths["combined"]),
        pd.read_parquet(paths["robustness"]),
        json.loads(paths["source_check"].read_text(encoding="utf-8")),
    )


def write_country_checkpoint(
    paths: dict[str, Path],
    product: pd.DataFrame,
    partner: pd.DataFrame,
    combined: pd.DataFrame,
    robustness: pd.DataFrame,
    source_check: dict[str, Any],
) -> None:
    paths["product"].parent.mkdir(parents=True, exist_ok=True)
    product.to_parquet(paths["product"], index=False)
    partner.to_parquet(paths["partner"], index=False)
    combined.to_parquet(paths["combined"], index=False)
    robustness.to_parquet(paths["robustness"], index=False)
    paths["source_check"].write_text(json.dumps(source_check, indent=2, sort_keys=True), encoding="utf-8")


def run_ev_hs6_harmonized_expansion(
    *,
    country_sample: str = COUNTRY_SAMPLE,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    max_countries: int | None = None,
    fresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Path]]:
    if country_sample != COUNTRY_SAMPLE:
        raise ValueError("The harmonized-HS6 EV-style runner is rd2-only; use --country-sample rd2_countries.")
    configure_country_sample(country_sample=country_sample)
    countries = country_info_records(save_country_panel())
    if max_countries is not None:
        countries = countries[: int(max_countries)]
    aggregate_path = sample_processed_path("exercise_12_export_aggregates.parquet", country_sample)
    if not aggregate_path.exists():
        raise FileNotFoundError(f"Exercise 12 aggregate is missing: {aggregate_path}")
    deflator = load_us_gdp_deflator()
    hs_lookup = load_lt_hgl_hs1992_conversion_weights()
    horizons = tuple(int(h) for h in horizons)
    checkpoint_dir = sample_processed_path(CHECKPOINT_DIR_NAME, country_sample)
    if fresh and checkpoint_dir.exists():
        shutil.rmtree(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    started_at_utc = now_utc()
    all_product: list[pd.DataFrame] = []
    all_partner: list[pd.DataFrame] = []
    all_combined: list[pd.DataFrame] = []
    all_robustness: list[pd.DataFrame] = []
    source_checks: dict[int, dict[str, Any]] = {}
    harmonization_checks: list[dict[str, Any]] = []
    print(
        f"Running Exercise 12 EV-style harmonized-HS6 expansion decomposition for {len(countries)} rd2 countries; "
        f"horizons={horizons}, threshold=${ACTIVE_THRESHOLD_USD_2024:,.0f} in {CONSTANT_USD_YEAR} USD",
        flush=True,
    )
    for idx, country in enumerate(countries, start=1):
        print(f"[{idx}/{len(countries)}] {country.country} ({country.iso3}) before read: {memory_status()}", flush=True)
        paths = checkpoint_paths(checkpoint_dir, country.reporter_code)
        checkpoint = read_country_checkpoint(paths)
        if checkpoint is not None and checkpoint[4].get("hs_harmonization_method") != "lt_hgl_weighted_hs1992":
            checkpoint = None
        if checkpoint is not None:
            product_rows, partner_rows, combined_rows, robustness_rows, source_check = checkpoint
            source_checks[country.reporter_code] = source_check
            harmonization_checks.append(source_check.get("harmonization_value_diagnostics", {}))
            if not product_rows.empty:
                all_product.append(product_rows)
            if not partner_rows.empty:
                all_partner.append(partner_rows)
            if not combined_rows.empty:
                all_combined.append(combined_rows)
            if not robustness_rows.empty:
                all_robustness.append(robustness_rows)
            print(
                f"  checkpoint: product_rows={len(product_rows):,} partner_rows={len(partner_rows):,} "
                f"combined_rows={len(combined_rows):,}; {memory_status()}",
                flush=True,
            )
            del product_rows, partner_rows, combined_rows, robustness_rows
            gc.collect()
            continue
        values = read_product_partner_for_reporter(aggregate_path, country.reporter_code)
        harmonization_diag = hs6_harmonization_value_diagnostics(values, hs_lookup)
        source_check = {
            "rows_after_filters": int(len(values)),
            "hs6_999999_rows_after_filters": int(normalize_hs6_series(values["cmd_code"]).eq("999999").sum()) if not values.empty else 0,
            "partner_code_0_rows_after_filters": int(pd.to_numeric(values["partner_code"], errors="coerce").eq(0).sum()) if not values.empty else 0,
            "hs_harmonization_method": "lt_hgl_weighted_hs1992",
            "lt_hgl_target": f"{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}",
            "lt_hgl_source_doi": LT_HGL_DATASET_DOI,
            "lt_hgl_source_version": LT_HGL_DATASET_VERSION,
            "harmonization_value_diagnostics": harmonization_diag,
        }
        cells, missing_deflator_years = prepare_hs6_harmonized_values(values, deflator, hs_lookup)
        source_check["source_years_without_deflator"] = missing_deflator_years
        product_rows, partner_rows, combined_rows, robustness_rows, diagnostics = compute_country_decomposition(
            cells,
            country,
            horizons,
        )
        product_rows = relabel_for_hs6(product_rows)
        partner_rows = relabel_for_hs6(partner_rows)
        combined_rows = relabel_for_hs6(combined_rows)
        robustness_rows = relabel_for_hs6(robustness_rows)
        source_check.update(diagnostics)
        source_checks[country.reporter_code] = source_check
        harmonization_checks.append(harmonization_diag)
        write_country_checkpoint(paths, product_rows, partner_rows, combined_rows, robustness_rows, source_check)
        if not product_rows.empty:
            all_product.append(product_rows)
        if not partner_rows.empty:
            all_partner.append(partner_rows)
        if not combined_rows.empty:
            all_combined.append(combined_rows)
        if not robustness_rows.empty:
            all_robustness.append(robustness_rows)
        print(
            f"  cells={len(cells):,} product_rows={len(product_rows):,} partner_rows={len(partner_rows):,} "
            f"combined_rows={len(combined_rows):,}; lt_hgl_coverage={harmonization_diag.get('clean_nonambiguous_value_share'):.1%} "
            f"missing={harmonization_diag.get('unmatched_value_share'):.1%}; {memory_status()}",
            flush=True,
        )
        del values, cells, product_rows, partner_rows, combined_rows, robustness_rows
        gc.collect()

    product = pd.concat(all_product, ignore_index=True) if all_product else pd.DataFrame()
    partner = pd.concat(all_partner, ignore_index=True) if all_partner else pd.DataFrame()
    combined = pd.concat(all_combined, ignore_index=True) if all_combined else pd.DataFrame()
    robustness = pd.concat(all_robustness, ignore_index=True) if all_robustness else pd.DataFrame()
    latest = latest_5y_country_rows(product)
    combined_latest = latest_5y_combined_country_rows(combined)
    validation = validate_hs4_shape(
        product_rows=product,
        partner_rows=partner,
        combined_rows=combined,
        latest_5y=latest,
        combined_latest_5y=combined_latest,
        robustness=robustness,
        countries=countries,
        horizons=horizons,
        source_checks=source_checks,
        deflator=deflator,
    )
    validation["product_level"] = PRODUCT_LEVEL
    validation["product_level_label"] = PRODUCT_LEVEL_LABEL
    validation["lt_hgl_citation"] = LUKASZUK_TORUN_CITATION
    validation["harvard_growth_lab_weights"] = HARVARD_GROWTH_LAB_WEIGHTS
    total_observed = float(sum(item.get("observed_trade_value", 0.0) for item in harmonization_checks))
    total_clean = float(sum(item.get("clean_nonambiguous_trade_value", 0.0) for item in harmonization_checks))
    total_ambiguous = float(sum(item.get("ambiguous_trade_value", 0.0) for item in harmonization_checks))
    total_unmatched = float(sum(item.get("unmatched_trade_value", 0.0) for item in harmonization_checks))
    total_converted = float(sum(item.get("converted_trade_value", 0.0) for item in harmonization_checks))
    conversion_residual = total_converted - max(total_observed - total_unmatched, 0.0)
    validation["harmonization_value_diagnostics"] = {
        "observed_trade_value": total_observed,
        "clean_nonambiguous_trade_value": total_clean,
        "ambiguous_trade_value": total_ambiguous,
        "unmatched_trade_value": total_unmatched,
        "converted_trade_value": total_converted,
        "conversion_value_residual": conversion_residual,
        "clean_nonambiguous_value_share": safe_divide(total_clean, total_observed),
        "ambiguous_value_share": safe_divide(total_ambiguous, total_observed),
        "unmatched_value_share": safe_divide(total_unmatched, total_observed),
        "lt_hgl_theoretical_assignable_value_share": safe_divide(total_clean + total_ambiguous, total_observed),
        "lt_hgl_target": f"{LT_HGL_TARGET_LABEL}/{LT_HGL_TARGET_REVISION}",
        "lt_hgl_source_doi": LT_HGL_DATASET_DOI,
        "lt_hgl_source_version": LT_HGL_DATASET_VERSION,
    }
    harmonization_blockers: list[str] = []
    if total_unmatched != 0:
        harmonization_blockers.append("LT/HGL HS1992 conversion is missing filtered source value")
    residual_tolerance = max(1.0, total_observed * 1e-10)
    validation["harmonization_value_residual_tolerance"] = residual_tolerance
    if abs(conversion_residual) > residual_tolerance:
        harmonization_blockers.append("LT/HGL HS1992 weighted conversion does not conserve filtered trade value")
    if harmonization_blockers:
        validation.setdefault("blockers", []).extend(harmonization_blockers)
        validation["status"] = "blocked"
    if validation.get("status") != "ok":
        raise RuntimeError(f"EV harmonized-HS6 validation failed: {validation.get('blockers')}")
    validation["lt_hgl_weight_metadata"] = HARVARD_GROWTH_LAB_WEIGHTS
    paths = write_hs6_outputs(
        country_sample=country_sample,
        aggregate_path=aggregate_path,
        deflator=deflator,
        product_rows=product,
        partner_rows=partner,
        combined_rows=combined,
        robustness_rows=robustness,
        validation=validation,
        started_at_utc=started_at_utc,
        lt_hgl_weight_metadata=validation["lt_hgl_weight_metadata"],
    )
    return product, partner, combined, robustness, validation, paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-sample", choices=[COUNTRY_SAMPLE], default=COUNTRY_SAMPLE)
    parser.add_argument("--horizons", nargs="+", type=int, default=list(DEFAULT_HORIZONS))
    parser.add_argument("--max-countries", type=int, default=None, help="Optional smoke-test cap on countries processed.")
    parser.add_argument("--fresh", action="store_true", help="Delete per-country harmonized-HS6 EV checkpoints first.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    _product, _partner, _combined, _robustness, validation, paths = run_ev_hs6_harmonized_expansion(
        country_sample=args.country_sample,
        horizons=args.horizons,
        max_countries=args.max_countries,
        fresh=args.fresh,
    )
    print("Validation:", json.dumps(validation, indent=2), flush=True)
    print("Wrote:", flush=True)
    for key, path in paths.items():
        print(f"  {key}: {path}", flush=True)


if __name__ == "__main__":
    main()
